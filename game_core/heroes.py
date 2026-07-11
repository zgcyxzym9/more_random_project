from game_core.card import Card

from .enums import *
from .manager import Listener
from .action import *
from .event import *

class ZhiRenWuShi:
    id = 1
    name = "纸人武士"
    atk = 3
    hp = 4
    type = "fire"


class TianXieGuiTuanHuo:
    id = 2
    name = "天邪鬼团伙"
    atk = 2
    hp = 5
    type = "wind"


class QuanShen:
    id = 3
    name = "犬神"
    atk = 2
    hp = 5
    type = "fire"
    on_upgrade = (lambda s: s.owner.GiveCardToHand(["XinShenLianMo"]),
                  lambda s: [(setattr(c, "attributes", [CardAttributes.INSTANT]) if c.id == 17 else None) for c in s.owner.hand.cards] if s.level == 2 else None,
                  lambda s: [(setattr(c, "attributes", [CardAttributes.NO_FIRE_CONSUMPTION]) if c.id == 17 else None) for c in s.owner.hand.cards] if s.level == 3 else None,)
    counter = {"xin_shen_lian_mo": 0}


class TaoHuaYao:
    id = 4
    name = "桃花妖"
    atk = 1
    hp = 6
    type = "fire"
    listeners = (Listener("heal",
                          lambda e, s: any(t in s.owner.heroes for t in e.event.target) and (e.event.source.get_corresponding_hero() == s if type(e.event.source).__name__ == "Card" else e.event.source == s),
                          (lambda e, s: GiveBuff("atk", 1, s, [t for t in e.event.target if t in s.owner.heroes]),)),
                 Listener("revive",
                          lambda e, s: any(t in s.owner.heroes for t in e.event.target) and (e.event.source.get_corresponding_hero() == s if type(e.event.source).__name__ == "Card" else e.event.source == s),
                          (lambda e, s: GiveBuff("atk", 1, s, [t for t in e.event.target if t in s.owner.heroes]),)),)
    on_death = (lambda s: [c.attributes.remove(CardAttributes.INSTANT) for c in s.owner.hand.cards + s.owner.deck.cards if c.id == 24 and CardAttributes.INSTANT in c.attributes],)
    on_revive = (lambda s: [c.attributes.append(CardAttributes.INSTANT) for c in s.owner.hand.cards + s.owner.deck.cards if c.id == 24 and CardAttributes.INSTANT not in c.attributes],)


class BuZhiHuo:
    id = 5
    name = "不知火"
    atk = 2
    hp = 4
    type = "fire"
    listeners = (Listener("begin turn",
                          lambda e, s: e.next_player == s.owner,
                          lambda e, s: GiveBuff("inspiration_atk", 1, s, [s])),)


def _create_huoqumo_listeners():
    l1 = Listener("play card",
                  lambda e, s: s.owner == e.event.card.owner and e.event.card.get_corresponding_hero().type == "fire",
                  (lambda e, s: setattr(s, 'listeners', [l2, l3]),))
    l2 = Listener("play card",
                  lambda e, s: s.owner == e.event.card.owner and e.event.card.get_corresponding_hero().type == "fire",
                  (lambda e, s: GiveBuff("atk", 1, s, [s]),
                   lambda e, s: GiveBuff("hp", 1, s, [s]),
                   lambda e, s: setattr(s, 'listeners', [l3])))
    l3 = Listener("begin turn",
                  lambda e, s: e.next_player != s.owner,
                  (lambda e, s: setattr(s, 'listeners', [l4]),))
    l4 = Listener("begin turn",
                  lambda e, s: e.next_player == s.owner,
                  (lambda e, s: setattr(s, 'listeners', [l1, l3]),))
    return (l1, l3)

class HuoQuMo:
    id = 6
    name = "火取魔"
    atk = 2
    hp = 5
    type = "fire"
    # 回合当你使用第二章"fire"类角色的牌时，火取魔获得1攻击力和1生命值。
    # 实现方案：三个Listener
    # 1: 收听play card信息，如果是自己回合的play card并且是fire类角色的卡牌，则把listener列表替换成2和3
    # 2：收听play card信息，如果是自己回合的play card并且是fire类角色的卡牌，则获得1攻击力和1生命值，并把listener列表替换成3
    # 3：收听begin turn信息，如果轮到对手出牌则把listener列表替换成4
    # 4：收听begin turn信息，如果轮到自己出牌则把listener列表替换成1和3
    # 初始的时候listener列表为1和3，在initial pick阶段会进行一个没有play card的完整周期，所以不用担心对手先出牌怎么办
    listeners = _create_huoqumo_listeners()