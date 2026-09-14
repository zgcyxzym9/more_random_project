import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.selector import _is_inference_mode  # 星号导入不含下划线名
from game_core.manager import Listener

class TaoZhiXinXi:
    id = 18
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃之馨息"
    level_req = 1
    require_target = (lambda s: IsDamaged(s.owner.heroes + s.owner.opponent.heroes + [s.owner, s.owner.opponent]),)
    select_target = (lambda s: select_target(s.owner, IsDamaged(s.owner.heroes + s.owner.opponent.heroes + [s.owner, s.owner.opponent]), s),)
    on_play = (lambda s: Heal(5, s, s.owner.selected_targets),)

def _huaxinfeng_deck_card(s):
    """花信风的随机抽牌目标。

    推理模式下对手牌库是假的（WuShiZhiQuan*32），按式神过滤后必为空，
    select_random_target 的空列表分支会弹输入且只接受精确类名，实战中
    无法完成——此时默认抽一张白板牌 WuShiZhiQuan（优先取牌库中实际
    存在的张，便于真实从牌库移除），并打警告。训练模式行为不变。
    """
    cards = [c for c in s.owner.deck.cards
             if c.hero == s.owner.selected_targets[0].type_name]
    if cards:
        return select_random_target(s.owner, cards,
                                    context="花信风: 从牌库随机抽一张牌")
    if _is_inference_mode(s.owner):
        print("[Warning] 花信风: 推理模式牌库无该式神的牌，默认抽 WuShiZhiQuan")
        in_deck = [c for c in s.owner.deck.cards if c.eng_name == "WuShiZhiQuan"]
        if in_deck:
            return in_deck[0]
        from game_core.card import Card
        return Card.GetCard("WuShiZhiQuan")
    return select_random_target(s.owner, [],
                                context="花信风: 从牌库随机抽一张牌")


class HuaXinFeng:
    id = 19
    type = "spell"
    hero = "TaoHuaYao"
    name = "花信风"
    level_req = 1
    require_target = (lambda s: [hero for hero in s.owner.heroes if len([card for card in s.owner.deck.cards if card.get_corresponding_hero() == hero]) > 0],)
    attributes = (CardAttributes.INSTANT,)
    select_target = (lambda s: select_target(s.owner, [hero for hero in s.owner.heroes if len([card for card in s.owner.deck.cards if card.get_corresponding_hero() == hero]) > 0], s),)
    on_play = (lambda s: DrawSelectedCardFromDeck(s.owner, _huaxinfeng_deck_card(s)),
               lambda s: s.owner.deck.shuffle())

class TaoZhiYaoYao:
    id = 20
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃之夭夭"
    level_req = 2
    attributes = (CardAttributes.NO_FIRE_CONSUMPTION,)
    on_play = (lambda s: setattr(s.owner, "inspiration_atk", s.owner.inspiration_atk + 2),
               lambda s: setattr(s.owner, "inspiration_def", s.owner.inspiration_def + 2))
    
class FengShi:
    id = 21
    type = "morph"
    hero = "TaoHuaYao"
    name = "丰实"
    level_req = 2
    atk = 3
    hp = 7
    on_play = (lambda s: s.get_corresponding_hero().listeners.append(
        Listener("begin turn", lambda e, s: e.next_player == s.owner, (
            lambda e, s: Heal(3, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="丰实: 回合开始随机治疗一个受伤式神"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,),)),
        lambda s: Heal(3, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="丰实: 入场随机治疗一个受伤式神"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,)

class TaoYuChunFeng:
    id = 22
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃语春风"
    level_req = 2
    require_target = (lambda s: IsDead(s.owner.heroes),)
    select_target = (lambda s: select_target(s.owner, IsDead(s.owner.heroes), s),)
    on_play = (lambda s: Revive(s, s.owner.selected_targets),
               lambda s: s.owner.selected_targets[0].attributes.append(HeroAttributes.AGILE))

class ShengKai:
    id = 23
    type = "morph"
    hero = "TaoHuaYao"
    name = "盛开"
    level_req = 3
    atk = 4
    hp = 9
    on_play = (lambda s: s.get_corresponding_hero().listeners.append(
        Listener("begin turn", lambda e, s: e.next_player == s.owner and len(IsDamaged(s.owner.heroes)) > 0, (
            lambda e, s: Heal(2, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="盛开: 回合开始随机治疗"),)),
            lambda e, s: Heal(2, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="盛开: 回合开始随机治疗"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,
            lambda e, s: Heal(2, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="盛开: 回合开始随机治疗"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,
        ))),
        lambda s: Heal(2, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="盛开: 入场随机治疗"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,
        lambda s: Heal(2, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="盛开: 入场随机治疗"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,
        lambda s: Heal(2, s, (select_random_target(s.owner, IsDamaged(s.owner.heroes), context="盛开: 入场随机治疗"),)) if len(IsDamaged(s.owner.heroes)) > 0 else None,
    )

class TaoHuaZhuoZhuo:
    id = 24
    type = "spell"
    hero = "TaoHuaYao"
    name = "桃华灼灼"
    level_req = 3
    attributes = (CardAttributes.INSTANT, CardAttributes.CAN_PLAY_WHEN_DEAD)
    on_play = (lambda s: Revive(s, [h for h in s.owner.heroes if not h.is_alive]),
               lambda s: [h.attributes.append(HeroAttributes.AGILE) for h in s.owner.heroes if HeroAttributes.AGILE not in h.attributes])


# ═══════════════════════════════════════════════════════════════════════════════
#  桃花妖 缺失卡牌：25 觉醒·桃花妖 / 26 繁花似锦 / 27 桃红簇簇
# ═══════════════════════════════════════════════════════════════════════════════
from game_core.heroes import _taohuayao_heal_condition


def _juexingtaohuayao_on_play(s):
    """觉醒·桃花妖：觉醒（替换被动为永久 +2/+2），然后治疗目标 5 点。

    先觉醒再治疗，保证本卡的治疗也能触发觉醒后的被动。
    """
    hero = s.get_corresponding_hero()
    # 移除旧被动（治疗/复活 +1 攻击力，临时加成），替换为觉醒被动（永久 +2 攻击力/+2 生命值）
    hero.listeners = [l for l in hero.listeners if getattr(l, '_tag', '') != 'taohuayao_passive']
    hero.listeners.append(Listener("heal", _taohuayao_heal_condition, (
        lambda e, s2: [t.get_permanent_buff("atk", 2) for t in e.event.target if t in s2.owner.heroes],
        lambda e, s2: [t.get_permanent_buff("hp", 2) for t in e.event.target if t in s2.owner.heroes],
    )))
    hero.listeners.append(Listener("after revive", _taohuayao_heal_condition, (
        lambda e, s2: [t.get_permanent_buff("atk", 2) for t in e.event.target if t in s2.owner.heroes],
        lambda e, s2: [t.get_permanent_buff("hp", 2) for t in e.event.target if t in s2.owner.heroes],
    )))
    return Heal(5, s, s.owner.selected_targets)


class JueXingTaoHuaYao:
    id = 25
    type = "spell"
    hero = "TaoHuaYao"
    name = "觉醒·桃花妖"
    level_req = 3
    require_target = (lambda s: IsDamaged(s.owner.heroes + s.owner.opponent.heroes + [s.owner, s.owner.opponent]),)
    select_target = (lambda s: select_target(s.owner, IsDamaged(s.owner.heroes + s.owner.opponent.heroes + [s.owner, s.owner.opponent]), s),)
    on_play = (_juexingtaohuayao_on_play,)


def _taohongcucu_remove(hero):
    """移除 桃红簇簇/繁花似锦 形态：恢复基础身材+永久加成，清理所有相关回调。

    幂等：可被保护触发、式神死亡、重复调用多次执行。
    """
    in_morph = getattr(hero, '_taohongcucu_active', False)
    if in_morph:
        hero._taohongcucu_active = False
        hero.morphed_id = 0
        hero.atk = hero.original_atk + hero.perm_buff_atk
        hero.current_max_hp = hero.original_hp + hero.perm_buff_hp
        if hero.hp > hero.current_max_hp:
            hero.hp = hero.current_max_hp
    # 清理 move 监听器
    hero.listeners = [l for l in hero.listeners if getattr(l, '_tag', '') != 'taohongcucu']
    # 清理所有友方式神上的保护回调
    for ally in hero.owner.heroes:
        ally.on_before_death = tuple(cb for cb in ally.on_before_death if getattr(cb, '_tag', '') != 'taohongcucu_protect')
    # 清理 on_death 自清理
    hero.on_death = [cb for cb in hero.on_death if getattr(cb, '_tag', '') != 'taohongcucu_death']


def _taohongcucu_on_play(s):
    """桃红簇簇（及默认打出桃红簇簇的繁花似锦）形态效果。

    1. 己方式神进入/离开战斗区时恢复 2 生命值（move 监听器）
    2. 己方准备区式神受到致命伤害时免疫（幸存 1 血）并移除本形态
    3. 羁绊：进场时若樱花妖在场且存活，为所有己方式神恢复 2 生命值
    """
    hero = s.get_corresponding_hero()
    player = s.owner
    if getattr(hero, '_taohongcucu_active', False):
        return  # 已在桃红簇簇形态，重复打出不叠加

    hero._taohongcucu_active = True

    # 1. 进出战斗区 → 恢复 2 生命值
    move_l = Listener("move",
                      lambda e, s2: (e.event.hero.owner == s2.owner
                                     and (e.event.to_zone == "battle" or e.event.from_zone == "battle")),
                      (lambda e, s2: Heal(2, s2, (e.event.hero,)),))
    move_l._tag = 'taohongcucu'
    hero.listeners.append(move_l)

    # 2. 准备区式神致命伤害保护
    def _make_protector(h):
        def _protect(ally):
            # 仅保护准备区（非战斗区、非气绝）的友方式神
            if not ally.is_alive or ally.state != "pending":
                return False
            if getattr(ally, 'is_summoned', False):
                return False  # 召唤物离场而非气绝，无需保护
            # 免疫此次伤害：幸存 1 血，然后移除桃红簇簇形态
            ally.hp = 1
            _taohongcucu_remove(h)
            return True
        _protect._tag = 'taohongcucu_protect'
        return _protect

    for ally in player.heroes:
        ally.on_before_death = tuple(ally.on_before_death) + (_make_protector(hero),)

    # 式神死亡时清理（morphed_id 已复位，_taohongcucu_remove 会跳过身材重置但仍清理回调）
    def _on_death(h):
        _taohongcucu_remove(h)
    _on_death._tag = 'taohongcucu_death'
    # on_death 可能是 tuple（桃花妖类定义），统一转为 list 后追加
    hero.on_death = list(hero.on_death) + [_on_death]

    # 3. 羁绊：樱花妖在场时为所有己方式神恢复 2 生命值
    sakura = [h for h in player.heroes if "樱花" in h.name and h.is_alive and h.level > 0]
    if sakura:
        return Heal(2, sakura[0], player.heroes)
    return None


class TaoHongCuCu:
    id = 27
    type = "morph"
    hero = "TaoHuaYao"
    name = "桃红簇簇"
    level_req = 2
    atk = 3
    hp = 6
    on_play = (_taohongcucu_on_play,)


class FanHuaSiJin:
    id = 26
    type = "morph"
    hero = "TaoHuaYao"
    name = "繁花似锦"
    level_req = 2
    atk = 3
    hp = 6
    # 选择使用一项：桃花妖-桃红簇簇；樱花妖-落英缤纷。
    # 樱花妖（落英缤纷）尚未实现，暂默认打出 桃红簇簇 形态。
    on_play = (_taohongcucu_on_play,)