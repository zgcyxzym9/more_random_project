from enums import *
import sys
sys.path.insert(0, "E:\more_random_project")
from game_core.action import *

class WuShiZhiQuan:
    id = 1
    type = "attack"
    hero = "ZhiRenWuShi"
    name = "武士之拳"
    level_req = 1
    buff_atk = 1


class WuShiZhiDi:
    id = 2
    type = "spell"
    hero = "ZhiRenWuShi"
    name = "武士之笛"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: GiveBuff("round_buff_atk", 1, s.owner.heroes),)


class WuShiZhiLi:
    id = 3
    type = "spell"
    hero = "ZhiRenWuShi"
    name = "武士之笠"
    level_req = 2
    on_play = (lambda s: GiveBuff("current_max_hp", 2, s.get_corresponding_hero()), 
               lambda s: GiveBuff("hp", 2, s.get_corresponding_hero()), 
               lambda s: GiveBuff("atk", 2, s.get_corresponding_hero()))

class WuShiZhiRen:
    id = 4
    type = "attack"
    hero = "ZhiRenWuShi"
    name = "武士之刃"
    level_req = 3
    buff_atk = 3
    buff_def = 2