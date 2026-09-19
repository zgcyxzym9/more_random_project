import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener, CardEnhance

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
    # 增强效果由 心技一体 (#13) 的形态监听器注入，此处不重复判断

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
    # 增强效果由 心技一体 (#13) 的形态监听器注入，此处不重复判断

def _xinjiyiti_enhance(card):
    """心技一体 (#13) 打出：冻结本局已使用的心身炼磨次数作为增强值。

    增强条件在打出时结算：此后即使再使用心身炼磨，也不会追加加成。
    效果为 犬神 的战斗牌获得 +bonus 攻击力/+bonus 护甲。
    """
    hero = card.get_corresponding_hero()
    bonus = hero.counter["xin_shen_lian_mo"]
    if bonus <= 0:
        return  # 本局未使用过心身炼磨，增强不生效

    def _inject(e, s):
        """在战斗牌被打出前，把增强值注入其 buff_atk/buff_def。

        不恢复 buff_atk/buff_def：引擎把战斗牌力量折入 combat_buff_atk、
        战后清零，式神面板不会泄漏注入值；卡牌上保留注入值即
        「犬神战斗牌永久 +bonus」的增强语义。
        """
        c = e.event.card
        c.buff_atk = getattr(c, 'buff_atk', 0) + bonus
        c.buff_def = getattr(c, 'buff_def', 0) + bonus

    l = Listener("play card",
                 lambda e, s: (isinstance(e.event, PlayCardEvent) and
                               not e.event.response and
                               getattr(e.event.card, 'owner', None) == s.owner and
                               e.event.card.hero == "QuanShen" and
                               e.event.card.type == "attack"),
                 (_inject,), phase="before")
    # 防止重复叠加（心技一体只生效一份）
    hero.listeners = [lst for lst in hero.listeners if getattr(lst, '_tag', '') != 'xinjiyiti']
    l._tag = 'xinjiyiti'
    hero.listeners.append(l)


class XinJiYiTi:
    id = 13
    type = "morph"
    hero = "QuanShen"
    name = "心技一体"
    level_req = 2
    atk = 3
    hp = 5
    attributes = (CardAttributes.ENHANCE,)
    on_play = (_xinjiyiti_enhance,)

class ShouHu:
    id = 14
    type = "attack"
    hero = "QuanShen"
    name = "守护"
    level_req = 2
    buff_atk = 0
    buff_def = 4
    # 增强效果由 心技一体 (#13) 的形态监听器注入，此处不重复判断
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    # 响应：敌方式神攻击己方式神（目标不是犬神本人）时自动打出，犬神移入战斗区拦截。
    # 只拦截攻击式神，不拦直击牌手（target 须为 Hero）。
    response_condition = (lambda s, event, target: (
        event.hero.owner is s.owner.opponent
        and getattr(target, "entity_type", None) == "hero"
        and target.owner is s.owner
        and target is not s.get_corresponding_hero()
    ),)
    on_response = (lambda s, event, target: _shouhu_on_response(s, event, target),)

def _shouhu_on_response(s, event, target):
    """守护：犬神移入战斗区拦截本次攻击；追猎攻击者把攻击目标重定向到犬神。

    目标重定向走 selected_targets 通道：_resolve_attack_target 在 HUNTING 时读取它，
    play_card / step 末尾都会清空，无残留。不修改 event.target——handle_event 的
    deal damage 等分支把 event.target 当列表用，且 step 二次广播会让读它的监听器双触发。
    """
    hero = s.get_corresponding_hero()
    if hero.state != "attacking":
        hero.move_to_battle()
    if HeroAttributes.HUNTING in event.hero.attributes:
        event.player.selected_targets = [hero]

def _xinjianluanwu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero.morphed_id == s.id:
        return
    cards = s.owner.hand.cards + s.owner.deck.cards
    for card in cards:
        if card.hero == "QuanShen":
            card.attributes.append(CardAttributes.INSTANT)
    def _on_death(h):
        for card in cards:
            if card.hero == "QuanShen" and CardAttributes.INSTANT in card.attributes:
                card.attributes.remove(CardAttributes.INSTANT)
        h.on_death = [e for e in h.on_death if e is not _on_death]
    hero.on_death.append(_on_death)

class XinJianLuanWu:
    id = 15
    type = "morph"
    hero = "QuanShen"
    name = "心剑乱舞"
    level_req = 3
    atk = 4
    hp = 9
    on_play = (_xinjianluanwu_on_play,)

class JueXingQuanShen:
    id = 16
    type = "spell"
    hero = "QuanShen"
    name = "觉醒·犬神"
    level_req = 3
    on_play = (lambda s: setattr(s.get_corresponding_hero(), "on_upgrade", None),
               lambda s: s.get_corresponding_hero().listeners.append(
                   Listener("begin turn",
                            lambda e, s: e.next_player != s.owner,
                            (lambda e, s: s.get_permanent_buff("hp", 1),
                             lambda e, s: s.get_permanent_buff("atk", 1),
                             lambda e, s: s.revive() if s.state == "dead" else None))
               ),
               lambda s: s.get_corresponding_hero().original_listeners.append(
                   Listener("begin turn",
                            lambda e, s: e.next_player != s.owner,
                            (lambda e, s: s.get_permanent_buff("hp", 1),
                             lambda e, s: s.get_permanent_buff("atk", 1),
                             lambda e, s: s.revive() if s.state == "dead" else None))
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
    enhance = (CardEnhance(cond=lambda s: s.get_corresponding_hero().level == 2, attributes=(CardAttributes.INSTANT,),),
               CardEnhance(cond=lambda s: s.get_corresponding_hero().level == 3, attributes=(CardAttributes.NO_FIRE_CONSUMPTION,),),)

    