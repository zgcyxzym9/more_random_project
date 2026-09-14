"""净琉璃御前 专属卡牌（8 张：id 71-78，对应 cards.json）"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _is_wood_type(hero):
    """检查式神是否为苍叶派系 (wood type)"""
    return hero.type == "wood"


def _other_wood_heroes(hero, player, require_alive=True):
    """返回 player 中除 hero 外所有苍叶(wood)派系式神"""
    result = []
    for h in player.heroes:
        if h is hero:
            continue
        if require_alive and not h.is_alive:
            continue
        if _is_wood_type(h):
            result.append(h)
    return result


def _all_wood(player):
    """检查玩家的所有式神是否都是苍叶派系"""
    return all(_is_wood_type(h) for h in player.heroes)


def _reduce_countdown(hero, amount: int = 1):
    """倒计时 -X：归零时重置并触发 on_countdown（与以津真天/妖琴师模式一致）。"""
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


# ── 1勾卡牌 ───────────────────────────────────────────────────────────────

class WuRan:
    """无染：形态 3/5 迅捷。增强：你每有一个未气绝的其他苍叶式神，此牌便获得1力量。"""
    id = 71
    type = "morph"
    hero = "JingLiuLiYuQian"
    name = "无染"
    level_req = 1
    atk = 3
    hp = 5
    on_play = (lambda s: _wuran_on_play(s),)

def _wuran_on_play(s):
    hero = s.get_corresponding_hero()
    cnt = len(_other_wood_heroes(hero, s.owner))
    s.atk = 3 + cnt
    if HeroAttributes.AGILE not in hero.attributes:
        hero.attributes.append(HeroAttributes.AGILE)


# ── 明澈：在手牌期间，每回合首次运势成功时 +1力量 并随机强化一次 ──
# 强化池：7 个关键字 + 数值项（+1力量 / +1护甲）。跨回合永久叠加，关键字去重。
_MINGCHE_ENHANCE_POOL = (
    HeroAttributes.PENETRATE,      # 贯通
    HeroAttributes.FIRST_STRIKE,   # 先攻
    HeroAttributes.RANGED,         # 远程
    HeroAttributes.DIRECT_ATTACK,  # 直击
    HeroAttributes.LIFESTEAL,      # 吸血
    HeroAttributes.TENACIOUS,      # 不屈
    HeroAttributes.FATAL,          # 必杀
    "atk",                         # +1力量
    "def",                         # +1护甲
)

def _mingche_init(card):
    if not hasattr(card, "_mingche_power"):
        card._mingche_power = 0          # 累计力量（每次强化固定 +1，数值"+1力量"项再 +1）
        card._mingche_def_bonus = 0      # 累计护甲（数值"+1护甲"项）
        card._mingche_keywords = []      # 累计关键字词条（去重）
        card._mingche_enhanced_turn = -1 # 本回合是否已强化（按 game.turn_count 判断）

def _mingche_enhance_cond(e, s):
    """本回合首次运势成功、此牌仍在自己手牌时触发。"""
    if s.owner is None:
        return False
    game = s.owner.game
    if s not in s.owner.hand.cards:
        return False
    if game.current_player is not s.owner:
        return False  # 只在自己的回合强化
    if getattr(s, "_mingche_enhanced_turn", -1) == game.turn_count:
        return False  # 每回合至多强化一次
    src = getattr(e.event, "source_hero", None)
    if src is None or getattr(src, "owner", None) is not s.owner:
        return False
    return True

def _mingche_enhance_trigger(e, s):
    _mingche_init(s)
    game = s.owner.game
    s._mingche_enhanced_turn = game.turn_count
    # 每次强化固定 +1力量
    s._mingche_power += 1
    # 随机强化一次：关键字（去重）或数值（+1力量 / +1护甲）
    pick = _MINGCHE_ENHANCE_POOL[game.rng.randint(0, len(_MINGCHE_ENHANCE_POOL) - 1)]
    if isinstance(pick, HeroAttributes):
        if pick not in s._mingche_keywords:
            s._mingche_keywords.append(pick)
    elif pick == "atk":
        s._mingche_power += 1
    elif pick == "def":
        s._mingche_def_bonus += 1

def _mingche_on_play(s):
    _mingche_init(s)
    s.buff_atk += s._mingche_power
    s.buff_def += s._mingche_def_bonus
    hero = s.get_corresponding_hero()
    added = []
    for kw in s._mingche_keywords:
        if kw not in hero.attributes:
            hero.attributes.append(kw)
            added.append(kw)
    s._mingche_added = added

def _mingche_after_play(s):
    _mingche_init(s)
    hero = s.get_corresponding_hero()
    for kw in getattr(s, "_mingche_added", ()):
        if kw in hero.attributes:
            hero.attributes.remove(kw)

class MingChe:
    """明澈：战斗 +1/+1。增强：每回合你的运势判定成功时，此牌获得+1力量并随机强化一次（在手牌期间累积）。"""
    id = 72
    type = "attack"
    hero = "JingLiuLiYuQian"
    name = "明澈"
    level_req = 1
    buff_atk = 1
    buff_def = 1
    listeners = (Listener("fortune success", _mingche_enhance_cond, (_mingche_enhance_trigger,)),)
    on_play = (lambda s: _mingche_on_play(s),)
    after_play = (lambda s: _mingche_after_play(s),)


class QiShi:
    """启示：对一个式神造成3点伤害。增强：若己方式神都为苍叶派系，此牌获得+1伤害和贯通。"""
    id = 73
    type = "spell"
    hero = "JingLiuLiYuQian"
    name = "启示"
    level_req = 1
    require_target = (lambda s: [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _qishi_on_play(s),)

def _qishi_on_play(s):
    dmg = 3
    source = s.get_corresponding_hero()
    penetrated = False
    if _all_wood(s.owner):
        dmg += 1
        if HeroAttributes.PENETRATE not in source.attributes:
            source.attributes.append(HeroAttributes.PENETRATE)
            penetrated = True
    s.owner.game.handle_event(DealDamage(dmg, source, s.owner.selected_targets))
    if penetrated:
        source.attributes.remove(HeroAttributes.PENETRATE)


# ── 2勾卡牌 ───────────────────────────────────────────────────────────────

def _liuliguangjing_targets(player):
    """力量小于等于2的存活式神（己方或敌方，由使用者选择）。"""
    return [h for h in (player.heroes + player.opponent.heroes)
            if h.is_alive and h.atk <= 2 and h.level > 0]

def _liuliguangjing_apply(player, played=None):
    """驻场期间：己方苍叶式神对牌手造成的伤害 +1（每张琉璃光境叠加一次）。"""
    count = sum(1 for c in player.illusion_zone if getattr(c, "eng_name", "") == "LiuLiGuangJing")
    if played is not None and getattr(played, "eng_name", "") == "LiuLiGuangJing":
        count += 1  # 进场时本卡尚未进入 illusion_zone，需把自身计入
    for h in player.heroes:
        if h.is_alive and h.type == "wood":
            h.round_buff_player_damage = count

def _liuliguangjing_on_play(s):
    player = s.owner
    # 1. 进场：移动一个力量≤2的式神（由使用者选择）
    if player.selected_targets:
        target = player.selected_targets[0]
        if target.state == "attacking":
            target.move_to_standby()
        else:
            target.move_to_battle()
    # 2. 驻场效果立即生效（round_buff 在回合开始被 clear_round_effects 清空，
    #    此后每回合开始时重新挂上，直到幻境被摧毁）
    _liuliguangjing_apply(player, played=s)
    card = s
    l = Listener("begin turn",
                 lambda e, s2: e.next_player == s2 and card in s2.illusion_zone,
                 (lambda e, s2: _liuliguangjing_apply(s2),))
    l._tag = "liuliguangjing"
    player.listeners.append(l)

class LiuLiGuangJing:
    """琉璃光境：幻境 6 耐久。进场时移动一个力量小于等于2的式神。己方苍叶式神对牌手造成的伤害+1。"""
    id = 74
    type = "illusion"
    hero = "JingLiuLiYuQian"
    name = "琉璃光境"
    level_req = 2
    durability = 6
    require_target = (lambda s: _liuliguangjing_targets(s.owner),)
    select_target = (lambda s: select_target(s.owner, _liuliguangjing_targets(s.owner), s),)
    on_play = (lambda s: _liuliguangjing_on_play(s),)


def _shuangsheng_countdown_attack(h):
    """倒计时3：发起攻击，本次攻击获得直击。"""
    if h is None or not h.is_alive:
        return
    if h.morphed_id != 75:
        return  # 已离开双生形态（更换形态 / 复活后）不再发动
    if HeroAttributes.DIRECT_ATTACK not in h.attributes:
        h.attributes.append(HeroAttributes.DIRECT_ATTACK)
    h.owner.game.handle_event(HeroAttackEvent(h.owner, h))
    if HeroAttributes.DIRECT_ATTACK in h.attributes:
        h.attributes.remove(HeroAttributes.DIRECT_ATTACK)

def _shuangsheng_on_play(s):
    hero = s.get_corresponding_hero()
    hero.countdown = 3
    hero.countdown_max = 3
    if _shuangsheng_countdown_attack not in hero.on_countdown:
        hero.on_countdown = hero.on_countdown + (_shuangsheng_countdown_attack,)
    # 每当你运势判定成功时，净琉璃御前倒计时-1
    def _on_fortune(e, s2):
        _reduce_countdown(s2, 1)
    l = Listener("fortune success",
                 lambda e, s2: s2.is_alive and s2.morphed_id == 75
                               and getattr(e.event, "source_hero", None) is not None
                               and e.event.source_hero.owner is s2.owner,
                 (_on_fortune,))
    l._tag = "shuangsheng_fortune"
    # 同名牌重复打出时去重，避免监听器叠加
    hero.listeners = [l2 for l2 in hero.listeners if getattr(l2, "_tag", "") != "shuangsheng_fortune"]
    hero.listeners.append(l)

class ShuangSheng:
    """双生：形态 6/5。倒计时3：发起攻击，本次攻击获得直击。每当你运势判定成功时，净琉璃御前倒计时-1。"""
    id = 75
    type = "morph"
    hero = "JingLiuLiYuQian"
    name = "双生"
    level_req = 2
    atk = 6
    hp = 5
    on_play = (lambda s: _shuangsheng_on_play(s),)


class JueXingJingLiuLiYuQian:
    """觉醒·净琉璃御前：自身与其他苍叶式神永久+1/+1。
    “使用其他苍叶式神的牌时，净琉璃御前本回合+1力量”为式神基础被动（heroes.py），此处不重复实现。"""
    id = 76
    type = "spell"
    hero = "JingLiuLiYuQian"
    name = "觉醒·净琉璃御前"
    level_req = 2
    on_play = (lambda s: _juexing_jllyq_on_play(s),)

def _juexing_jllyq_on_play(s):
    hero = s.get_corresponding_hero()
    # 觉醒：净琉璃御前自身永久 +1/+1，其他苍叶式神永久 +1/+1
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    for h in _other_wood_heroes(hero, s.owner):
        h.get_permanent_buff("atk", 1)
        h.get_permanent_buff("hp", 1)


# ── 3勾卡牌 ───────────────────────────────────────────────────────────────

class AnYu:
    """暗羽：你的所有式神获得直击（永久）。"""
    id = 77
    type = "spell"
    hero = "JingLiuLiYuQian"
    name = "暗羽"
    level_req = 3
    on_play = (lambda s: _anyu_on_play(s),)

def _anyu_on_play(s):
    for h in s.owner.heroes:
        if HeroAttributes.DIRECT_ATTACK not in h.attributes:
            h.attributes.append(HeroAttributes.DIRECT_ATTACK)


class JingLiuLi:
    """净琉璃：战斗牌。使己方所有苍叶派系式神本回合获得免疫战斗伤害，
    然后随机顺序各发动一次攻击（净琉璃御前本人的攻击由战斗牌固有规则承担）。"""
    id = 78
    type = "attack"
    hero = "JingLiuLiYuQian"
    name = "净琉璃"
    level_req = 3
    on_play = (lambda s: _jingliuli_on_play(s),)

def _jingliuli_on_play(s):
    hero = s.get_corresponding_hero()
    player = s.owner
    game = player.game
    # 1. 己方所有苍叶派系式神本回合免疫战斗伤害
    for h in player.heroes:
        if h.type == "wood":
            clear_combat_immune(h)  # 去重
            h.listeners.append(make_combat_immune_listener())
    # 2. 其他存活苍叶式神随机顺序各发动一次攻击
    others = [h for h in player.heroes if h.is_alive and h.type == "wood" and h is not hero]
    game.rng.shuffle(others)
    for h in others:
        # 走标准攻击路径：广播 hero attack 让敌方响应牌可触发
        game.handle_event(HeroAttackEvent(player, h))