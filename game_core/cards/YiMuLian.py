"""一目连 专属卡牌（cards 203-211）

风符·破 / 风符·护 / 罡风 / 风符·势 / 觉醒·一目连 /
风符·瞬(响应) / 风符·湮 / 风符·龙 / 风韵雅乐

数据来源：cards.json + tmp_cards_json/YiMuLian.json（描述逐字拷贝）。
引擎缺失/语义无法核实的机制一律标注 TODO（需引擎支持，等审批）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


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


def _revive_countdown_reduce(hero, amount: int = 1):
    """气绝倒计时 -X：减少复活倒计时（round_until_alive），存活时无实际效果。"""
    if hero is None or hero.round_until_alive <= 0:
        return
    hero.round_until_alive = max(0, hero.round_until_alive - amount)


def _cards_json():
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_MORPH_NAMES_CACHE = None


def _morph_names(hero_name):
    """cards.json 中指定式神的形态牌 eng_name 列表。"""
    global _MORPH_NAMES_CACHE
    if _MORPH_NAMES_CACHE is None:
        cache = {}
        for c in _cards_json():
            if c["type"] == "morph":
                cache.setdefault(c["hero"], []).append(c["eng_name"])
        _MORPH_NAMES_CACHE = cache
    return _MORPH_NAMES_CACHE.get(hero_name, [])


def _random_morph_to_hand(player, hero_name):
    """随机获得 1 张指定式神的形态牌。"""
    names = _morph_names(hero_name)
    if not names:
        return
    chosen = random_choice(player, names, context=f"随机获得 {hero_name} 形态牌")
    if chosen is not None:
        player.GiveCardToHand([chosen])


_AWAKEN_NAMES_CACHE = None


def _awaken_names(hero_name):
    """cards.json 中指定式神的觉醒牌（eng_name 以 JueXing 开头）列表。"""
    global _AWAKEN_NAMES_CACHE
    if _AWAKEN_NAMES_CACHE is None:
        cache = {}
        for c in _cards_json():
            if c["eng_name"].startswith("JueXing"):
                cache.setdefault(c["hero"], []).append(c["eng_name"])
        _AWAKEN_NAMES_CACHE = cache
    return _AWAKEN_NAMES_CACHE.get(hero_name, [])


def _random_awaken_to_hand(player, hero_name):
    """羁绊：随机获得 1 张指定式神的觉醒牌。"""
    names = _awaken_names(hero_name)
    if not names:
        return
    chosen = random_choice(player, names, context=f"随机获得 {hero_name} 觉醒牌")
    if chosen is not None:
        player.GiveCardToHand([chosen])


def _enemy_characters(player):
    """敌方所有角色：存活式神 + 敌方牌手。"""
    enemies = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
    enemies.append(player.opponent)
    return enemies


# ── 一目连倒计时效果注册表 ──────────────────────────────────────────────────
# key = 形态牌 eng_name；value = 倒计时效果回调（hero -> Event/None）。
# 供「本局游戏生效过的一目连所有倒计时效果」查询（风韵雅乐）。
_YL_COUNTDOWN_EFFECTS = {}


def _record_yl_countdown_used(hero, key):
    """记录某倒计时效果在本局游戏生效过（仅记录，不重复去重）。"""
    game = hero.owner.game
    if not hasattr(game, "_yl_countdown_used"):
        game._yl_countdown_used = set()
    game._yl_countdown_used.add(key)


def _yl_countdown_trigger(hero, key, effect):
    """触发一目连的一个倒计时效果并记录「本局生效过」，结算返回的事件。"""
    _record_yl_countdown_used(hero, key)
    result = effect(hero)
    if result is not None and isinstance(result, Event):
        hero.owner.game.handle_event(result)


def _yl_morph_leave(hero, key, effect, cleanup):
    """形态牌离场/被消灭：觉醒下一目连触发该形态的倒计时效果，随后重置倒计时。"""
    if hero.is_awakened:
        _yl_countdown_trigger(hero, key, effect)
    # 形态离场，倒计时随之失效
    hero.countdown_max = 0
    hero.countdown = 0
    hero.on_countdown = ()
    if cleanup in hero.listeners:
        hero.listeners.remove(cleanup)


def _yl_setup_morph_countdown(hero, cd_max, key, effect):
    """形态牌进入时设置倒计时，并注册离场清理/觉醒触发监听器。

    一个式神身上最多一个倒计时（faq）：换形态/离场时由本监听器复位。
    """
    hero.countdown_max = cd_max
    hero.countdown = cd_max
    hero.on_countdown = (lambda h: _yl_countdown_trigger(h, key, effect),)
    cleanup = Listener("morph leave",
                       (lambda e, h: getattr(e.event, "hero", None) is h),
                       (lambda e, h: _yl_morph_leave(h, key, effect, cleanup),))
    cleanup._tag = "yl_morph_countdown"
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "yl_morph_countdown"]
    hero.listeners.append(cleanup)


def _yl_destroy_morph(hero, reason="destroy"):
    """消灭一目连身上的形态牌：广播 MorphLeaveEvent 后重置身材与倒计时。"""
    old = hero.morphed_id
    if old == 0:
        return
    hero.owner.game.handle_event(MorphLeaveEvent(hero, old, reason))
    hero.morphed_id = 0
    hero.atk = hero.original_atk + hero.perm_buff_atk
    hero.current_max_hp = hero.original_hp + hero.perm_buff_hp
    if hero.hp > hero.current_max_hp:
        hero.hp = hero.current_max_hp
    hero.countdown_max = 0
    hero.countdown = 0
    hero.on_countdown = ()


# ── 倒计时效果 ──────────────────────────────────────────────────────────────

def _fengfupo_countdown(hero):
    """倒计时2：投射：造成3点伤害。"""
    opp = hero.owner.opponent
    return ProjectileEvent(3, hero, [opp.attack_zone])


def _fengfuhu_countdown(hero):
    """倒计时2：你获得5护甲。"""
    hero.owner.defense += 5


def _fengfushi_countdown(hero):
    """倒计时2：鼓舞：获得+3攻击与+3护甲。"""
    hero.owner.inspiration_atk += 3
    hero.owner.inspiration_def += 3


def _fengfuyan_countdown(hero):
    """倒计时2：消灭敌方战斗区的式神。"""
    opp = hero.owner.opponent
    target = opp.attack_zone
    if target is not None and getattr(target, "is_alive", False):
        hero.owner.game._last_damage_source = hero
        target.hp = 0
        target.check_death()


def _fengfulong_countdown(hero):
    """倒计时2：随机对一个敌方角色造成6点伤害，此效果之前每触发过一次，多作用一个目标。

    目标数 = 1 + 之前触发次数（本次不重复计入，先读后增）。
    每个目标均承受 6 点伤害；目标互不相同（不放回随机抽样）。
    """
    player = hero.owner
    game = player.game
    game.counters.ensure("fengfulong_triggers", persistent=True)
    n = game.counters.get("fengfulong_triggers", 0) + 1
    game.counters.inc("fengfulong_triggers")
    enemies = _enemy_characters(player)
    if not enemies:
        return
    targets = random_sample(player, enemies, min(n, len(enemies)), context="风符·龙: 随机目标")
    if targets:
        game.handle_event(DealDamage(6, hero, targets))


# ── 形态牌 ──────────────────────────────────────────────────────────────────

class FengFuPo:
    id = 203
    type = "morph"
    hero = "YiMuLian"
    name = "风符·破"
    level_req = 1
    atk = 3
    hp = 6
    on_play = (lambda s: _fengfupo_on_play(s),)


def _fengfupo_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _yl_setup_morph_countdown(hero, 2, "FengFuPo", _fengfupo_countdown)
    # 觉醒：形态牌进场时触发倒计时效果
    if hero.is_awakened:
        _yl_countdown_trigger(hero, "FengFuPo", _fengfupo_countdown)


class FengFuHu:
    id = 204
    type = "morph"
    hero = "YiMuLian"
    name = "风符·护"
    level_req = 1
    atk = 2
    hp = 7
    on_play = (lambda s: _fengfuhu_on_play(s),)


def _fengfuhu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _yl_setup_morph_countdown(hero, 2, "FengFuHu", _fengfuhu_countdown)
    if hero.is_awakened:
        _yl_countdown_trigger(hero, "FengFuHu", _fengfuhu_countdown)


class GangFeng:
    id = 205
    type = "spell"
    hero = "YiMuLian"
    name = "罡风"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _gangfeng_on_play(s),)


def _gangfeng_on_play(s):
    # 瞬发 消灭一目连上的形态牌，抽两张牌
    hero = s.get_corresponding_hero()
    if hero is not None:
        _yl_destroy_morph(hero, reason="destroy")
    s.owner.draw()
    s.owner.draw()


class FengFuShi:
    id = 206
    type = "morph"
    hero = "YiMuLian"
    name = "风符·势"
    level_req = 2
    atk = 3
    hp = 8
    on_play = (lambda s: _fengfushi_on_play(s),)


def _fengfushi_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _yl_setup_morph_countdown(hero, 2, "FengFuShi", _fengfushi_countdown)
    if hero.is_awakened:
        _yl_countdown_trigger(hero, "FengFuShi", _fengfushi_countdown)


class JueXingYiMuLian:
    id = 207
    type = "spell"
    hero = "YiMuLian"
    name = "觉醒·一目连"
    level_req = 2
    on_play = (lambda s: _juexing_yml_on_play(s),)


def _juexing_yml_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 2)
    hero.is_awakened = True
    # 随机获得一张一目连的形态牌
    _random_morph_to_hand(s.owner, "YiMuLian")
    # 觉醒：一目连的形态牌进场、离场或被消灭时触发倒计时效果。
    # 进场：由各形态 on_play 判断 is_awakened 触发；
    # 离场/被消灭：由各形态注册的 _yl_morph_countdown 监听器判断 is_awakened 触发。
    # 无需额外注册监听器。


class FengFuShun:
    id = 208
    type = "morph"
    hero = "YiMuLian"
    name = "风符·瞬"
    level_req = 2
    atk = 6
    hp = 9
    attributes = (CardAttributes.INSTANT,)
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: s.get_corresponding_hero() is target,)
    on_play = (lambda s: _fengfushun_on_play(s),)


def _fengfushun_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 回合结束时此牌自毁：监听第一个「end turn」广播（出牌回合的结束）。
    # 战斗牌/响应形态：不设置倒计时，仅按 6/9 身材生效一回合。
    tag = "fengfushun_end"
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]
    listener = Listener("end turn",
                        (lambda e, h: h.morphed_id == 208),
                        (lambda e, h: _fengfushun_end(h),))
    listener._tag = tag
    hero.listeners.append(listener)


def _fengfushun_end(hero):
    _yl_destroy_morph(hero, reason="destroy")
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "fengfushun_end"]


class FengFuYan:
    id = 209
    type = "morph"
    hero = "YiMuLian"
    name = "风符·湮"
    level_req = 3
    atk = 4
    hp = 6
    on_play = (lambda s: _fengfuyan_on_play(s),)


def _fengfuyan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _yl_setup_morph_countdown(hero, 2, "FengFuYan", _fengfuyan_countdown)
    if hero.is_awakened:
        _yl_countdown_trigger(hero, "FengFuYan", _fengfuyan_countdown)


class FengFuLong:
    id = 210
    type = "morph"
    hero = "YiMuLian"
    name = "风符·龙"
    level_req = 3
    atk = 5
    hp = 8
    on_play = (lambda s: _fengfulong_on_play(s),)


def _fengfulong_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _yl_setup_morph_countdown(hero, 2, "FengFuLong", _fengfulong_countdown)
    if hero.is_awakened:
        _yl_countdown_trigger(hero, "FengFuLong", _fengfulong_countdown)


class FengYunYaYue:
    """风韵雅乐（战斗牌）：触发本局游戏生效过的一目连所有倒计时效果（每种最多一次）。
    羁绊：随机获得1张妖琴师觉醒牌。"""
    id = 211
    type = "attack"
    hero = "YiMuLian"
    name = "风韵雅乐"
    level_req = 2
    on_play = (lambda s: _fengyunyayue_on_play(s),)


def _fengyunyayue_on_play(s):
    owner = s.owner
    hero = s.get_corresponding_hero()
    used = getattr(owner.game, "_yl_countdown_used", set())
    for key in list(used):
        effect = _YL_COUNTDOWN_EFFECTS.get(key)
        if effect is not None and hero is not None:
            _yl_countdown_trigger(hero, key, effect)
    # 羁绊：随机获得1张妖琴师觉醒牌（妖琴师存活且等级≥1）
    yqs = next((h for h in owner.heroes
                if h.type_name == "YaoQinShi" and h.is_alive and h.level > 0), None)
    if yqs is not None:
        _random_awaken_to_hand(owner, "YaoQinShi")


# ── 注册倒计时效果（供风韵雅乐查询） ───────────────────────────────────────

_YL_COUNTDOWN_EFFECTS.update({
    "FengFuPo": _fengfupo_countdown,
    "FengFuHu": _fengfuhu_countdown,
    "FengFuShi": _fengfushi_countdown,
    "FengFuYan": _fengfuyan_countdown,
    "FengFuLong": _fengfulong_countdown,
})
