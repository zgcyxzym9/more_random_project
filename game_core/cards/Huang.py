"""荒（Huang）专属卡牌

数据来源：tmp_cards_json/Huang.json + Huang.sources.md（游侠/优新/9game/萌娘百科交叉核实）。
数值（勾玉/身材/幻境耐久）与 game_core/cards/cards.json 一致。

实现说明：
- 荒的基础能力（造成战斗伤害时，己方所有幻境+1耐久）在 heroes.py 的荒 base listener 中实现，
  觉醒·荒无需重复注册该效果。
- 星轨的「贯通」由卡牌自行组合溢出伤害（引擎的 projectile 分支不做贯通过量转移）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


def _huang(owner):
    return next((h for h in owner.heroes if h.type_name == "Huang"), None)


# ── 1勾 ────────────────────────────────────────────────────────────────────

class XingGui:
    """星轨：贯通 己方回合开始时，投射：造成等同于它耐久的伤害，然后自毁。"""
    id = 130
    type = "illusion"
    hero = "Huang"
    name = "星轨"
    level_req = 1
    durability = 4
    on_play = (lambda s: _xinggui_on_play(s),)


def _xinggui_on_play(s):
    player = s.owner
    tag = "xinggui-" + str(id(s))

    def cond(e, owner):
        return e.next_player is owner and s in owner.illusion_zone

    def effect(e, owner):
        _xinggui_trigger(owner, s)

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


def _xinggui_trigger(player, card):
    """投射：造成等同耐久的伤害（对敌方战斗区式神或敌方牌手），贯通溢出击中敌方牌手，然后自毁。"""
    game = player.game
    opp = player.opponent
    target = opp.attack_zone
    if target is None:
        target = opp
    if getattr(target, "entity_type", None) == "hero":
        hp_before = target.hp
        defense_before = target.defense
        game.handle_event(ProjectileEvent(card.durability, card, [target]))
        # 贯通：投射伤害减护甲后的实际伤害超出目标生命时，溢出转移给敌方牌手
        actual = card.durability - min(defense_before, card.durability)
        excess = actual - hp_before
        if excess > 0:
            game.handle_event(DealDamage(excess, card, [opp]))
    else:
        game.handle_event(ProjectileEvent(card.durability, card, [target]))
    # 自毁
    if card in player.illusion_zone:
        player.illusion_zone.remove(card)
    game.handle_event(IllusionDestroyedEvent(player, card))


class HuangHai:
    """荒海：瞬发 被消灭时，将此牌回手并失去此能力。"""
    id = 131
    type = "illusion"
    hero = "Huang"
    name = "荒海"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    durability = 1
    on_play = (lambda s: _huanghai_on_play(s),)


def _huanghai_on_play(s):
    if getattr(s, "_huanghai_used", False):
        return  # 已触发过「被消灭时回手」：失去此能力
    player = s.owner
    tag = "huanghai-" + str(id(s))

    def cond(e, owner):
        return getattr(e.event, "card", None) is s

    def effect(e, owner):
        # 引擎的 receive_damage 在广播「幻境消灭」前已把幻境从幻境区移除，
        # 故此处不能以「仍在幻境区」为前置条件，直接处理回手。
        if s in owner.illusion_zone:
            owner.illusion_zone.remove(s)
        owner.hand.append(s)
        owner.sort_hand()
        s._huanghai_used = True  # 失去此能力
        owner.listeners = [l for l in owner.listeners if getattr(l, "_tag", "") != tag]

    l = Listener("illusion destroyed", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


# ── 2勾 ────────────────────────────────────────────────────────────────────

class YuHui:
    """余辉：弃一张幻境牌，然后抽三张牌，使其中的幻境牌本回合获得瞬发。

    TODO（需引擎支持，等审批）：「弃一张幻境牌」需要从手牌中选择一张幻境牌，
    引擎的目标选择机制只作用于式神/牌手（select_target → candidate_targets），
    不支持选择手牌中的卡牌，故本卡暂不实现。
    """
    id = 132
    type = "spell"
    hero = "Huang"
    name = "余辉"
    level_req = 2


class XingYun:
    """星陨：己方回合开始时，随机对一个敌方角色造成2点伤害，重复幻境耐久次，然后自毁。"""
    id = 133
    type = "illusion"
    hero = "Huang"
    name = "星陨"
    level_req = 2
    durability = 4
    on_play = (lambda s: _xingyun_on_play(s),)


def _xingyun_on_play(s):
    player = s.owner
    tag = "xingyun-" + str(id(s))

    def cond(e, owner):
        return e.next_player is owner and s in owner.illusion_zone

    def effect(e, owner):
        _xingyun_trigger(owner, s)

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


def _xingyun_trigger(player, card):
    game = player.game
    opp = player.opponent
    # 重复耐久次，每次随机选择一个敌方角色（存活且已升级的敌方式神 / 敌方牌手）
    for _ in range(card.durability):
        heroes = [h for h in opp.heroes if h.is_alive and h.level > 0]
        candidates = heroes + [opp]
        target = random_choice(player, candidates, context="星陨")
        if target is None:
            continue
        game.handle_event(DealDamage(2, card, [target]))
    # 自毁
    if card in player.illusion_zone:
        player.illusion_zone.remove(card)
    game.handle_event(IllusionDestroyedEvent(player, card))


class XingChenZhiJing:
    """星辰之境：增强：你每有一个幻境，此牌便获得1力量和1生命。"""
    id = 134
    type = "morph"
    hero = "Huang"
    name = "星辰之境"
    level_req = 2
    atk = 5
    hp = 5
    on_play = (lambda s: _xingchen_on_play(s),)


def _xingchen_on_play(s):
    # 增强：每有一个（己方场上）幻境，+1 力量 +1 生命。形态牌自身非幻境，不计入。
    num = len(s.owner.illusion_zone)
    s.atk = 5 + num
    s.hp = 5 + num


class JueXingHuang:
    """觉醒·荒：将一张「荒海」置入手牌。觉醒：每当荒造成战斗伤害时，使己方所有幻境获得1幻境耐久。
    每当你使用幻境牌时，荒获得迅捷。"""
    id = 135
    type = "spell"
    hero = "Huang"
    name = "觉醒·荒"
    level_req = 2
    on_play = (lambda s: _juexinghuang_on_play(s),)


def _juexinghuang_on_play(s):
    player = s.owner
    hero = _huang(player)
    if hero is None:
        return
    # 将一张「荒海」置入手牌
    player.GiveCardToHand(["HuangHai"])
    # 觉醒：永久 +1/+1（觉醒牌数值直接写在 on_play，同其它式神觉醒牌）。
    # 「造成战斗伤害→幻境+1耐久」为荒的基础能力（heroes.py），无需重复注册。
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    # 每当你使用幻境牌时，荒获得迅捷
    tag = "juexinghuang_agi"
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]
    l = Listener("illusion played",
                 lambda e, h: getattr(e.event, "card", None) is not None
                              and getattr(e.event.card, "owner", None) is h.owner,
                 (lambda e, h: _juexinghuang_agi(e, h),))
    l._tag = tag
    hero.listeners.append(l)


def _juexinghuang_agi(e, h):
    if HeroAttributes.AGILE not in h.attributes:
        h.attributes.append(HeroAttributes.AGILE)


class MingYunLuoXuan:
    """命运螺旋：当你使用幻境牌时，使荒发动攻击且免疫本次战斗伤害。"""
    id = 137
    type = "morph"
    hero = "Huang"
    name = "命运螺旋"
    level_req = 3
    atk = 5
    hp = 8
    on_play = (lambda s: _mingyunluoxuan_on_play(s),)


def _mingyunluoxuan_on_play(s):
    hero = _huang(s.owner)
    if hero is None:
        return
    tag = "mingyunluoxuan-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]

    def cond(e, h):
        return (h.is_alive and not h.stunned and h.morphed_id == 137
                and getattr(e.event, "card", None) is not None
                and getattr(e.event.card, "owner", None) is h.owner)

    def effect(e, h):
        # 使荒发动攻击且免疫本次战斗伤害（敌方战斗区式神为空则攻击敌方牌手）
        opp = h.owner.opponent
        target = opp.attack_zone if opp.attack_zone is not None else opp
        clear_combat_immune(h)  # 去重
        h.listeners.append(make_combat_immune_listener())
        h.owner.game.handle_event(HeroAttackEvent(h.owner, h))
        clear_combat_immune(h)

    l = Listener("illusion played", cond, (effect,))
    l._tag = tag
    hero.listeners.append(l)


# ── 3勾 ────────────────────────────────────────────────────────────────────

class YueZhui:
    """月坠：当此牌获得幻境耐久时，效果+2（自毁伤害 10→12→…，用户裁决 (a)）。
    自己回合开始时获得1幻境耐久，然后若幻境耐久≥30则自毁并对所有敌方角色造成
    10点伤害（含效果加成后的数值）。

    耐久增长监听走引擎统一入口 Game.gain_illusion_durability 广播的
    IllusionDurabilityGainEvent（#12）；自身回合开始的 +1 同样计入效果次数。
    """
    id = 136
    type = "illusion"
    hero = "Huang"
    name = "月坠"
    level_req = 3
    durability = 15
    on_play = (lambda s: _yuezhui_on_play(s),)


def _yuezhui_on_play(s):
    player = s.owner
    tag = "yuezhui-" + str(id(s))
    s._yuezhui_bonus = 0   # 每获得1次幻境耐久累计 +2，自毁时结算 10+bonus 伤害

    # 当此牌获得幻境耐久时，效果+2（包括自身回合开始的 +1，用户裁决）
    def gain_cond(e, owner):
        return e.event.card is s and s in owner.illusion_zone

    def gain_effect(e, owner):
        s._yuezhui_bonus += 2

    l_gain = Listener("illusion durability gain", gain_cond, (gain_effect,))
    l_gain._tag = tag
    player.listeners.append(l_gain)

    def cond(e, owner):
        return e.next_player is owner and s in owner.illusion_zone

    def effect(e, owner):
        # 自己回合开始时获得1幻境耐久
        owner.game.gain_illusion_durability(s, 1)
        if s.durability < 30:
            return
        # 耐久≥30：自毁并对所有敌方角色造成伤害（本次触发的 +2 已计入 bonus）
        dmg = 10 + getattr(s, "_yuezhui_bonus", 0)
        if s in owner.illusion_zone:
            owner.illusion_zone.remove(s)
        owner.game.handle_event(IllusionDestroyedEvent(owner, s))
        for h in [x for x in owner.opponent.heroes if x.is_alive and x.level > 0]:
            owner.game.handle_event(DealDamage(dmg, s, [h]))
        owner.game.handle_event(DealDamage(dmg, s, [owner.opponent]))

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)
