"""青蛙瓷器 专属卡牌（8 张：id 97-104，对应 cards.json）"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.heroes import _qingwaciqi_awaken_listener
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _enemy_characters(player):
    """敌方角色候选：存活且已升级的敌方式神 + 敌方牌手。"""
    opp = player.opponent
    return [h for h in opp.heroes if h.is_alive and h.level > 0] + [opp]


# ── 1勾卡牌 ─────────────────────────────────────────────────────────────────

def _chuqian_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 运势4：将一张「出千」置入手牌（on_play 在出击前结算）
    if s.owner.game.roll_fortune(hero, 4):
        s.owner.GiveCardToHand(["ChuQian"])


class ChuQian:
    """出千：出击并施加1护甲。运势4：将一张「出千」置入手牌。"""
    id = 97
    type = "attack"
    hero = "QingWaCiQi"
    name = "出千"
    level_req = 1
    buff_def = 1
    on_play = (lambda s: _chuqian_on_play(s),)


def _lingshangkaihua_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 运势成功 → 青蛙瓷器 +1 力量（跨回合/跨形态，直接改 atk；气绝后随 revive 重置）。
    # 觉醒后效果触发两次 → +2。监听器随 morphed_id==98 自失效，重复打出按 tag 去重。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "lingshangkaihua"]
    l = Listener("fortune success",
                 lambda e, h: h.is_alive and h.morphed_id == 98 and e.event.source_hero.owner == h.owner,
                 (_lingshangkaihua_fortune,))
    l._tag = "lingshangkaihua"
    hero.listeners.append(l)


def _lingshangkaihua_fortune(e, h):
    h.atk += 2 if h.is_awakened else 1


class LingShangKaiHua:
    """岭上开花：形态 2/7。当你运势判定成功时，青蛙瓷器获得1力量（觉醒后触发两次）。"""
    id = 98
    type = "morph"
    hero = "QingWaCiQi"
    name = "岭上开花"
    level_req = 1
    atk = 2
    hp = 7
    on_play = (lambda s: _lingshangkaihua_on_play(s),)


def _jiulianbaodeng_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 增强：本局游戏你投骰子每投出过一次 1-6 中不重复数字时，此牌 +1力量 +1生命。
    # 点数由 hero 的 fortune roll 追踪监听器累计到 qw_distinct_mask。
    # morph 分支先跑 on_play 后读 atk/hp，故在此写回最终数值（基础 3/3）。
    mask = hero.counters.get("qw_distinct_mask", 0)
    count = bin(mask).count("1")
    s.atk = 3 + count
    s.hp = 3 + count


class JiuLianBaoDeng:
    """九莲宝灯：形态 3/3。增强：本局游戏你投骰子每投出过一次 1-6 中不重复数字时，此牌 +1力量 +1生命。"""
    id = 99
    type = "morph"
    hero = "QingWaCiQi"
    name = "九莲宝灯"
    level_req = 1
    atk = 3
    hp = 3
    on_play = (lambda s: _jiulianbaodeng_on_play(s),)


def _lizhi_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    game = s.owner.game
    # 若青蛙瓷器有形态，本次运势判定必定成功（阈值 1，任何点数均成功）。
    # 作为普通出击或响应打出都走此路径（响应战斗牌只施加效果，不发起攻击）。
    threshold = 1 if hero.morphed_id != 0 else 4
    if game.roll_fortune(hero, threshold):
        clear_combat_immune(hero)  # 去重
        hero.listeners.append(make_combat_immune_listener())  # 本回合免疫战斗伤害


def _lizhi_response_cond(s, event, target):
    """当青蛙瓷器被攻击时（敌方出击，目标是青蛙瓷器），自动使用。"""
    hero = s.get_corresponding_hero()
    if hero is None:
        return False
    if event.hero.owner is s.owner:
        return False  # 己方出击，不响应
    return getattr(event, "target", None) is hero or event.hero.owner.opponent.attack_zone is hero


class LiZhi:
    """立直：运势4：免疫战斗伤害。若青蛙瓷器有形态，本次运势判定必定成功。
    响应：当青蛙瓷器被攻击时，自动使用。"""
    id = 100
    type = "attack"
    hero = "QingWaCiQi"
    name = "立直"
    level_req = 1
    buff_atk = 0   # 响应战斗牌路径会无条件访问 buff_atk/buff_def（见 game.py _play_response_card）
    buff_def = 0
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: _lizhi_response_cond(s, event, target),)
    on_play = (lambda s: _lizhi_on_play(s),)


# ── 2勾卡牌 ─────────────────────────────────────────────────────────────────

def _menqianqing_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 当青蛙瓷器出击或被攻击时，运势4：获得2护甲（觉醒后触发两次 → 4）。
    # 监听器在广播阶段（战斗结算前）触发，护甲可用于本次战斗。随 morphed_id==101 自失效。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "menqianqing"]
    l = Listener("hero attack", _menqianqing_cond, (_menqianqing_effect,))
    l._tag = "menqianqing"
    hero.listeners.append(l)


def _menqianqing_cond(e, s):
    if not (s.is_alive and s.morphed_id == 101):
        return False
    ev = e.event
    if ev.hero is s:
        return True   # 青蛙瓷器出击
    if ev.hero.owner is s.owner:
        return False  # 己方其他式神出击，与青蛙瓷器无关
    # 敌方出击：目标为青蛙瓷器（HUNTING 指定或敌方攻击区）
    return getattr(ev, "target", None) is s or ev.hero.owner.opponent.attack_zone is s


def _menqianqing_effect(e, s):
    if not s.owner.game.roll_fortune(s, 4):
        return
    gain = 4 if s.is_awakened else 2  # 觉醒后效果触发两次
    s.owner.game.handle_event(GiveBuff("defense", gain, s, [s]))


class MenQianQing:
    """门前清：形态 2/9。当青蛙瓷器出击或被攻击时，运势4：获得2护甲（觉醒后触发两次）。"""
    id = 101
    type = "morph"
    hero = "QingWaCiQi"
    name = "门前清"
    level_req = 2
    atk = 2
    hp = 9
    on_play = (lambda s: _menqianqing_on_play(s),)


def _touzizhadan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    targets = s.owner.selected_targets or []
    if not targets:
        return
    game = s.owner.game
    # 捕获本次运势骰子点数：临时监听器存下 FortuneRollEvent，roll 返回后读最终 result
    # （含座敷童子重掷等所有 fortune roll 监听器的修改）。
    holder = {}

    def _record(e, h):
        holder["evt"] = e.event

    l = Listener("fortune roll", lambda e, h: h is hero, (_record,))
    l._tag = "_touzizhadan_capture"
    hero.listeners.append(l)
    try:
        game.roll_fortune(hero, 1)  # 运势1 必成功
    finally:
        hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != "_touzizhadan_capture"]
    evt = holder.get("evt")
    value = evt.result if evt is not None else 1
    # 造成等同于骰子点数的伤害；觉醒后效果触发两次（两次独立伤害，而非伤害x2，
    # 避免被单次免疫类响应牌吞掉整段伤害）。
    game.handle_event(DealDamage(value, hero, targets))
    if hero.is_awakened:
        game.handle_event(DealDamage(value, hero, targets))


class TouZiZhaDan:
    """骰子炸弹：瞬发 运势1：对一个敌方角色造成等同于骰子点数的伤害。"""
    id = 102
    type = "spell"
    hero = "QingWaCiQi"
    name = "骰子炸弹"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    require_target = (lambda s: _enemy_characters(s.owner),)
    select_target = (lambda s: select_target(s.owner, _enemy_characters(s.owner), s),)
    on_play = (lambda s: _touzizhadan_on_play(s),)


# ── 3勾卡牌 ─────────────────────────────────────────────────────────────────

def _zhuanyun_after(s):
    """攻击后运势4：随机弃两张手牌并再次使用此牌（再次出击）。

    补充说明：手上只剩一张手牌时，无法再次使用。这里理解为链式：每轮出击后
    若手牌 >1 且运势4 成功，弃两张并再次出击，直到手牌 ≤1、运势失败或式神气绝。
    再次使用不消耗鬼火。

    注意：引擎在 after_play 之后才把本牌移入 used_card，此时 s 仍位于手牌中。
    「再次使用」语义上本牌已不在手，故判定与弃牌均排除 s，避免把它数进手牌数
    或随机弃掉正在使用的这张转运。
    """
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    owner = s.owner
    game = owner.game
    while True:
        if not hero.is_alive:
            return  # 式神气绝，无法再次出击
        candidates = [c for c in owner.hand.cards if c is not s]
        if len(candidates) <= 1:
            return  # 手上只剩一张手牌时无法再次使用
        if not game.roll_fortune(hero, 4):
            return
        to_discard = random_sample(owner, candidates, 2, context="转运")
        for c in to_discard:
            owner.hand.remove(c)
            owner.used_card.append(c)
        # 再次使用此牌：青蛙瓷器再次出击（效果循环到下一轮判定）
        game.handle_event(HeroAttackEvent(owner, hero, s))


class ZhuanYun:
    """转运：攻击后运势4：随机弃两张手牌并再次使用此牌（手牌≤1时无法再次使用）。"""
    id = 103
    type = "attack"
    hero = "QingWaCiQi"
    name = "转运"
    level_req = 3
    after_play = (lambda s: _zhuanyun_after(s),)


def _juexingqingwaciqi_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)
    hero.is_awakened = True
    # 基础被动升级为觉醒版（效果触发两次）：同步替换 listeners 与 original_listeners，
    # 保证气绝→复活后仍保持觉醒状态（YaoHu 觉醒同款模式）。
    awaken = _qingwaciqi_awaken_listener()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "qwc_fortune"]
    hero.original_listeners = [l for l in hero.original_listeners if getattr(l, "_tag", "") != "qwc_fortune"]
    hero.listeners.append(awaken)
    hero.original_listeners.append(awaken)


class JueXingQingWaCiQi:
    """觉醒·青蛙瓷器：永久+2/+2。觉醒后你运势判定成功后效果触发两次。"""
    id = 104
    type = "spell"
    hero = "QingWaCiQi"
    name = "觉醒·青蛙瓷器"
    level_req = 3
    on_play = (lambda s: _juexingqingwaciqi_on_play(s),)
