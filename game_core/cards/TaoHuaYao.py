import sys
sys.path.insert(0, "E:\more_random_project")
from game_core.action import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
import random as r

class TaoZhiXinXi:
    id = 18
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃之馨息"
    level_req = 1
    require_target = (lambda s: IsDamaged(s.owner.heroes + s.owner.opponent.heroes + [s.owner, s.owner.opponent]),)
    select_target = (lambda s: select_target(s.owner, IsDamaged(s.owner.heroes + s.owner.opponent.heroes + [s.owner, s.owner.opponent]), s),)
    on_play = (lambda s: Heal(5, s, s.owner.selected_targets),)

class HuaXinFeng:
    id = 19
    type = "spell"
    hero = "TaoHuaYao"
    name = "花信风"
    level_req = 1
    require_target = (lambda s: [hero for hero in s.owner.heroes if len([card for card in s.owner.deck if card.hero == hero]) > 0],)
    attributes = (CardAttributes.INSTANT,)
    select_target = (lambda s: select_target(s.owner, [hero for hero in s.owner.heroes if len([card for card in s.owner.deck if card.hero == hero]) > 0], s),)
    on_play = (lambda s: DrawSelectedCardFromDeck(s.owner, r.choice([card for card in s.owner.deck if card.hero == s.owner.selected_targets[0].type_name])),
               lambda s: s.owner.deck.shuffle())

class TaoZhiYaoYao:
    id = 20
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃之夭夭"
    level_req = 2
    attributes = (CardAttributes.NO_FIRE_CONSUMPTION,)
    on_play = (lambda s: setattr(s.get_corresponding_hero(), "inspiration_atk", getattr(s.get_corresponding_hero(), "inspiration_atk") + 2),
               lambda s: setattr(s.get_corresponding_hero(), "inspiration_def", getattr(s.get_corresponding_hero(), "inspiration_def") + 2))
    
class FengShi:
    id = 21
    type = "morph"
    hero = "TaoHuaYao"
    name = "丰实"
    level_req = 2
    atk = 3
    hp = 7
    on_play = (lambda s: setattr(s.get_corresponding_hero(), "listeners", getattr(s.get_corresponding_hero(), "listeners") + 
        (Listener("begin turn", lambda e, s: e.next_player == s.owner, (
            lambda e, s: Heal(3, s, (r.choice(IsDamaged(s.owner.heroes)),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,),),)),)

class TaoYuChunFeng:
    id = 22
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃语春风"
    level_req = 2
    require_target = (lambda s: IsDead(s.owner.heroes),)
    select_target = (lambda s: select_target(s.owner, IsDead(s.owner.heroes), s),)
    on_play = (lambda s: s.owner.selected_targets[0].revive(),
               lambda s: s.owner.selected_targets[0].attributes.append(HeroAttributes.AGILE))

class ShengKai:
    id = 23
    type = "morph"
    hero = "TaoHuaYao"
    name = "盛开"
    level_req = 3
    atk = 4
    hp = 9
    on_play = (lambda s: s.get_corresponding_hero().counter.update({"ShengKai": 2,}),
               lambda s: setattr(s.get_corresponding_hero(), "listeners", getattr(s.get_corresponding_hero(), "listeners") + (
                   Listener("begin turn", lambda e, s: e.next_player == s.owner and s.counter["ShengKai"] > 0 and len(IsDamaged(s.owner.heroes)) > 0, 
                            (lambda e, s: Heal(2, s, (r.choice(IsDamaged(s.owner.heroes),),)),
                             lambda e, s: s.counter.update({"ShengKai": s.counter["ShengKai"] - 1,}))),
               )))