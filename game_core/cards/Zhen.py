"""鸩 专属卡牌（cards 194-202）

鸩羽 / 鸩羽苏生 / 寂寥心象 / 毒蚀 / 觉醒·鸩 /
致命诱惑 / 碧羽散华(TODO被动) / 毒之华 / 蚀刃毒羽

数据来源：cards.json + tmp_cards_json/Zhen.json（描述逐字拷贝）。
引擎缺失/语义无法核实的机制一律标注 TODO（需引擎支持，等审批）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _countdown_reduce(hero, amount: int = 1):
    """倒计时 -X（妖琴师模式）：扣减 countdown，归零时重置并触发倒计时效果。"""
    if hero is None or hero.countdown_max <= 0 or hero.countdown <= 0:
        return
    hero.countdown -= amount
    if hero.countdown <= 0:
        hero.countdown = hero.countdown_max
        game = hero.owner.game
        game.handle_event(CountdownEvent(hero))
        for callback in hero.on_countdown:
            result = callback(hero)
            if result is not None and isinstance(result, Event):
                game.handle_event(result)


def _attack_target(s):
    """s 即将攻击的目标（战斗区式神或敌方牌手）。"""
    hero = s.get_corresponding_hero()
    if hero is None:
        return None
    return s.owner.game._resolve_attack_target(s.owner, hero)


# ── 战斗牌条件：目标带破甲 ──────────────────────────────────────────────────

def _zhenyu_on_play(s):
    """若攻击有破甲的角色，鸩本回合免疫战斗伤害。"""
    hero = s.get_corresponding_hero()
    target = _attack_target(s)
    if hero is not None and target is not None and getattr(target, "penetration", 0) > 0:
        clear_combat_immune(hero)  # 去重
        hero.listeners.append(make_combat_immune_listener())


def _clear_combat_immune(s):
    """攻击结算后清除战斗伤害免疫（引擎回合开始/死亡时也会清除）。"""
    hero = s.get_corresponding_hero()
    if hero is not None:
        clear_combat_immune(hero)


class ZhenYu:
    id = 194
    type = "attack"
    hero = "Zhen"
    name = "鸩羽"
    level_req = 1
    buff_atk = 2
    on_play = (lambda s: _zhenyu_on_play(s),)
    after_play = (lambda s: _clear_combat_immune(s),)


class ZhenYuSuSheng:
    id = 195
    type = "spell"
    hero = "Zhen"
    name = "鸩羽苏生"
    level_req = 1
    on_play = (lambda s: _zhenyususheng_on_play(s),)


def _zhenyususheng_on_play(s):
    # 使鸩倒计时-2，抽一张牌
    _countdown_reduce(s.get_corresponding_hero(), 2)
    s.owner.game.handle_event(DrawEvent(s.owner, 1))


_JILIAO_TAG = "jiliaoxinxiang_passive"


def _jiliaoxinxiang_setup(s):
    """寂寥心象进场：挂「敌方获得破甲」被动监听（morphed_id 门控，形态离场自动失效）。

    引擎侧破甲结附统一走 Game.apply_penetration（广播 "armor break applied"，
    清零不广播），见 game.py。
    """
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != _JILIAO_TAG]  # 去重
    game = hero.owner.game
    game.counters.ensure("jiliaoxinxiang_used", initial=0, reset_per_turn=True)
    listener = Listener("armor break applied", _jiliaoxinxiang_match, (_jiliaoxinxiang_trigger,))
    listener._tag = _JILIAO_TAG
    hero.listeners.append(listener)


def _jiliaoxinxiang_match(e, hero):
    """寂寥心象在场、获得破甲的是敌方角色（式神或牌手），且本回合尚未触发过。"""
    if hero.morphed_id != JiLiaoXinXiang.id or not hero.is_alive:
        return False
    opp = hero.owner.opponent
    target = e.event.target
    if target is not opp and getattr(target, "owner", None) is not opp:
        return False
    return hero.owner.game.counters.get("jiliaoxinxiang_used", 0) == 0


def _jiliaoxinxiang_trigger(e, hero):
    """两分支每回合合计一次：先消耗次数再结算——分支2 的结附会再次广播本事件，
    次数已消耗故不会递归/双触发。敌方战斗区为空时分支2 无处结附，次数仍消耗
    （事件已触发，两分支共享每回合一次的额度）。"""
    game = hero.owner.game
    game.counters.inc("jiliaoxinxiang_used")
    target = e.event.target
    if target is hero.owner.opponent:
        # 敌方牌手获得破甲 → 敌方战斗区式神获得等量破甲
        battle = target.attack_zone
        if battle is not None and battle.is_alive:
            game.apply_penetration(hero, battle, e.event.amount)
    else:
        # 敌方式神获得破甲 → 鸩倒计时-2（归零触发基础能力，其结附同样被次数门挡住）
        _countdown_reduce(hero, 2)


class JiLiaoXinXiang:
    """寂寥心象：4/6 形态。被动（每回合两分支合计一次）：
    当敌方式神获得破甲时，鸩的倒计时-2；或当敌方牌手获得破甲时，
    敌方战斗区式神获得等量破甲。实现见 _jiliaoxinxiang_* 三个函数。"""
    id = 196
    type = "morph"
    hero = "Zhen"
    name = "寂寥心象"
    level_req = 2
    atk = 4
    hp = 6
    on_play = (_jiliaoxinxiang_setup,)


class DuShi:
    """毒蚀：本次战斗中双方造成的伤害效果转化为等量的破甲。
    响应：当鸩被攻击时，自动使用此牌。

    实现：监听器挂在战斗伤害的 "deal damage" 预伤害广播上
    （_resolve_single_hit 扣血前广播 DealDamage(..., "combat")），命中时
    把受击方写入 immune_targets（引擎跳过扣血并提前 return），同时改为
    受击方获得等量破甲。转化量 = 广播时的实际伤害（已扣护甲、含暴击倍增）。
    攻击逻辑（advance/反击/连击/先攻）照常执行；无实际扣血故不广播
    damage dealt，伤害触发型效果不触发。法术/投射伤害不转化
    （只匹配 damage_type=="combat"）。响应/主动打出共用同一监听器。
    """
    id = 197
    type = "attack"
    hero = "Zhen"
    name = "毒蚀"
    level_req = 2
    buff_atk = 4
    buff_def = 0   # 响应战斗牌路径无条件访问 buff_atk/buff_def（见 game.py _play_response_card）
    is_beginning_card = True
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: _dushi_response_cond(s, event, target),)
    on_play = (lambda s: _dushi_on_play(s),)
    after_play = (lambda s: _dushi_after_play(s),)


def _dushi_response_cond(s, event, target):
    """鸩被攻击时：攻击方为敌方且被攻击目标是鸩本人。"""
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return False
    attacker = getattr(event, "hero", None)
    if attacker is None or attacker.owner is s.owner:
        return False  # 己方攻击不响应
    return target is hero


_DUSHI_TAG = "dushi_pen_convert"


def _dushi_match(e, h):
    """鸩参与本次战斗伤害（为受击方或伤害来源）即命中；只转化战斗伤害。"""
    base = e.event
    if getattr(base, "damage_type", "spell") != "combat":
        return False
    targets = getattr(base, "target", None) or ()
    return h in targets or getattr(base, "source", None) is h


def _dushi_convert(e, _h):
    """受击方获得等量破甲，并写入 immune_targets 使引擎跳过扣血。

    转化量与护甲同口径（receive_damage 的护甲分支）：护甲先吸收
    min(伤害, 护甲) 并照常消耗，溢出部分才转化为破甲。
    """
    base = e.event
    targets = [t for t in (getattr(base, "target", None) or ())
               if getattr(t, "state", None) != "dead"]
    game = base.source.owner.game
    for t in targets:
        armor = getattr(t, "defense", 0) or 0
        absorbed = min(armor, base.value)
        if armor:
            t.defense = armor - absorbed
        game.apply_penetration(base.source, t, base.value - absorbed)
    base.immune_targets = getattr(base, "immune_targets", set()) | set(targets)


def _dushi_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != _DUSHI_TAG]  # 去重
    listener = Listener("deal damage", _dushi_match, (_dushi_convert,))
    listener._tag = _DUSHI_TAG
    hero.listeners.append(listener)


def _dushi_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != _DUSHI_TAG]


class JueXingZhen:
    id = 198
    type = "spell"
    hero = "Zhen"
    name = "觉醒·鸩"
    level_req = 2
    on_play = (lambda s: _juexingzhen_on_play(s),)


def _juexingzhen_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 使敌方牌手获得2点破甲
    s.owner.game.apply_penetration(hero, s.owner.opponent, 2)
    hero.get_permanent_buff("atk", 1)
    hero.is_awakened = True
    # 觉醒：倒计时2：使敌方牌手获得2点破甲。
    # 本局游戏每触发过一次鸩的基础能力，此效果额外+1。
    hero.on_countdown = (_zhen_awakened_countdown,)


def _zhen_awakened_countdown(hero):
    game = hero.owner.game
    # 从觉醒开始累计鸩的基础能力触发次数（觉醒后的每次倒计时触发都计入一次）。
    # 局限：觉醒前的倒计时触发未计入（需改 heroes.py 的 `_zhen_countdown`，属引擎/基础
    # 数据变更，已列入报告待审批）。
    game.counters.ensure("zhen_base_count", persistent=True)
    game.counters.inc("zhen_base_count")
    hero.owner.game.apply_penetration(hero, hero.owner.opponent,
                                      2 + game.counters.get("zhen_base_count", 0))


class ZhiMingYouHuo:
    id = 199
    type = "attack"
    hero = "Zhen"
    name = "致命诱惑"
    level_req = 2
    buff_atk = 2
    buff_def = 2
    on_play = (lambda s: _zhimingyouhuo_on_play(s),)
    after_play = (lambda s: _zhimingyouhuo_after(s),)


def _zhimingyouhuo_on_play(s):
    """若攻击有破甲的角色，获得吸血。"""
    hero = s.get_corresponding_hero()
    target = _attack_target(s)
    if (hero is not None and target is not None
            and getattr(target, "penetration", 0) > 0
            and HeroAttributes.LIFESTEAL not in hero.attributes):
        hero.attributes.append(HeroAttributes.LIFESTEAL)
        s._lifesteal_added = True


def _zhimingyouhuo_after(s):
    hero = s.get_corresponding_hero()
    if hero is not None and getattr(s, "_lifesteal_added", False):
        if HeroAttributes.LIFESTEAL in hero.attributes:
            hero.attributes.remove(HeroAttributes.LIFESTEAL)
        s._lifesteal_added = False


class BiYuSanHua:
    # TODO（需引擎支持，等审批）：鸩造成的破甲效果转化为等量的伤害。
    # 需要引擎在破甲结附处提供钩子（当前无破甲广播点，见寂寥心象）。
    # 本卡作为 5/7 形态牌正常生效。
    id = 200
    type = "morph"
    hero = "Zhen"
    name = "碧羽散华"
    level_req = 3
    atk = 5
    hp = 7


class DuZhiHua:
    id = 201
    type = "attack"
    hero = "Zhen"
    name = "毒之华"
    level_req = 3
    on_play = (lambda s: _duzhihua_on_play(s),)
    after_play = (lambda s: _duzhihua_after(s),)


def _duzhihua_on_play(s):
    """本次战斗中鸩对敌方角色造成战斗伤害时，使其获得等同于其一半生命的破甲。"""
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "duzhihua"]
    listener = Listener("damage dealt",
                        (lambda e, h: (getattr(e.event, "source", None) is h
                                       and getattr(e.event, "damage_type", None) == "combat")),
                        (lambda e, h: _duzhihua_trigger(e, h),))
    listener._tag = "duzhihua"
    hero.listeners.append(listener)


def _duzhihua_trigger(e, h):
    # damage dealt 的 target 恒为列表（战斗单目标为 [victim]）
    target = getattr(e.event, "target", None)
    target = target[0] if target else None
    if target is None or getattr(target, "hp", 0) <= 0:
        return
    # 式神取其一半最大生命；牌手取其一半当前生命
    if target.entity_type == "hero":
        half = target.current_max_hp // 2
    else:
        half = target.hp // 2
    if half > 0:
        h.owner.game.apply_penetration(h, target, half)


def _duzhihua_after(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "duzhihua"]


class ShiRenDuYu:
    id = 202
    type = "attack"
    hero = "Zhen"
    name = "蚀刃毒羽"
    level_req = 2
    buff_atk = 2
    buff_def = 2
    on_play = (lambda s: _shirenduyu_on_play(s),)
    after_play = (lambda s: _shirenduyu_after(s),)


def _shirenduyu_on_play(s):
    hero = s.get_corresponding_hero()
    target = _attack_target(s)
    # 若攻击有破甲的角色，攻击后使其获得相同数量的破甲（此处先记录目标与其破甲值）
    if hero is not None and target is not None and getattr(target, "penetration", 0) > 0:
        s._duyu_target = target
        s._duyu_capture = getattr(target, "penetration", 0)
    else:
        s._duyu_target = None
        s._duyu_capture = 0
    # 羁绊：以津真天倒计时-2（以津真天存活且等级≥1）
    yjzt = next((h for h in s.owner.heroes
                 if h.type_name == "YiJinZhenTian" and h.is_alive and h.level > 0), None)
    if yjzt is not None:
        _countdown_reduce(yjzt, 2)


def _shirenduyu_after(s):
    target = getattr(s, "_duyu_target", None)
    capture = getattr(s, "_duyu_capture", 0)
    if target is None or capture <= 0:
        return
    # 攻击后使目标获得相同数量的破甲（目标已死则无效）
    if getattr(target, "hp", 0) > 0:
        hero = s.get_corresponding_hero()
        s.owner.game.apply_penetration(hero if hero is not None else s, target, capture)
