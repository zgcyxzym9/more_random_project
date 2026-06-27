import sys
sys.path.insert(0, "E:\more_random_project")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener

# Counter used for number of XinShenLianMo used, used for attack cards

class JiBanDeJiaZhi:
    id = 9
    type = "spell"
    hero = "QuanShen"
    name = "羁绊的价值"
    level_req = 1
    on_play = (lambda s: Heal(s.get_corresponding_hero().current_max_hp, s, (s.get_corresponding_hero(),)),)

class XinZhan:
    id = 10
    type = "attack"
    hero = "QuanShen"
    name = "心斩"
    level_req = 1
    buff_atk = 0
    buff_def = 2
    on_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk + s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def + s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),)
    after_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk - s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def - s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),)

class XinJiGuiChu:
    id = 11
    type = "spell"
    hero = "QuanShen"
    name = "心即归处"
    level_req = 2
    attributes = (CardAttributes.INSTANT, CardAttributes.CAN_PLAY_WHEN_DEAD)
    require_target = (lambda s: [s.get_corresponding_hero()] if s.get_corresponding_hero().hp <= 0 else [],)
    on_play = (lambda s: s.get_corresponding_hero().revive(),)

class EJiZhan:
    id = 12
    type = "attack"
    hero = "QuanShen"
    name = "恶·即·斩"
    level_req = 2
    buff_atk = 4
    buff_def = 0
    on_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk + s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def + s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),)
    after_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk - s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def - s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),)

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
    on_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk + s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def + s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),)
    after_play = (lambda s: (s.__setattr__('buff_atk', s.buff_atk - s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),
                lambda s: (s.__setattr__('buff_def', s.buff_def - s.get_corresponding_hero().counter["xin_shen_lian_mo"]) if s.owner.hand.contain("XinJiYiTi") else None),)
    listeners = (Listener("hero attack event", lambda e, s: e.event.player == s.owner.opponent and s.owner.attack_zone is not None,
                          (lambda e, s: _shouhu_response(e, s),)),)

def _shouhu_response(e, s):
    if not s.owner.game.can_play_card(s.owner, s):
        return
    setattr(e.event, "revert", True)
    e.event.player.opponent.advance_hero(e.event.hero)
    if CardAttributes.NO_FIRE_CONSUMPTION not in s.attributes:
        if CardAttributes.INSTANT in s.attributes and not s.owner.instant_used:
            s.owner.instant_used = True
        else:
            s.owner.fire_cnt -= 1
    s.owner.game.play_card(s.owner, s)

class XinJianLuanWu:
    id = 15
    type = "morph"
    hero = "QuanShen"
    name = "心剑乱舞"
    level_req = 3
    atk = 4
    hp = 9
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
                                 (lambda s: s.get_permanent_buff("hp", 1),
                                  lambda s: s.get_permanent_buff("atk", 1),
                                  lambda s: s.revive() if s.state == "dead" else None),
                                  ),
                lambda s: s.get_corresponding_hero().get_permanent_buff("hp", 1),
                lambda s: s.get_corresponding_hero().get_permanent_buff("atk", 1))

class XinShenLianMo:
    id = 17
    type = "spell"
    hero = "QuanShen"
    name = "心身炼磨"
    level_req = 1
    on_play = (lambda s: s.get_corresponding_hero().get_permanent_buff("hp", 1),
                lambda s: s.get_corresponding_hero().get_permanent_buff("atk", 1),
                lambda s: s.get_corresponding_hero().counter.update({"xin_shen_lian_mo": s.get_corresponding_hero().counter["xin_shen_lian_mo"] + 1}),)

    