import sys
sys.path.insert(0, "E:\more_random_project")
from game_core.action import *
from game_core.enums import *
from game_core.selector import *

class TianXieGuiChiRanShao:
    id = 5
    type = "spell"
    hero = "TianXieGuiTuanHuo"
    name = "天邪鬼赤·燃烧"
    level_req = 1
    on_play = (lambda s: DealDamage(1, s.owner.opponent.heroes),)


class TianXieGuiHuangGuWu:
    id = 6
    type = "spell"
    hero = "TianXieGuiTuanHuo"
    name = "天邪鬼黄·鼓舞"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)


class TianXieGuiQingYuanJi:
    id = 7
    type = "spell"
    hero = "TianXieGuiTuanHuo"
    name = "天邪鬼青·鸢击"
    level_req = 1 ####NEED TO REVERT TO 2
    on_play = (lambda s: CallSelector(select_target, s.owner, s.owner.opponent.heroes, s),
               lambda s: DealDamage(4, s.owner.selected_targets),)


class TianXieGuiLvPaiDa:
    id = 8
    type = "spell"
    hero = "TianXieGuiTuanHuo"
    name = "天邪鬼绿·拍打"
    level_req = 3
    on_play = (lambda s: DealDamage(4, s.owner.opponent),)