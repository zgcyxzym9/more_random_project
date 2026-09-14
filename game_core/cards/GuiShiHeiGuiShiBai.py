"""鬼使黑＆鬼使白（GuiShiHeiGuiShiBai）专属卡牌。

2021《吉运缘结》切换式神：黑/白同一实体，form="Hei"/"Bai" 区分形态。
切换机制（黑死切白、白倒计时回黑、充能/能量等）已由 game_core/heroes.py
的 _gsgb_* 回调实现并验证（experiments/gsgb_smoke.py），本模块只实现卡牌，
使用 heroes._gsgb_switch_form 实现形态切换类效果。

数据来源：game_core/cards/cards.json（id 246-255）+ tmp_cards_json/GuiShiHeiGuiShiBai.json。
form 字段照抄自 cards.json（数据一致用；引擎不消费）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.heroes import _gsgb_switch_form
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _gsgb_hero(s):
    """返回卡牌对应的鬼使黑白式神。"""
    return s.get_corresponding_hero()


def _gsgb_attack(player, hero, card=None):
    """让式神发起一次攻击（卡牌主动攻击，不经过 step/鬼火/出击次数检查）。

    走 handle_event(HeroAttackEvent) 标准攻击路径：广播「hero attack」让敌方响应牌
    （守护等）可触发；复用引擎的移入战斗区 / 目标解析 / 结算 / 响应清理逻辑。
    """
    game = player.game
    if not hero.is_alive:
        return
    game.handle_event(HeroAttackEvent(player, hero, card))


# ═══════════════════════════════════════════════════════════════════════════
#  1勾卡牌
# ═══════════════════════════════════════════════════════════════════════════

# ── 246 冥界之镰（Hei / attack）─────────────────────────────────────────────
def _mingjiezhlian_on_blast(s):
    # 爆能2：获得瞬发。on_blast 由引擎在能量扣除后、鬼火结算前调用（play_card），
    # 瞬发即时生效：本张牌免鬼火并占用本回合瞬发名额（引擎 _consume_fire 读取）。
    if CardAttributes.INSTANT not in s.attributes:
        s.attributes.append(CardAttributes.INSTANT)


def _mingjiezhlian_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    # 穿刺：本次战斗获得
    if HeroAttributes.PIERCING not in hero.attributes:
        hero.attributes.append(HeroAttributes.PIERCING)
        s._piercing_added = True


def _mingjiezhlian_after_play(s):
    hero = _gsgb_hero(s)
    if hero is not None and getattr(s, "_piercing_added", False) \
            and HeroAttributes.PIERCING in hero.attributes:
        hero.attributes.remove(HeroAttributes.PIERCING)


class MingJieZhiLian:
    """冥界之镰：穿刺 爆能2：获得瞬发。"""
    id = 246
    type = "attack"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "冥界之镰"
    level_req = 1
    buff_atk = 1
    buff_def = 1
    attributes = (CardAttributes.BLAST,)
    energy_cost = 2
    on_blast = (lambda s: _mingjiezhlian_on_blast(s),)
    on_play = (lambda s: _mingjiezhlian_on_play(s),)
    after_play = (lambda s: _mingjiezhlian_after_play(s),)


# ── 247 兄弟之忆（Bai / spell）─────────────────────────────────────────────
def _xiongdi_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    # 切换为鬼使黑并使其发起攻击
    _gsgb_switch_form(hero, "Hei", via="active")
    player = s.owner
    clear_combat_immune(hero)  # 去重
    hero.listeners.append(make_combat_immune_listener())  # 本次战斗免疫伤害
    _gsgb_attack(player, hero)
    clear_combat_immune(hero)


class XiongDiZhiYi:
    """兄弟之忆：仅鬼使白可用。切换为鬼使黑并使其发起攻击，本次战斗免疫伤害。

    TODO（form 门控需引擎支持，等审批）：本牌为 Bai 侧卡，仅鬼使白形态可打出。
    当前引擎 can_play_card 无 form 门控，黑形态也可打出本牌（此处不硬编码门控）。
    """
    id = 247
    type = "spell"
    hero = "GuiShiHeiGuiShiBai"
    form = "Bai"
    name = "兄弟之忆"
    level_req = 1
    on_play = (lambda s: _xiongdi_on_play(s),)


# ── 248 活死人（Hei / morph）───────────────────────────────────────────────
def _huosiren_cond(e, s):
    """本形态（morphed_id=248）存活期间，由该式神造成伤害。"""
    return (s.is_alive and s.morphed_id == 248
            and getattr(e.event, "source", None) is s)


def _huosiren_energy(e, s):
    s.counters.inc("energy")
    s.owner.game.handle_event(EnergyGainEvent(s, 1))


def _huosiren_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "huosiren_dmg"]
    # 战斗/法术伤害统一走 "damage dealt" 纯通知，合并为单个监听器
    l = Listener("damage dealt", _huosiren_cond, (_huosiren_energy,))
    l._tag = "huosiren_dmg"
    hero.listeners.append(l)


class HuoSiRen:
    """活死人：造成伤害时获得1能量。"""
    id = 248
    type = "morph"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "活死人"
    level_req = 1
    atk = 3
    hp = 6
    on_play = (lambda s: _huosiren_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════
#  2勾卡牌
# ═══════════════════════════════════════════════════════════════════════════

# ── 249 惩戒（Hei / attack）─────────────────────────────────────────────────
def _chengjie_on_blast(s):
    # 爆能2：获得追猎。on_blast 先于引擎的追猎选目标门（play_card）执行，
    # 打出时可任选一名敌方式神（含准备区）作为本次攻击目标，由玩家提交
    # SelectTarget 选定（多候选）或引擎自动选定（单候选）。
    hero = _gsgb_hero(s)
    if hero is not None and HeroAttributes.HUNTING not in hero.attributes:
        hero.attributes.append(HeroAttributes.HUNTING)
        s._hunting_added = True


def _chengjie_after_play(s):
    hero = _gsgb_hero(s)
    if hero is not None and getattr(s, "_hunting_added", False) \
            and HeroAttributes.HUNTING in hero.attributes:
        hero.attributes.remove(HeroAttributes.HUNTING)


class ChengJie:
    """惩戒：爆能2：获得追猎。"""
    id = 249
    type = "attack"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "惩戒"
    level_req = 2
    buff_atk = 2
    buff_def = 2
    attributes = (CardAttributes.BLAST,)
    energy_cost = 2
    on_blast = (lambda s: _chengjie_on_blast(s),)
    after_play = (lambda s: _chengjie_after_play(s),)


# ── 250 冥界引路人（Hei / spell / 觉醒）────────────────────────────────────
def _gsgb_to_lingluren(card):
    """把一张「冥界引路人」卡原地改为「冥界领路人」（id 254）。

    原地改写字段以保持引用（正在打出的那张也安全：play_card 的 on_play
    迭代已在循环开始捕获原 tuple）。
    """
    card.id = 254
    card.type = "spell"
    card.card_type = get_card_enum("spell")
    card.hero = "GuiShiHeiGuiShiBai"
    card.form = "Bai"
    card.name = "冥界领路人"
    card.eng_name = "MingJieLingLuRen"
    card.level_req = 3
    card.attributes = list(MingJieLingLuRen.attributes)
    card.on_play = MingJieLingLuRen.on_play
    card.after_play = getattr(MingJieLingLuRen, "after_play", ())
    card.buff_atk = 2
    card.buff_hp = 2
    card.is_token = False
    card.energy_cost = 0


def _gsgb_transform_same_name(s):
    """使用后本局游戏内所有「冥界引路人」同名牌改为「冥界领路人」。

    覆盖手牌/牌库/弃牌堆；正在打出的这张也一并原地改写（随后进入弃牌堆）。
    """
    player = s.owner
    for zone in (player.hand.cards, player.deck.cards, player.used_card.cards):
        for c in zone:
            if getattr(c, "eng_name", None) == "MingJieYinLuRen":
                _gsgb_to_lingluren(c)


def _mingjieyinluren_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    # 觉醒标准加成
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    # 觉醒：充能（黑形态已有；标记让充能跨形态保留/气绝拦截耗能降至1），迅捷
    hero._awakened_hei = True
    if HeroAttributes.ENERGY_CHARGE not in hero.attributes:
        hero.attributes.append(HeroAttributes.ENERGY_CHARGE)
    if HeroAttributes.AGILE not in hero.attributes:
        hero.attributes.append(HeroAttributes.AGILE)
    # 使用后本局同名牌改为冥界领路人
    _gsgb_transform_same_name(s)


class MingJieYinLuRen:
    """冥界引路人：觉醒：充能，迅捷。当鬼使黑气绝时，消耗2能量，切换为鬼使白。
    使用后本局游戏内所有同名牌改为「冥界领路人」。

    气绝切换机制本身已由 heroes._gsgb_before_death 实现（基础耗能2）；
    本觉醒标记 _awakened_hei 使切换耗能降至 1 并让充能跨形态保留。
    """
    id = 250
    type = "spell"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "冥界引路人"
    level_req = 2
    buff_atk = 1
    buff_hp = 1
    on_play = (lambda s: _mingjieyinluren_on_play(s),)


# ── 251 无常鬼使（Hei / spell / 响应）──────────────────────────────────────
def _wuchang_response_cond(s, event, target):
    """响应：当鬼使黑被攻击时（敌方攻击且目标是鬼使黑），自动使用。"""
    hero = _gsgb_hero(s)
    if hero is None or not hero.is_alive or hero.form != "Hei":
        return False
    if getattr(event, "hero", None) is None or event.hero.owner is s.owner:
        return False   # 己方出击，不响应
    return (getattr(event, "target", None) is hero
            or event.hero.owner.opponent.attack_zone is hero)


def _wuchang_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    # 切换为鬼使白使其倒计时变为1
    _gsgb_switch_form(hero, "Bai", via="active")
    hero.countdown_max = 1
    hero.countdown = 1
    # 获得+3力量和+1生命（本次战斗）
    hero.round_buff_atk += 3
    hero.current_max_hp += 1
    hero.hp += 1
    # 然后发起攻击
    _gsgb_attack(s.owner, hero)


class WuChangGuiShi:
    """无常鬼使：切换为鬼使白使其倒计时变为1，并获得+3力量和+1生命，然后发起攻击。
    响应：当鬼使黑被攻击时，自动使用。

    TODO（form 门控需引擎支持，等审批）：本牌为 Hei 侧卡，仅鬼使黑形态可打出。
    TODO（响应攻击结算需引擎支持，等审批）：直接 game.attack 发起攻击不广播
    HeroAttackEvent，因此本次攻击不会触发敌方响应牌（如守护）。
    """
    id = 251
    type = "spell"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "无常鬼使"
    level_req = 2
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: _wuchang_response_cond(s, event, target),)
    on_play = (lambda s: _wuchang_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════
#  3勾卡牌
# ═══════════════════════════════════════════════════════════════════════════

# ── 252 索命（Hei / attack）─────────────────────────────────────────────────
def _suoming_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    # 本次战斗每使用过一次此牌，此牌便+1力量与+1护甲（累计使用次数）
    used = hero.counters.get("suoming_used", 0)
    s.buff_atk = getattr(s, "buff_atk", 0) + used
    s.buff_def = getattr(s, "buff_def", 0) + used


def _suoming_after_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    hero.counters.ensure("suoming_used", initial=0, persistent=True)
    hero.counters.inc("suoming_used")
    # 增强：攻击后本局游戏每切换一次便复制使用一次此牌。
    # heroes.py 维护 gsgb_switch_count（只计主动/倒计时切换）供此增强使用。
    # 复制使用的副本带 _suoming_copy 标记，不再递归复制。
    if getattr(s, "_suoming_copy", False):
        return
    switch_count = hero.counters.get("gsgb_switch_count", 0)
    if switch_count <= 0:
        return
    from game_core.card import Card
    game = s.owner.game
    for _ in range(switch_count):
        copy = Card.GetCard("SuoMing")
        copy.assign_owner(s.owner)
        copy._suoming_copy = True
        # 增强的复制使用是效果的一部分，不消耗鬼火（无消耗属性：效果联动打出免费）
        copy.attributes.append(CardAttributes.NO_FIRE_CONSUMPTION)
        game.play_card(s.owner, copy)


class SuoMing:
    """索命：本次战斗每使用过一次此牌，此牌便+1力量与+1护甲。
    增强：攻击后本局游戏每切换回鬼使黑一次，便复制使用一次此牌。

    实现说明：使用次数持久计数器 suoming_used（累计全对局）；增强的「切换次数」
    复用 heroes._gsgb_switch_form 维护的 gsgb_switch_count（每主动/倒计时切换 +1，
    与 heroes.py 注释「供索命每切换一次增强」一致）。
    """
    id = 252
    type = "attack"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "索命"
    level_req = 3
    buff_atk = 0
    buff_def = 0
    on_play = (lambda s: _suoming_on_play(s),)
    after_play = (lambda s: _suoming_after_play(s),)


# ── 253 夺命宣判（Hei / morph）──────────────────────────────────────────────
def _duoming_end_cond(e, s):
    return (s.is_alive and s.morphed_id == 253
            and getattr(e.event, "type", "") == "end turn"
            and s.owner.game.current_player is s.owner)


def _duoming_end_effect(e, s):
    """回合结束时切换为鬼使白，且每有1能量，鬼使白获得1护甲。"""
    energy = s.counters.get("energy", 0)
    _gsgb_switch_form(s, "Bai", via="active")
    s.defense = energy   # 切换后 defense 被 _gsgb_apply_form 清零，需重新授予


def _duoming_leave_effect(e, s):
    """形态离场（气绝拦截 / 被替换 / 白死）时移除本次形态授予的关键词。"""
    if getattr(s, "_duoming_keywords", False):
        for attr in (HeroAttributes.FATAL, HeroAttributes.FIRST_STRIKE):
            if attr in s.attributes:
                s.attributes.remove(attr)
        s._duoming_keywords = False


def _duoming_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    if not getattr(hero, "_duoming_keywords", False):
        for attr in (HeroAttributes.FATAL, HeroAttributes.FIRST_STRIKE):
            if attr not in hero.attributes:
                hero.attributes.append(attr)
        hero._duoming_keywords = True
    # 回合结束切换为白 + 每能量1护甲
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "duoming_end"]
    l_end = Listener("end turn", _duoming_end_cond, (_duoming_end_effect,))
    l_end._tag = "duoming_end"
    hero.listeners.append(l_end)
    # 形态离场清理关键词
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "duoming_leave"]
    l_leave = Listener("morph leave",
                       lambda e, s: getattr(e.event, "hero", None) is s
                                    and getattr(e.event, "morph_id", None) == 253,
                       (_duoming_leave_effect,))
    l_leave._tag = "duoming_leave"
    hero.listeners.append(l_leave)


class DuoMingXuanPan:
    """夺命宣判：瞬发、必杀、先攻。回合结束时切换为鬼使白，且每有1能量，鬼使白获得1护甲。

    TODO（form 门控需引擎支持，等审批）：本牌为 Hei 侧形态卡，仅鬼使黑形态可打出。
    """
    id = 253
    type = "morph"
    hero = "GuiShiHeiGuiShiBai"
    form = "Hei"
    name = "夺命宣判"
    level_req = 3
    atk = 6
    hp = 5
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _duoming_on_play(s),)


# ── 254 冥界领路人（Bai / spell / 觉醒）────────────────────────────────────
def _lingluren_dmg_cond(e, s):
    """每回合一次：鬼使白（白形态存活）受到伤害时。

    "damage dealt" 纯通知的 target 恒为列表（战斗单目标也是 [victim]），
    故统一用 `s in ev.target` 判断，不再区分 deal/combat 两种事件形态。
    """
    if not (s.is_alive and s.form == "Bai"):
        return False
    if s.counters.get("hunshou_used_turn", 0) > 0:
        return False
    ev = e.event
    return s in getattr(ev, "target", ())


def _lingluren_dmg_effect(e, s):
    """自动使用「魂狩」：投射造成等同于鬼使白受到的伤害的等量伤害。"""
    s.counters.ensure("hunshou_used_turn", initial=0, reset_per_turn=True)
    s.counters.set("hunshou_used_turn", 1)
    ev = e.event
    dmg = getattr(ev, "value", 0)
    if dmg <= 0:
        return
    from game_core.card import Card
    player = s.owner
    if len(player.hand.cards) >= 12:
        return
    token = Card.GetCard("HunShou")
    token.assign_owner(player)
    token.hunshou_damage = dmg
    player.hand.append(token)
    player.sort_hand()
    player.game.play_card(player, token)


def _lingluren_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    # 觉醒标准加成
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)
    hero._awakened_bai = True
    # 觉醒：不屈
    if HeroAttributes.TENACIOUS not in hero.attributes:
        hero.attributes.append(HeroAttributes.TENACIOUS)
    # 倒计时1：切换为鬼使黑（当前即白形态时立即生效）
    if hero.form == "Bai":
        hero.countdown_max = 1
        hero.countdown = 1
    # 每回合一次：鬼使白受到伤害时自动使用魂狩（觉醒持久：死亡后仍保留）。
    # 战斗/法术伤害统一走 "damage dealt" 纯通知，合并为单个监听器。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "lingluren_hunshou"]
    hero.original_listeners = [l for l in hero.original_listeners
                               if getattr(l, "_tag", "") != "lingluren_hunshou"]
    l = Listener("damage dealt", _lingluren_dmg_cond, (_lingluren_dmg_effect,))
    l._tag = "lingluren_hunshou"
    hero.listeners.append(l)
    hero.original_listeners.append(l)


class MingJieLingLuRen:
    """冥界领路人：瞬发 觉醒：不屈。倒计时1：切换为鬼使黑。
    每回合一次，当鬼使白受到伤害时，自动使用「魂狩」。

    TODO（form 门控需引擎支持，等审批）：本牌为 Bai 侧卡，仅鬼使白形态可打出。
    TODO（投射/法术伤害路径需引擎支持，等审批）："受到伤害"仅覆盖 deal damage 与
    combat damage 两条广播路径；投射（ProjectileEvent）不广播伤害事件，投射伤害
    不触发魂狩。
    """
    id = 254
    type = "spell"
    hero = "GuiShiHeiGuiShiBai"
    form = "Bai"
    name = "冥界领路人"
    level_req = 3
    buff_atk = 2
    buff_hp = 2
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _lingluren_on_play(s),)


# ── 255 魂狩（Bai / spell / 衍生 Token）────────────────────────────────────
def _hunshou_on_play(s):
    hero = _gsgb_hero(s)
    if hero is None:
        return
    dmg = getattr(s, "hunshou_damage", 0)
    if dmg <= 0:
        return
    # 投射：命中敌方战斗区；战斗区为空时由引擎投射分支改打敌方牌手
    s.owner.game.handle_event(ProjectileEvent(dmg, hero, [s.owner.opponent.attack_zone]))


class HunShou:
    """魂狩：投射：造成等同于鬼使白受到的伤害的等量伤害。

    伤害量由「冥界领路人」在自动使用时写入 hunshou_damage；非自动打出时无上下文，
    按 0 处理。
    """
    id = 255
    type = "spell"
    hero = "GuiShiHeiGuiShiBai"
    form = "Bai"
    name = "魂狩"
    level_req = 1
    # 「冥界领路人」被动自动使用（常在敌方回合），不消耗鬼火
    attributes = (CardAttributes.NO_FIRE_CONSUMPTION,)
    on_play = (lambda s: _hunshou_on_play(s),)
