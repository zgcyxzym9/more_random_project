from enums import *
import sys
sys.path.insert(0, "E:\more_random_project")
from game_core.action import *
from game_core.selector import *

class JiBanDeJiaZhi:
    id = 9
    type = "spell"
    hero = "QuanShen"
    name = "羁绊的价值"
    level_req = 1
    on_play = (lambda s: Heal(s.get_corresponding_hero().current_max_hp, s.get_corresponding_hero()),)

class XinZhan:
    id = 10
    type = "attack"
    hero = "QuanShen"
    name = "心斩"
    level_req = 1
    buff_atk = 0
    buff_def = 2
    on_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk + s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def + s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),)
    after_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk - s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def - s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),)

class XinJiGuiChu:
    id = 11
    type = "spell"
    hero = "QuanShen"
    name = "心即归处"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: s.get_corresponding_hero().revive())

class EJiZhan:
    id = 12
    type = "attack"
    hero = "QuanShen"
    name = "恶·即·斩"
    level_req = 2
    buff_atk = 4
    buff_def = 0
    on_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk + s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def + s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),)
    after_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk - s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def - s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),)

class XinJiYiTi:
    id = 13
    type = "morph"
    hero = "QuanShen"
    name = "心技一体"
    level_req = 2
    atk = 3
    hp = 5

class ShouHu:
    id = 14
    type = "attack"
    hero = "QuanShen"
    name = "守护"
    level_req = 2
    buff_atk = 0
    buff_def = 4
    on_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk + s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def + s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),)
    after_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk - s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def - s.get_corresponding_hero().xin_shen_lian_mo_cnt) if s.owner.hand.contain("XinJiYiTi") else None),)
    on_friendly_hero_take_damage = ()
    ## THIS CARD IS WIP DO NOT USE

class XinJianLuanWu:
    id = 15
    type = "morph"
    hero = "QuanShen"
    name = "心剑乱舞"
    level_req = 3
    buff_atk = 4
    buff_def = 9
    after_play = (lambda s: [card.attributes.append(CardAttributes.INSTANT) for card in s.owner.hand if card.hero == "QuanShen" and CardAttributes.INSTANT not in card.attributes],
                  lambda s: [card.attributes.append(CardAttributes.INSTANT) for card in s.owner.deck if card.hero == "QuanShen" and CardAttributes.INSTANT not in card.attributes])

class JueXingQuanShen:
    id = 16
    type = "spell"
    hero = "QuanShen"
    name = "觉醒·犬神"
    level_req = 3
    on_play = (lambda s: setattr(s.get_corresponding_hero(), "on_upgrade", None),
               lambda s: setattr(s.get_corresponding_hero(), "on_self_round_end", 
                                 (lambda s: setattr(s, "original_hp", getattr(s, "original_hp") + 1),
                                  lambda s: setattr(s, "original_atk", getattr(s, "original_atk") + 1),
                                  lambda s: setattr(s, "hp", getattr(s, "hp") + 1),
                                  lambda s: setattr(s, "atk", getattr(s, "atk") + 1),
                                  lambda s: setattr(s, "current_max_hp", getattr(s, "current_max_hp") + 1),
                                  lambda s: s.get_corresponding_hero().revive() if s.get_corresponding_hero().state == "dead" else None),
                                  ),
                lambda s: setattr(s, "original_hp", getattr(s, "original_hp") + 1),
                lambda s: setattr(s, "original_atk", getattr(s, "original_atk") + 1),
                lambda s: setattr(s, "hp", getattr(s, "hp") + 1),
                lambda s: setattr(s, "atk", getattr(s, "atk") + 1),
                lambda s: setattr(s, "current_max_hp", getattr(s, "current_max_hp") + 1),)

class XinShenLianMo:
    id = 17
    type = "spell"
    hero = "QuanShen"
    name = "心身炼磨"
    level_req = 1
    on_play = (lambda s: setattr(s, "original_hp", getattr(s, "original_hp") + 1),
                lambda s: setattr(s, "original_atk", getattr(s, "original_atk") + 1),
                lambda s: setattr(s, "hp", getattr(s, "hp") + 1),
                lambda s: setattr(s, "atk", getattr(s, "atk") + 1),
                lambda s: setattr(s, "current_max_hp", getattr(s, "current_max_hp") + 1),)

    