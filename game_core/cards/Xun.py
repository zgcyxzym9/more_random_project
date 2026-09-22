"""薰 专属卡牌（cards 220-229）

温柔的守护 / 决意 / 干扰投掷 / 鸮之利爪 / 鸮之警惕 /
觉醒·薰 / 祈愿之翼 / 鸮之庇佑 / 鸮羽共鸣(协战) / 鸮鸣(幻境)

数据来源：cards.json + tmp_cards_json/Xun.json（描述逐字拷贝）。
引擎缺失/语义无法核实的机制一律标注 TODO（需引擎支持，等审批）。
"""
import sys
import os
import json
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


def _enemy_heroes(player):
    """敌方存活且已升级的式神（无帷幕）。"""
    return [h for h in player.opponent.heroes
            if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes]


def _guarded_hero(player):
    """当前结附「鸮之守护」的己方式神（同一时间唯一）。"""
    for h in player.heroes:
        if h.counters.get("hawk_protection", 0) > 0:
            return h
    return None


def _attach_guard(player, target):
    """结附「鸮之守护」。

    祈愿之翼后：失去唯一但效果不能叠加——结附时改为使己方全体式神结附。
    """
    if getattr(player, "_qyzy_all_guard", False):
        for h in player.heroes:
            if h.is_alive:
                h.counters.set("hawk_protection", 1)
        return
    for h in player.heroes:
        if h.counters.get("hawk_protection", 0) > 0:
            h.counters.set("hawk_protection", 0)
    target.counters.set("hawk_protection", 1)


# ── 形态牌随机入手（祈愿之翼用） ────────────────────────────────────────────

def _cards_json():
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
    """随机获得 1 张指定式神的形态牌。

    祈愿之翼「选择一张薰的形态牌置入手牌」：引擎无「选一张卡入手」交互，
    以随机近似（与一目连·觉醒一致）。
    """
    names = _morph_names(hero_name)
    if not names:
        return
    chosen = random_choice(player, names, context=f"随机获得 {hero_name} 形态牌")
    if chosen is not None:
        player.GiveCardToHand([chosen])


# ── 1勾卡牌 ─────────────────────────────────────────────────────────────────

class WenRouDeShouHu:
    """温柔的守护：瞬发 使一个己方式神结附「鸮之守护」。抽一张牌。"""
    id = 220
    type = "spell"
    hero = "Xun"
    name = "温柔的守护"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner,
                                             [h for h in s.owner.heroes if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _wenrou_on_play(s),)


def _wenrou_on_play(s):
    player = s.owner
    target = player.selected_targets[0]
    _attach_guard(player, target)
    player.game.handle_event(DrawEvent(player, 1))


class JueYi:
    """决意：己方回合开始时，使你结附「鸮之守护」的式神获得1生命。"""
    id = 221
    type = "morph"
    hero = "Xun"
    name = "决意"
    level_req = 1
    atk = 2
    hp = 4
    on_play = (lambda s: _jueyi_on_play(s),)


def _jueyi_on_play(s):
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "jueyi"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 221,
                 (lambda e, h: _jueyi_trigger(h),))
    l._tag = "jueyi"
    hero.listeners.append(l)


def _jueyi_trigger(h):
    bearer = _guarded_hero(h.owner)
    if bearer is not None and bearer.is_alive:
        h.owner.game.handle_event(GiveBuff("hp", 1, h, [bearer]))


def _ganrao_cond(e, s):
    attacker = getattr(e.event, "hero", None)
    if attacker is None or attacker.owner is not s.owner.opponent:
        return False
    if not attacker.is_alive:
        return False
    target = getattr(e.event, "target", None)
    if target is None:
        target = s.owner.attack_zone
    if target is None:
        return False
    return target.owner is s.owner and target.counters.get("hawk_protection", 0) > 0


def _ganrao_response(e, s):
    """旧式响应：敌方回合、攻击守护式神时自动打出（每次攻击至多一次）。"""
    owner = s.owner
    if owner.game.current_player is not owner.opponent:
        return
    can_play, _ = owner.game.can_play_card(owner, s)
    if not can_play:
        return
    attacker = e.event.hero
    owner.selected_targets = [attacker]
    owner.game.play_card(owner, s)   # 鬼火由 play_card 内部统一扣除


class GanRaoTouZhi:
    """干扰投掷：对一个式神造成1点伤害并使其本回合不能对结附「鸮之守护」的式神造成伤害。
    响应：当敌方式神攻击你结附「鸮之守护」的式神时，自动对其使用。"""
    id = 222
    type = "spell"
    hero = "Xun"
    name = "干扰投掷"
    level_req = 1
    attributes = (CardAttributes.RESPONSE,)
    require_target = (lambda s: _enemy_heroes(s.owner),)
    select_target = (lambda s: select_target(s.owner, _enemy_heroes(s.owner), s),)
    listeners = (Listener("hero attack", _ganrao_cond, (_ganrao_response,)),)
    on_play = (lambda s: _ganrao_on_play(s),)


def _ganrao_on_play(s):
    player = s.owner
    target = player.selected_targets[0]
    player.game.handle_event(DealDamage(1, s, [target]))
    target.counters.ensure("ganrao_block_guarded", initial=0, reset_per_turn=True)
    target.counters.set("ganrao_block_guarded", 1)
    _install_ganrao_block(player)


# ── 干扰投掷的「不能造成伤害」压制监听 ──────────────────────────────────────
# 由 _ganrao_on_play 惰性安装在牌手身上（一次安装，按被标记的敌方式神过滤）。

def _install_ganrao_block(player):
    if getattr(player, "_ganrao_block_installed", False):
        return
    player._ganrao_block_installed = True
    l = Listener("hero attack", _ganrao_block_cond, (_ganrao_block_trigger,))
    l._tag = "ganrao_block"
    player.listeners.append(l)


def _ganrao_block_cond(e, p):
    attacker = getattr(e.event, "hero", None)
    if attacker is None or attacker.owner is not p.opponent:
        return False
    if attacker.counters.get("ganrao_block_guarded", 0) <= 0:
        return False
    target = getattr(e.event, "target", None)
    if target is None:
        target = p.attack_zone
    if target is None:
        return False
    return target.owner is p and target.counters.get("hawk_protection", 0) > 0


def _ganrao_block_trigger(e, p):
    # 一次性标记：本次攻击不造成战斗伤害（attack() 结算时消费）
    e.event.hero._suppress_combat_damage = True


# ── 2勾卡牌 ─────────────────────────────────────────────────────────────────

class XiaoZhiLiZhao:
    """鸮之利爪：结附「鸮之守护」的己方式神获得2力量。"""
    id = 223
    type = "morph"
    hero = "Xun"
    name = "鸮之利爪"
    level_req = 2
    atk = 3
    hp = 6
    on_play = (lambda s: _lizhao_on_play(s),)


def _lizhao_on_play(s):
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "lizhao"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 223,
                 (lambda e, h: _lizhao_reapply(h),))
    l._tag = "lizhao"
    hero.listeners.append(l)
    _lizhao_reapply(hero)


def _lizhao_reapply(h):
    """重算鸮之利爪的 +2 力量：守护随回合转移时，从旧宿主移除、加到新宿主。"""
    player = h.owner
    for hero in list(player.heroes):
        if getattr(hero, "_lizhao_bonus", False):
            if hero.is_alive:
                hero.atk -= 2
            hero._lizhao_bonus = False
    bearer = _guarded_hero(player)
    if bearer is not None and bearer.is_alive:
        bearer.atk += 2
        bearer._lizhao_bonus = True


class XiaoZhiJingTi:
    """鸮之警惕：结附「鸮之守护」的己方式神获得帷幕。"""
    id = 224
    type = "morph"
    hero = "Xun"
    name = "鸮之警惕"
    level_req = 2
    atk = 4
    hp = 5
    on_play = (lambda s: _jingti_on_play(s),)


def _jingti_on_play(s):
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "jingti"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 224,
                 (lambda e, h: _jingti_reapply(h),))
    l._tag = "jingti"
    hero.listeners.append(l)
    _jingti_reapply(hero)


def _jingti_reapply(h):
    """重算鸮之警惕的帷幕：守护转移时，移除旧宿主上的（本牌附加的）帷幕、加到新宿主。"""
    player = h.owner
    for hero in list(player.heroes):
        if getattr(hero, "_jingti_veil", False):
            if HeroAttributes.VEIL in hero.attributes:
                hero.attributes.remove(HeroAttributes.VEIL)
            hero._jingti_veil = False
    bearer = _guarded_hero(player)
    if bearer is not None and bearer.is_alive:
        if HeroAttributes.VEIL not in bearer.attributes:
            bearer.attributes.append(HeroAttributes.VEIL)
        bearer._jingti_veil = True


class JueXingXun:
    """觉醒·薰：觉醒：当你的式神攻击时，使其结附「鸮之守护」。"""
    id = 225
    type = "spell"
    hero = "Xun"
    name = "觉醒·薰"
    level_req = 2
    on_play = (lambda s: _juexingxun_on_play(s),)


def _juexingxun_on_play(s):
    hero = s.get_corresponding_hero()
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    player = s.owner
    # 觉醒：当你的式神攻击时，使其结附「鸮之守护」。
    # 挂在牌手上（觉醒是永久能力，不随式神气绝重置）。
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != "xun_awaken"]
    l = Listener("hero attack",
                 lambda e, p: getattr(e.event, "hero", None) is not None and e.event.hero.owner is p,
                 (lambda e, p: _attach_guard(p, e.event.hero),))
    l._tag = "xun_awaken"
    player.listeners.append(l)


# ── 3勾卡牌 ─────────────────────────────────────────────────────────────────

class QiYuanZhiYi:
    """祈愿之翼：瞬发 选择一张薰的形态牌置入手牌。「鸮之守护」失去唯一但效果不能叠加。
    本局游戏中当己方式神结附「鸮之守护」时，改为使己方全体式神结附。"""
    id = 226
    type = "spell"
    hero = "Xun"
    name = "祈愿之翼"
    level_req = 3
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _qyzy_on_play(s),)


def _qyzy_on_play(s):
    player = s.owner
    hero = s.get_corresponding_hero()
    # 选择一张薰的形态牌置入手牌（以随机近似）
    _random_morph_to_hand(player, "Xun")
    player._qyzy_all_guard = True
    # 「本局游戏中当己方式神结附鸮之守护时，改为使己方全体式神结附」：
    # 基础能力（薰）在对方回合开始广播时清空旧守护、结附到本回合最后攻击者。
    # 把扩散监听挂在薰身上并排在基础能力之后，同一广播中先执行基础能力、后扩散到全体。
    # 注意：薰气绝时 hero.listeners 被重置为 original_listeners，扩散监听随之丢失——
    # 此时基础能力也不再触发（其条件含 s.is_alive），整体行为仍一致；唯觉醒·薰等
    # 挂牌手的效果在薰死亡期间附加守护时不会扩散（极端情形，记录在案）。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "qyzy_spread"]
    l = Listener("begin turn",
                 lambda e, h: (h.is_alive and getattr(h.owner, "_qyzy_all_guard", False)
                               and e.next_player != h.owner),
                 (lambda e, h: _qyzy_spread(h.owner),))
    l._tag = "qyzy_spread"
    hero.listeners.append(l)


def _qyzy_spread(player):
    for h in player.heroes:
        if h.is_alive:
            h.counters.set("hawk_protection", 1)


class XiaoZhiBiYou:
    """鸮之庇佑：使一个己方式神结附「鸮之守护」。结附「鸮之守护」的己方式神获得不屈。"""
    id = 227
    type = "morph"
    hero = "Xun"
    name = "鸮之庇佑"
    level_req = 3
    atk = 5
    hp = 8
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner,
                                             [h for h in s.owner.heroes if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _biyou_on_play(s),)


def _biyou_on_play(s):
    player = s.owner
    target = player.selected_targets[0]
    _attach_guard(player, target)
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "biyou"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 227,
                 (lambda e, h: _biyou_reapply(h),))
    l._tag = "biyou"
    hero.listeners.append(l)
    _biyou_reapply(hero)


def _biyou_reapply(h):
    """重算鸮之庇佑的不屈：守护转移时，移除旧宿主上的（本牌附加的）不屈、加到新宿主。"""
    player = h.owner
    for hero in list(player.heroes):
        if getattr(hero, "_biyou_tenacious", False):
            if HeroAttributes.TENACIOUS in hero.attributes:
                hero.attributes.remove(HeroAttributes.TENACIOUS)
            hero._biyou_tenacious = False
    bearer = _guarded_hero(player)
    if bearer is not None and bearer.is_alive:
        if HeroAttributes.TENACIOUS not in bearer.attributes:
            bearer.attributes.append(HeroAttributes.TENACIOUS)
        bearer._biyou_tenacious = True


class XiaoYuGongMing:
    """鸮羽共鸣（协战·薰×山风）：选择使用一项：山风-庇羽；薰-鸮鸣。

    山风（ShanFeng）未实现：协战牌的英雄选择列表仍按 heroes 声明，
    运行时只会选中薰（山风不在场），庇羽分支代码防御式保留。
    """
    id = 228
    type = "coop"
    hero = "Xun"
    heroes = ("Xun", "ShanFeng")
    name = "鸮羽共鸣"
    level_req = 1
    require_target = (lambda s: [h for h in s.owner.heroes
                                 if h.type_name in ("Xun", "ShanFeng") and h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner,
                                             [h for h in s.owner.heroes
                                              if h.type_name in ("Xun", "ShanFeng")
                                              and h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _xiaoyugongming_on_play(s),)


def _xiaoyugongming_on_play(s):
    player = s.owner
    played = s.get_corresponding_hero()
    if played is None:
        return
    if played.type_name == "ShanFeng":
        # 庇羽：山风结附「鸮之守护」并永久+1攻击（山风未实现，防御式保留）
        _attach_guard(player, played)
        played.get_permanent_buff("atk", 1)
    else:
        # 鸮鸣：己方所有式神倒计时-1
        for h in player.heroes:
            if h.is_alive and h.countdown_max > 0:
                _countdown_reduce(h, 1)


class XiaoMing:
    """鸮鸣（幻境，仅衍生牌）：每当己方具「鸮之守护」的式神发起攻击时，
    该式神获得+1力量直到回合结束；若是本回合第2次触发则抽1张牌。
    羁绊：进场时山风倒计时-2。"""
    id = 229
    type = "illusion"
    hero = "Xun"
    name = "鸮鸣"
    level_req = 1
    duration = 5
    is_beginning_card = False
    on_play = (lambda s: _xiaoming_on_play(s),)


def _xiaoming_on_play(s):
    player = s.owner
    # 羁绊：进场时山风倒计时-2（山风未实现：防御式查找，找不到则无效果）
    sf = next((h for h in player.heroes if h.type_name == "ShanFeng"), None)
    if sf is not None:
        _countdown_reduce(sf, 2)
    # 幻境区不参与 broadcast 的实体迭代，挂在牌手上；离开幻境区即失效。
    state = {"turn": None, "count": 0}

    def _cond(e, p):
        if s not in p.illusion_zone:
            return False
        attacker = getattr(e.event, "hero", None)
        if attacker is None or attacker.owner is not p:
            return False
        return attacker.counters.get("hawk_protection", 0) > 0

    def _trigger(e, p):
        # 一次攻击会广播两次 hero attack（step + handle_event），按事件对象去重
        tset = getattr(e.event, "_xiaoming_triggers", None)
        if tset is None:
            tset = set()
            e.event._xiaoming_triggers = tset
        key = id(s)
        if key in tset:
            return
        tset.add(key)
        turn = getattr(p.game, "turn_count", 0)
        if state["turn"] != turn:
            state["turn"] = turn
            state["count"] = 0
        state["count"] += 1
        attacker = e.event.hero
        attacker.round_buff_atk += 1
        if state["count"] == 2:
            p.game.handle_event(DrawEvent(p, 1))

    tag = f"xiaoming_{id(s)}"
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]
    l = Listener("hero attack", _cond, (_trigger,))
    l._tag = tag
    player.listeners.append(l)
