from enums import *

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
    #attributes = (CardAttributes.INSTANT,)
    level_req = 1


class WuShiZhiLi:
    id = 3
    type = "spell"
    hero = "ZhiRenWuShi"
    name = "武士之笠"
    level_req = 2

class WuShiZhiRen:
    id = 4
    type = "attack"
    hero = "ZhiRenWuShi"
    name = "武士之刃"
    level_req = 3
    buff_atk = 3
    buff_def = 2