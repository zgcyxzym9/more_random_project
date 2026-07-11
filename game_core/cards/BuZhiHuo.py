import sys
sys.path.insert(0, "E:\more_random_project")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# PLACEHOLDER: is_beginning_card=false，且"你的出击加成效果在使用战斗牌时也会生效"涉及不知火英雄的出击加成机制与战斗牌的交互，目前框架尚不支持
class BuYeZhiWu:
    id = 28
    type = "morph"
    hero = "BuZhiHuo"
    name = "不夜之舞"
    level_req = 1
    atk = 4
    hp = 5


class ZhenYiZhiGe:
    id = 29
    type = "spell"
    hero = "BuZhiHuo"
    name = "真意之歌"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: setattr(s.get_corresponding_hero(), "inspiration_atk", getattr(s.get_corresponding_hero(), "inspiration_atk") + 1),
               lambda s: setattr(s.get_corresponding_hero(), "inspiration_def", getattr(s.get_corresponding_hero(), "inspiration_def") + 1),
               lambda s: setattr(s.owner, "attack_available", True))


class ZiYouZhiGe:
    id = 30
    type = "spell"
    hero = "BuZhiHuo"
    name = "自由之歌"
    level_req = 2
    require_target = (lambda s: s.owner.heroes,)
    select_target = (lambda s: select_target(s.owner, s.owner.heroes, s),)
    on_play = (lambda s: s.owner.selected_targets[0].attributes.append(HeroAttributes.AGILE) if HeroAttributes.AGILE not in s.owner.selected_targets[0].attributes else None,
               lambda s: setattr(s.get_corresponding_hero(), "inspiration_atk", getattr(s.get_corresponding_hero(), "inspiration_atk") + 2),
               lambda s: setattr(s.get_corresponding_hero(), "inspiration_def", getattr(s.get_corresponding_hero(), "inspiration_def") + 2))


# PLACEHOLDER: is_beginning_card=false，且"远程"关键词及"出击并对敌方牌手造成伤害时抽牌"的触发机制目前框架尚不支持
class ChuHuiZhiWu:
    id = 31
    type = "morph"
    hero = "BuZhiHuo"
    name = "初会之舞"
    level_req = 2
    atk = 2
    hp = 6


# PLACEHOLDER: is_beginning_card=false，且"召唤一个'烬染不夜'"的召唤机制目前框架尚不支持
class XingHuoZhiGe:
    id = 32
    type = "spell"
    hero = "BuZhiHuo"
    name = "星火之歌"
    level_req = 2


def _create_juexing_buzhihuo_listeners():
    """创建觉醒·不知火的 listener 组合，返回初始应加入的 listener 集合。

    l1: 监听不知火出击 → 若已有贯通则仅移除自身，否则提供 PENETRATE 并换成 l2。
    l2: 监听对手回合开始(己方回合结束) → 移除 PENETRATE → 移除自身。
    l3: 监听己方回合开始 → 鼓舞 +2 atk, +1 def。
    """
    l1 = Listener("hero attack",
                  lambda e, s: e.event.hero == s,
                  (lambda e, s: s.listeners.remove(l1) if HeroAttributes.PENETRATE in s.attributes
                                else (s.attributes.append(HeroAttributes.PENETRATE),
                                      s.listeners.remove(l1),
                                      s.listeners.append(l2)),))
    l2 = Listener("begin turn",
                  lambda e, s: e.next_player != s.owner,
                  (lambda e, s: s.attributes.remove(HeroAttributes.PENETRATE) if HeroAttributes.PENETRATE in s.attributes else None,
                   lambda e, s: s.listeners.remove(l2)))
    l3 = Listener("begin turn",
                  lambda e, s: e.next_player == s.owner,
                  (lambda e, s: setattr(s, "inspiration_atk", s.inspiration_atk + 2),
                   lambda e, s: setattr(s, "inspiration_def", s.inspiration_def + 1)))
    return (l1, l3)

# PLACEHOLDER: "鼓舞效果额外获得+1/+1"的全局鼓舞修饰机制需要等待所有卡牌均完成之后再实现
class JueXingBuZhiHuo:
    id = 33
    type = "spell"
    hero = "BuZhiHuo"
    name = "觉醒·不知火"
    level_req = 2
    on_play = (lambda s: s.get_permanent_buff("atk", 1),
               lambda s: s.get_permanent_buff("hp", 1),
               lambda s: [s.get_corresponding_hero().listeners.remove(l) for l in s.get_corresponding_hero().listeners if l in s.get_corresponding_hero().original_listeners],
               lambda s: setattr(s.get_corresponding_hero(), "original_listeners", list(_create_juexing_buzhihuo_listeners())),
               lambda s: [s.get_corresponding_hero().listeners.append(l) for l in _create_juexing_buzhihuo_listeners()],
               # TODO: modify every possible inspiration to grant +1 inspiration_atk and +1 inspiration_def,
               )


# PLACEHOLDER: is_beginning_card=false，且"出击加成效果不会因出击而消耗"涉及不知火英雄出击加成消耗机制的修改，目前框架尚不支持
class LiShangZhiWu:
    id = 34
    type = "morph"
    hero = "BuZhiHuo"
    name = "离殇之舞"
    level_req = 3
    atk = 5
    hp = 5


def _jinghongzhiwu_trigger_effect(e, s):
    import random as r
    effect_list = ()    # TODO: 补充完整effect list
    effect = r.choice(effect_list)
    s.owner.game.handle_event(effect)

# PLACEHOLDER: "每个回合开始前随机触发一个效果"涉及复杂的随机效果池，具体效果列表未定义
class JingHongZhiWu:
    id = 35
    type = "morph"
    hero = "BuZhiHuo"
    name = "惊鸿之舞"
    level_req = 3
    atk = 7
    hp = 7
    on_play = (lambda s: setattr(s.get_corresponding_hero(), "listeners", [Listener("begin turn", lambda e, s: True, (_jinghongzhiwu_trigger_effect,))]),)
