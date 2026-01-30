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
    on_upgrade = (lambda s: s.GiveCardToHand(["XinShenLianMo"]),
                  lambda s: [(c.attributes.append(CardAttributes.INSTANT) if c.id == 17 else None) for c in s.hand] if s.level == 2 else [])
    xin_shen_lian_mo_cnt = 0


class TaoHuaYao:
    id = 4
    name = "桃花妖"
    atk = 1
    hp = 6
    listeners = (Listener("heal", 
                          lambda e, s: e.action.target in s.owner.heroes and (e.action.source.owner == s if type(e).__name__ == "Card" else e.action.source == s), 
                          (lambda e, s: GiveBuff("atk", 1, s.get_corresponding_hero(), e.action.target),)))