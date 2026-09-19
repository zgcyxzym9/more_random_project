"""凤凰火 专属卡牌（完整实现：id 154-163）

数据源：cards.json（id/type/level_req/数值/中文名/description）+ tmp_cards_json/FengHuangHuo.sources.md（机制备注）。
规则冲突时以 cards.json 为准。

实现要点：
- 焚羽(157)：形态，非战斗伤害+1，由 _fhh_noncombat_bonus 统一读取（不单独挂监听器）。
- 觉醒·凤凰火(159)：觉醒后己方式神使用法术牌时投射1点伤害；与基础能力投射用 get_corresponding_hero() is not h 去重。
- 炎舞(160)：贯通+投射。引擎的 projectile 分支未处理贯通溢出，故改走 deal damage 分支（临时给凤凰火加 PENETRATE）。
- 出云(161)：形态在场时凤凰火使用法术牌 → 将一张「凤火」置入手牌（morphed_id 守卫防止形态替换后陈旧监听）。
- 涅槃明灯(162)/涅槃业火(163)：共享 _niepanyehuo_apply；青行灯选项卡未实现。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.heroes import _fhh_note_player_damage


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _fhh_noncombat_bonus(hero):
    """焚羽(FenYu, id=157)形态：凤凰火造成的所有非战斗伤害+1。"""
    if hero is None:
        return 0
    return 1 if hero.morphed_id == FenYu.id else 0


def _fhh_noncombat_damage(hero, base):
    """凤凰火非战斗伤害：基础值 + 焚羽加成 + 本回合法术伤害加成（手动结算时统一入口）。

    仅用于 on_play 内手动 handle_event 的场景；返回 DealDamage 时引擎会自动补
    round_buff_spell_damage，本函数不用于那种路径。
    """
    return base + _fhh_noncombat_bonus(hero) + getattr(hero, "round_buff_spell_damage", 0)


def _fhh_awaken_projectile(e, h):
    """觉醒·凤凰火：己方式神使用法术牌时，投射1点伤害（命中牌手计入炎舞增强）。"""
    target = [h.owner.opponent.attack_zone]  # None → 敌方牌手
    _fhh_note_player_damage(h, target)
    h.owner.game.handle_event(ProjectileEvent(1, h, target))


def _fhh_niepan_use(name, hero):
    """涅槃业火自动使用：凤鸣/引燃/瑞翔（各一次、按顺序；不触发基础能力投射）。

    自动使用的法术不广播「play card」，因此凤凰火基础能力/出云/觉醒投射等
    「使用法术牌时」效果不会重复触发（与手牌打出区分）。
    """
    game = hero.owner.game
    opp = hero.owner.opponent
    if name == "FengMing":
        dmg = _fhh_noncombat_damage(hero, 2)
        _fhh_note_player_damage(hero, [opp])
        game.handle_event(DealDamage(dmg, hero, [opp]))
    elif name == "YinRan":
        target = opp.attack_zone if opp.attack_zone is not None and opp.attack_zone.is_alive else opp
        dmg = _fhh_noncombat_damage(hero, 2)
        game.handle_event(DealDamage(dmg, hero, [target]))
        if getattr(target, "entity_type", None) == "hero" and not target.is_alive:
            # 若消灭则再对其牌手造成伤害
            _fhh_note_player_damage(hero, [opp])
            game.handle_event(DealDamage(dmg, hero, [opp]))
        elif getattr(target, "entity_type", None) == "player":
            _fhh_note_player_damage(hero, [target])
    elif name == "RuiXiang":
        targets = [h for h in opp.heroes if h.is_alive and h.level > 0] + [opp]
        dmg = _fhh_noncombat_damage(hero, 1)
        _fhh_note_player_damage(hero, [opp])
        game.handle_event(DealDamage(dmg, hero, targets))


def _niepanyehuo_apply(s, hero):
    """涅槃业火（本回合限定，不可叠加）：其他式神从手牌使用法术时，
    凤凰火按顺序不重复使用凤鸣/引燃/瑞翔。

    从手牌使用 = 「play card」广播（响应牌经 play_card 直调不广播）。
    效果在下一个 begin_turn（敌方回合开始）清除。
    """
    if hero is None:
        return
    order = ["FengMing", "YinRan", "RuiXiang"]
    used = {"FengMing": False, "YinRan": False, "RuiXiang": False}

    def _trigger(e, h):
        card = e.event.card
        if card.owner is not h.owner:
            return
        if card.get_corresponding_hero() is h:
            return  # 凤凰火自己的法术不触发（相同法术只会触发一次由 used 保证）
        if card.card_type != CardType.SPELL:
            return
        for name in order:
            if not used[name]:
                used[name] = True
                _fhh_niepan_use(name, h)
                return

    def _clear(e, h):
        h.listeners = [l for l in h.listeners if getattr(l, "_tag", "") != "fhh_niepan_buff"]
        h.original_listeners = [x for x in h.original_listeners if getattr(x, "_tag", "") != "fhh_niepan_buff"]

    l_trig = Listener("play card", lambda e, h: True, (_trigger,), phase="after")
    l_trig._tag = "fhh_niepan_buff"
    l_clr = Listener("begin turn", lambda e, h: e.next_player != h.owner, (_clear,))
    l_clr._tag = "fhh_niepan_buff"
    # 不可叠加：先移除旧实例再挂新实例
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "fhh_niepan_buff"]
    hero.listeners += [l_trig, l_clr]
    # 羁绊：获得一张「明灯」（TODO：项目中无「明灯」卡牌，待补充后实现）


# ── 1勾 法术 ──────────────────────────────────────────────────────────────

class FengMing:
    """凤鸣：瞬发 对敌方牌手造成2点伤害。"""
    id = 154
    type = "spell"
    hero = "FengHuangHuo"
    name = "凤鸣"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (lambda s: _fengming_on_play(s),)


def _fengming_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    opp = hero.owner.opponent
    _fhh_note_player_damage(hero, [opp])
    hero.owner.game.handle_event(DealDamage(_fhh_noncombat_damage(hero, 2), hero, [opp]))


class RuiXiang:
    """瑞翔：对所有敌方角色造成1点伤害。"""
    id = 155
    type = "spell"
    hero = "FengHuangHuo"
    name = "瑞翔"
    level_req = 1
    is_beginning_card = True
    on_play = (lambda s: _ruixiang_on_play(s),)


def _ruixiang_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    opp = hero.owner.opponent
    targets = [h for h in opp.heroes if h.is_alive and h.level > 0] + [opp]
    _fhh_note_player_damage(hero, [opp])
    hero.owner.game.handle_event(DealDamage(_fhh_noncombat_damage(hero, 1), hero, targets))


class YinRan:
    """引燃：对一个式神造成2点伤害，若消灭则再对它的牌手造成2点伤害。"""
    id = 156
    type = "spell"
    hero = "FengHuangHuo"
    name = "引燃"
    level_req = 1
    is_beginning_card = True
    require_target = (lambda s: [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _yinran_on_play(s),)


def _yinran_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not s.owner.selected_targets:
        return
    target = s.owner.selected_targets[0]
    game = hero.owner.game
    dmg = _fhh_noncombat_damage(hero, 2)
    game.handle_event(DealDamage(dmg, hero, [target]))
    if not target.is_alive:
        opp = hero.owner.opponent
        _fhh_note_player_damage(hero, [opp])
        game.handle_event(DealDamage(dmg, hero, [opp]))


# ── 2勾 ────────────────────────────────────────────────────────────────────

class FenYu:
    """焚羽：凤凰火造成的所有非战斗伤害+1。"""
    id = 157
    type = "morph"
    hero = "FengHuangHuo"
    name = "焚羽"
    level_req = 2
    atk = 4
    hp = 6
    is_beginning_card = True
    # 非战斗伤害+1 由 _fhh_noncombat_bonus 在 morphed_id==157 时统一生效


class FengHuo:
    """凤火：对一个式神造成5点伤害。"""
    id = 158
    type = "spell"
    hero = "FengHuangHuo"
    name = "凤火"
    level_req = 2
    is_beginning_card = True
    require_target = (lambda s: [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _fenghuo_on_play(s),)


def _fenghuo_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not s.owner.selected_targets:
        return
    hero.owner.game.handle_event(DealDamage(_fhh_noncombat_damage(hero, 5), hero, s.owner.selected_targets))


class JueXingFengHuangHuo:
    """觉醒·凤凰火：觉醒：当己方式神使用法术牌时，投射：造成1点伤害。"""
    id = 159
    type = "spell"
    hero = "FengHuangHuo"
    name = "觉醒·凤凰火"
    level_req = 2
    is_beginning_card = True
    on_play = (lambda s: _juexing_fhh_on_play(s),)


def _juexing_fhh_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    # 觉醒效果气绝后保留（挂 original_listeners）
    l = Listener("play card",
                 lambda e, h: h.is_alive and e.event.card.owner == h.owner
                 and e.event.card.card_type == CardType.SPELL
                 and e.event.card.get_corresponding_hero() is not h,
                 (_fhh_awaken_projectile,), phase="after")
    l._tag = "fhh_awaken"
    for tag in ("fhh_awaken",):
        hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != tag]
        hero.original_listeners = [x for x in hero.original_listeners if getattr(x, "_tag", "") != tag]
    hero.listeners += [l]
    hero.original_listeners += [l]


# ── 3勾 ────────────────────────────────────────────────────────────────────

class YanWu:
    """炎舞：贯通 投射：造成5点伤害。增强：本局游戏凤凰火每对敌方牌手造成一次伤害，此牌伤害+1。"""
    id = 160
    type = "spell"
    hero = "FengHuangHuo"
    name = "炎舞"
    level_req = 3
    is_beginning_card = True
    on_play = (lambda s: _yanwu_on_play(s),)


def _yanwu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    game = hero.owner.game
    opp = hero.owner.opponent
    hits = game.counters.get("fhh_player_dmg_hits", 0)
    dmg = _fhh_noncombat_damage(hero, 5 + hits)
    # 贯通：走 deal damage 分支实现溢出（projectile 分支不处理贯通）
    penetrated = False
    if HeroAttributes.PENETRATE not in hero.attributes:
        hero.attributes.append(HeroAttributes.PENETRATE)
        penetrated = True
    target = opp.attack_zone if opp.attack_zone is not None and opp.attack_zone.is_alive else opp
    _fhh_note_player_damage(hero, [target])  # 战斗区为空时直接命中牌手
    game.handle_event(DealDamage(dmg, hero, [target]))
    if penetrated:
        hero.attributes.remove(HeroAttributes.PENETRATE)


class ChuYun:
    """出云：当凤凰火使用法术牌时，将一张「凤火」置入手牌。"""
    id = 161
    type = "morph"
    hero = "FengHuangHuo"
    name = "出云"
    level_req = 3
    atk = 5
    hp = 5
    is_beginning_card = True
    on_play = (lambda s: _chuyun_on_play(s),)


def _chuyun_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 形态在场：凤凰火使用法术牌 → 将一张「凤火」置入手牌
    # morphed_id 守卫：形态被替换/离场后监听器不再生效，避免陈旧触发
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "chuyun_fenghuo"]
    l = Listener("play card",
                 lambda e, h: h.is_alive and h.morphed_id == ChuYun.id
                 and e.event.card.owner == h.owner
                 and e.event.card.card_type == CardType.SPELL
                 and e.event.card.get_corresponding_hero() == h,
                 (_chuyun_give_fenghuo,), phase="after")
    l._tag = "chuyun_fenghuo"
    hero.listeners.append(l)


def _chuyun_give_fenghuo(e, h):
    h.owner.GiveCardToHand(["FengHuo"])


# ── 协战：涅槃明灯（凤凰火×青行灯） ──────────────────────────────────────

class NiePanMingDeng:
    """涅槃明灯：选择使用一项：凤凰火-涅槃业火；青行灯-烛火重燃。"""
    id = 162
    type = "coop"
    hero = "FengHuangHuo"
    heroes = ["FengHuangHuo", "QingXingDeng"]
    name = "涅槃明灯"
    level_req = 2
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (lambda s: _niepanmingdeng_on_play(s),)


def _niepanmingdeng_on_play(s):
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "FengHuangHuo":
        # 凤凰火-涅槃业火
        _niepanyehuo_apply(s, hero)
    elif hero.type_name == "QingXingDeng":
        # 青行灯-烛火重燃：青行灯未实现，TODO（待青行灯实现后完成）
        pass


class NiePanYeHuo:
    """涅槃业火：瞬发 本回合其他式神从手牌使用法术时（相同法术只会触发一次），
    凤凰火按顺序不重复使用凤鸣/引燃/瑞翔（不可叠加）。羁绊：获得一张明灯。"""
    id = 163
    type = "spell"
    hero = "FengHuangHuo"
    name = "涅槃业火"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = False
    on_play = (lambda s: _niepanyehuo_on_play(s),)


def _niepanyehuo_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _niepanyehuo_apply(s, hero)
