"""酒吞童子卡牌（id 298-307）。

牌面文本以 cards.json 末尾条目（298-307，用户修订版 2026-09-25）为准。
基础能力（受伤获得力量）与本回合受伤追踪计数器在 heroes.py 酒吞段：
- jiutun_dmg_taken_turn：本回合所受理论伤害之和（百鬼夜行的 X）
- jiutun_friendly_dmg_turn：本回合受到过己方伤害的次数（无尽愤怒条件）
口径与成长一致（"deal damage" 结算前广播、value>0、目标含酒吞；理论伤害
口径=护甲/减免扣除前值，用户裁决 2026-09-25）。

实现注记：
- 自损牌（醉里乾坤/鬼王/醉酒当歌）伤害来源均为酒吞童子本人（wiki 法术牌：
  伤害来源仍然视为该式神），因此享受自身成长与己方伤害判定（含自身）。
- 战斗关键字「不屈」的战斗内结算由引擎 _resolve_single_hit 完成；法术伤害
  通道不结算不屈（引擎现状），醉酒当歌的自伤保护用 on_before_death 守护
  回调临时实现（狂啸同款机制）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


def _jiutun_hero(player):
    """player 存活的酒吞童子；没有则 None。"""
    return next((h for h in player.heroes
                 if h.type_name == "JiuTunTongZi" and h.is_alive), None)


def _battle_tenacious(s, hero, flag):
    """为本次战斗授予不屈（战斗牌关键字）：无则追加并记 flag。

    追加的不屈由 after_play 移除（战斗中途被引擎消耗时移除为空操作）；
    式神本就有不屈（神子形态等）时不动、也不代为移除。
    """
    if HeroAttributes.TENACIOUS not in hero.attributes:
        hero.attributes.append(HeroAttributes.TENACIOUS)
        setattr(s, flag, True)


def _battle_tenacious_cleanup(s, hero, flag):
    """after_play：移除本牌授予的战斗不屈（幂等）。"""
    if getattr(s, flag, False):
        if HeroAttributes.TENACIOUS in hero.attributes:
            hero.attributes.remove(HeroAttributes.TENACIOUS)
        setattr(s, flag, False)


# ═══════════════════════════════════════════════════════════════════════════════
#  298 醉里乾坤 (ZuiLiQianKun)
#  瞬发 对酒吞童子造成1点伤害，抽一张牌。
# ═══════════════════════════════════════════════════════════════════════════════
def _zuiliqiankun_on_play(s):
    hero = _jiutun_hero(s.owner)
    if hero is None:
        return
    # 先受伤再抽牌（按牌面顺序）；伤害来源=酒吞本人 → 触发自身成长。
    # 致死则抽牌效果无影响（用户裁决 2026-09-25）；狂啸守护保命则照常抽。
    s.owner.game.handle_event(DealDamage(1, hero, [hero]))
    if hero.is_alive:
        s.owner.game.handle_event(DrawEvent(s.owner, 1))


class ZuiLiQianKun:
    id = 298
    type = "spell"
    hero = "JiuTunTongZi"
    name = "醉里乾坤"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)      # 瞬发
    is_beginning_card = True
    on_play = (_zuiliqiankun_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  299 狂气 (KuangQi)
#  本次战斗获得不屈。（1 力量）
# ═══════════════════════════════════════════════════════════════════════════════
def _kuangqi_on_play(s):
    # 不屈先于战斗结算授予（play_card attack 分支 on_play → buff → HeroAttackEvent）
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    _battle_tenacious(s, hero, "_kuangqi_granted")


def _kuangqi_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        _battle_tenacious_cleanup(s, hero, "_kuangqi_granted")


class KuangQi:
    id = 299
    type = "attack"
    hero = "JiuTunTongZi"
    name = "狂气"
    level_req = 1
    buff_atk = 1
    is_beginning_card = True
    on_play = (_kuangqi_on_play,)
    after_play = (_kuangqi_after_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  300 鬼王 (GuiWang)
#  进场时对酒吞童子造成4点伤害。（6/10）
# ═══════════════════════════════════════════════════════════════════════════════
def _guiwang_after_play(s):
    # after_play 位于 morph 分支身材替换+满血之后：4 点自伤基于形态血量结算
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    s.owner.game.handle_event(DealDamage(4, hero, [hero]))


class GuiWang:
    id = 300
    type = "morph"
    hero = "JiuTunTongZi"
    name = "鬼王"
    level_req = 2
    atk = 6
    hp = 10
    is_beginning_card = True
    after_play = (_guiwang_after_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  301 狂啸 (KuangXiao)
#  本回合酒吞童子生命不会降到1以下。
#  响应：当酒吞童子将受到伤害时，自动使用。
# ═══════════════════════════════════════════════════════════════════════════════
def _kuangxiao_guard(hero):
    """血量下限守护回调（on_before_death 协议：返回 True 阻止死亡）。

    计数器有效期内把血量钳到 1 并阻止气绝；过期时惰性摘除自身（check_death
    是唯一死亡结算点，三条伤害通道共用，故经此实现「生命不会降到1以下」）。
    已知局限：必杀在守护之后置 hp=0（FATAL 后置结算），会绕过本守护——与
    不屈/必杀交互一致（必杀更强），记录为现状。
    """
    def cb(h):
        if h.counters.get("jiutun_kuangxiao_turn", 0) <= 0:
            h.on_before_death = tuple(c for c in h.on_before_death if c is not cb)
            return False
        if h.hp < 1:
            h.hp = 1
        return True
    cb._jiutun_kuangxiao_guard = True
    return cb


def _kuangxiao_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    # reset_per_turn：下个回合开始（任一方）过期，「本回合」语义
    hero.counters.ensure("jiutun_kuangxiao_turn", initial=0, reset_per_turn=True)
    hero.counters.set("jiutun_kuangxiao_turn", 1)
    if not any(getattr(c, "_jiutun_kuangxiao_guard", False)
               for c in hero.on_before_death):
        hero.on_before_death = hero.on_before_death + (_kuangxiao_guard(hero),)


def _kuangxiao_response_cond(card, src, target):
    # 响应：当酒吞童子将受到伤害时（敌方回合限制由引擎 _auto_response 保证）。
    # "deal damage" 事件不进 _response_target 映射（target 恒为 None），受击方
    # 从 src.target 列表取。战斗通道（game.py:1515）与法术通道（handle_event）
    # 的 before 广播均开放响应扫描，故战斗各命中段/法术/贯通溢出全覆盖。
    hero = card.get_corresponding_hero()
    targets = getattr(src, "target", None) or []
    return hero is not None and hero.is_alive and hero in targets


class KuangXiao:
    id = 301
    type = "spell"
    hero = "JiuTunTongZi"
    name = "狂啸"
    level_req = 2
    is_beginning_card = True
    # 响应挂在 "deal damage" 的结算前广播（「将受到伤害时」，先于伤害落位）：
    # 战斗每段命中、法术直伤、贯通溢出均为响应点；连击两段各提供一次机会
    # （每事件至多响应一张，手牌顺序）。酒吞主动攻击时受到的反击不触发——
    # 响应仅敌方回合生效（wiki 响应语义，引擎 _auto_response 限定）。
    response_trigger = "deal damage"
    response_phase = "before"
    response_condition = (_kuangxiao_response_cond,)
    on_play = (_kuangxiao_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  302 无尽愤怒 (WuJinFenNu)
#  若本回合酒吞童子受到过己方伤害，此牌获得+2力量和+2护甲。（2 力量）
# ═══════════════════════════════════════════════════════════════════════════════
def _wujinfennu_on_play(s):
    # 条件在 on_play 折算（attack 分支 on_play 先于 buff_atk/buff_def 读取）：
    # +2 力量仅本次战斗（随 combat_buff_atk 战后清零），+2 护甲按战斗牌规则持续
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if hero.counters.get("jiutun_friendly_dmg_turn", 0) > 0:
        s.buff_atk = getattr(s, "buff_atk", 0) + 2
        s.buff_def = getattr(s, "buff_def", 0) + 2


class WuJinFenNu:
    id = 302
    type = "attack"
    hero = "JiuTunTongZi"
    name = "无尽愤怒"
    level_req = 2
    buff_atk = 2
    is_beginning_card = True
    on_play = (_wujinfennu_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  303 神子 (ShenZi)
#  瞬发 不屈（6/8）
# ═══════════════════════════════════════════════════════════════════════════════
def _shenzi_morph_leave_cond(e, s):
    return getattr(e.event, "hero", None) is s


def _shenzi_tenacious_cleanup(e, s):
    """形态离场（被替换或随气绝消灭）时移除形态授予的不屈（幂等）。"""
    if getattr(s, "_shenzi_tenacious", False):
        if HeroAttributes.TENACIOUS in s.attributes:
            s.attributes.remove(HeroAttributes.TENACIOUS)
        s._shenzi_tenacious = False
    s.listeners = [l for l in s.listeners
                   if getattr(l, "_tag", None) != "_shenzi_tenacious_cleanup"]


def _shenzi_on_play(s):
    # 形态关键字「不屈」持续到形态离场：运行时挂 tag 清理监听器
    # （山兔形态先例）。replace/destroy 两条 MorphLeave 通道都先于 check_death
    # 的监听器重置触发，清理必然执行。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if HeroAttributes.TENACIOUS not in hero.attributes:
        hero.attributes.append(HeroAttributes.TENACIOUS)
        hero._shenzi_tenacious = True
    hero.listeners = [l for l in hero.listeners
                      if getattr(l, "_tag", None) != "_shenzi_tenacious_cleanup"]
    l = Listener("morph leave", _shenzi_morph_leave_cond,
                 (_shenzi_tenacious_cleanup,))
    l._tag = "_shenzi_tenacious_cleanup"
    hero.listeners.append(l)


class ShenZi:
    id = 303
    type = "morph"
    hero = "JiuTunTongZi"
    name = "神子"
    level_req = 3
    atk = 6
    hp = 8
    attributes = (CardAttributes.INSTANT,)      # 瞬发
    is_beginning_card = True
    on_play = (_shenzi_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  304 觉醒·酒吞童子 (JueXingJiuTunTongZi)
#  觉醒：贯通 每当酒吞童子受到伤害时，获得等量的力量。（+1 力量/+3 生命）
# ═══════════════════════════════════════════════════════════════════════════════
def _juexingjiutun_on_play(s):
    # +1/+3 为永久加成（JSON buff_atk 1 / buff_hp 3），法术牌不走自动读取，
    # 按觉醒·书翁先例经 get_permanent_buff 实装；「获得等量力量」由 heroes.py
    # 成长监听器的 is_awakened 分支完成。贯通挂在 hero.attributes：check_death
    # 只移除迅捷，跨气绝保留，与觉醒同为全局永久效果。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 3)
    hero.is_awakened = True
    if HeroAttributes.PENETRATE not in hero.attributes:
        hero.attributes.append(HeroAttributes.PENETRATE)


class JueXingJiuTunTongZi:
    id = 304
    type = "spell"
    hero = "JiuTunTongZi"
    name = "觉醒·酒吞童子"
    level_req = 3
    is_beginning_card = True
    on_play = (_juexingjiutun_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  305 百鬼夜行 (BaiGuiYeXing)
#  瞬发 对其他所有式神各造成X点伤害，X为酒吞童子本回合所受伤害之和。
# ═══════════════════════════════════════════════════════════════════════════════
def _baiguiyexing_on_play(s):
    hero = _jiutun_hero(s.owner)
    if hero is None:
        return
    # 「其他所有式神」：双方除酒吞外的全部存活式神（0 级式神由引擎伤害分支跳过）
    targets = [h for p in (s.owner, s.owner.opponent) for h in p.heroes
               if h.is_alive and h is not hero]
    x = hero.counters.get("jiutun_dmg_taken_turn", 0)
    if not targets or x <= 0:
        return
    s.owner.game.handle_event(DealDamage(x, hero, targets))


class BaiGuiYeXing:
    id = 305
    type = "spell"
    hero = "JiuTunTongZi"
    name = "百鬼夜行"
    level_req = 3
    attributes = (CardAttributes.INSTANT,)      # 瞬发
    is_beginning_card = True
    on_play = (_baiguiyexing_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  306 狂歌豪情 (KuangGeHaoQing) — 协战：酒吞童子×茨木童子
#  选择使用一项：酒吞童子-醉酒当歌；茨木童子-地狱豪焰
# ═══════════════════════════════════════════════════════════════════════════════
def _kuanggehaqing_on_play(s):
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "JiuTunTongZi":
        # 酒吞童子-醉酒当歌：协战半卡按森佑灵矢先例只结算效果不发起攻击
        # （不屈无战斗可保护，效果结算后由 after_play 部分立即移除）
        _zuijiudangge_on_play(s)
        _zuijiudangge_after_play(s)
    elif hero.type_name == "CiMuTongZi":
        # 茨木童子-地狱豪焰：茨木童子未实现，TODO（待茨木童子实现后完成）
        pass


class KuangGeHaoQing:
    id = 306
    type = "coop"
    hero = "JiuTunTongZi"
    heroes = ["JiuTunTongZi", "CiMuTongZi"]
    name = "狂歌豪情"
    level_req = 1
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (_kuanggehaqing_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  307 醉酒当歌 (ZuiJiuDangGe)
#  不屈 对酒吞童子造成3点伤害，获得等量的护甲。
#  羁绊：获得一张茨木童子当前等级的战斗牌。
# ═══════════════════════════════════════════════════════════════════════════════
def _zuijiudangge_on_play(s):
    # 不屈先于自伤授予；不屈同时保护本次 3 点自伤——法术伤害通道不结算不屈
    # （引擎现状），故临时挂 on_before_death 守护（狂啸同款机制，作用域仅本次
    # 自伤结算，随后立即摘除）。hp≤1 时不屈本就不生效（wiki：生命大于1时受伤
    # 至多减至1），不挂守护、伤害可致死。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    _battle_tenacious(s, hero, "_zuijiu_granted")
    guard = None
    if hero.hp > 1:
        def guard(h):
            h.hp = 1
            return True
        hero.on_before_death = hero.on_before_death + (guard,)
    s.owner.game.handle_event(DealDamage(3, hero, [hero]))
    if guard is not None:
        hero.on_before_death = tuple(c for c in hero.on_before_death
                                     if c is not guard)
    # 「获得等量的护甲」：按牌面名义值 3 结算；来源为牌，GiveBuff 跳过气绝式神
    s.owner.game.handle_event(GiveBuff("defense", 3, s, [hero]))
    # 羁绊：获得一张茨木童子当前等级的战斗牌——茨木童子未实现，
    # TODO（待茨木童子实现后完成，参考灵矢贯虹的未实现先例）


def _zuijiudangge_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        _battle_tenacious_cleanup(s, hero, "_zuijiu_granted")


class ZuiJiuDangGe:
    id = 307
    type = "attack"
    hero = "JiuTunTongZi"
    name = "醉酒当歌"
    level_req = 1
    is_beginning_card = False
    on_play = (_zuijiudangge_on_play,)
    after_play = (_zuijiudangge_after_play,)
