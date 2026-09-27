"""茨木童子卡牌（id 308-316）。

牌面文本以 cards.json 条目（308-316，用户修订版 2026-09-27）为准。
式神段（基础能力/觉醒倍增/断臂最大值追踪/迁怒/罗生门之鬼计数/豪焰光环与
结算）在 heroes.py 茨木段；本文件只实现卡牌打出侧逻辑。

口径与裁决记录（用户 2026-09-27）：
- 罗生门之鬼强化池（增强，仅手牌中获得，打出后形态不再获得新强化）：
  必杀/迅捷/不屈/贯通/远程/瞬发（卡牌 INSTANT）/帷幕/复活茨木童子
  （CAN_PLAY_WHEN_DEAD + 打出时复活）/连击（「战斗额外先进行一次攻击」）/直击/
  身板+1/+1。各里程碑独立随机，同种强化可重复获得。
- 「基础式神」= 非召唤物（is_summoned=False，排除冰墙/雪球等 token）。
- 罗生门之鬼击杀计数监听器挂在茨木童子身上（heroes.py），茨木气绝期间
  计数暂停（引擎死亡重置监听器；持久计数器数值保留）。
- 迁怒触发判定用「被消灭者 = 最近一次攻击时敌方战斗区占用者」快照
  （heroes.py hero attack 监听器记录）——check_death 会在击杀事件前清空
  attack_zone，事件时刻无法直接读区；严格排除地狱之手追猎再攻击对准备区
  式神的击杀触发迁怒（符合牌面「消灭敌方战斗区式神」限定）。
- 地狱之手：追猎首攻由 select_target 选定；after_play 中循环「随机攻击一个
  敌方生命最低的式神」，茨木气绝 / 敌方全气绝 / 未击杀即停（用户裁决
  2026-09-27：只要击杀可重复触发）。迁怒先于再攻击结算（击杀事件在战斗内）。
- 觉醒·茨木童子：buff_hp:1 = 觉醒永久加成（get_permanent_buff，跨形态/死亡）；
  「获得2力量和2护甲」为本条命有效加成（GiveBuff，用户裁决 2026-09-27）。
  觉醒后己方回合开始力量翻倍，上限 65535（用户裁决）。
- 地狱豪焰豪焰效果池（用户 2026-09-27 定义，随机不重复，共 4 个；共享部分
  「使用战斗牌时获得+1力量+1护甲」按已获得个数叠加）：
  0. 击杀式神后使该式神气绝倒计时+1
  1. 击杀式神后获得+2力量
  2. 击杀式神后回复3点生命或气绝倒计时-1（按自己是否气绝自动决定）
  3. 击杀式神后对敌方牌手造成3点伤害
  位掩存于茨木持久计数器 cimu_haoyan_mask（heroes.py 光环/结算监听器消费）。
  「本次战斗击杀」检测用 on_play 快照敌方存活集合、after_play 比对（战斗窗口
  同步结算，期间敌方响应牌不会自动打出）。
- 羁绊（地狱豪焰/狂歌豪情茨木分支）：另一位协战式神（酒吞童子）存活且等级
  不为 0 时生效（faq 协战羁绊规则）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


def _cimu_hero(player):
    """player 存活的茨木童子；没有则 None。"""
    return next((h for h in player.heroes
                 if h.type_name == "CiMuTongZi" and h.is_alive), None)


# ═══════════════════════════════════════════════════════════════════════════════
#  308 鬼之手 (GuiZhiShou)
#  若敌方战斗区没有式神，将一个敌方式神移入战斗区。
# ═══════════════════════════════════════════════════════════════════════════════
def _guizhishou_on_play(s):
    # 玩家选择拉取目标（用户裁决 2026-09-27，羽迹先例）；战斗区非空时
    # select_target 解析为 None，无 selected_targets，直接正常攻击。
    targets = getattr(s.owner, "selected_targets", None) or []
    if not targets:
        return
    tgt = targets[0]
    # 移入敌方战斗区（战斗区已有其他式神时自动换下；已在战斗区则不重复移动）
    if tgt.owner.attack_zone is not tgt:
        tgt.move_to_battle()


class GuiZhiShou:
    id = 308
    type = "attack"
    hero = "CiMuTongZi"
    name = "鬼之手"
    level_req = 1
    is_beginning_card = True

    @staticmethod
    def select_target(card):
        """敌方战斗区为空且存在可拉取的敌方式神时进入目标选择；否则跳过。"""
        player = card.owner
        if player is None:
            return None
        if player.opponent.attack_zone is not None:
            return None
        cands = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
        if not cands:
            return None
        return (lambda s: select_target(player, cands, s),)

    on_play = (_guizhishou_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  309 豪拳 (HaoQuan)
#  获得3力量。
# ═══════════════════════════════════════════════════════════════════════════════
def _haoquan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    s.owner.game.handle_event(GiveBuff("atk", 3, s, [hero]))


class HaoQuan:
    id = 309
    type = "spell"
    hero = "CiMuTongZi"
    name = "豪拳"
    level_req = 1
    is_beginning_card = True
    on_play = (_haoquan_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  310 黑焰之手 (HeiYanZhiShou)
#  远程
# ═══════════════════════════════════════════════════════════════════════════════
def _heiyanzhishou_on_play(s):
    # 本次攻击远程（不进入战斗区、不受反击）：狂气临时不屈同款
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if HeroAttributes.RANGED not in hero.attributes:
        hero.attributes.append(HeroAttributes.RANGED)
        setattr(s, "_heiyan_granted", True)


def _heiyanzhishou_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None and getattr(s, "_heiyan_granted", False):
        if HeroAttributes.RANGED in hero.attributes:
            hero.attributes.remove(HeroAttributes.RANGED)
        setattr(s, "_heiyan_granted", False)


class HeiYanZhiShou:
    id = 310
    type = "attack"
    hero = "CiMuTongZi"
    name = "黑焰之手"
    level_req = 2
    is_beginning_card = True
    on_play = (_heiyanzhishou_on_play,)
    after_play = (_heiyanzhishou_after_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  311 迁怒 (QianNu)
#  当茨木童子消灭敌方战斗区式神时，对其准备区式神各造成2点伤害。（3/7）
#  击杀判定与「战斗区」快照见 heroes.py 茨木段监听器（_cimu_qn_on_kill）。
# ═══════════════════════════════════════════════════════════════════════════════
class QianNu:
    id = 311
    type = "morph"
    hero = "CiMuTongZi"
    name = "迁怒"
    level_req = 2
    atk = 3
    hp = 7
    is_beginning_card = True


# ═══════════════════════════════════════════════════════════════════════════════
#  312 断臂 (DuanBi)
#  茨木童子的力量变为本局游戏的最大值。
# ═══════════════════════════════════════════════════════════════════════════════
def _duanbi_on_play(s):
    # cimu_max_atk 由 heroes.py give-buff 监听器维护（持久，气绝不丢）。
    # 兜底折算当前面板，覆盖 get_permanent_buff 等不走事件的力量变更。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    maxv = max(hero.counters.get("cimu_max_atk", 0), hero.atk)
    if getattr(hero, "is_awakened", False):
        maxv = min(maxv, 65535)
    delta = maxv - hero.atk
    if delta > 0:
        s.owner.game.handle_event(GiveBuff("atk", delta, s, [hero]))


class DuanBi:
    id = 312
    type = "spell"
    hero = "CiMuTongZi"
    name = "断臂"
    level_req = 2
    is_beginning_card = True
    on_play = (_duanbi_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  313 罗生门之鬼 (LuoShengMenZhiGui)
#  增强：本局游戏中，当己方累计消灭敌方战斗区1/3/5个基础式神时此牌随机强化
#  一次。（4/6）强化仅手牌中获得；打出后形态不再获得新强化（用户裁决）。
#  击杀计数监听器在 heroes.py 茨木段（_cimu_rsm_on_kill）。
# ═══════════════════════════════════════════════════════════════════════════════
# 强化池键（随机用）：顺序即 pool 索引
_RSM_POOL_KEYS = ("fatal", "agile", "tenacious", "penetrate", "ranged",
                  "instant", "veil", "revive", "double_strike", "direct",
                  "body")

_RSM_ATTR_MAP = {
    "fatal": HeroAttributes.FATAL,            # 必杀
    "agile": HeroAttributes.AGILE,            # 迅捷
    "tenacious": HeroAttributes.TENACIOUS,    # 不屈
    "penetrate": HeroAttributes.PENETRATE,    # 贯通
    "ranged": HeroAttributes.RANGED,          # 远程
    "veil": HeroAttributes.VEIL,              # 帷幕
    "double_strike": HeroAttributes.DOUBLE_STRIKE,  # 连击=「额外先进行一次攻击」
    "direct": HeroAttributes.DIRECT_ATTACK,   # 直击
}


def _rsm_apply_random_enhance(hero):
    """罗生门之鬼随机强化一次（heroes.py 击杀计数监听器在里程碑处调用）。

    仅当牌在手牌中时生效（打出后不强化）；随机可重复获得同种强化。
    属性类强化暂存卡牌 _rsm_hero_attrs（on_play 转移给式神，形态离场清理）；
    瞬发/复活改卡牌可打出性；身板直接加卡牌身材（morph 结算按卡牌值替换）。
    """
    card = next((c for c in hero.owner.hand.cards
                 if c.eng_name == "LuoShengMenZhiGui"), None)
    if card is None:
        return
    n = len(_RSM_POOL_KEYS)
    key = _RSM_POOL_KEYS[hero.owner.game.rng.randint(0, n - 1)]
    if key in _RSM_ATTR_MAP:
        card._rsm_hero_attrs = (getattr(card, "_rsm_hero_attrs", ())
                                + (_RSM_ATTR_MAP[key],))
    elif key == "instant":
        card.attributes.append(CardAttributes.INSTANT)
    elif key == "revive":
        # 气绝时可打出 + 打出时立刻复活
        card._rsm_revive = True
        if CardAttributes.CAN_PLAY_WHEN_DEAD not in card.attributes:
            card.attributes.append(CardAttributes.CAN_PLAY_WHEN_DEAD)
    elif key == "body":
        card.atk += 1
        card.hp += 1


def _rsm_form_cleanup(e, h):
    """罗生门形态离场（被替换/随气绝消灭）：移除形态授予的属性（幂等）。"""
    for a in getattr(h, "_rsm_form_attrs", ()) or ():
        if a in h.attributes:
            h.attributes.remove(a)
    h._rsm_form_attrs = ()
    h.listeners = [l for l in h.listeners
                   if getattr(l, "_tag", None) != "_rsm_form_cleanup"]


def _luoshengmen_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 复活强化：茨木气绝时立刻复活。morph 分支 on_play 先于身材替换，
    # 复活后随即装备 4/6+ 身材并满血。
    if getattr(s, "_rsm_revive", False) and not hero.is_alive:
        s.owner.game.handle_event(Revive(s, [hero]))
    # 手牌中获得的属性类强化转移给式神（去重），形态离场时清理（神子先例）
    gained = []
    for a in getattr(s, "_rsm_hero_attrs", ()) or ():
        if a not in hero.attributes:
            hero.attributes.append(a)
            gained.append(a)
    hero._rsm_form_attrs = tuple(gained)
    hero.listeners = [l for l in hero.listeners
                      if getattr(l, "_tag", None) != "_rsm_form_cleanup"]
    l = Listener("morph leave",
                 lambda e, h: getattr(e.event, "hero", None) is h,
                 (_rsm_form_cleanup,))
    l._tag = "_rsm_form_cleanup"
    hero.listeners.append(l)


class LuoShengMenZhiGui:
    id = 313
    type = "morph"
    hero = "CiMuTongZi"
    name = "罗生门之鬼"
    level_req = 2
    atk = 4
    hp = 6
    is_beginning_card = True
    on_play = (_luoshengmen_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  314 地狱之手 (DiYuZhiShou)
#  追猎 本次战斗中若消灭式神，再次随机攻击一个敌方生命最低的式神。
# ═══════════════════════════════════════════════════════════════════════════════
def _diyuzhishou_on_play(s):
    # 本次攻击追猎（引擎 _resolve_attack_target 读 selected_targets）
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if HeroAttributes.HUNTING not in hero.attributes:
        hero.attributes.append(HeroAttributes.HUNTING)
        setattr(s, "_diyu_granted", True)


def _diyuzhishou_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        # 首攻中已气绝：仅清理临时追猎
        if hero is not None and getattr(s, "_diyu_granted", False):
            if HeroAttributes.HUNTING in hero.attributes:
                hero.attributes.remove(HeroAttributes.HUNTING)
            setattr(s, "_diyu_granted", False)
        return
    # 循环再攻击：随机攻击敌方生命最低的式神（并列随机），击杀则重复；
    # 茨木气绝 / 敌方全气绝 / 未击杀即停（用户裁决 2026-09-27）。
    # 经 HeroAttackEvent 走引擎 "hero attack" 分支：结算与正常战斗牌攻击一致；
    # 追猎保持到循环结束——引擎 _resolve_attack_target 靠它读取 selected_targets
    # 指定再攻击目标（战斗区已空时无追猎会默认改为攻击牌手）。
    game = s.owner.game
    while hero.is_alive:
        cands = [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0]
        if not cands:
            break
        lowest = min(h.hp for h in cands)
        pool = [h for h in cands if h.hp == lowest]
        tgt = pool[game.rng.randint(0, len(pool) - 1)]
        s.owner.selected_targets = [tgt]
        game.handle_event(HeroAttackEvent(s.owner, hero, s))
        s.owner.selected_targets = None
        if tgt.is_alive:
            break
    # 循环结束（未击杀/气绝/敌全灭）后移除本次临时追猎
    if getattr(s, "_diyu_granted", False):
        if HeroAttributes.HUNTING in hero.attributes:
            hero.attributes.remove(HeroAttributes.HUNTING)
        setattr(s, "_diyu_granted", False)


class DiYuZhiShou:
    id = 314
    type = "attack"
    hero = "CiMuTongZi"
    name = "地狱之手"
    level_req = 3
    is_beginning_card = True

    @staticmethod
    def select_target(card):
        """追猎目标选择（存活且已升级的敌方式神，含准备区）。

        与引擎追猎选目标门口径一致：帷幕不限制追猎选目标
        （game.py 追猎门注释），故不排除 VEIL 目标。
        """
        player = card.owner
        if player is None:
            return None
        cands = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
        if not cands:
            return None
        return (lambda s: select_target(player, cands, s),)

    on_play = (_diyuzhishou_on_play,)
    after_play = (_diyuzhishou_after_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  315 觉醒·茨木童子 (JueXingCiMuTongZi)
#  获得2力量和2护甲。觉醒：己方回合开始时茨木童子的力量翻倍。
#  （buff_hp:1 = 觉醒永久加成，跨形态/死亡保留；2力2甲为 GiveBuff 本条命加成，
#   用户裁决 2026-09-27。觉醒后力量上限 65535，倍增在 heroes.py 茨木段。）
# ═══════════════════════════════════════════════════════════════════════════════
def _juexingcimu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    hero.get_permanent_buff("hp", 1)
    s.owner.game.handle_event(GiveBuff("atk", 2, s, [hero]))
    s.owner.game.handle_event(GiveBuff("defense", 2, s, [hero]))
    hero.is_awakened = True


class JueXingCiMuTongZi:
    id = 315
    type = "spell"
    hero = "CiMuTongZi"
    name = "觉醒·茨木童子"
    level_req = 3
    buff_hp = 1
    is_beginning_card = True
    on_play = (_juexingcimu_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  316 地狱豪焰 (DiYuHaoYan)
#  若本次战斗击杀敌方式神，则本局游戏茨木童子随机获得一个不重复的豪焰效果。
#  羁绊：酒吞童子对自己造成1点伤害，使茨木童子获得2护甲。
# ═══════════════════════════════════════════════════════════════════════════════
def _diyuhaoyan_bond_on_play(s):
    """羁绊：酒吞童子对自己造成1点伤害，使茨木童子获得2护甲。

    羁绊条件按 faq 协战规则：另一位协战式神（酒吞童子）存活且等级不为 0。
    狂歌豪情协战选茨木分支（JiuTunTongZi.py，用户已授权最小改动）复用本函数；
    协战半卡不发起攻击（森佑灵矢先例），豪焰击杀成长无战斗不触发。
    """
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    partner = next((h for h in s.owner.heroes
                    if h.type_name == "JiuTunTongZi"
                    and h.is_alive and h.level > 0), None)
    if partner is None:
        return
    # 先自损再给护甲（按牌面顺序）；自伤来源为酒吞本人
    s.owner.game.handle_event(DealDamage(1, partner, [partner]))
    s.owner.game.handle_event(GiveBuff("defense", 2, s, [hero]))


def _diyuhaoyan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    _diyuhaoyan_bond_on_play(s)
    # 快照敌方存活集合：after_play 比对检测「本次战斗击杀敌方式神」。
    # 战斗窗口内为同步结算（敌方回合响应牌不会在我方回合自动打出），
    # 快照差集即本次战斗的击杀（含迁怒等茨木效果的连带击杀）。
    s._haoyan_alive_snapshot = tuple(h for h in s.owner.opponent.heroes
                                     if h.is_alive)


def _haoyan_rider_0(s, killed):
    """击杀式神后使该式神气绝倒计时+1（召唤物无倒计时，加值无影响）。"""
    killed.round_until_alive += 1


def _haoyan_rider_1(s, killed):
    """击杀式神后获得+2力量。"""
    s.owner.game.handle_event(GiveBuff("atk", 2, s, [s]))


def _haoyan_rider_2(s, killed):
    """击杀式神后回复3点生命或气绝倒计时-1（按自己是否气绝自动决定）。

    气绝倒计时-1 只递减不就地复活：减到 0 后按常规在下个己方回合开始复活
    （begin_turn 的 round_until_alive<=0 分支）。
    """
    if s.is_alive:
        s.owner.game.handle_event(Heal(3, s, [s]))
    else:
        s.round_until_alive = max(0, s.round_until_alive - 1)


def _haoyan_rider_3(s, killed):
    """击杀式神后对敌方牌手造成3点伤害。"""
    s.owner.game.handle_event(DealDamage(3, s, [s.owner.opponent]))


_HAOYAN_RIDERS = (_haoyan_rider_0, _haoyan_rider_1,
                  _haoyan_rider_2, _haoyan_rider_3)


def _diyuhaoyan_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    killed = [h for h in getattr(s, "_haoyan_alive_snapshot", ())
              if not h.is_alive]
    s._haoyan_alive_snapshot = ()
    if not killed:
        return
    mask = hero.counters.get("cimu_haoyan_mask", 0)
    ungained = [i for i in range(len(_HAOYAN_RIDERS)) if not (mask >> i) & 1]
    if not ungained:
        return
    idx = ungained[s.owner.game.rng.randint(0, len(ungained) - 1)]
    hero.counters.ensure("cimu_haoyan_mask", initial=0, persistent=True)
    hero.counters.set("cimu_haoyan_mask", mask | (1 << idx))
    # 光环（使用战斗牌+1/+1）与击杀结算由 heroes.py 茨木段监听器按位掩码执行


class DiYuHaoYan:
    id = 316
    type = "attack"
    hero = "CiMuTongZi"
    name = "地狱豪焰"
    level_req = 1
    is_beginning_card = False
    on_play = (_diyuhaoyan_on_play,)
    after_play = (_diyuhaoyan_after_play,)
