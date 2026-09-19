import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


def _buyezhiwu_inject(e, s):
    """不夜之舞：战斗牌打出前注入当前鼓舞值并消耗。

    引擎 E2 已移除战斗牌路径的默认鼓舞应用/消耗；
    此监听器把 不知火 的鼓舞效果扩展到战斗牌。
    """
    c = e.event.card
    hero = c.get_corresponding_hero()
    # 鼓舞生效数值经 InspireEvent 广播：觉醒·不知火的「鼓舞效果额外+1/+1」
    # 等监听器在此统一加成（与引擎出击路径同一机制），见 game_core/event.py。
    evt = InspireEvent(s.owner, hero,
                       s.owner.inspiration_atk, s.owner.inspiration_def)
    s.owner.game.handle_event(evt)
    c.buff_atk = getattr(c, 'buff_atk', 0) + evt.atk
    c.buff_def = getattr(c, 'buff_def', 0) + evt.defense
    # 战斗牌使用鼓舞后正常消耗（关键字/特殊效果同样随池结算：
    # 作用于战斗牌对应式神，如「本回合获得贯通」）
    if hero is not None:
        _effects, s.owner.inspiration_effects = s.owner.inspiration_effects, []
        for _f in _effects:
            _f(hero)
    s.owner.inspiration_atk = 0
    s.owner.inspiration_def = 0


def _buyezhiwu_match(e, s):
    """仅拦截本方主动打出的战斗牌（play_card 内 "play card" before 前置广播点）。

    - 形态门控：不知火当前形态不再是此卡时被动失效（仿笨拙/妖刀万华的
      morphed_id 模式；死亡时 morphed_id 清零，同样自动失效）。
    - 前置广播点位于 can_play_card 正式校验与目标选择之后：打出必然发生，不再
      复检 can_play_card（此时鬼火已扣，复检会因鬼火不足误判）。响应通道
      （response=True）不触发：响应牌只施加效果，不消耗鼓舞（既有语义）。
    """
    c = e.event.card
    return (s.morphed_id == BuYeZhiWu.id and
            isinstance(e.event, PlayCardEvent) and
            not e.event.response and
            getattr(c, 'owner', None) == s.owner and
            c.type == "attack")


def _buyezhiwu_on_play(card):
    hero = card.get_corresponding_hero()
    l = Listener("play card", _buyezhiwu_match, (_buyezhiwu_inject,), phase="before")
    # 防止重复叠加（不夜之舞只生效一份）
    hero.listeners = [lst for lst in hero.listeners if getattr(lst, '_tag', '') != 'buyezhiwu']
    l._tag = 'buyezhiwu'
    hero.listeners.append(l)


class BuYeZhiWu:
    id = 28
    type = "morph"
    hero = "BuZhiHuo"
    name = "不夜之舞"
    level_req = 1
    atk = 4
    hp = 5
    on_play = (_buyezhiwu_on_play,)


class ZhenYiZhiGe:
    id = 29
    type = "spell"
    hero = "BuZhiHuo"
    name = "真意之歌"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: setattr(s.owner, "inspiration_atk", s.owner.inspiration_atk + 1),
               lambda s: setattr(s.owner, "inspiration_def", s.owner.inspiration_def + 1),
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
               lambda s: setattr(s.owner, "inspiration_atk", s.owner.inspiration_atk + 2),
               lambda s: setattr(s.owner, "inspiration_def", s.owner.inspiration_def + 2))


def _chuhui_zhiwu_on_play(card):
    hero = card.get_corresponding_hero()
    # 远程：从准备区攻击，不受反击
    if HeroAttributes.RANGED not in hero.attributes:
        hero.attributes.append(HeroAttributes.RANGED)
    # 出击直击敌方牌手 → 抽一张牌。
    # 仅监听 step 层 "hero attack" 广播（携带已解析的 .target），事件层广播无
    # .target，自动去重，且不会把战斗牌攻击误判为出击（战斗牌只走事件层广播）。
    # 形态门控：morphed_id 不再是此卡时被动失效（死亡清零同样失效）。
    l = Listener("hero attack",
                 lambda e, s: (s.morphed_id == ChuHuiZhiWu.id and
                               getattr(e.event, 'target', None) == s.owner.opponent
                               and getattr(e.event, 'hero', None) is not None
                               and e.event.hero.owner == s.owner),
                 (lambda e, s: s.owner.draw(),))
    hero.listeners = [lst for lst in hero.listeners if getattr(lst, '_tag', '') != 'chuhui_zhiwu']
    l._tag = 'chuhui_zhiwu'
    hero.listeners.append(l)


class ChuHuiZhiWu:
    id = 31
    type = "morph"
    hero = "BuZhiHuo"
    name = "初会之舞"
    level_req = 2
    atk = 2
    hp = 6
    on_play = (_chuhui_zhiwu_on_play,)


class XingHuoZhiGe:
    id = 32
    type = "spell"
    hero = "BuZhiHuo"
    name = "星火之歌"
    level_req = 2
    on_play = (lambda s: s.owner.game.handle_event(SummonEvent(s.owner, "JinRanBuYe")),)


def _create_juexing_buzhihuo_listeners():
    """创建觉醒·不知火的 listener 组合，返回初始应加入的 listener 集合。

    l3: 监听 InspireEvent（鼓舞生效，四个消费点统一广播）→ 己方鼓舞额外
        +1/+1（文本「你的鼓舞效果额外获得+1攻击力与+1护盾」）。空池(0/0)
        不加成；event.player 门控只对己方生效。

    「鼓舞：本回合获得贯通」不在此实现：它是鼓舞池效果，打出觉醒时以
    _inspire_penetrate_effect 存入 player.inspiration_effects，由引擎在下
    一次消耗鼓舞（出击/战斗牌）时作用于消耗的式神（见 player.py、game.py
    出击消耗点、_buyezhiwu_inject 战斗牌消耗点）。

    旧实现的回合开始监听「己方回合开始时鼓舞额外+1攻击力」已删除：觉醒能力
    替换式神基础能力（wiki 关键字-觉醒），而觉醒文本中的「己方回合开始时，
    鼓舞：获得+1攻击力」与基础能力逐字相同，保留英雄基础被动即可，不应叠加
    成每回合+2（且基础被动自带 is_alive 门控，旧监听器没有）。
    """
    l3 = Listener("inspire",
                  lambda e, s: (e.event.player is s.owner and s.is_alive
                                and (e.event.atk > 0 or e.event.defense > 0)),
                  (lambda e, s: setattr(e.event, "atk", e.event.atk + 1),
                   lambda e, s: setattr(e.event, "defense", e.event.defense + 1)))
    l3._tag = 'juexing_buzhihuo'
    return (l3,)


def _inspire_penetrate_effect(e):
    """「鼓舞：本回合获得贯通」的池效果：给即将出击（或消耗鼓舞）的式神 e
    叠加贯通，对手回合开始（即己方回合结束）时移除。

    e 已有贯通（如山童先天贯通）时不重复添加、也不挂清理监听器，避免回合末
    把先天贯通洗掉（参照呜丸 _maowei_had_penetrate 的取舍）。
    """
    if HeroAttributes.PENETRATE in e.attributes:
        return
    e.attributes.append(HeroAttributes.PENETRATE)

    def _cleanup(ev, h):
        h.listeners = [l for l in h.listeners if getattr(l, '_tag', '') != 'buzhihuo_inspire_penetrate']
        if HeroAttributes.PENETRATE in h.attributes:
            h.attributes.remove(HeroAttributes.PENETRATE)

    l = Listener("begin turn",
                 lambda ev, h: ev.next_player != h.owner,
                 (_cleanup,))
    l._tag = 'buzhihuo_inspire_penetrate'
    e.listeners.append(l)


def _juexing_buzhihuo_awaken(s):
    """置 is_awakened：本卡 type 为 "spell"，引擎 spell 分支不自动设置，
    与其余觉醒牌一致在 on_play 中手动设置。"""
    s.get_corresponding_hero().is_awakened = True


class JueXingBuZhiHuo:
    id = 33
    type = "spell"
    hero = "BuZhiHuo"
    name = "觉醒·不知火"
    level_req = 2
    on_play = (lambda s: [s.get_corresponding_hero().listeners.remove(l) for l in list(s.get_corresponding_hero().listeners)
                          if getattr(l, '_tag', '') == 'juexing_buzhihuo'],
               lambda s: _juexing_buzhihuo_awaken(s),
               # 觉醒法术自带 +1/+1：式神永久获得卡牌上的力量/生命（wiki 关键字-觉醒，
               # faq：属性增加会保留），实装方式同觉醒·火取魔。
               lambda s: s.get_corresponding_hero().get_permanent_buff("atk", 1),
               lambda s: s.get_corresponding_hero().get_permanent_buff("hp", 1),
               # 觉醒能力替换基础能力（wiki 关键字-觉醒）：觉醒文本「己方回合开始时，
               # 鼓舞：获得+1攻击力」与基础能力逐字相同，保留英雄基础被动即可，
               # 不另挂回合开始监听器（见 _create_juexing_buzhihuo_listeners）；
               # 「你的鼓舞效果额外+1攻击力/+1护盾」由 l3 在 InspireEvent（鼓舞生效
               # 事件）上统一结算。original_listeners 追加觉醒监听器，使觉醒监听器
               # 在气绝/复活后持续（faq：觉醒不因死亡回退）。
               lambda s: setattr(s.get_corresponding_hero(), "original_listeners",
                                 list(s.get_corresponding_hero().original_listeners) + list(_create_juexing_buzhihuo_listeners())),
               lambda s: [s.get_corresponding_hero().listeners.append(l) for l in _create_juexing_buzhihuo_listeners()],
               # 「鼓舞：本回合获得贯通」为鼓舞池效果：入池，下一次消耗鼓舞时
               # 作用于消耗的式神（_inspire_penetrate_effect）
               lambda s: s.owner.inspiration_effects.append(_inspire_penetrate_effect),)


def _lisangzhiwu_on_play(card):
    hero = card.get_corresponding_hero()
    # 出击（step 层广播，event 为 HeroAttack action）时置一次性标记，引擎在出击
    # 消耗鼓舞前检查并跳过消耗（方案A：仿 _suppress_combat_damage）。
    # step 层广播在 special_attack 分支之前触发，因此同时覆盖普通出击与
    # 召唤物（烬染不夜等）的 special_attack 出击；事件层传的是 HeroAttackEvent，
    # isinstance 不匹配，战斗牌/效果攻击也不会误置标记。引擎在出击处理前复位标记，
    # 被拒绝出击（眩晕/鬼火不足等）不会泄漏。
    l = Listener("hero attack",
                 lambda e, s: (s.morphed_id == LiShangZhiWu.id
                               and isinstance(e.event, HeroAttack)
                               and e.event.hero.owner == s.owner),
                 (lambda e, s: setattr(s.owner, '_skip_inspiration_consume', True),))
    hero.listeners = [lst for lst in hero.listeners if getattr(lst, '_tag', '') != 'lisangzhiwu']
    l._tag = 'lisangzhiwu'
    hero.listeners.append(l)


class LiShangZhiWu:
    id = 34
    type = "morph"
    hero = "BuZhiHuo"
    name = "离殇之舞"
    level_req = 3
    atk = 5
    hp = 5
    on_play = (_lisangzhiwu_on_play,)


def _jinghongzhiwu_trigger_effect(e, s):
    # s 为惊鸿之舞对应的英雄(不知火)。effect_list 为可随机触发的效果池。
    # 说明:原描述共 19 个效果,其中依赖框架尚不存在机制的以下几项已按约定跳过、
    # 不放进随机池:不屈/帷幕、召唤烬染不夜、破甲、眩晕,以及"随机获得一种出击效果"
    # 里除贯通(PENETRATE)之外的 远程/不屈/必杀/连击/吸血。因此第 7 项在这里退化为
    # "+2/+2 鼓舞 + 贯通";其余 15 项均以现有事件/字段忠实实现。

    game = s.owner.game
    me = s.owner
    opp = s.owner.opponent

    def my_heroes():
        return [h for h in me.heroes if h.is_alive and h.level > 0]

    def opp_heroes():
        return [h for h in opp.heroes if h.is_alive and h.level > 0]

    # 2. 复活我方全体式神
    def eff_revive_all():
        dead = [h for h in me.heroes if h.state == "dead"]
        if dead:
            game.handle_event(Revive(s, dead))

    # 3. 对敌方牌手造成 4 点伤害
    def eff_damage_opp_player():
        game.handle_event(DealDamage(4, s, [opp]))

    # 4. 我方投射 5 点伤害(打敌方战斗区式神;无战斗区式神则不生效)
    def eff_projection():
        if opp.attack_zone is not None:
            game.handle_event(DealDamage(5, s, [opp.attack_zone]))

    # 5. 我方牌手回复 6 点血量
    def eff_heal_player():
        game.handle_event(Heal(6, s, [me]))

    # 6. 对敌方全体式神造成 2 点伤害
    def eff_damage_all_opp():
        targets = opp_heroes()
        if targets:
            game.handle_event(DealDamage(2, s, targets))

    # 7. 获得 +2/+2 鼓舞,并获得贯通(唯一可实现的出击效果)
    def eff_inspire_and_penetrate():
        me.inspiration_atk += 2
        me.inspiration_def += 2
        if HeroAttributes.PENETRATE not in s.attributes:
            s.attributes.append(HeroAttributes.PENETRATE)

    # 8. 我方全体式神 +1 攻 +1 血 +1 甲
    def eff_all_plus_111():
        targets = my_heroes()
        if targets:
            game.handle_event(GiveBuff("atk", 1, s, targets))
            game.handle_event(GiveBuff("hp", 1, s, targets))
            game.handle_event(GiveBuff("defense", 1, s, targets))

    # 9. 我方战斗区式神 +2 攻 +2 血 +2 甲
    def eff_battlezone_plus_222():
        if me.attack_zone is not None and me.attack_zone.is_alive:
            tz = [me.attack_zone]
            game.handle_event(GiveBuff("atk", 2, s, tz))
            game.handle_event(GiveBuff("hp", 2, s, tz))
            game.handle_event(GiveBuff("defense", 2, s, tz))

    # 10. 我方随机两个式神永久获得 +1 攻 +1 血
    def eff_two_random_permanent():
        from game_core.selector import random_sample as _rs
        pool = my_heroes()
        for h in _rs(me, pool, min(2, len(pool)), context="惊鸿之舞: 随机两个式神永久+1/+1"):
            h.get_permanent_buff("atk", 1)
            h.get_permanent_buff("hp", 1)

    # 11. 我方抽一张牌
    def eff_draw():
        me.draw()

    # 12. 我方获得一点鬼火
    def eff_gain_fire():
        me.fire_cnt += 1

    # 16. 我方攻击力最高式神 +2 攻并获得贯通
    def eff_highest_atk_penetrate():
        pool = my_heroes()
        if pool:
            top = max(pool, key=lambda h: h.atk)
            game.handle_event(GiveBuff("atk", 2, s, [top]))
            if HeroAttributes.PENETRATE not in top.attributes:
                top.attributes.append(HeroAttributes.PENETRATE)

    # 17. 我方全体获得迅捷
    def eff_all_agile():
        for h in my_heroes():
            if HeroAttributes.AGILE not in h.attributes:
                h.attributes.append(HeroAttributes.AGILE)

    # 18. 敌方全体式神降两点攻击
    def eff_opp_all_minus2_atk():
        targets = opp_heroes()
        if targets:
            game.handle_event(GiveBuff("atk", -2, s, targets))

    # 19. 我方牌手获得 8 点护甲
    def eff_player_plus8_armor():
        me.defense += 8

    effect_list = (
        ("复活我方全体式神",               eff_revive_all),             # 2
        ("对敌方牌手造成4点伤害",           eff_damage_opp_player),      # 3
        ("投射5点伤害",                    eff_projection),             # 4
        ("我方牌手回复6点血量",             eff_heal_player),            # 5
        ("对敌方全体式神造成2点伤害",       eff_damage_all_opp),         # 6
        ("鼓舞+2/+2并获得贯通",            eff_inspire_and_penetrate),  # 7
        ("我方全体式神+1/+1/+1甲",         eff_all_plus_111),           # 8
        ("战斗区式神+2/+2/+2甲",           eff_battlezone_plus_222),    # 9
        ("随机两个式神永久+1/+1",          eff_two_random_permanent),   # 10
        ("抽一张牌",                       eff_draw),                   # 11
        ("获得一点鬼火",                   eff_gain_fire),              # 12
        ("攻击力最高的式神+2攻并获得贯通",  eff_highest_atk_penetrate),  # 16
        ("我方全体获得迅捷",               eff_all_agile),              # 17
        ("敌方全体式神-2攻",               eff_opp_all_minus2_atk),     # 18
        ("我方牌手获得8点护甲",            eff_player_plus8_armor),     # 19
    )
    # 使用 selector 中的通用随机函数以支持推理模式下的手动同步
    from game_core.selector import random_choice as _rc
    _, chosen = _rc(me, effect_list, context="惊鸿之舞: 回合开始随机触发效果")
    chosen()

def _jinghongzhiwu_on_play(card):
    hero = card.get_corresponding_hero()
    # 形态"额外获得"形态效果：保留英雄基础被动，追加本形态的回合开始监听器。
    # 按 _tag 去重防止重复结附同形态。
    # 形态门控：morphed_id 不再是此卡时被动失效（死亡清零同样失效）。
    hero.listeners = [lst for lst in hero.listeners if getattr(lst, '_tag', '') != 'jinghongzhiwu']
    l = Listener("begin turn",
                 lambda e, s: (s.morphed_id == JingHongZhiWu.id and
                               e.next_player == s.owner),
                 (_jinghongzhiwu_trigger_effect,))
    l._tag = 'jinghongzhiwu'
    hero.listeners.append(l)


class JingHongZhiWu:
    id = 35
    type = "morph"
    hero = "BuZhiHuo"
    name = "惊鸿之舞"
    level_req = 3
    atk = 7
    hp = 7
    on_play = (_jinghongzhiwu_on_play,)
