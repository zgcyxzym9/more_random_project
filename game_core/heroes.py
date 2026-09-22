from .enums import *
from .manager import Listener
from .action import *
from .event import *
from .selector import *
from .damage_immunity import clear_combat_immune

# ═══════════════════════════════════════════════════════════════════════════════
#  1. 纸人武士 (ZhiRenWuShi)
# ═══════════════════════════════════════════════════════════════════════════════
class ZhiRenWuShi:
    id = 1
    name = "纸人武士"
    atk = 3
    hp = 4
    type = "fire"


# ═══════════════════════════════════════════════════════════════════════════════
#  2. 天邪鬼团伙 (TianXieGuiTuanHuo)
# ═══════════════════════════════════════════════════════════════════════════════
class TianXieGuiTuanHuo:
    id = 2
    name = "天邪鬼团伙"
    atk = 2
    hp = 5
    type = "wind"


# ═══════════════════════════════════════════════════════════════════════════════
#  3. 犬神 (QuanShen)
# ═══════════════════════════════════════════════════════════════════════════════
def _xinshenlianmo_on_upgrade(hero, attr):
    """心身炼磨升级效果：为所有区域的 心身炼磨 卡牌追加属性。

    追加而非替换，保留卡牌已有的其他属性（如瞬发、无消耗叠加时互不丢失）；
    遍历 手牌/牌库/已使用 三个区域，避免升级时卡牌不在手牌导致漏改。
    """
    for zone in (hero.owner.hand.cards, hero.owner.deck.cards, hero.owner.used_card):
        for c in zone:
            if c.id == 17 and attr not in c.attributes:
                c.attributes.append(attr)


class QuanShen:
    id = 3
    name = "犬神"
    atk = 2
    hp = 5
    type = "fire"
    on_upgrade = (lambda s: s.owner.GiveCardToHand(["XinShenLianMo"]),)
    counter = {"xin_shen_lian_mo": 0}


# ═══════════════════════════════════════════════════════════════════════════════
#  4. 桃花妖 (TaoHuaYao)
# ═══════════════════════════════════════════════════════════════════════════════
def _taohuayao_heal_condition(e, s):
    """桃花妖被动触发条件：目标是己方式神，且治疗/复活来源是桃花妖自身。"""
    return (s.is_alive
            and any(t in s.owner.heroes for t in e.event.target)
            and (e.event.source.get_corresponding_hero() == s
                 if type(e.event.source).__name__ == "Card" else e.event.source == s))


def _create_taohuayao_listeners():
    """桃花妖被动：治疗或复活己方式神时，给目标 +1 攻击力。

    加 _tag 标记，供 觉醒·桃花妖 (#25) 识别并替换为觉醒版被动。
    """
    l1 = Listener("heal", _taohuayao_heal_condition,
                  (lambda e, s: GiveBuff("atk", 1, s, [t for t in e.event.target if t in s.owner.heroes]),))
    l2 = Listener("after revive", _taohuayao_heal_condition,
                  (lambda e, s: GiveBuff("atk", 1, s, [t for t in e.event.target if t in s.owner.heroes]),))
    l1._tag = 'taohuayao_passive'
    l2._tag = 'taohuayao_passive'
    return (l1, l2)


class TaoHuaYao:
    id = 4
    name = "桃花妖"
    atk = 1
    hp = 6
    type = "fire"
    listeners = _create_taohuayao_listeners()
    on_death = (lambda s: [c.attributes.remove(CardAttributes.INSTANT) for c in s.owner.hand.cards + s.owner.deck.cards if c.id == 24 and CardAttributes.INSTANT in c.attributes],)
    on_revive = (lambda s: [c.attributes.append(CardAttributes.INSTANT) for c in s.owner.hand.cards + s.owner.deck.cards if c.id == 24 and CardAttributes.INSTANT not in c.attributes],)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. 不知火 (BuZhiHuo)
# ═══════════════════════════════════════════════════════════════════════════════
class BuZhiHuo:
    id = 5
    name = "不知火"
    atk = 2
    hp = 4
    type = "fire"
    listeners = (Listener("begin turn",
                          lambda e, s: s.is_alive and e.next_player == s.owner,
                          (lambda e, s: setattr(s.owner, "inspiration_atk", s.owner.inspiration_atk + 1),),),)


def _jinranbuye_special_attack(hero):
    """烬染不夜的特殊攻击：对两个随机敌方角色造成 (自身攻击力 + 鼓舞攻击力) 的伤害。

    在 game.step 出击路径中由 special_attack 回调调用，替代正常战斗流程。
    鼓舞生效数值已由出击路径经 InspireEvent 广播并转移到 hero.inspiration_atk
    （觉醒·不知火的「鼓舞效果额外+1/+1」等监听器在广播时统一加成），此处直接
    读取。鼓舞护盾不用于特殊攻击（既有行为，维持不变）。
    """
    player = hero.owner
    game = player.game
    opp = player.opponent
    targets = [h for h in opp.heroes if h.is_alive and h.level > 0]
    if opp.state != PlayerState.LOST:
        targets.append(opp)
    from game_core.selector import random_sample
    chosen = random_sample(player, targets, min(2, len(targets)),
                           context="烬染不夜: 随机选择两个敌方角色")
    dmg = hero.atk + hero.inspiration_atk
    game.handle_event(DealDamage(dmg, hero, chosen))


# ═══════════════════════════════════════════════════════════════════════════════
#  5.5 烬染不夜 (JinRanBuYe) — 不知火 星火之歌 的召唤物
# ═══════════════════════════════════════════════════════════════════════════════
class JinRanBuYe:
    id = 200
    name = "烬染不夜"
    atk = 2
    hp = 2
    type = "fire"
    base_attributes = (HeroAttributes.AGILE,)
    special_attack = _jinranbuye_special_attack


# ═══════════════════════════════════════════════════════════════════════════════
#  6. 火取魔 (HuoQuMo)
#  被动：每回合当你使用第二张红莲派系式神的牌时，火取魔获得1力量和1生命。
# ═══════════════════════════════════════════════════════════════════════════════
def _huoqumo_fire_card_cond(e, s):
    # 计数与火取魔死活无关：气绝期间打出的红莲牌同样计入
    hero = e.event.card.get_corresponding_hero()
    return (s.owner == e.event.card.owner
            and hero is not None and hero.type == "fire")

def _huoqumo_fire_card_effect(e, s):
    # persistent：check_death 的 reset_all 不清零，气绝不影响本回合计数；
    # reset_per_turn：begin_turn 对双方式神统一重置，即“每回合”一次机会
    s.counters.ensure("huoqumo_fire_cards", initial=0,
                      persistent=True, reset_per_turn=True)
    s.counters.inc("huoqumo_fire_cards", 1)
    if s.counters.get("huoqumo_fire_cards") == 2 and s.is_alive:
        s.owner.game.handle_event(GiveBuff("atk", 1, s, [s]))
        s.owner.game.handle_event(GiveBuff("hp", 1, s, [s]))

class HuoQuMo:
    id = 6
    name = "火取魔"
    atk = 2
    hp = 5
    type = "fire"
    # "play card" 监听器一律 phase="after"（完成广播）——历史语义即读结算后的
    # 战场状态，全项目统一（见 manager.Listener 与 PlayCardEvent 的说明）
    listeners = (Listener("play card", _huoqumo_fire_card_cond,
                          (_huoqumo_fire_card_effect,), phase="after"),)


# ═══════════════════════════════════════════════════════════════════════════════
#  7. 九命猫 (JiuMingMao) — 苍叶派系
#  基础能力：气绝时结附一个「九命」并立即复活。
#  当结附 ≥5 个「九命」时，永久气绝，移除所有专属牌（除「向死而生」外）。
# ═══════════════════════════════════════════════════════════════════════════════
def _jiumingmao_on_death(s):
    """九命猫死亡时：增加九命层数，若 <5 则复活，否则永久死亡。"""
    s.counters.ensure("jiu_ming", initial=0, persistent=True)
    s.counters.inc("jiu_ming", 1)
    jm = s.counters.get("jiu_ming")
    if jm >= 5:
        # 永久死亡
        from .event import PermanentDeathEvent
        s.owner.game.handle_event(PermanentDeathEvent(s))
    else:
        # 立即复活
        s.revive()


class JiuMingMao:
    id = 7
    name = "九命猫"
    atk = 3
    hp = 2
    type = "wood"
    on_death = (_jiumingmao_on_death,)
    counter = {}


# ═══════════════════════════════════════════════════════════════════════════════
#  8. 以津真天 (YiJinZhenTian) — 苍叶派系
#  基础能力：倒计时2，将一张「黄金羽」置入手牌。
#  觉醒：倒计时1，黄金羽可以以敌方式神为目标。
# ═══════════════════════════════════════════════════════════════════════════════
def _yijinzhentian_countdown(s):
    """倒计时归零：生成黄金羽。"""
    from .card import Card
    token = Card.GetCard("HuangJinYu")
    token.assign_owner(s.owner)
    if len(s.owner.hand.cards) < 12:
        s.owner.hand.append(token)
        s.owner.sort_hand()


class YiJinZhenTian:
    id = 8
    name = "以津真天"
    atk = 2
    hp = 5
    type = "wood"
    countdown = 2
    countdown_max = 2
    on_countdown = (_yijinzhentian_countdown,)


# ═══════════════════════════════════════════════════════════════════════════════
#  9. 鸦天狗 (YaTianGou) — 苍叶派系
#  基础能力：鸦天狗移动时，投射造成1点伤害。
# ═══════════════════════════════════════════════════════════════════════════════
def _yatianGou_on_move(s, from_zone, to_zone):
    """移动时投射1点伤害给敌方战斗区式神。"""
    # 记录本回合移动次数（供正义必胜等增强读取；每回合自动重置）
    s.counters.ensure("move_this_turn", initial=0, reset_per_turn=True)
    s.counters.inc("move_this_turn")
    opp = s.owner.opponent
    if opp.attack_zone is not None and opp.attack_zone.is_alive:
        s.owner.game.handle_event(ProjectileEvent(1, s, [opp.attack_zone]))


class YaTianGou:
    id = 9
    name = "鸦天狗"
    atk = 1
    hp = 6
    type = "wood"
    on_move = (_yatianGou_on_move,)


# ═══════════════════════════════════════════════════════════════════════════════
#  10. 净琉璃御前 (JingLiuLiYuQian) — 苍叶派系
#  基础能力：使用其他苍叶式神的牌时，本回合+1攻击。
# ═══════════════════════════════════════════════════════════════════════════════
def _jingliuliyuqian_on_wood_card(e, s):
    if e.event.card.owner != s.owner:
        return
    corr = e.event.card.get_corresponding_hero()
    if corr is not None and corr is not s and corr.type == "wood":
        s.round_buff_atk += 1


class JingLiuLiYuQian:
    id = 10
    name = "净琉璃御前"
    atk = 2
    hp = 5
    type = "wood"
    listeners = (Listener("play card",
                          lambda e, s: s.is_alive
                                       and e.event.card.owner == s.owner
                                       and e.event.card.get_corresponding_hero() is not None
                                       and e.event.card.get_corresponding_hero() != s
                                       and e.event.card.get_corresponding_hero().type == "wood",
                          (_jingliuliyuqian_on_wood_card,), phase="after"),)


# ═══════════════════════════════════════════════════════════════════════════════
#  11. 座敷童子 (ZuoFuTongZi) — 苍叶派系
#  每次运势判定中，当骰子点数为1时，重投一次。
# ═══════════════════════════════════════════════════════════════════════════════
def _zuofutongzi_reroll(e, s):
    # 重投一次：修改 event.result，roll_fortune 会读取修改后的结果
    e.event.result = s.owner.game.rng.randint(1, 6)


def _zuofutongzi_cond(e, s):
    # 基础能力：掷出 1 时重投；觉醒（觉醒·座敷童子）后：运势判定失败时重投
    if not s.is_alive or e.event.source_hero.owner != s.owner:
        return False
    if s.is_awakened:
        return e.event.result < e.event.threshold
    return e.event.result == 1


class ZuoFuTongZi:
    id = 11
    name = "座敷童子"
    atk = 2
    hp = 5
    type = "wood"
    listeners = (Listener("fortune roll",
                          _zuofutongzi_cond,
                          (_zuofutongzi_reroll,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  12. 妖狐 (YaoHu) — 苍叶派系
#  基础能力：当妖狐使用法术牌时，运势4：随机对一个敌方角色造成2点伤害。
#  觉醒（觉醒·妖狐）：使用法术牌或运势判定成功时，随机对一个敌方角色造成基础伤害。
#  聚气可永久提升基础能力伤害；狂风刃卷的增强读取本局妖狐造成伤害的次数。
# ═══════════════════════════════════════════════════════════════════════════════
def _yaohu_basic_damage(hero) -> int:
    """妖狐基础能力伤害：默认 2，聚气永久 +1（可在气绝/复活后保留）。"""
    hero.counters.ensure("yaohu_basic_damage", initial=2, persistent=True)
    return hero.counters.get("yaohu_basic_damage", 2)


def _yaohu_boost_basic_damage(hero):
    """聚气：妖狐的基础能力造成的伤害永久 +1。"""
    hero.counters.ensure("yaohu_basic_damage", initial=2, persistent=True)
    hero.counters.inc("yaohu_basic_damage")


def _yaohu_enemy_characters(hero):
    """敌方角色候选：存活且已升级的敌方式神 + 敌方牌手。"""
    opp = hero.owner.opponent
    candidates = [h for h in opp.heroes if h.is_alive and h.level > 0]
    candidates.append(opp)
    return candidates


def _yaohu_deal_random_damage(hero):
    """随机对一个敌方角色造成基础能力伤害。"""
    target = select_random_target(hero.owner, _yaohu_enemy_characters(hero), context="妖狐: 运势随机伤害")
    if target is None:
        return
    hero.owner.game.handle_event(DealDamage(_yaohu_basic_damage(hero), hero, [target]))


def _yaohu_spell(e, s):
    """基础能力：妖狐使用法术牌时，运势4 成功后随机对一个敌方角色造成伤害。"""
    if s.is_alive and s.owner.game.roll_fortune(s, 4):
        _yaohu_deal_random_damage(s)


def _yaohu_awaken_spell(e, s):
    """觉醒·妖狐：使用法术牌时，直接随机对一个敌方角色造成基础伤害（无需运势）。"""
    if s.is_alive:
        _yaohu_deal_random_damage(s)


def _yaohu_awaken_fortune(e, s):
    """觉醒·妖狐：运势判定成功时，随机对一个敌方角色造成基础伤害。"""
    if s.is_alive:
        _yaohu_deal_random_damage(s)


def _yaohu_damage_track(e, s):
    """累计妖狐本局造成伤害的次数（狂风刃卷「妖狐造成过2次伤害」增强条件）。"""
    src = getattr(e.event, "source", None)
    if src is None:
        return
    hero = src.get_corresponding_hero() if hasattr(src, "get_corresponding_hero") else src
    if hero is s and s.is_alive:
        s.counters.ensure("yaohu_damage_dealt", initial=0, persistent=True)
        s.counters.inc("yaohu_damage_dealt")


def _yaohu_spell_listener():
    l = Listener("play card",
                 lambda e, s: s.is_alive and e.event.card.owner == s.owner and e.event.card.card_type == CardType.SPELL,
                 (_yaohu_spell,), phase="after")
    l._tag = "yaohu_spell"
    return l


def _yaohu_damage_track_listener():
    """妖狐造成伤害时计数（狂风刃卷增强）。

    三条伤害通道统一走 "damage dealt" 结算后纯通知：法术/能力、战斗
    （含先攻/连击/反击）、投射（旧实现投射无事件、漏计数，现已补齐）。
    """
    l = Listener("damage dealt",
                 lambda e, s: s.is_alive,
                 (_yaohu_damage_track,))
    l._tag = "yaohu_damage_track"
    return l


def _yaohu_awaken_listeners():
    """觉醒·妖狐的监听器集合：使用法术牌 / 运势判定成功 均触发基础伤害。"""
    l1 = Listener("play card",
                  lambda e, s: s.is_alive and e.event.card.owner == s.owner and e.event.card.card_type == CardType.SPELL,
                  (_yaohu_awaken_spell,), phase="after")
    l1._tag = "yaohu_awaken"
    l2 = Listener("fortune success",
                  lambda e, s: s.is_alive and getattr(e.event, "source_hero", None) is not None
                               and e.event.source_hero.owner is s.owner,
                  (_yaohu_awaken_fortune,))
    l2._tag = "yaohu_awaken"
    return (l1, l2)


class YaoHu:
    id = 12
    name = "妖狐"
    atk = 2
    hp = 4
    type = "wood"
    listeners = (_yaohu_spell_listener(),
                 _yaohu_damage_track_listener())


# ═══════════════════════════════════════════════════════════════════════════════
#  13. 青蛙瓷器 (QingWaCiQi) — 苍叶派系
#  基础能力：在你运势判定成功过的回合，青蛙瓷器本回合获得2力量。
#  觉醒·青蛙瓷器：觉醒后你运势判定成功后效果触发两次（被动变为 +4 力量）。
#  九莲宝灯增强：追踪本玩家投出的不重复骰子点数（qw_distinct_mask 持久计数器）。
# ═══════════════════════════════════════════════════════════════════════════════
def _qingwaciqi_fortune(e, s):
    s.round_buff_atk += 2


def _qingwaciqi_awakened_fortune(e, s):
    # 觉醒后：运势判定成功的效果触发两次（+2 力量执行两次）
    s.round_buff_atk += 4


def _qingwaciqi_fortune_listener(double: bool = False):
    """基础/觉醒版运势成功监听器。觉醒版将「+2 力量」执行两次（+4）。"""
    cb = _qingwaciqi_awakened_fortune if double else _qingwaciqi_fortune
    l = Listener("fortune success",
                 lambda e, s: s.is_alive and e.event.source_hero.owner == s.owner,
                 (cb,))
    l._tag = "qwc_fortune"
    return l


def _qingwaciqi_awaken_listener():
    """觉醒·青蛙瓷器替换基础被动时使用。"""
    return _qingwaciqi_fortune_listener(double=True)


def _qingwaciqi_track_roll(e, s):
    """九莲宝灯增强：记录本局游戏本玩家投出的不重复骰子点数（1-6 位掩码）。

    持久计数器（persistent=True）→ 气绝/复活不清零；不要求 is_alive，
    气绝期间的掷骰也计入「本局游戏」。
    """
    s.counters.ensure("qw_distinct_mask", initial=0, persistent=True, max_val=63)
    mask = s.counters.get("qw_distinct_mask", 0)
    s.counters.set("qw_distinct_mask", mask | (1 << (e.event.result - 1)))


class QingWaCiQi:
    id = 13
    name = "青蛙瓷器"
    atk = 2
    hp = 6
    type = "wood"
    listeners = (
        _qingwaciqi_fortune_listener(),
        Listener("fortune roll",
                 lambda e, s: e.event.source_hero.owner == s.owner,
                 (_qingwaciqi_track_roll,)),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  14. 山兔 (ShanTu) — 苍叶派系
#  基础能力：己方回合开始时，运势6：其他己方式神的倒计时-1（含气绝倒计时）并获得1攻击力。
# ═══════════════════════════════════════════════════════════════════════════════
def _shantu_begin_turn(e, s):
    # 觉醒替换基础能力（wiki「关键字-觉醒」）：觉醒·山兔的觉醒效果接管，基础能力不再触发
    if getattr(s, "is_awakened", False):
        return
    if not s.owner.game.roll_fortune(s, 6):
        return
    others = [h for h in s.owner.heroes if h is not s]
    alive = [h for h in others if h.is_alive]
    if alive:
        s.owner.game.handle_event(GiveBuff("atk", 1, s, alive))
    for h in others:
        if not h.is_alive:
            # 气绝倒计时加速：归零立即复活
            if h.round_until_alive > 0:
                h.round_until_alive -= 1
                if h.round_until_alive <= 0:
                    h.revive()
            continue
        if h.countdown > 0:
            h.countdown -= 1
            if h.countdown <= 0 and h.countdown_max > 0:
                h.countdown = h.countdown_max
                from .event import CountdownEvent
                s.owner.game.handle_event(CountdownEvent(h))
                for cb in h.on_countdown:
                    result = cb(h)
                    if isinstance(result, Event):
                        s.owner.game.handle_event(result)


def _shantu_count_six(e, s):
    """6点计数：山兔「本局游戏你骰子每投出一次6点」类增强的计数基础。

    计入己方所有式神的最终掷骰结果（含座敷童子），存于山兔持久计数器
    （气绝/死亡不重置）。监听 "fortune success" 而非 "fortune roll"：
    前者携带最终结果，天然规避监听器顺序问题（萌即正义强制6 /
    座敷童子重投会修改 roll 的 result）。
    """
    s.counters.ensure("sixes_rolled", persistent=True)
    s.counters.inc("sixes_rolled")


class ShanTu:
    id = 14
    name = "山兔"
    atk = 3
    hp = 4
    type = "wood"
    listeners = (Listener("begin turn",
                          lambda e, s: s.is_alive and e.next_player == s.owner,
                          (_shantu_begin_turn,)),
                 Listener("fortune success",
                          lambda e, s: e.event.source_hero.owner is s.owner and e.event.result == 6,
                          (_shantu_count_six,)),)


def _shantu_count_six(e, s):
    """6点计数：山兔「本局游戏你骰子每投出一次6点」类增强的计数基础。

    计入己方所有式神的最终掷骰结果（含座敷童子），存于山兔持久计数器
    （气绝/死亡不重置）。监听 "fortune success" 而非 "fortune roll"：
    前者携带最终结果，天然规避监听器顺序问题（萌即正义强制6 /
    座敷童子重投会修改 roll 的 result）。
    """
    s.counters.ensure("sixes_rolled", persistent=True)
    s.counters.inc("sixes_rolled")


# ═══════════════════════════════════════════════════════════════════════════════
#  15. 辉夜姬 (HuiYeJi) — 青岚派系
#  基础能力：幻境叠加。辉夜姬只能持有一个辉夜姬幻境，
#  新的辉夜姬幻境入场时替换旧的，并把旧幻境的耐久叠加到新幻境上。
#  觉醒后：旧幻境的能力随耐久一起叠加到新幻境上（HuiYeJi.py 的 _hyj_active 判定）。
# ═══════════════════════════════════════════════════════════════════════════════
def _hyj_track_summoned(player, card):
    """记录本局已召唤的辉夜姬幻境种类（觉醒·辉夜姬增强条件：五种不同幻境）。"""
    names = getattr(player, "_hyj_summoned", None)
    if names is None:
        names = set()
        player._hyj_summoned = names
    names.add(card.eng_name)


def _huiyeji_illusion_merge(e, s):
    card = e.event.card
    zone = s.owner.illusion_zone
    # 记录本局已召唤的辉夜姬幻境种类
    _hyj_track_summoned(s.owner, card)
    # 旧辉夜姬幻境（新入场卡自己除外）：耐久叠加到新幻境上并移除
    old_hyj = [ill for ill in zone if ill is not card and getattr(ill, "hero", None) == "HuiYeJi"]
    for old in old_hyj:
        # 耐久叠加走统一入口（#12：增长广播 IllusionDurabilityGainEvent）
        s.owner.game.gain_illusion_durability(card, max(0, old.durability))
        # 觉醒后：旧幻境的能力叠加到新幻境上（新幻境吸收旧幻境及其已吸收的）
        if s.is_awakened:
            absorbed = getattr(card, "absorbed", None)
            if absorbed is None:
                absorbed = []
                card.absorbed = absorbed
            absorbed.append(old)
            absorbed.extend(getattr(old, "absorbed", []))
        zone.remove(old)


class HuiYeJi:
    id = 15
    name = "辉夜姬"
    atk = 1
    hp = 5
    type = "wind"
    listeners = (Listener("illusion played",
                          lambda e, s: s.is_alive and e.event.player == s.owner and getattr(e.event.card, "hero", None) == "HuiYeJi",
                          (_huiyeji_illusion_merge,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  15.5 石钵 (ShiBo) — 佛前石钵 的召唤物
#  力量0 生命5 青岚派系（wind）召唤物，战斗中阻挡敌方攻击。
# ═══════════════════════════════════════════════════════════════════════════════
class ShiBo:
    id = 201
    name = "石钵"
    atk = 0
    hp = 5
    type = "wind"


# ═══════════════════════════════════════════════════════════════════════════════
#  5.6 小糖人/大糖人 (XiaoTangRen/DaTangRen) — 饴细工 的召唤物（融合）
#  数值经用户裁决（#13）：小糖人 2/2、大糖人 4/4 不屈；均具融合（FUSE），
#  进场时与己方场上同组（fuse_group="TangRen"）融合体合并（引擎 summon 分支结算）。
# ═══════════════════════════════════════════════════════════════════════════════
class XiaoTangRen:
    id = 202
    name = "小糖人"
    atk = 2
    hp = 2
    type = "earth"
    base_attributes = (HeroAttributes.FUSE,)
    fuse_group = "TangRen"


class DaTangRen:
    id = 203
    name = "大糖人"
    atk = 4
    hp = 4
    type = "earth"
    base_attributes = (HeroAttributes.FUSE, HeroAttributes.TENACIOUS)
    fuse_group = "TangRen"


# ═══════════════════════════════════════════════════════════════════════════════
#  16. 泷夜叉姬 (LongYeChaJi) — 紫岩派系
#  基础能力：若你有幻境，泷夜叉姬便获得1攻击力（每回合开始时判定）。
# ═══════════════════════════════════════════════════════════════════════════════
def _longyechaji_begin_turn(e, s):
    if s.owner.illusion_zone:
        s.round_buff_atk += 1


class LongYeChaJi:
    id = 16
    name = "泷夜叉姬"
    atk = 3
    hp = 4
    type = "earth"
    listeners = (Listener("begin turn",
                          lambda e, s: s.is_alive and e.next_player == s.owner,
                          (_longyechaji_begin_turn,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  17. 荒 (Huang) — 青岚派系
#  基础能力：荒造成战斗伤害时，己方所有幻境获得+1耐久。
# ═══════════════════════════════════════════════════════════════════════════════
def _huang_combat_illusion(e, s):
    for ill in s.owner.illusion_zone:
        # 耐久增长走统一入口（#12：增长广播 IllusionDurabilityGainEvent）
        s.owner.game.gain_illusion_durability(ill, 1)


class Huang:
    id = 17
    name = "荒"
    atk = 2
    hp = 6
    type = "wind"
    listeners = (Listener("hero attack",
                          lambda e, s: s.is_alive and e.event.hero == s,
                          (_huang_combat_illusion,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  18. 土御门胡桃 (TuYuMenHuTao) — 紫岩派系
#  基础能力：当土御门胡桃出击时，若己方有气绝的式神，使所有己方式神气绝倒计时-1，
#  本次攻击不造成战斗伤害。
# ═══════════════════════════════════════════════════════════════════════════════
def _tuyumenhutao_attack(e, s):
    dead = [h for h in s.owner.heroes if not h.is_alive]
    if not dead:
        return
    for h in dead:
        h.round_until_alive = max(0, h.round_until_alive - 1)
    # 本次攻击不造成战斗伤害：由 game.attack 读取一次性标记后清除
    s._suppress_combat_damage = True


class TuYuMenHuTao:
    id = 18
    name = "土御门胡桃"
    atk = 2
    hp = 5
    type = "earth"
    listeners = (Listener("hero attack",
                          lambda e, s: s.is_alive and e.event.hero == s,
                          (_tuyumenhutao_attack,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  19. 山童 (ShanTong) — 红莲派系
#  基础能力：贯通。山童主动攻击式神时，过量伤害转移给敌方牌手。
# ═══════════════════════════════════════════════════════════════════════════════
class ShanTong:
    id = 19
    name = "山童"
    atk = 3
    hp = 4
    type = "fire"
    base_attributes = (HeroAttributes.PENETRATE,)


# ═══════════════════════════════════════════════════════════════════════════════
#  20. 凤凰火 (FengHuangHuo) — 红莲派系
#  基础能力：凤凰火使用法术牌时，投射造成1点伤害。
# ═══════════════════════════════════════════════════════════════════════════════
def _fhh_note_player_damage(hero, targets):
    """记录凤凰火对敌方牌手造成的一次伤害（炎舞增强「本局每对牌手造成一次伤害+1」）。

    targets 中的 None 表示投射在战斗区为空时落到敌方牌手。
    由凤凰火各卡牌效果与基础能力回调调用，供 炎舞(YanWu) 的增强读取。
    """
    if hero is None:
        return
    tlist = targets if isinstance(targets, (list, tuple)) else [targets]
    opp = hero.owner.opponent
    if any(t is None or t is opp or getattr(t, "entity_type", None) == "player" for t in tlist):
        game = hero.owner.game
        game.counters.ensure("fhh_player_dmg_hits", persistent=True)
        game.counters.inc("fhh_player_dmg_hits")


def _fhh_base_ability(e, s):
    """凤凰火基础能力：使用法术牌时投射1点伤害。

    焚羽(FenYu, id=157)形态下，凤凰火造成的所有非战斗伤害+1（基础投射也享受）；
    同时记录对敌方牌手的伤害（炎舞增强）。焚羽 id 直接引用，避免与卡牌模块循环导入。
    """
    bonus = 1 if s.morphed_id == 157 else 0  # 157 = 焚羽 FenYu
    target = [s.owner.opponent.attack_zone]  # None → 敌方牌手
    _fhh_note_player_damage(s, target)
    s.owner.game.handle_event(ProjectileEvent(1 + bonus, s, target))


class FengHuangHuo:
    id = 20
    name = "凤凰火"
    atk = 2
    hp = 4
    type = "fire"
    listeners = (Listener("play card",
                          lambda e, s: s.is_alive and e.event.card.owner == s.owner and e.event.card.card_type == CardType.SPELL and e.event.card.get_corresponding_hero() == s,
                          (_fhh_base_ability,), phase="after"),)


# ═══════════════════════════════════════════════════════════════════════════════
#  21. 妖刀姬 (YaoDaoJi) — 苍叶派系
#  基础能力：妖刀姬对敌方牌手造成伤害时，她的战斗牌本回合获得瞬发。
# ═══════════════════════════════════════════════════════════════════════════════
def _yaodaoji_hit_player(target):
    """判断受害者中是否含牌手（兼容 combat damage 单对象 / deal damage 列表两种格式）。"""
    targets = target if isinstance(target, (list, tuple)) else [target]
    return any(getattr(t, "entity_type", None) == "player" for t in targets)


def _yaodaoji_source_from(e, s):
    """本次伤害的来源是否归属妖刀姬（来源可能是式神本身，也可能是其卡牌）。"""
    src = getattr(e.event, "source", None)
    if src is s:
        return True
    if hasattr(src, "get_corresponding_hero"):
        return src.get_corresponding_hero() is s
    return False


def _yaodaoji_grant_instant(e, s):
    """妖刀姬对敌方牌手造成伤害：本回合她的手牌中妖刀姬战斗牌获得瞬发。"""
    if not _yaodaoji_hit_player(e.event.target):
        return
    for c in s.owner.hand.cards:
        if c.hero == "YaoDaoJi" and c.card_type == CardType.ATTACK \
                and CardAttributes.INSTANT not in c.attributes:
            c.attributes.append(CardAttributes.INSTANT)


def _yaodaoji_clear_instant(e, s):
    """本回合开始时，清除上一回合赋予的战斗牌瞬发（瞬发只持续触发回合）。"""
    for c in s.owner.hand.cards:
        if c.hero == "YaoDaoJi" and c.card_type == CardType.ATTACK \
                and CardAttributes.INSTANT in c.attributes:
            c.attributes.remove(CardAttributes.INSTANT)


def _yaodaoji_count_kill(e, s):
    """记录妖刀姬本局游戏消灭的式神数（禁锢之刀增强、不祥之刃抽牌判定）。"""
    s.owner.game.counters.ensure("yaodaoji_kills", persistent=True)
    s.owner.game.counters.inc("yaodaoji_kills")


class YaoDaoJi:
    id = 21
    name = "妖刀姬"
    atk = 3
    hp = 4
    type = "wood"
    listeners = (
        # 妖刀姬对敌方牌手造成伤害（战斗/法术/投射统一走 damage dealt 纯通知）
        Listener("damage dealt",
                 lambda e, s: s.is_alive and _yaodaoji_source_from(e, s),
                 (_yaodaoji_grant_instant,)),
        # 本回合结束（下一次己方回合开始）清除瞬发
        Listener("begin turn",
                 lambda e, s: e.next_player == s.owner.opponent,
                 (_yaodaoji_clear_instant,)),
        # 击杀计数：本局消灭式神数（killer 为 _last_damage_source，战斗击杀即妖刀姬）
        Listener("hero kill",
                 lambda e, s: s.is_alive and getattr(e.event, "killer", None) is s,
                 (_yaodaoji_count_kill,)),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  22. 白狼 (BaiLang) — 苍叶派系
#  基础能力：己方回合时，白狼对敌方式神造成战斗伤害时，对敌方牌手造成2点伤害。
# ═══════════════════════════════════════════════════════════════════════════════
class BaiLang:
    id = 22
    name = "白狼"
    atk = 3
    hp = 4
    type = "wood"
    # 基础能力：己方回合时，白狼对敌方式神造成战斗伤害时，对敌方牌手造成2点伤害。
    # 旧实现挂在 "hero attack"（仅 step 层广播带 target），且攻击在守护重定向/伤害被
    # 格挡等情形下仍误触发；改用 "damage dealt" 结算后纯通知，按实际造成的战斗伤害触发。
    listeners = (Listener("damage dealt",
                          lambda e, s: (s.is_alive
                                        and not s.is_awakened
                                        and e.event.source is s
                                        and getattr(e.event, "damage_type", None) == "combat"
                                        and e.event.target
                                        and s.owner.game.current_player is s.owner
                                        and getattr(e.event.target[0], "entity_type", None) == "hero"
                                        and getattr(e.event.target[0], "owner", None) is s.owner.opponent
                                        and getattr(e.event, "value", 0) > 0),
                          (lambda e, s: s.owner.game.handle_event(DealDamage(2, s, [s.owner.opponent])),)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  23. 妖琴师 (YaoQinShi) — 苍叶派系
#  基础能力：倒计时3，为己方所有角色（式神与牌手）恢复3生命。
#  觉醒：使用妖琴师的觉醒法术牌时，使妖琴师的倒计时-3（一次最多减到0，溢出不结算）。
#  基础能力每次结算时记录版本（_yqs_resolved_versions，大合奏「每生效过一种」判定）。
# ═══════════════════════════════════════════════════════════════════════════════
def _yaoqinshi_countdown(s):
    """倒计时3：为己方所有存活式神与牌手恢复3生命。"""
    targets = [h for h in s.owner.heroes if h.is_alive]
    targets.append(s.owner)
    s.owner.game.handle_event(Heal(3, s, targets))


def _yaoqinshi_track_resolved(_e, s):
    """记录本局已结算过的基础能力版本（大合奏用）。

    「countdown」在 on_countdown 回调运行前广播（三条结算路径一致：
    tick_countdown / _countdown_reduce / _yaoqinshi_awaken），此刻的
    on_countdown[0] 即将结算的版本，以其函数名为键记入牌手
    _yqs_resolved_versions 集合（本局持久，双方各记各的）。
    """
    cbs = getattr(s, "on_countdown", ())
    if not cbs:
        return
    resolved = getattr(s.owner, "_yqs_resolved_versions", None)
    if resolved is None:
        resolved = s.owner._yqs_resolved_versions = set()
    resolved.add(cbs[0].__name__)


def _yaoqinshi_awaken(_e, s):
    """使用妖琴师的觉醒法术牌：倒计时-3；若归零则立即结算一次倒计时效果。"""
    if s.countdown_max <= 0:
        return
    s.countdown = max(0, s.countdown - 3)
    if s.countdown <= 0:
        s.countdown = s.countdown_max
        s.owner.game.handle_event(CountdownEvent(s))
        for callback in s.on_countdown:
            result = callback(s)
            if isinstance(result, Event):
                s.owner.game.handle_event(result)


class YaoQinShi:
    id = 23
    name = "妖琴师"
    atk = 3
    hp = 4
    type = "wood"
    countdown = 3
    countdown_max = 3
    on_countdown = (_yaoqinshi_countdown,)
    listeners = (Listener("play card",
                          lambda e, s: s.is_alive and e.event.card.owner == s.owner
                                       and e.event.card.eng_name.startswith("JueXing")
                                       and e.event.card.get_corresponding_hero() == s,
                          (_yaoqinshi_awaken,), phase="after"),
                 Listener("countdown",
                          lambda e, s: getattr(e.event, "hero", None) is s,
                          (_yaoqinshi_track_resolved,)))


# ═══════════════════════════════════════════════════════════════════════════════
#  24. 鸩 (Zhen) — 苍叶派系
#  基础能力：倒计时2，使敌方牌手获得2破甲。
# ═══════════════════════════════════════════════════════════════════════════════
def _zhen_countdown(s):
    s.owner.game.apply_penetration(s, s.owner.opponent, 2)


class Zhen:
    id = 24
    name = "鸩"
    atk = 2
    hp = 5
    type = "wood"
    countdown = 2
    countdown_max = 2
    on_countdown = (_zhen_countdown,)


# ═══════════════════════════════════════════════════════════════════════════════
#  25. 一目连 (YiMuLian) — 苍叶派系
#  基础能力：己方回合开始时，获得+1防御。
# ═══════════════════════════════════════════════════════════════════════════════
class YiMuLian:
    id = 25
    name = "一目连"
    atk = 2
    hp = 6
    type = "wood"
    # phase="after"：引擎的回合开始清甲（hero.defense = 0）发生在 before 广播之后，
    # 监听 before 阶段的 +1 防御会随即被清零（从未生效的既有 bug）；after 广播点
    # 位于清甲/复活/倒计时/充能结算之后、抽牌之前，+1 防御得以保留。
    listeners = (Listener("begin turn",
                          lambda e, s: s.is_alive and e.next_player == s.owner,
                          (lambda e, s: GiveBuff("defense", 1, s, [s]),),
                          phase="after"),)


# ═══════════════════════════════════════════════════════════════════════════════
#  26. 饴细工 (YiXiGong) — 紫岩派系
#  基础能力：每回合一次，饴细工使用法术牌时，烹饪（生成食材或合成佳肴）。
# ═══════════════════════════════════════════════════════════════════════════════
def _yixigong_cook(_e, s):
    s.counters.ensure("yixigong_cooked", initial=0, reset_per_turn=True)
    if s.counters.get("yixigong_cooked") > 0:
        return
    s.counters.set("yixigong_cooked", 1)
    s.owner.game.cook(s.owner, s)


# ── 佳肴获得跟踪（「本局游戏获得了 X 张佳肴」类增强条件的公共计数）─────────────
# 计数存于牌手对象（跨式神气绝/复活持续，「本局游戏」口径，随饴细工开局即生效）：
# - 烹饪合成：CookEvent 广播前佳肴已入手牌，以手牌佳肴增量计入；
# - 直接获得（甘如暖阳等）：经 _yxg_gain_jiaoyao 同步（cards/YiXiGong.py 调用）；
# - 佳肴从手牌打出（"play card" 完成事件广播）时同步基准。
# 监听条件不带 is_alive：饴细工气绝期间的获得仍属「本局游戏」；等级门槛无影响
# （佳肴只可能产生于烹饪/直接获得，均需饴细工已升级）。

def _yxg_track_ensure(player):
    if getattr(player, "_yxg_tracker_ready", False):
        return
    player._yxg_tracker_ready = True
    player._yxg_jiaoyao_total = 0
    player._yxg_jiaoyao_baseline = 0


def _yxg_track_cook(_e, s):
    player = s.owner
    _yxg_track_ensure(player)
    now = sum(1 for c in player.hand.cards if getattr(c, "eng_name", "") == "JiaYao")
    gained = now - player._yxg_jiaoyao_baseline
    if gained > 0:
        player._yxg_jiaoyao_total += gained
    player._yxg_jiaoyao_baseline = now


def _yxg_jiaoyao_played(e, s):
    """监听条件：本牌手的「佳肴」从手牌打出（"play card" 完成事件）。"""
    card = getattr(e.event, "card", None)
    return (card is not None and getattr(card, "eng_name", "") == "JiaYao"
            and getattr(card, "owner", None) is s.owner)


def _yxg_track_play(_e, s):
    # 打出的佳肴此前已按「获得」计入 total 与手牌基准：下调基准，
    # 避免下次烹饪以手牌增量计数时把这张佳肴重复计入。
    player = s.owner
    _yxg_track_ensure(player)
    player._yxg_jiaoyao_baseline = max(0, player._yxg_jiaoyao_baseline - 1)


def _yxg_gain_jiaoyao(player, n=1, in_hand=True):
    """非烹饪来源获得佳肴（甘如暖阳等）时的计数同步（cards/YiXiGong.py 调用）。

    in_hand=False：佳肴未入手牌（如手牌已满直接进弃牌堆），不计入手牌基准。
    """
    _yxg_track_ensure(player)
    player._yxg_jiaoyao_total += n
    if in_hand:
        player._yxg_jiaoyao_baseline += n


class YiXiGong:
    id = 26
    name = "饴细工"
    atk = 2
    hp = 5
    type = "earth"
    listeners = (Listener("play card",
                          lambda e, s: s.is_alive and e.event.card.owner == s.owner
                                       and e.event.card.card_type == CardType.SPELL
                                       and e.event.card.get_corresponding_hero() == s,
                          (_yixigong_cook,), phase="after"),
                 Listener("cook",
                          lambda e, s: e.event.player is s.owner,
                          (_yxg_track_cook,)),
                 Listener("play card", _yxg_jiaoyao_played, (_yxg_track_play,), phase="after"))


# ═══════════════════════════════════════════════════════════════════════════════
#  27. 薰 (Xun) — 紫岩派系
#  基础能力：己方回合结束时，使本回合最后一个攻击的式神结附「鸮之守护」（受到伤害 -1）。
#  触发时机在对方回合开始广播时（己方回合已结束），此时 last_attacking_hero 即为本回合最后攻击者。
# ═══════════════════════════════════════════════════════════════════════════════
def _xun_attach_guard(e, s):
    last = s.owner.last_attacking_hero
    if last is not None and last.is_alive:
        # 鸮之守护只能存在于一个式神上：清除旧的，结附到本回合最后攻击的式神
        for h in s.owner.heroes:
            if h.counters.get("hawk_protection", 0) > 0:
                h.counters.set("hawk_protection", 0)
        last.counters.set("hawk_protection", 1)


class Xun:
    id = 27
    name = "薰"
    atk = 2
    hp = 4
    type = "earth"
    listeners = (Listener("begin turn",
                          lambda e, s: s.is_alive and e.next_player != s.owner,
                          (_xun_attach_guard,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  28. 五丸 (WuWan) — 红莲派系
#  基础能力：当五丸对敌方牌手造成战斗伤害时，烹饪。
# ═══════════════════════════════════════════════════════════════════════════════
class WuWan:
    id = 28
    name = "五丸"
    atk = 3
    hp = 4
    type = "fire"
    # 基础能力：当五丸对敌方牌手造成战斗伤害时，烹饪。
    # 监听 "damage dealt" 结算后纯通知（任意战斗路径均触发，含效果攻击）；target 恒为列表。
    # 贯通过量走 DealDamage（damage_type="spell"），不会触发烹饪——与旧 hero attack 行为一致。
    listeners = (Listener("damage dealt",
                          lambda e, s: (s.is_alive
                                        and e.event.source is s
                                        and getattr(e.event, "damage_type", None) == "combat"
                                        and e.event.target
                                        and getattr(e.event.target[0], "entity_type", None) == "player"
                                        and getattr(e.event, "value", 0) > 0),
                          (lambda e, s: s.owner.game.cook(s.owner, s),)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  29. 食灵 (ShiLing) — 红莲派系
#  基础能力：每当己方式神烹饪时，食灵获得1攻击力。
# ═══════════════════════════════════════════════════════════════════════════════
class ShiLing:
    id = 29
    name = "食灵"
    atk = 2
    hp = 6
    type = "fire"
    listeners = (Listener("cook",
                          lambda e, s: s.is_alive and e.event.player == s.owner,
                          (lambda e, s: GiveBuff("atk", 1, s, [s]),)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  30. 鬼使黑＆鬼使白 (GuiShiHeiGuiShiBai) — 红莲派系
#  2021《吉运缘结》切换式神：黑/白同一实体，form="Hei"/"Bai" 区分形态。
#  黑 3/4「充能。当鬼使黑气绝时，消耗2能量，切换为鬼使白。」
#  白 2/6「倒计时3：切换为鬼使黑。」
#  卡池 9 张（黑7白2）+ 衍生「魂狩」，见 tmp_cards_json/GuiShiHeiGuiShiBai.json。
#  注意：不是 2024 湮灭双生重做版独立式神。机制见 tmp_cards_json/GuiShiHeiGuiShiBai_mechanics.md。
# ═══════════════════════════════════════════════════════════════════════════════
_GSGB_FORM_DATA = {
    "Hei": {"atk": 3, "hp": 4, "base_attributes": (HeroAttributes.ENERGY_CHARGE,)},
    "Bai": {"atk": 2, "hp": 6, "base_attributes": ()},
}


def _gsgb_apply_form(hero, to_form):
    """按新形态应用面板/倒计时/充能词条，并清除临时数值。"""
    fd = _GSGB_FORM_DATA[to_form]
    hero.form = to_form
    hero.atk = fd["atk"] + hero.perm_buff_atk                # 永久加成跨形态保留
    hero.current_max_hp = fd["hp"] + hero.perm_buff_hp
    hero.hp = hero.current_max_hp                            # 新形态满状态登场
    if to_form == "Bai":
        hero.countdown_max = 1 if getattr(hero, "_awakened_bai", False) else 3
        hero.countdown = hero.countdown_max
    else:
        hero.countdown_max = 0                                # 离开白形态必须清零倒计时
        hero.countdown = 0
    if to_form == "Hei":
        if HeroAttributes.ENERGY_CHARGE not in hero.attributes:
            hero.attributes.append(HeroAttributes.ENERGY_CHARGE)
    else:  # Bai：白基础无充能；仅黑侧对应卡牌（如冥界引路人，若提供充能永久效果）后充能永久、可覆盖白形态
        if not getattr(hero, "_awakened_hei", False) and HeroAttributes.ENERGY_CHARGE in hero.attributes:
            hero.attributes.remove(HeroAttributes.ENERGY_CHARGE)
    # 临时 buff 清除（GiveBuff 数值由 atk/current_max_hp 重置隐式丢弃）
    hero.defense = 0
    hero.penetration = 0
    hero.round_buff_atk = 0
    hero.round_buff_spell_damage = 0
    hero.round_buff_player_damage = 0
    clear_combat_immune(hero)  # 切形态清临时战斗免疫监听器


def _gsgb_switch_form(hero, to_form, via="active"):
    """切换形态。via: "death_intercept" | "countdown" | "active"。"""
    if to_form == hero.form:
        return
    game = hero.owner.game if hero.owner is not None else None
    if via == "death_intercept":
        # 气绝触发切换：形态牌/眩晕/形态监听清除（主动/倒计时切换则保留）
        if hero.morphed_id != 0 and game is not None:
            game.handle_event(MorphLeaveEvent(hero, hero.morphed_id, "destroy"))
        hero.morphed_id = 0
        hero.listeners = list(hero.original_listeners)
        hero.stunned = False
        cost = 1 if getattr(hero, "_awakened_hei", False) else 2
        hero.counters.dec("energy", cost)                     # 共享能量池，持久保留
        if game is not None:
            game.handle_event(EnergySpendEvent(hero, cost, None))
    else:
        # 主动/倒计时切换：保留形态牌、保留眩晕，不计气绝
        hero.counters.ensure("gsgb_switch_count", initial=0, persistent=True)  # 供索命“每切换一次”增强
        hero.counters.inc("gsgb_switch_count")                # 只计倒计时/主动切换（与机制调研一致）
    _gsgb_apply_form(hero, to_form)


def _gsgb_before_death(hero):
    """黑形态气绝 → 能量充足则拦截并切白（实体不死、白站场）；否则普通气绝。"""
    if not hero.is_alive or hero.form != "Hei":
        return False
    cost = 1 if getattr(hero, "_awakened_hei", False) else 2
    if hero.counters.get("energy", 0) < cost:
        return False                                          # 能量不足：黑普通气绝
    game = hero.owner.game if hero.owner is not None else None
    if game is not None:
        game.handle_event(AboutToDieEvent(hero))              # 补发：气绝类响应/触发仍生效
    _gsgb_switch_form(hero, "Bai", via="death_intercept")     # 内部耗能+抬白满血+广播
    return True                                               # 拦截：check_death 提前 return


def _gsgb_countdown(hero):
    """白形态倒计时结束 → 自动切回黑。"""
    if hero.form == "Bai":
        _gsgb_switch_form(hero, "Hei", via="countdown")


def _gsgb_on_death(hero):
    """白死 → 整个实体以黑身份气绝（复活由 on_revive 强制回黑）。黑死则保持黑。"""
    if hero.form == "Bai":
        hero.form = "Hei"
        hero.countdown_max = 0
        hero.countdown = 0


def _gsgb_revive(hero):
    """复活强制回黑形态（恢复黑面板 + 充能词条）。"""
    _gsgb_apply_form(hero, "Hei")


class GuiShiHeiGuiShiBai:
    id = 30
    name = "鬼使黑＆鬼使白"
    atk = 3
    hp = 4
    type = "fire"
    form = "Hei"                                   # 初始黑形态（Hero.__init__ 读取 hero_obj.form）
    base_attributes = (HeroAttributes.ENERGY_CHARGE,)
    FORM_DATA = _GSGB_FORM_DATA                    # 供未来卡牌类引用（类属性）
    on_before_death = (_gsgb_before_death,)
    on_countdown = (_gsgb_countdown,)              # 黑形态 countdown_max=0 不会 tick，守卫防误触
    on_death = (_gsgb_on_death,)
    on_revive = (_gsgb_revive,)


# ═══════════════════════════════════════════════════════════════════════════════
#  31. 小鹿男 (XiaoLuNan) — 青岚派系
#  基础能力：充能。小鹿男复活时，获得2能量。
# ═══════════════════════════════════════════════════════════════════════════════
def _xiaolunan_revive(s):
    s.counters.inc("energy", 2)
    if s.owner is not None and s.owner.game is not None:
        s.owner.game.handle_event(EnergyGainEvent(s, 2))


class XiaoLuNan:
    id = 31
    name = "小鹿男"
    atk = 2
    hp = 6
    type = "wind"
    base_attributes = (HeroAttributes.ENERGY_CHARGE,)
    on_revive = (_xiaolunan_revive,)


# ═══════════════════════════════════════════════════════════════════════════════
#  32. 镰鼬 (LianYou) — 红莲派系
#  基础能力：充能。当镰鼬对牌手造成伤害时，获得1能量。
# ═══════════════════════════════════════════════════════════════════════════════
def _lianyou_gain_energy(e, s):
    s.counters.inc("energy", 1)
    s.owner.game.handle_event(EnergyGainEvent(s, 1))


class LianYou:
    id = 32
    name = "镰鼬"
    atk = 3
    hp = 4
    type = "fire"
    base_attributes = (HeroAttributes.ENERGY_CHARGE,)
    # 基础能力：充能。当镰鼬对牌手造成伤害时，获得1能量。
    # 监听 "damage dealt" 结算后纯通知。规则文本未限定「战斗」，但旧实现（hero attack）
    # 只覆盖攻击命中牌手，且镰鼬无打牌手伤害的法术/投射，故按 combat 过滤保持行为一致。
    listeners = (Listener("damage dealt",
                          lambda e, s: (s.is_alive
                                        and e.event.source is s
                                        and getattr(e.event, "damage_type", None) == "combat"
                                        and e.event.target
                                        and getattr(e.event.target[0], "entity_type", None) == "player"
                                        and getattr(e.event, "value", 0) > 0),
                          (_lianyou_gain_energy,)),)


# ═══════════════════════════════════════════════════════════════════════════════
#  33. 日和坊 (RiHeFang) — 红莲派系
#  基础能力：充能。能量不足时可用生命代替能量消耗（不能使生命值降到0）。
#  注：HP 代偿依赖引擎层 on_before_energy_spend 回调，尚未实现，暂只加充能词条。
# ═══════════════════════════════════════════════════════════════════════════════
class RiHeFang:
    id = 33
    name = "日和坊"
    atk = 1
    hp = 6
    type = "fire"
    base_attributes = (HeroAttributes.ENERGY_CHARGE,)


# ═══════════════════════════════════════════════════════════════════════════════
#  34. 兵俑 (BingYong) — 紫岩派系
#  基础能力：己方回合开始时，兵俑获得2点护甲（觉醒·兵俑后替换为3点）。
#  形态持续效果（不动如山/森罗之阵）以 morphed_id 门控挂在下方监听器里
#  （仿焚羽的 morphed_id 模式）：original_listeners 气绝时重置、复活后恢复，
#  与形态状态天然同步，无需卡牌侧手动装卸。
# ═══════════════════════════════════════════════════════════════════════════════
def _bingyong_snapshot_armor(e, s):
    # 觉醒后「兵俑的护甲不会在己方回合开始时被移除」的快照侧：before 广播点
    # 位于引擎清甲（begin_turn 式神循环中 hero.defense = 0）之前，此处把当前
    # 护甲存入普通属性。快照不门控 is_alive：气绝式神的护甲同样被清零，快照
    # 到 0 即可避免复活后读到最后一次存活回合的陈旧数值产生幻影护甲。
    s._by_armor_snapshot = s.defense


def _bingyong_restore_armor(e, s):
    s.defense += getattr(s, "_by_armor_snapshot", 0)


def _bingyong_budongru_eff(e, s):
    # 不动如山（morphed_id==284）：己方回合开始时若兵俑在战斗区，获得3点力量。
    # round_buff_atk 为本回合力量（clear_round_effects 在 before 广播前已清零，
    # 此处加的数值本回合有效）。battle_zone 判定须在 before 广播点：begin_turn
    # 的 retract_hero 在 after 前已清空 attack_zone，after 读到的恒为空。
    s.round_buff_atk += 3


def _bingyong_senluo_cap(e, s):
    # 森罗之阵（morphed_id==286）：兵俑有护甲时受到的伤害封顶。用户裁决语义
    # （2026-09-22）：伤害最多只能移除护甲——有护甲时本次命中的气血损失为 0，
    # 溢出部分蒸发。封顶 min(伤害, 护甲) 后必被护甲全额吸收（护甲减免统一在
    # receive_damage 结算）。效果伤害与战斗伤害两条路径的 pre-damage 广播时
    # 护甲均完好（战斗路径护甲减免已随扣血移交 receive_damage），单公式通吃。
    # 广播传入的是包装 Event，真实 DealDamage 在 e.event 上，改其 value。
    # 局限：多目标 AOE 的 value 为共享数值，无法按单目标封顶，仅单目标可封顶。
    dmg = getattr(e, "event", None)
    if dmg is not None:
        dmg.value = min(dmg.value, s.defense)


class BingYong:
    id = 34
    name = "兵俑"
    atk = 1
    hp = 6
    type = "earth"
    listeners = (
        # 快照（before，每个己方回合开始都刷新）
        Listener("begin turn",
                 lambda e, s: e.next_player == s.owner,
                 (_bingyong_snapshot_armor,),
                 phase="before"),
        # 觉醒侧：还原清甲前的护甲（after 广播点在清甲之后）。常驻监听器靠
        # is_awakened 门控——觉醒跨气绝保留，且本监听器属于 original_listeners，
        # 气绝时随 listeners 重置、复活后恢复，与觉醒状态始终同步。
        Listener("begin turn",
                 lambda e, s: (s.is_alive and s.is_awakened
                               and e.next_player == s.owner),
                 (_bingyong_restore_armor,),
                 phase="after"),
        # 不动如山（284）：己方回合开始时若兵俑在战斗区，获得3点力量。
        # before 广播点读上一回合的战斗区状态（见 _bingyong_budongru_eff）。
        Listener("begin turn",
                 lambda e, s: (s.is_alive and s.morphed_id == 284
                               and e.next_player == s.owner
                               and s.owner.attack_zone is s),
                 (_bingyong_budongru_eff,),
                 phase="before"),
        # 森罗之阵（286）：兵俑有护甲时受伤封顶（单目标伤害，效果与战斗路径
        # 通吃，语义见 _bingyong_senluo_cap）。广播包装对象的负载在 e.event 上。
        Listener("deal damage",
                 lambda e, s: (s.is_alive and s.morphed_id == 286
                               and s.defense > 0
                               and getattr(e, "event", None) is not None
                               and len(e.event.target) == 1
                               and e.event.target[0] is s),
                 (_bingyong_senluo_cap,),
                 phase="before"),
        # 基础能力：己方回合开始时获得2点护甲；觉醒·兵俑后替换为3点。用 after
        # 广播点——引擎的回合开始清甲发生在 before 广播之后，监听 before 加的
        # 护甲会随即被清零（从未生效的既有 bug）；after 位于清甲之后，护甲得以
        # 保留。觉醒后先还原旧甲（还原监听器在前）再加新甲。
        Listener("begin turn",
                 lambda e, s: s.is_alive and e.next_player == s.owner,
                 (lambda e, s: GiveBuff("defense", 3 if s.is_awakened else 2, s, [s]),),
                 phase="after"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  35. 书翁 (ShuWeng) — 青岚派系
#  基础能力：起始手牌+1。
#  形态持续效果（纪行 290 / 明心 294）以 morphed_id 门控挂在下方监听器里
#  （仿兵俑的 morphed_id 模式）。觉醒·书翁（297）的空牌库被动由引擎
#  handle_event 的 "draw" 分支结算（DrawEvent 抽牌事件，用户裁决 2026-09-22）。
# ═══════════════════════════════════════════════════════════════════════════════
def _shuweng_bonus_draw(e, s):
    s._sw_bonus_drawn = True
    s.owner.game.handle_event(DrawEvent(s.owner, 1))


def _shuweng_mingxin_replace(e, s):
    """明心（morphed_id==294）：回合开始的抽牌改为检视牌库顶三张然后选一张
    置入手牌，然后洗牌库。在 "turn draw" 事件上置 replaced 并给出候选与回调；
    引擎在蓄力结算完成后进入 SELECTING_TARGET（复用既有选目标流程），选定后
    回调结算（ShuWeng 检视流程的洗牌用 game.rng，同五道难题惯例）。
    """
    evt = getattr(e, "event", None)
    if evt is None or evt.player is not s.owner:
        return
    top = s.owner.deck.cards[:3]
    if not top:
        return   # 牌库空：无牌可检视，不替换（交回引擎正常抽牌 → 空牌库流程）
    evt.replaced = True
    evt.candidates = list(top)

    def _apply(chosen):
        p = s.owner
        if chosen in p.deck.cards:
            p.deck.remove(chosen)
            p.hand.append(chosen)
            p.sort_hand()
        p.game.rng.shuffle(p.deck.cards)

    evt.on_chosen = _apply


class ShuWeng:
    id = 35
    name = "书翁"
    atk = 1
    hp = 5
    type = "wind"
    # 基础能力「起始手牌+1」：起始手牌发放依赖引擎层发牌流程（审批清单改动2，
    # 未实现），经用户裁决改为「5张调度完成后、第一回合开始时再抽一张牌」。
    # begin turn 的 after 广播位于常规抽牌之前：双方 INITIAL_PICK 阶段被
    # state 条件跳过，双方调度完成后的首个真实回合开始时先抽这张牌、再抽
    # 回合抽牌。一次性旗标用普通属性而非 per-turn 计数器——计数器清零发生在
    # before/after 广播之间，普通属性不受影响。书翁 0 级即可触发：broadcast
    # 对 type_name == "ShuWeng" 豁免 0 级跳过（开局即生效的能力，game.py），
    # 因此书翁在阵容任意位置都能在首回合生效，无需等待升级。
    listeners = (
        Listener("begin turn",
                 lambda e, s: (e.next_player == s.owner
                               and s.owner.state != PlayerState.INITIAL_PICK
                               and not getattr(s, "_sw_bonus_drawn", False)),
                 (_shuweng_bonus_draw,),
                 phase="after"),
        # 纪行（290）迅捷：引擎的 AGILE 在出击后被消耗，故在己方回合开始时
        # 重新授予（胡桃觉醒的既有近似）：形态期间每回合第一个出击免鬼火。
        Listener("begin turn",
                 lambda e, s: (s.is_alive and s.morphed_id == 290
                               and e.next_player == s.owner
                               and HeroAttributes.AGILE not in s.attributes),
                 (lambda e, s: s.attributes.append(HeroAttributes.AGILE),)),
        # 纪行（290）形态离场：未消耗的迅捷随形态移除（形态离场含被替换与
        # 随气绝消灭两种；气绝路径 check_death 随后还会移除一次，幂等）。
        Listener("morph leave",
                 lambda e, s: (getattr(e.event, "morph_id", 0) == 290
                               and e.event.hero is s
                               and HeroAttributes.AGILE in s.attributes),
                 (lambda e, s: s.attributes.remove(HeroAttributes.AGILE),)),
        # 纪行（290）：当书翁对敌方牌手造成伤害时，抽一张牌。damage dealt 为
        # 结算后通知（连浪先例：value>0 才计）；对手 LOST 后不再触发（觉醒·
        # 书翁空牌库「伤害→抽牌→伤害」链在对手死亡时自然终止）。抽牌走
        # DrawEvent（觉醒后空牌库时同样经引擎分支结算为10点伤害）。
        Listener("damage dealt",
                 lambda e, s: (s.is_alive and s.morphed_id == 290
                               and e.event.source is s
                               and s.owner.opponent in e.event.target
                               and getattr(e.event, "value", 0) > 0
                               and s.owner.opponent.state != PlayerState.LOST),
                 (lambda e, s: s.owner.game.handle_event(DrawEvent(s.owner, 1)),)),
        # 明心（294）：回合开始的抽牌改为检视三选一（见 _shuweng_mingxin_replace）。
        Listener("turn draw",
                 lambda e, s: (s.is_alive and s.morphed_id == 294
                               and getattr(e.event, "player", None) is s.owner),
                 (_shuweng_mingxin_replace,)),
    )
