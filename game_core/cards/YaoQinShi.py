"""妖琴师 专属卡牌（cards 184-193）

觉醒·入阵歌 / 惊弦 / 大合奏 / 觉醒·神乐歌 / 疯魔琴心 / 魔音扰心 /
觉醒·镇魂歌 / 余音 / 风之乐章(协战) / 幻音绝弦

数据来源：cards.json + tmp_cards_json/YaoQinShi.json（描述逐字拷贝）。
引擎缺失/语义无法核实的机制一律标注 TODO（需引擎支持，等审批）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *
from game_core.heroes import _yaoqinshi_countdown


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _countdown_reduce(hero, amount: int = 1):
    """倒计时 -X（妖琴师模式）：扣减 countdown，归零时重置并触发倒计时效果。

    与 heroes.py `_yaoqinshi_awaken` / 以津真天 `_countdown_reduce` 一致：
    一次最多减到 0，溢出不额外结算（faq）。
    """
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


def _revive_countdown_reduce(hero, amount: int = 1):
    """气绝倒计时 -X：减少复活倒计时（round_until_alive），存活时无实际效果。"""
    if hero is None or hero.round_until_alive <= 0:
        return
    hero.round_until_alive = max(0, hero.round_until_alive - amount)


def _enemy_characters(player):
    """敌方所有角色：存活式神 + 敌方牌手。"""
    enemies = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
    enemies.append(player.opponent)
    return enemies


def _cards_json():
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_YL_MORPH_NAMES = None


def _yl_morph_names():
    """cards.json 中一目连（YiMuLian）的形态牌 eng_name 列表。"""
    global _YL_MORPH_NAMES
    if _YL_MORPH_NAMES is None:
        _YL_MORPH_NAMES = [c["eng_name"] for c in _cards_json()
                           if c["hero"] == "YiMuLian" and c["type"] == "morph"]
    return _YL_MORPH_NAMES


def _random_yl_morph_to_hand(player):
    """羁绊：随机获得 1 张一目连形态牌。"""
    names = _yl_morph_names()
    if not names:
        return
    chosen = random_choice(player, names, context="幻音绝弦 羁绊: 随机获得一目连形态牌")
    if chosen is not None:
        player.GiveCardToHand([chosen])


# ── 觉醒倒计时效果 ──────────────────────────────────────────────────────────

def _juexing_ruzhenge_countdown(hero):
    """倒计时3：造成5点伤害，随机分配给所有敌方角色。

    实现取「5 次随机目标各 1 点」的分配方式（随机可重复命中）。
    敌方牌手与存活敌方式神均纳入随机池。
    """
    player = hero.owner
    enemies = _enemy_characters(player)
    if not enemies:
        return
    game = player.game
    for _ in range(5):
        target = random_choice(player, enemies, context="觉醒·入阵歌: 随机分配伤害")
        if target is None:
            continue
        game.handle_event(DealDamage(1, hero, [target]))


def _juexing_shenyuege_countdown(hero):
    """倒计时3：己方其他式神倒计时-1并获得1点力量与1点生命。

    力量/生命加成使用 GiveBuff（式神存活期间保留，气绝后丢失），
    每次倒计时触发都会叠加一次。
    """
    player = hero.owner
    for h in player.heroes:
        if h is hero or not h.is_alive or h.level <= 0:
            continue
        _countdown_reduce(h, 1)
        player.game.handle_event(GiveBuff("atk", 1, hero, [h]))
        player.game.handle_event(GiveBuff("hp", 1, hero, [h]))


def _juexing_zhenhun_countdown(hero):
    """倒计时3：抽一张牌，获得1点鬼火。"""
    hero.owner.draw()
    hero.owner.fire_cnt += 1


def _awaken_on_play(s, buff_atk=0, buff_hp=0, effect=None):
    """觉醒牌通用 on_play：永久加成 + 觉醒标记 + 替换基础倒计时效果。

    妖琴师的「使用觉醒牌倒计时-3」已由 heroes.py `_yaoqinshi_awaken` 实现，
    此处不再重复。
    """
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    if buff_atk:
        hero.get_permanent_buff("atk", buff_atk)
    if buff_hp:
        hero.get_permanent_buff("hp", buff_hp)
    hero.is_awakened = True
    if effect is not None:
        hero.on_countdown = (effect,)


# ── 非觉醒卡牌 ──────────────────────────────────────────────────────────────

class JueXingRuZhenGe:
    id = 184
    type = "spell"
    hero = "YaoQinShi"
    name = "觉醒·入阵歌"
    level_req = 1
    on_play = (lambda s: _awaken_on_play(s, buff_hp=1, effect=_juexing_ruzhenge_countdown),)


class JingXian:
    id = 185
    type = "spell"
    hero = "YaoQinShi"
    name = "惊弦"
    level_req = 1
    require_target = (lambda s: _countdown_targets(s.owner),)
    select_target = (lambda s: select_target(s.owner, _countdown_targets(s.owner), s),)
    on_play = (lambda s: _countdown_reduce(s.owner.selected_targets[0], 2),)


def _countdown_targets(player):
    """惊弦可选目标：双方所有存活且等级≥1 的式神。"""
    return [h for h in player.heroes + player.opponent.heroes if h.is_alive and h.level > 0]


class DaHeZou:
    """大合奏：瞬发 增强：本局游戏妖琴师的基础能力每生效过一种，此牌便具有对应效果。

    口径（用户确认）：
    - 「生效过一种」= 该版本的基础能力倒计时效果本局结算过一次（自然倒计时、
      惊弦/疯魔琴心等倒计时减到 0、觉醒牌「倒计时-3」触发的结算均算）；
    - 打出时按固定顺序重放每种已生效版本的效果：基础治愈 → 觉醒·入阵歌 →
      觉醒·神乐歌 → 觉醒·镇魂歌；
    - 一种都未生效时打出无效果。
    版本记录由 heroes.py 妖琴师的 "countdown" 监听在结算瞬间完成
    （牌手 _yqs_resolved_versions，以结算瞬间 on_countdown[0] 的函数名为版本键，
    随觉醒替换 on_countdown 而变化）。
    卡面的「增强」指效果随游戏进程变化，非关键字-增强机制（无打出条件加成）。
    """
    id = 186
    type = "spell"
    hero = "YaoQinShi"
    name = "大合奏"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _dahezou_on_play(s),)


# 大合奏重放的固定顺序（用户口径：按固定顺序）：基础治愈 → 入阵歌 → 神乐歌 → 镇魂歌。
# 键 = 结算瞬间 on_countdown 首个回调的函数名（heroes.py 妖琴师监听记录）。
_DAHEZOU_VERSIONS = (
    ("_yaoqinshi_countdown", _yaoqinshi_countdown),
    ("_juexing_ruzhenge_countdown", _juexing_ruzhenge_countdown),
    ("_juexing_shenyuege_countdown", _juexing_shenyuege_countdown),
    ("_juexing_zhenhun_countdown", _juexing_zhenhun_countdown),
)


def _dahezou_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    resolved = getattr(s.owner, "_yqs_resolved_versions", ())
    for key, effect in _DAHEZOU_VERSIONS:
        if key in resolved:
            effect(hero)


class JueXingShenYueGe:
    id = 187
    type = "spell"
    hero = "YaoQinShi"
    name = "觉醒·神乐歌"
    level_req = 2
    on_play = (lambda s: _awaken_on_play(s, buff_atk=1, effect=_juexing_shenyuege_countdown),)


class FengMoQinXin:
    id = 188
    type = "spell"
    hero = "YaoQinShi"
    name = "疯魔琴心"
    level_req = 2
    require_target = (lambda s: [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner,
                                             [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],
                                             s),)
    on_play = (lambda s: _fengmoqinxin_on_play(s),)


def _fengmoqinxin_on_play(s):
    target = s.owner.selected_targets[0]
    # 使一个敌方式神的倒计时+2（目标无倒计时则此段无效）
    if target.countdown_max > 0 and target.countdown > 0:
        target.countdown += 2
    # 使妖琴师的倒计时-2
    _countdown_reduce(s.get_corresponding_hero(), 2)


_MOYIN_TAG = "moyinraoxin_active"


def _moyin_negate(act, enemy):
    """让正在使用的牌失效：拦截出牌、补扣费用（仅普通出牌路径）、移出牌堆。

    act 为 "play card" 广播的原始事件：普通出牌是 PlayCard action（手动广播/
    尚未进入 step 或 play_card，扣费未发生），响应牌是 Event（费用已由
    _consume_fire 扣除）。
    """
    card = getattr(act, "card", None)
    if isinstance(act, PlayCard):
        # 手动广播的 PlayCard 事件未经过 play_card，需手动补扣，
        # 使被失效的牌费用（鬼火/瞬发次数）正常消耗。
        enemy.game._consume_fire(enemy, card)
    act.revert = True
    if card is not None:
        enemy.move_card_to_used(card)
    enemy.selected_targets = None


def _moyin_response_cond(e, s):
    """响应门槛：敌方在其自己回合使用牌，且此牌可打出（模拟响应条件）。

    出牌者 == current_player 表示敌方回合的普通出牌；敌方响应牌（出牌者是
    current_player.opponent）不在此响应，交由主动场景（_moyin_active）拦截。
    """
    act = getattr(e, "event", None)
    if act is None:
        return False
    player = s.owner            # 妖琴师牌手
    enemy = player.opponent
    # 出牌者：响应牌广播的 Event 带 player；step 广播的 PlayCard action 无 player，
    # 用正在使用牌的归属者（card.owner）判定。
    actor = getattr(act, "player", None)
    if actor is None:
        actor = getattr(getattr(act, "card", None), "owner", None)
    if actor is not enemy:
        return False
    if actor is not player.game.current_player:
        return False
    can_play, _ = player.game.can_play_card(player, s)
    return can_play


def _moyin_response(e, s):
    """响应打出：模拟响应（消耗妖琴师鬼火）并康掉敌方正在使用的牌。"""
    player = s.owner
    enemy = player.opponent
    player.game._consume_fire(player, s)   # 响应费用：与引擎统一实现一致
    player.move_card_to_used(s)          # 响应牌使用后进弃牌堆
    act = getattr(e, "event", None)
    if act is not None:
        _moyin_negate(act, enemy)


def _moyin_active_on_play(s):
    """主动打出：本回合敌方使用的下一张牌失效（己方回合敌方只会出响应牌）。"""
    player = s.owner
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != _MOYIN_TAG]
    l_neg = Listener("play card", _moyin_active_cond, (_moyin_active_negate,))
    l_neg._tag = _MOYIN_TAG
    l_clean = Listener("begin turn",
                       lambda e, p: e.next_player is p.opponent,
                       (_moyin_active_cleanup,))
    l_clean._tag = _MOYIN_TAG
    player.listeners += [l_neg, l_clean]


def _moyin_active_cond(e, p):
    """主动场景：敌方在己方回合使用牌（只可能是敌方响应牌）。"""
    act = getattr(e, "event", None)
    if act is None:
        return False
    actor = getattr(act, "player", None)
    if actor is None:
        actor = getattr(getattr(act, "card", None), "owner", None)
    return actor is p.opponent


def _moyin_active_negate(e, p):
    _moyin_negate(getattr(e, "event", None), p.opponent)
    _moyin_active_cleanup(e, p)   # 一次性：康掉一张后即失效


def _moyin_active_cleanup(e, p):
    p.listeners = [l for l in p.listeners if getattr(l, "_tag", "") != _MOYIN_TAG]


class MoYinRaoXin:
    """魔音扰心：响应——当敌方牌手将使用牌时，自动使用；效果——敌方牌手本回合使用的下一张牌不会生效。

    纯卡牌层实现（引擎仅在 _play_response_card 补了「响应牌出牌」的 "play card" 广播）：
    - 响应场景（敌方回合、此牌在手牌）：手牌自携监听器拦截敌方本回合使用的牌，
      自动消耗此牌（模拟响应打出）并使敌方正在使用的牌失效。
    - 主动场景（己方回合打出）：on_play 挂一次性监听器，使敌方在己方回合使用的牌
      （实际只会是敌方响应牌）失效；己方回合结束（敌方回合 begin turn）时清空。
    被失效的牌费用（鬼火/瞬发次数）正常消耗，牌进弃牌堆。
    """
    id = 189
    type = "spell"
    hero = "YaoQinShi"
    name = "魔音扰心"
    level_req = 2
    on_play = (lambda s: _moyin_active_on_play(s),)
    # 手牌自携响应监听器（不走引擎 _auto_response：以监听器模拟响应门槛）
    listeners = (Listener("play card", _moyin_response_cond, (_moyin_response,)),)


class JueXingZhenHunGe:
    id = 190
    type = "spell"
    hero = "YaoQinShi"
    name = "觉醒·镇魂歌"
    level_req = 3
    on_play = (lambda s: _awaken_on_play(s, buff_atk=1, buff_hp=1, effect=_juexing_zhenhun_countdown),)


class YuYin:
    id = 191
    type = "spell"
    hero = "YaoQinShi"
    name = "余音"
    level_req = 3
    on_play = (lambda s: _yuyin_on_play(s),)


def _yuyin_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 使妖琴师的倒计时-3
    _countdown_reduce(hero, 3)
    # 使己方其他未气绝式神的倒计时-1（仅存活式神）
    for h in s.owner.heroes:
        if h is hero or not h.is_alive:
            continue
        _countdown_reduce(h, 1)


# ── 协战：风之乐章 ──────────────────────────────────────────────────────────

class FengZhiYueZhang:
    """风之乐章（协战牌）：选择使用一项——一目连·风韵雅乐 / 妖琴师·幻音绝弦。"""
    id = 192
    type = "coop"
    hero = "YaoQinShi"
    heroes = ["YaoQinShi", "YiMuLian"]
    name = "风之乐章"
    level_req = 2
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes
         if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (lambda s: _fengzhiyuezhang_on_play(s),)


def _fengzhiyuezhang_on_play(s):
    # 协战：由 play_card 依据 selected_targets 设置 played_by
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "YiMuLian":
        # 风韵雅乐（战斗牌）：协战仅结算其效果部分（触发一目连本局生效过的倒计时效果），
        # 引擎不支持协战牌附带战斗，因此不产生攻击。
        _run_option_card(s, "FengYunYaYue")
    else:
        # 幻音绝弦
        _run_option_card(s, "HuanYinJueXian")


def _run_option_card(s, eng_name):
    """用 Card.GetCard 取选项牌，仅执行其 on_play（复用效果函数，避免跨模块导入）。"""
    from game_core.card import Card
    card = Card.GetCard(eng_name)
    card.assign_owner(s.owner)
    for callback in card.on_play:
        result = callback(card)
        if isinstance(result, Event):
            s.owner.game.handle_event(result)


class HuanYinJueXian:
    id = 193
    type = "spell"
    hero = "YaoQinShi"
    name = "幻音绝弦"
    level_req = 2
    on_play = (lambda s: _huanyinjuexian_on_play(s),)


def _huanyinjuexian_on_play(s):
    player = s.owner
    # 下一个己方回合开始时：所有己方式神倒计时-1；已气绝式神改为气绝倒计时-2
    tag = "huanyinjuexian"
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]
    listener = Listener("begin turn",
                        (lambda e, p: e.next_player == p),
                        (lambda e, p: _huanyinjuexian_trigger(p),))
    listener._tag = tag
    player.listeners.append(listener)
    # 羁绊：随机获得 1 张一目连形态牌（一目连存活且等级≥1）
    yml = next((h for h in player.heroes
                if h.type_name == "YiMuLian" and h.is_alive and h.level > 0), None)
    if yml is not None:
        _random_yl_morph_to_hand(player)


def _huanyinjuexian_trigger(player):
    for h in player.heroes:
        if h.is_alive:
            _countdown_reduce(h, 1)
        else:
            _revive_countdown_reduce(h, 2)
    # 一次性监听器：结算后移除
    player.listeners = [l for l in player.listeners
                        if getattr(l, "_tag", "") != "huanyinjuexian"]
