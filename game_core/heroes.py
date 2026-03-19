from game_core.card import Card

from .enums import *
from .manager import Listener
from .action import *

class ZhiRenWuShi:
    id = 1
    name = "纸人武士"
    atk = 3
    hp = 4


class TianXieGuiTuanHuo:
    id = 1
    name = "天邪鬼团伙"
    atk = 2
    hp = 5


class QuanShen:
    id = 3
    name = "犬神"
    atk = 2
    hp = 5
    on_upgrade = (lambda s: s.owner.GiveCardToHand(["XinShenLianMo"]),
                  lambda s: [(setattr(c, "attributes", [CardAttributes.INSTANT]) if c.id == 17 else None) for c in s.owner.hand.cards] if s.level == 2 else None,
                  lambda s: [(setattr(c, "attributes", [CardAttributes.NO_FIRE_CONSUMPTION]) if c.id == 17 else None) for c in s.owner.hand.cards] if s.level == 3 else None,)
    xin_shen_lian_mo_cnt = 0


class TaoHuaYao:
    id = 4
    name = "桃花妖"
    atk = 1
    hp = 6
    listeners = (Listener("heal", 
                          lambda e, s: any(t in s.owner.heroes for t in e.action.target) and (e.action.source.get_corresponding_hero() == s if type(e.action.source).__name__ == "Card" else e.action.source == s), 
                          (lambda e, s: GiveBuff("atk", 1, s, [t for t in e.action.target if t in s.owner.heroes]),)),
                 Listener("revive",
                          lambda e, s: any(t in s.owner.heroes for t in e.action.target) and (e.action.source.get_corresponding_hero() == s if type(e.action.source).__name__ == "Card" else e.action.source == s), 
                          (lambda e, s: GiveBuff("atk", 1, s, [t for t in e.action.target if t in s.owner.heroes]),)),)