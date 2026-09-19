"""座敷童子 专属卡牌

运势（Fortune）机制由 game.Game.roll_fortune 驱动；座敷童子的基础能力
（掷出1重投）与觉醒（失败重投）见 game_core/heroes.py。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _player_zft(player, card):
    """返回 player 自己的座敷童子式神；没有则退回卡牌对应的座敷童子。"""
    for h in player.heroes:
        if h.type_name == "ZuoFuTongZi":
            return h
    return card.get_corresponding_hero()


def _fortune_both(card, threshold: int, on_success):
    """双方牌手各自运势 threshold：成功则对对应牌手执行 on_success(player)。"""
    game = card.owner.game
    for p in (card.owner, card.owner.opponent):
        if game.roll_fortune(_player_zft(p, card), threshold):
            on_success(p)


def _heal_player(p, value: int):
    """牌手恢复生命（不超过当前生命上限）。"""
    p.hp = min(p.current_max_hp, p.hp + value)


# ── 1勾卡牌 ───────────────────────────────────────────────────────────────

class JinYunDaJi:
    """金运大吉：形态 3/6。进场和己方回合开始时，双方牌手「运势4」：抽一张牌。"""
    id = 79
    type = "morph"
    hero = "ZuoFuTongZi"
    name = "金运大吉"
    level_req = 1
    atk = 3
    hp = 6
    on_play = (lambda s: _jinyundaji_on_play(s),)

def _jinyundaji_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 进场：双方牌手运势4 → 抽一张牌
    _fortune_both(s, 4, lambda p: p.draw())
    # 己方回合开始时：双方牌手运势4 → 抽一张牌（形态离场后失效）
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "jinyundaji_begin"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 79,
                 (lambda e, h: _fortune_both(s, 4, lambda p: p.draw()),))
    l._tag = "jinyundaji_begin"
    hero.listeners.append(l)


class WuGuFengRang:
    """五谷丰壤：形态 2/7。进场和己方回合开始时，双方牌手「运势4」：恢复3生命。"""
    id = 80
    type = "morph"
    hero = "ZuoFuTongZi"
    name = "五谷丰壤"
    level_req = 1
    atk = 2
    hp = 7
    on_play = (lambda s: _wugufengrang_on_play(s),)

def _wugufengrang_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 进场：双方牌手运势4 → 恢复3生命
    _fortune_both(s, 4, lambda p: _heal_player(p, 3))
    # 己方回合开始时：双方牌手运势4 → 恢复3生命（形态离场后失效）
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "wugufengrang_begin"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 80,
                 (lambda e, h: _fortune_both(s, 4, lambda p: _heal_player(p, 3)),))
    l._tag = "wugufengrang_begin"
    hero.listeners.append(l)


class FuShouShuangQuan:
    """福寿双全：形态 4/5。增强：座敷童子有形态牌时，此牌获得瞬发且使用时抽一张牌。
    此牌进场或离场时，双方各获得1点鬼火。

    实现说明：增强的「瞬发」以进场时返还刚消耗的1点鬼火近似（需已有1点鬼火才能
    打出，与真·瞬发在 0 鬼火时不可打出的差异见 faq/已知限制）。
    """
    id = 81
    type = "morph"
    hero = "ZuoFuTongZi"
    name = "福寿双全"
    level_req = 1
    atk = 4
    hp = 5
    on_play = (lambda s: _fushoushuangquan_on_play(s),)

def _fushoushuangquan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    owner = s.owner
    # 增强：座敷童子已有形态牌时 → 获得瞬发（返还刚消耗的1点鬼火）且使用时抽一张牌
    if hero.morphed_id != 0:
        owner.fire_cnt += 1
        owner.draw()
    # 进场：双方各获得1点鬼火
    owner.fire_cnt += 1
    owner.opponent.fire_cnt += 1
    # 离场（气绝 / 被其他形态替换）：双方各获得1点鬼火
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "fushou_leave"]
    l_death = Listener("about to die", _fushou_death_cond, (_fushou_leave_give_fire,))
    l_death._tag = "fushou_leave"
    l_play = Listener("play card", _fushou_play_cond, (_fushou_leave_give_fire,), phase="before")
    l_play._tag = "fushou_leave"
    hero.listeners.append(l_death)
    hero.listeners.append(l_play)

def _fushou_death_cond(e, h):
    # 座敷童子仍处于福寿双全形态时气绝
    return getattr(e.event, "hero", None) is h and h.morphed_id == 81

def _fushou_play_cond(e, h):
    # 福寿双全仍生效时打出另一张座敷童子形态牌 → 福寿双全离场
    # （必须监听 "play card" 的 before 阶段：完成（after）广播时新形态已替换完毕，
    # morphed_id != 81 守卫将永远不成立；前置时机与旧版广播时序一致）
    if h.morphed_id != 81:
        return False
    card = getattr(e.event, "card", None)
    if card is None or getattr(card, "type", None) != "morph":
        return False
    return card.get_corresponding_hero() is h

def _fushou_leave_give_fire(e, h):
    h.owner.fire_cnt += 1
    h.owner.opponent.fire_cnt += 1


# ── 2勾卡牌 ───────────────────────────────────────────────────────────────

class JiaNeiAnQuan:
    """家内安全：形态 3/7。每当一个式神攻击后「运势4」：失败则被眩晕。

    运势来源为座敷童子（打出该形态的一方）；攻击在广播点即触发判定，
    被眩晕不中断本次已开始的攻击（等价于「攻击后被眩晕」）。
    """
    id = 82
    type = "morph"
    hero = "ZuoFuTongZi"
    name = "家内安全"
    level_req = 2
    atk = 3
    hp = 7
    on_play = (lambda s: _jianaianquan_on_play(s),)

def _jianaianquan_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "jinai_attack"]
    l = Listener("hero attack", _jinai_cond, (_jinai_trigger,))
    l._tag = "jinai_attack"
    hero.listeners.append(l)

def _jinai_cond(e, s):
    # 仅事件层广播（HeroAttackEvent）：出击/战斗牌各触发一次，step 层广播不重复触发
    return isinstance(e.event, HeroAttackEvent)

def _jinai_trigger(e, s):
    attacker = getattr(e.event, "hero", None)
    if attacker is None or not attacker.is_alive:
        return
    # 每当一个式神攻击后运势4：失败则被眩晕
    if not s.owner.game.roll_fortune(s, 4):
        attacker.stun()


class FuYunChangLong:
    """福运昌隆：抽一张牌。「运势4」：你获得2点鬼火。"""
    id = 83
    type = "spell"
    hero = "ZuoFuTongZi"
    name = "福运昌隆"
    level_req = 2
    on_play = (lambda s: _fuyunchanglong_on_play(s),)

def _fuyunchanglong_on_play(s):
    s.owner.draw()
    hero = s.get_corresponding_hero()
    if hero is not None and s.owner.game.roll_fortune(hero, 4):
        s.owner.fire_cnt += 2


# ── 觉醒 ────────────────────────────────────────────────────────────────────

class JueXingZuoFuTongZi:
    """觉醒·座敷童子：觉醒：每次「运势」判定中，当你「运势」判定失败时，重投一次。

    重投逻辑在 heroes.py 座敷童子基础能力中随 is_awakened 切换；buff_atk/buff_hp
    来自 cards.json（描述性数值，与鸦天狗等觉醒一致）。
    """
    id = 84
    type = "spell"
    hero = "ZuoFuTongZi"
    name = "觉醒·座敷童子"
    level_req = 3
    on_play = (lambda s: _juexing_zft_on_play(s),)

def _juexing_zft_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 3)
    hero.is_awakened = True


# ── 3勾卡牌 ───────────────────────────────────────────────────────────────

class HeQiManMan:
    """和气满满：形态 0/7。每当一个式神攻击时「运势4」：失败则本次战斗力量变为0。

    通过一次性标记 _suppress_combat_damage 令本次战斗攻击力为 0（与不可饶恕同款）。
    """
    id = 85
    type = "morph"
    hero = "ZuoFuTongZi"
    name = "和气满满"
    level_req = 3
    atk = 0
    hp = 7
    on_play = (lambda s: _heqimanman_on_play(s),)

def _heqimanman_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "heqi_attack"]
    l = Listener("hero attack", _heqi_cond, (_heqi_trigger,))
    l._tag = "heqi_attack"
    hero.listeners.append(l)

def _heqi_cond(e, s):
    return isinstance(e.event, HeroAttackEvent)

def _heqi_trigger(e, s):
    attacker = getattr(e.event, "hero", None)
    if attacker is None or not attacker.is_alive:
        return
    # 每当一个式神攻击时运势4：失败则本次战斗力量变为0
    if not s.owner.game.roll_fortune(s, 4):
        attacker._suppress_combat_damage = True


class FuManQianKun:
    """福满乾坤：条件：本局游戏双方「运势」判定成功12次。
    使双方生命变为30，抽手牌直至十张，获得3点鬼火。

    条件用 require_target 空列表门控（同向死而生）：不满足条件时返回 []，
    卡牌不可打出；满足时返回非空列表即可打出（无目标选择）。
    全局运势成功次数由 game.roll_fortune 累计（counters["fortune_success_total"]）。
    """
    id = 86
    type = "spell"
    hero = "ZuoFuTongZi"
    name = "福满乾坤"
    level_req = 3
    require_target = (lambda s: [s.get_corresponding_hero()]
                     if s.owner.game.counters.get("fortune_success_total", 0) >= 12 else [],)
    on_play = (lambda s: _fumanqiankun_on_play(s),)

def _fumanqiankun_on_play(s):
    game = s.owner.game
    for p in (game.player1, game.player2):
        # 使双方生命变为30
        p.hp = 30
        p.current_max_hp = 30
        # 抽手牌直至十张（牌库耗尽则停止）。打出中的这张牌此刻仍在手牌
        # （play_card 先跑 on_play 再移除），结算后离手，因此己方需补抽 1 张
        # 使最终手牌达到 10 张。
        target = 10 + (1 if p is s.owner and s in p.hand.cards else 0)
        while len(p.hand.cards) < target and not p.deck.is_empty():
            p.draw()
    # 获得3点鬼火
    s.owner.fire_cnt += 3


class FuXingGaoZhao:
    """福星高照（协战）：选择使用一项：山兔-幸运兔兔；座敷童子-鸿运当头。"""
    id = 87
    type = "coop"
    hero = "ZuoFuTongZi"
    heroes = ["ZuoFuTongZi", "ShanTu"]
    name = "福星高照"
    level_req = 3
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes
         if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (lambda s: _fuxinggaozhao_on_play(s),)

def _fuxinggaozhao_on_play(s):
    """选择使用一项：山兔-幸运兔兔；座敷童子-鸿运当头。"""
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "ShanTu":
        # 山兔-幸运兔兔：复用幸运兔兔的完整效果（增强/羁绊，s.owner 即打出者）
        from .ShanTu import xingyuntutu_effect
        xingyuntutu_effect(s)
    elif hero.type_name == "ZuoFuTongZi":
        # 座敷童子-鸿运当头
        _hongyundangtou_effect(s.owner, s)


class HongYunDangTou:
    """鸿运当头：生效前运势4：复活己方所有式神；己方所有式神随机使用1张他的专属形态牌。
    羁绊：从牌库抽取1张「这把算我赢」。"""
    id = 88
    type = "spell"
    hero = "ZuoFuTongZi"
    name = "鸿运当头"
    level_req = 3
    on_play = (lambda s: _hongyundangtou_on_play(s),)

def _hongyundangtou_on_play(s):
    _hongyundangtou_effect(s.owner, s)


# ── 鸿运当头实现（含福星高照「座敷童子-鸿运当头」分支）──────────────────────────

_MORPH_CACHE = None

def _hero_morph_names():
    """cards.json 中每位式神专属形态牌的 eng_name 列表（type == "morph"）。"""
    global _MORPH_CACHE
    if _MORPH_CACHE is None:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _MORPH_CACHE = {}
        for c in data:
            if c["type"] == "morph":
                _MORPH_CACHE.setdefault(c["hero"], []).append(c["eng_name"])
    return _MORPH_CACHE


def _random_morph_for_all(owner, card):
    """己方所有存活且已升级的式神各自随机使用1张他的专属形态牌。

    复刻 play_card 的 morph 分支：先跑 on_play（可修改 morph 身材，如萌即正义
    的增强），再按 morph 身材 + 保留加成替换式神身材，最后设置 morphed_id。
    """
    from game_core.card import Card
    game = owner.game
    for h in owner.heroes:
        if not h.is_alive or h.level <= 0 or getattr(h, "is_summoned", False):
            continue
        names = _hero_morph_names().get(h.type_name, [])
        if not names:
            continue
        chosen = random_choice(owner, names, context=f"鸿运当头: {h.name} 随机使用形态牌")
        if chosen is None:
            continue
        morph = Card.GetCard(chosen)
        morph.assign_owner(owner)
        morph.played_by = h  # get_corresponding_hero 返回该式神（非协战牌亦生效）
        if hasattr(morph, "on_play"):
            for cb in morph.on_play:
                result = cb(morph)
                if isinstance(result, Event):
                    game.handle_event(result)
        give_buff_atk = h.atk - h.original_atk - h.perm_buff_atk
        give_buff_hp = h.current_max_hp - h.original_hp - h.perm_buff_hp
        h.atk = morph.atk + h.perm_buff_atk + give_buff_atk
        h.current_max_hp = morph.hp + h.perm_buff_hp + give_buff_hp
        h.hp = h.current_max_hp
        h.morphed_id = morph.id
        if hasattr(morph, "after_play"):
            for cb in morph.after_play:
                result = cb(morph)
                if isinstance(result, Event):
                    game.handle_event(result)


def _draw_card_from_deck(player, eng_name):
    """从牌库抽取指定卡牌（羁绊：鸿运当头抽「这把算我赢」）。"""
    for c in player.deck.cards:
        if getattr(c, "eng_name", None) == eng_name:
            player.game.handle_event(DrawSelectedCardFromDeck(player, c))
            return


def _hongyundangtou_effect(owner, card):
    """鸿运当头效果（独立打出，或经协战牌福星高照选择「座敷童子-鸿运当头」）。

    1. 生效前运势4：复活己方所有式神
    2. 己方所有式神随机使用1张他的专属形态牌
    3. 羁绊：山兔存活时，从牌库抽取1张「这把算我赢」
    """
    game = owner.game
    zft = card.get_corresponding_hero()  # 座敷童子（福星高照分支时为 played_by）
    if zft is not None and game.roll_fortune(zft, 4):
        dead = [h for h in owner.heroes if not h.is_alive]
        if dead:
            game.handle_event(Revive(card, dead))
    _random_morph_for_all(owner, card)
    shantu = [h for h in owner.heroes
              if h.type_name == "ShanTu" and h.is_alive and h.level > 0]
    if shantu:
        _draw_card_from_deck(owner, "ZheBaSuanWoYing")