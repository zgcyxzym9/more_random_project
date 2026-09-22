import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener


def _fire_heroes_except(hero, player, require_alive=True):
    """返回 player 除 hero 外的红莲派系（type == "fire"）式神。

    红莲派系在 heroes.py 中以 type == "fire" 标记；require_alive 为 True 时
    仅统计未气绝（is_alive）的式神。
    """
    result = []
    for h in player.heroes:
        if h is hero:
            continue
        if require_alive and not h.is_alive:
            continue
        if h.type == "fire":
            result.append(h)
    return result


# 夜袭：你的出击加成效果在使用此牌时也会生效。
# 引擎的战斗牌路径不应用、不消耗鼓舞（game.py "attack" 分支：交由不夜之舞等
# 卡牌监听器负责），故在自身 on_play 中把牌手当前鼓舞叠入 buff_atk/buff_def
# （引擎随即将这些数值结入本次战斗，atk 在战后还原、def 同引擎出击路径保留），
# 并按出击语义消耗鼓舞。不仿不夜之舞的 "play card" 监听器：那是形态常驻被动
# （作用于之后打出的全部战斗牌），且在 step 广播点（can_play_card 校验之前）
# 注入，打出被拒也会消耗鼓舞；夜袭只作用于自身结算，on_play 直接注入即可。
def _yexi_on_play(s):
    # 鼓舞生效数值经 InspireEvent 广播：觉醒·不知火的「鼓舞效果额外+1/+1」
    # 等监听器在此统一加成（与引擎出击路径同一机制），见 game_core/event.py。
    evt = InspireEvent(s.owner, s.get_corresponding_hero(),
                       s.owner.inspiration_atk, s.owner.inspiration_def)
    s.owner.game.handle_event(evt)
    s.buff_atk = getattr(s, "buff_atk", 0) + evt.atk
    s.buff_def = getattr(s, "buff_def", 0) + evt.defense
    # 战斗牌使用鼓舞后正常消耗（与引擎出击路径语义一致）
    s.owner.inspiration_atk = 0
    s.owner.inspiration_def = 0


class YeXi:
    id = 36
    type = "attack"
    hero = "HuoQuMo"
    name = "夜袭"
    level_req = 1
    buff_atk = 1
    buff_def = 1
    on_play = (_yexi_on_play,)


# 蛮勇剑豪：贯通 若你有其他攻击力大于等于6的式神，获得+3攻击力。
# 形态牌在 "morph" 分支里会先执行 on_play，再用 card.atk / card.hp 覆盖英雄身材，
# 故把最终身材写回 card.atk / card.hp（每次按基础值重算，避免累加）。
def _manyong_on_play(s):
    hero = s.get_corresponding_hero()
    if HeroAttributes.PENETRATE not in hero.attributes:
        hero.attributes.append(HeroAttributes.PENETRATE)
    bonus = 3 if any(h is not hero and h.is_alive and h.atk >= 6 for h in s.owner.heroes) else 0
    s.atk = 3 + bonus
    s.hp = 6

class ManYongJianHao:
    id = 37
    type = "morph"
    hero = "HuoQuMo"
    name = "蛮勇剑豪"
    level_req = 1
    atk = 3
    hp = 6
    on_play = (_manyong_on_play,)


# 任侠：瞬发 使一个己方式神本回合获得追猎。
# 增强：若己方式神都为红莲派系，该式神额外获得3攻击力。
def _renxia_grant_hunting(hero):
    if HeroAttributes.HUNTING not in hero.attributes:
        hero.attributes.append(HeroAttributes.HUNTING)
    # 追猎为"本回合"效果：己方回合结束(对手回合开始)时移除，并清掉这个临时 listener
    cleanup = Listener("begin turn",
                       lambda e, s: e.next_player != s.owner,
                       (lambda e, s: s.attributes.remove(HeroAttributes.HUNTING) if HeroAttributes.HUNTING in s.attributes else None,
                        lambda e, s: s.listeners.remove(cleanup) if cleanup in s.listeners else None))
    hero.listeners.append(cleanup)


def _renxia_enhance_atk(hero):
    """任侠增强：下次攻击 +3 攻击力，攻击后移除（若本回合未攻击则由回合结束清理）。"""
    hero.round_buff_atk += 3

    def on_attack(event, hero_entity):
        # 此 listener 在 broadcast("hero attack") 时触发，
        # 发生在 attack() 执行之前，因此 round_buff_atk 仍有效。
        # 在攻击结束后的 _post_attack_cleanup 中清理 buff。
        def remove_after_attack(source, damage):
            hero_entity.round_buff_atk = max(0, hero_entity.round_buff_atk - 3)
            hero_entity.on_after_damage = tuple(
                cb for cb in hero_entity.on_after_damage if cb is not remove_after_attack
            )

        hero_entity.on_after_damage = hero_entity.on_after_damage + (remove_after_attack,)
        # 一次性 listener：只对首次攻击生效
        if cleanup in hero_entity.listeners:
            hero_entity.listeners.remove(cleanup)

    cleanup = Listener("hero attack",
                       lambda e, s: e.event.hero is s,
                       (on_attack,))
    hero.listeners.append(cleanup)


class RenXia:
    id = 38
    type = "spell"
    hero = "HuoQuMo"
    name = "任侠"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.heroes if h.is_alive], s),)
    on_play = (lambda s: _renxia_grant_hunting(s.owner.selected_targets[0]),
               lambda s: _renxia_enhance_atk(s.owner.selected_targets[0]) if all(h.type == "fire" for h in s.owner.heroes) else None)


# 鵺之火：使1个已方式神获得1力量和1生命。
# 进场和己方回合开始时，若己方任一式神的力量为场上最大或同为最大，抽一张牌。
def _yezhi_should_draw(player):
    """判断：己方任一存活且已升级式神的力量是否为场上（含对方）最大或同为最大。

    “场上”指双方所有存活且已升级(level>0)的式神，召唤物亦计入；力量即 atk。
    """
    me = [h for h in player.heroes if h.is_alive and h.level > 0]
    opp = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
    all_on_field = me + opp
    if not all_on_field:
        return False
    max_atk = max(h.atk for h in all_on_field)
    return any(h.atk == max_atk for h in me)


def _yezhi_draw(player):
    """满足抽牌条件则抽一张牌。"""
    if _yezhi_should_draw(player):
        player.game.handle_event(DrawEvent(player, 1))


def _yezhi_on_play_extra(card):
    """进场：触发一次抽牌判定；并挂上每回合开始的抽牌判定监听器。

    监听器挂在牌手身上：幻境区归属牌手，幻境离场判定随牌手的 listeners 走，
    不依赖火取魔自身的存活状态。
    每次己方回合开始时检查该幻境是否仍在本方幻境区（被摧毁后不再判定）。
    """
    _yezhi_draw(card.owner)
    l = Listener("begin turn",
                 lambda e, s: e.next_player == s and card in s.illusion_zone,
                 (lambda e, s: _yezhi_draw(s),))
    card.owner.listeners.append(l)


class YeZhiHuo:
    id = 39
    type = "illusion"
    hero = "HuoQuMo"
    name = "鵺之火"
    level_req = 2
    durability = 6
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.heroes if h.is_alive], s),)
    # 进场先结算 +1/+1（可能使该式神成为场上最大），再触发抽牌判定
    on_play = (lambda s: GiveBuff("atk", 1, s.get_corresponding_hero(), [s.owner.selected_targets[0]]),
               lambda s: GiveBuff("hp", 1, s.get_corresponding_hero(), [s.owner.selected_targets[0]]),
               lambda s: _yezhi_on_play_extra(s))


# 叶隐剑豪：贯通 增强：你每有一个其他未气绝的红莲派系式神，此牌便获得1攻击力和1生命值。
def _yeyin_on_play(s):
    hero = s.get_corresponding_hero()
    if HeroAttributes.PENETRATE not in hero.attributes:
        hero.attributes.append(HeroAttributes.PENETRATE)
    cnt = len(_fire_heroes_except(hero, s.owner))
    s.atk = 4 + cnt
    s.hp = 4 + cnt

class YeYinJianHao:
    id = 40
    type = "morph"
    hero = "HuoQuMo"
    name = "叶隐剑豪"
    level_req = 2
    atk = 4
    hp = 4
    on_play = (_yeyin_on_play,)


# 觉醒·火取魔：火取魔获得+1/+1（觉醒标准加成），己方其他红莲派系式神获得1攻击力和1生命值。
# 描述后半"本回合当你使用第二张红莲派系式神的牌时，火取魔获得1攻击力和1生命值"
# 即火取魔本体被动，已由 heroes.py 中的 HuoQuMo listeners 常驻实现，此处无需重复。
class JueXingHuoQuMo:
    id = 41
    type = "spell"
    hero = "HuoQuMo"
    name = "觉醒·火取魔"
    level_req = 2
    on_play = (lambda s: s.get_corresponding_hero().get_permanent_buff("atk", 1),
               lambda s: s.get_corresponding_hero().get_permanent_buff("hp", 1),
               lambda s: GiveBuff("atk", 1, s.get_corresponding_hero(), _fire_heroes_except(s.get_corresponding_hero(), s.owner)),
               lambda s: GiveBuff("hp", 1, s.get_corresponding_hero(), _fire_heroes_except(s.get_corresponding_hero(), s.owner)))


# 义盟：鼓舞：获得+X力量，+X护甲。X为己方存活的红莲派系式神数量的2倍。
# 鼓舞叠加到牌手 inspiration 池，下一次己方式神出击时随攻击消耗（引擎 hero attack 分支自动应用）。
def _alive_fire_heroes(player):
    """己方存活的红莲派系式神（含火取魔自身）。"""
    return [h for h in player.heroes if h.is_alive and h.type == "fire"]


def _yimeng_on_play(card):
    x = 2 * len(_alive_fire_heroes(card.owner))
    card.owner.inspiration_atk += x
    card.owner.inspiration_def += x


class YiMeng:
    id = 42
    type = "spell"
    hero = "HuoQuMo"
    name = "义盟"
    level_req = 3
    on_play = (_yimeng_on_play,)


# 火取剑豪：增强：获得己方所有其他红莲派系式神的攻击力和生命值，并获得他们的关键词能力。
# 关键词能力即 hero.attributes 中的 HeroAttributes（如贯通 PENETRATE、迅捷 AGILE）。
def _huoqujianhao_on_play(s):
    hero = s.get_corresponding_hero()
    add_atk = 0
    add_hp = 0
    for h in _fire_heroes_except(hero, s.owner):
        add_atk += h.atk
        add_hp += h.current_max_hp
        for attr in h.attributes:
            if attr not in hero.attributes:
                hero.attributes.append(attr)
    s.atk = 3 + add_atk
    s.hp = 3 + add_hp

class HuoQuJianHao:
    id = 43
    type = "morph"
    hero = "HuoQuMo"
    name = "火取剑豪"
    level_req = 3
    atk = 3
    hp = 3
    on_play = (_huoqujianhao_on_play,)
