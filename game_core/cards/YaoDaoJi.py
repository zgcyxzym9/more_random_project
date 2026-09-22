"""妖刀姬 专属卡牌（完整实现：id 164-173）

数据源：cards.json（id/type/level_req/数值/中文名/description）+ tmp_cards_json/YaoDaoJi.sources.md（机制备注）。
规则冲突时以 cards.json 为准（例：战意按 JSON 取 +2/+2，非 sources 的 +3/+3；不祥之刃按 JSON 为「消灭抽牌」）。

实现要点：
- 击杀计数由 heroes.py 中妖刀姬的「hero kill」监听器写入 game.counters["yaodaoji_kills"]（persistent）。
- 不祥之刃(164)：buff_def=1；on_play 记录击杀计数，after_play 若计数增加则抽牌。
- 见切(165)：战斗牌响应，on_play/after_play 挂/摘「免疫战斗伤害」监听器（damage_immunity）。
- 一闪(167)：NO_FIRE_CONSUMPTION 不消耗鬼火。
- 禁锢之刀(168)：增强，on_play 按击杀计数写入 buff_atk。
- 妖刀万华(169)：形态连击=DOUBLE_STRIKE；morph leave 时移除。
- 杀念(170)：随机三张妖刀姬战斗牌入手（允许重复）。
- 觉醒·妖刀姬(171)/刃影叠岚(173)：对牌手造成伤害 → 手牌战斗牌获得 不消耗鬼火 / 瞬发+1/+1；觉醒效果挂 original_listeners 气绝后保留。
- 刃影鹤唳(172)：协战；姑获鸟分支未实现（TODO）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.heroes import _yaodaoji_hit_player, _yaodaoji_source_from
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _yaodaoji_grant_no_fire(e, s):
    """觉醒·妖刀姬：对敌方牌手造成伤害 → 她的手牌中妖刀姬战斗牌本回合不消耗鬼火。"""
    if not _yaodaoji_hit_player(e.event.target):
        return
    for c in s.owner.hand.cards:
        if c.hero == "YaoDaoJi" and c.card_type == CardType.ATTACK \
                and CardAttributes.NO_FIRE_CONSUMPTION not in c.attributes:
            c.attributes.append(CardAttributes.NO_FIRE_CONSUMPTION)


def _yaodaoji_clear_no_fire(e, s):
    """下一回合开始清除战斗牌的「不消耗鬼火」。"""
    for c in s.owner.hand.cards:
        if c.hero == "YaoDaoJi" and c.card_type == CardType.ATTACK \
                and CardAttributes.NO_FIRE_CONSUMPTION in c.attributes:
            c.attributes.remove(CardAttributes.NO_FIRE_CONSUMPTION)


def _yaodaoji_grant_instant_plus(e, s):
    """刃影叠岚：对敌方牌手造成伤害 → 手牌妖刀姬战斗牌本回合获得瞬发及+1力量+1护甲。"""
    if not _yaodaoji_hit_player(e.event.target):
        return
    for c in s.owner.hand.cards:
        if c.hero == "YaoDaoJi" and c.card_type == CardType.ATTACK:
            if getattr(c, "_renyingdielan_plus", False):
                continue  # 已加成，避免同一张牌重复叠加
            c._renyingdielan_plus = True
            if CardAttributes.INSTANT not in c.attributes:
                c.attributes.append(CardAttributes.INSTANT)
            c.buff_atk = getattr(c, "buff_atk", 0) + 1
            c.buff_def = getattr(c, "buff_def", 0) + 1


def _yaodaoji_clear_instant_plus(e, s):
    """下一回合开始清除刃影叠岚赋予战斗牌的瞬发及+1/+1。"""
    for c in s.owner.hand.cards:
        if c.hero == "YaoDaoJi" and c.card_type == CardType.ATTACK \
                and getattr(c, "_renyingdielan_plus", False):
            c._renyingdielan_plus = False
            if CardAttributes.INSTANT in c.attributes:
                c.attributes.remove(CardAttributes.INSTANT)
            c.buff_atk = getattr(c, "buff_atk", 0) - 1
            c.buff_def = getattr(c, "buff_def", 0) - 1


# ── 1勾 战斗牌 ─────────────────────────────────────────────────────────────

class BuXiangZhiRen:
    """不祥之刃：消灭敌方式神时，抽一张牌。"""
    id = 164
    type = "attack"
    hero = "YaoDaoJi"
    name = "不祥之刃"
    level_req = 1
    buff_def = 1
    is_beginning_card = True
    on_play = (lambda s: _buxiang_on_play(s),)
    after_play = (lambda s: _buxiang_after_play(s),)


def _buxiang_on_play(s):
    s._buxiang_before_kills = s.owner.game.counters.get("yaodaoji_kills", 0)


def _buxiang_after_play(s):
    # 本次出击产生了击杀 → 抽一张牌
    if s.owner.game.counters.get("yaodaoji_kills", 0) > getattr(s, "_buxiang_before_kills", 0):
        s.owner.game.handle_event(DrawEvent(s.owner, 1))


class JianQie:
    """见切：免疫战斗伤害。响应：妖刀姬被攻击时，自动使用。"""
    id = 165
    type = "attack"
    hero = "YaoDaoJi"
    name = "见切"
    level_req = 1
    buff_atk = 1
    buff_def = 0   # 响应战斗牌路径无条件访问 buff_atk/buff_def（见 game.py _play_response_card）
    attributes = (CardAttributes.RESPONSE,)
    is_beginning_card = True
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: _jianqie_response_cond(s, event, target),)
    on_play = (lambda s: _jianqie_on_play(s),)
    after_play = (lambda s: _jianqie_after_play(s),)


def _jianqie_response_cond(s, event, target):
    """妖刀姬被攻击时：攻击方为敌方且被攻击目标是妖刀姬本人。"""
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return False
    attacker = getattr(event, "hero", None)
    if attacker is None or attacker.owner is s.owner:
        return False  # 己方攻击不响应
    return target is hero


def _jianqie_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        clear_combat_immune(hero)  # 去重：避免重复添加
        hero.listeners.append(make_combat_immune_listener())  # 本次战斗免疫战斗伤害


def _jianqie_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        clear_combat_immune(hero)


# ── 2勾 战斗牌 ─────────────────────────────────────────────────────────────

class ZhanYi:
    """战意：本次出击妖刀姬获得+2力量、+2护甲。"""
    id = 166
    type = "attack"
    hero = "YaoDaoJi"
    name = "战意"
    level_req = 2
    buff_atk = 2
    buff_def = 2
    is_beginning_card = True


class YiShan:
    """一闪：不消耗鬼火。"""
    id = 167
    type = "attack"
    hero = "YaoDaoJi"
    name = "一闪"
    level_req = 2
    attributes = (CardAttributes.NO_FIRE_CONSUMPTION,)
    is_beginning_card = True


class JinGuZhiDao:
    """禁锢之刀：增强：本局游戏妖刀姬每消灭一个式神，此牌获得+2力量。"""
    id = 168
    type = "attack"
    hero = "YaoDaoJi"
    name = "禁锢之刀"
    level_req = 2
    buff_atk = 0
    buff_def = 2
    is_beginning_card = True
    on_play = (lambda s: _jinguzhidao_on_play(s),)


def _jinguzhidao_on_play(s):
    kills = s.owner.game.counters.get("yaodaoji_kills", 0)
    s.buff_atk = 2 * kills  # 增强：本局每消灭一个式神 +2力量


# ── 3勾 ────────────────────────────────────────────────────────────────────

class YaoDaoWanHua:
    """妖刀万华：连击（战斗时额外先击中一次）。"""
    id = 169
    type = "morph"
    hero = "YaoDaoJi"
    name = "妖刀万华"
    level_req = 3
    atk = 3
    hp = 8
    is_beginning_card = True
    on_play = (lambda s: _yaodaowanhua_on_play(s),)


def _yaodaowanhua_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    if HeroAttributes.DOUBLE_STRIKE not in hero.attributes:
        hero.attributes.append(HeroAttributes.DOUBLE_STRIKE)  # 连击
    # 形态离场/被替换/随式神气绝时移除连击
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "yaodaowanhua_cleanup"]
    l = Listener("morph leave",
                 lambda e, h: e.event.morph_id == YaoDaoWanHua.id,
                 (_yaodaowanhua_leave,))
    l._tag = "yaodaowanhua_cleanup"
    hero.listeners.append(l)


def _yaodaowanhua_leave(e, h):
    if HeroAttributes.DOUBLE_STRIKE in h.attributes:
        h.attributes.remove(HeroAttributes.DOUBLE_STRIKE)
    h.listeners = [l for l in h.listeners if getattr(l, "_tag", "") != "yaodaowanhua_cleanup"]


class ShaNian:
    """杀念：随机将三张妖刀姬的战斗牌置入手牌。"""
    id = 170
    type = "spell"
    hero = "YaoDaoJi"
    name = "杀念"
    level_req = 3
    is_beginning_card = True
    on_play = (lambda s: _shanian_on_play(s),)


_YJD_BATTLE_CARDS = ("BuXiangZhiRen", "JianQie", "ZhanYi", "YiShan", "JinGuZhiDao")


def _shanian_on_play(s):
    if s.owner is None:
        return
    # 随机三张（允许重复）
    picks = [random_choice(s.owner, list(_YJD_BATTLE_CARDS), context="杀念: 随机选择妖刀姬战斗牌")
             for _ in range(3)]
    s.owner.GiveCardToHand(picks)


class JueXingYaoDaoJi:
    """觉醒·妖刀姬：觉醒：迅捷 当妖刀姬对敌方牌手造成伤害时，她的战斗牌本回合不消耗鬼火。"""
    id = 171
    type = "spell"
    hero = "YaoDaoJi"
    name = "觉醒·妖刀姬"
    level_req = 3
    is_beginning_card = True
    on_play = (lambda s: _juexing_ydj_on_play(s),)


def _juexing_ydj_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    if HeroAttributes.AGILE not in hero.attributes:
        hero.attributes.append(HeroAttributes.AGILE)  # 迅捷
    # 觉醒效果气绝后保留（挂 original_listeners）。
    # 战斗/法术伤害统一走 "damage dealt" 纯通知，合并为单个监听器。
    l1 = Listener("damage dealt",
                  lambda e, h: h.is_alive and _yaodaoji_source_from(e, h),
                  (_yaodaoji_grant_no_fire,))
    l1._tag = "ydj_awaken_no_fire"
    l2 = Listener("begin turn",
                  lambda e, h: e.next_player == h.owner,
                  (_yaodaoji_clear_no_fire,))
    l2._tag = "ydj_awaken_no_fire"
    for tag in ("ydj_awaken_no_fire",):
        hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != tag]
        hero.original_listeners = [x for x in hero.original_listeners if getattr(x, "_tag", "") != tag]
    hero.listeners += [l1, l2]
    hero.original_listeners += [l1, l2]


# ── 协战：刃影鹤唳（妖刀姬×姑获鸟） ──────────────────────────────────────

class RenYingHeLi:
    """刃影鹤唳：选择使用一项：妖刀姬-刃影叠岚；姑获鸟-鹤唳回风。"""
    id = 172
    type = "coop"
    hero = "YaoDaoJi"
    heroes = ["YaoDaoJi", "GuHuoNiao"]
    name = "刃影鹤唳"
    level_req = 2
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (lambda s: _renyingheli_on_play(s),)


def _renyingheli_on_play(s):
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "YaoDaoJi":
        # 妖刀姬-刃影叠岚
        _renyingdielan_on_play(s)
    elif hero.type_name == "GuHuoNiao":
        # 姑获鸟-鹤唳回风：姑获鸟未实现，TODO（待姑获鸟实现后完成）
        pass


class RenYingDieLan:
    """刃影叠岚：觉醒：当妖刀姬对敌方牌手造成伤害时，她的战斗牌本回合获得瞬发及+1力量和+1护甲。
    羁绊：姑获鸟发起一次攻击。"""
    id = 173
    type = "spell"
    hero = "YaoDaoJi"
    name = "刃影叠岚"
    level_req = 2
    is_beginning_card = False
    on_play = (lambda s: _renyingdielan_on_play(s),)


def _renyingdielan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.is_awakened = True
    hero.get_permanent_buff("hp", 1)  # JSON 元数据 buff_hp=1
    # 觉醒效果气绝后保留。
    # 战斗/法术伤害统一走 "damage dealt" 纯通知，合并为单个监听器。
    l1 = Listener("damage dealt",
                  lambda e, h: h.is_alive and _yaodaoji_source_from(e, h),
                  (_yaodaoji_grant_instant_plus,))
    l1._tag = "renyingdielan"
    l2 = Listener("begin turn",
                  lambda e, h: e.next_player == h.owner,
                  (_yaodaoji_clear_instant_plus,))
    l2._tag = "renyingdielan"
    for tag in ("renyingdielan",):
        hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != tag]
        hero.original_listeners = [x for x in hero.original_listeners if getattr(x, "_tag", "") != tag]
    hero.listeners += [l1, l2]
    hero.original_listeners += [l1, l2]
    # 羁绊：姑获鸟发起一次攻击（姑获鸟未实现，TODO）
    gu_huo = next((h for h in s.owner.heroes if h.type_name == "GuHuoNiao"), None)
    if gu_huo is not None and gu_huo.is_alive and gu_huo.level > 0:
        # TODO（需引擎/式神支持）：姑获鸟未实现，无法发起攻击
        pass
