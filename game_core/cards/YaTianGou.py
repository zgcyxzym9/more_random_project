"""鸦天狗 专属卡牌"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _ytg_moves_this_turn(hero) -> int:
    """本回合鸦天狗的移动次数（供正义必胜增强）。"""
    return hero.counters.get("move_this_turn", 0)


def _remove_morph(hero):
    """移除式神当前形态：恢复基础身材 + 永久加成，清空 morphed_id。

    供英雄无畏使用。引擎无全局形态注册表，各形态自带的监听器/回调不做通用清理。
    """
    if hero.morphed_id != 0:
        hero.morphed_id = 0
        hero.atk = hero.original_atk + hero.perm_buff_atk
        hero.current_max_hp = hero.original_hp + hero.perm_buff_hp
        if hero.hp > hero.current_max_hp:
            hero.hp = hero.current_max_hp


# ── 1勾卡牌 ───────────────────────────────────────────────────────────────

class ZhuiFeng:
    """追风：瞬发。移动鸦天狗，抽一张牌。"""
    id = 63
    type = "spell"
    hero = "YaTianGou"
    name = "追风"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _zhuifeng_on_play(s),)

def _zhuifeng_on_play(s):
    hero = s.get_corresponding_hero()
    if hero.state == "attacking":
        hero.move_to_standby()
    else:
        hero.move_to_battle()
    s.owner.draw()


class ZhengYiBiSheng:
    """正义必胜：战斗 +0/+0。增强：本回合鸦天狗每移动过一次，此牌获得+2力量。"""
    id = 64
    type = "attack"
    hero = "YaTianGou"
    name = "正义必胜"
    level_req = 1
    buff_atk = 0
    buff_def = 0
    on_play = (lambda s: _zhengyibisheng_on_play(s),)

def _zhengyibisheng_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        s.buff_atk += 2 * _ytg_moves_this_turn(hero)


class ZhengYiZhiCi:
    """正义之刺：战斗 +1/+2。若己方战斗区有其他式神，使其先攻击一次。"""
    id = 65
    type = "attack"
    hero = "YaTianGou"
    name = "正义之刺"
    level_req = 2
    buff_atk = 1
    buff_def = 2
    on_play = (lambda s: _zhengyizhici_on_play(s),)

def _zhengyizhici_on_play(s):
    hero = s.get_corresponding_hero()
    player = hero.owner
    if player.attack_zone is not None and player.attack_zone != hero and player.attack_zone.is_alive:
        ally = player.attack_zone
        # 走标准攻击路径：广播 hero attack 让敌方响应牌可触发
        player.game.handle_event(HeroAttackEvent(player, ally))


# ── 2勾卡牌 ───────────────────────────────────────────────────────────────

def _yayujizou_on_play(s):
    hero = s.get_corresponding_hero()
    # 移动两次
    hero.move_to_standby()
    hero.move_to_battle()

def _yayujizou_cond(e, s):
    """敌方攻击且目标是鸦天狗（战斗区，或追猎指定）。"""
    ytg = s.get_corresponding_hero()
    if ytg is None or not ytg.is_alive:
        return False
    attacker = e.event.hero
    if attacker is ytg or attacker.owner is s.owner:
        return False  # 己方攻击不响应
    # step 广播时目标已预解析（action.target）
    if getattr(e.event, "target", None) is not None:
        return e.event.target is ytg
    # handle_event 广播时：追猎看已选目标，否则看对方战斗区
    if HeroAttributes.HUNTING in attacker.attributes:
        sel = attacker.owner.selected_targets
        return sel is not None and len(sel) > 0 and sel[0] is ytg
    return attacker.owner.opponent.attack_zone is ytg

def _yayujizou_response(e, s):
    can_play, _ = s.owner.game.can_play_card(s.owner, s)
    if can_play:
        setattr(e.event, "revert", True)
        s.owner.game.play_card(s.owner, s)

class YaYuJiZou:
    """鸦羽疾走：移动，然后再次移动。响应：鸦天狗被攻击时，自动使用并取消本次攻击。"""
    id = 68
    type = "spell"
    hero = "YaTianGou"
    name = "鸦羽疾走"
    level_req = 2
    attributes = (CardAttributes.RESPONSE,)
    listeners = (Listener("hero attack", _yayujizou_cond, (_yayujizou_response,)),)
    on_play = (lambda s: _yayujizou_on_play(s),)


class YuJi:
    """羽迹：将一个敌方式神移入战斗区并使其眩晕，然后移动鸦天狗。"""
    id = 66
    type = "spell"
    hero = "YaTianGou"
    name = "羽迹"
    level_req = 2
    require_target = (lambda s: [h for h in s.owner.opponent.heroes
                                  if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes
                                                        if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _yuji_on_play(s),)

def _yuji_on_play(s):
    target = s.owner.selected_targets[0]
    # 移入敌方战斗区（战斗区已有其他式神时自动换下）；已在战斗区则不重复移动
    if target.owner.attack_zone is not target:
        target.move_to_battle()
    target.stun()
    hero = s.get_corresponding_hero()
    hero.move_to_battle()


class QunYaLuanWu:
    """群鸦乱舞：形态 2/8。己方回合结束时若鸦天狗在战斗区，对敌方所有式神造成1点伤害，鸦天狗恢复等量生命。"""
    id = 67
    type = "morph"
    hero = "YaTianGou"
    name = "群鸦乱舞"
    level_req = 2
    atk = 2
    hp = 8
    on_play = (lambda s: s.get_corresponding_hero().listeners.append(
        Listener("end turn",
                 lambda e, s: s.owner.attack_zone == s,
                 (lambda e, s: _qunyaluanwu_trigger(e, s),))
    ),)

def _qunyaluanwu_trigger(e, s):
    targets = [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0]
    if targets:
        dmg = len(targets)
        s.owner.game.handle_event(DealDamage(1, s, targets))
        s.owner.game.handle_event(Heal(dmg, s, [s]))


# ── 3勾卡牌 ───────────────────────────────────────────────────────────────

class YingXiongWuWei:
    """英雄无畏：移除一个敌方式神的当前状态，然后随机移除一个该式神的幻境。使其保持眩晕，直到鸦天狗使用牌、攻击或气绝。"""
    id = 69
    type = "spell"
    hero = "YaTianGou"
    name = "英雄无畏"
    level_req = 3
    require_target = (lambda s: [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0], s),)
    on_play = (lambda s: _yingxiongwuwei_on_play(s),)

def _yingxiongwuwei_on_play(s):
    target = s.owner.selected_targets[0]
    hero = s.get_corresponding_hero()
    player = s.owner
    # 1. 移除目标当前状态（形态）
    _remove_morph(target)
    # 2. 随机移除一个该式神的幻境
    _ytg_remove_random_illusion(player, target)
    # 3. 眩晕，直到鸦天狗使用牌、攻击或气绝
    target.stun()
    _ytg_register_stun_release(player, hero, target, exclude_card=s)

def _ytg_remove_random_illusion(player, target):
    """随机移除一个属于目标的幻境。"""
    zone = player.opponent.illusion_zone
    theirs = [ill for ill in zone if getattr(ill, "hero", "") == target.type_name]
    if not theirs:
        return
    picked = random_sample(player, theirs, 1, context="英雄无畏")
    if picked:
        player.opponent.illusion_zone.remove(picked[0])
        player.game.handle_event(IllusionDestroyedEvent(player.opponent, picked[0]))

def _ytg_register_stun_release(player, hero, target, exclude_card=None):
    """登记眩晕解除：鸦天狗使用牌 / 攻击 / 气绝时解除目标眩晕。

    exclude_card：英雄无畏自身。完成事件在 on_play（挂载）之后广播，
    不排除的话本次打出会立刻自触发解除、眩晕形同虚设。
    """
    tag = "yingxiongwuwei"
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]
    def _release(e, p):
        target.unstun()
        player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]
    l_play = Listener("play card",
                      lambda e, p: (e.event.card is not None
                                    and e.event.card is not exclude_card
                                    and e.event.card.owner == player),
                      (_release,))
    l_play._tag = tag
    l_atk = Listener("hero attack",
                     lambda e, p: getattr(e.event, "hero", None) is hero,
                     (_release,))
    l_atk._tag = tag
    l_death = Listener("hero kill",
                       lambda e, p: getattr(e.event, "killed", None) is hero,
                       (_release,))
    l_death._tag = tag
    player.listeners += [l_play, l_atk, l_death]


class JueXingYaTianGou:
    """觉醒·鸦天狗：觉醒：当鸦天狗移动时，发动一次攻击，本次攻击具有远程。"""
    id = 70
    type = "spell"
    hero = "YaTianGou"
    name = "觉醒·鸦天狗"
    level_req = 3
    on_play = (lambda s: _juexing_ytg_on_play(s),)

def _juexing_ytg_on_play(s):
    hero = s.get_corresponding_hero()
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)

    def _on_move_attack(h, from_zone, to_zone):
        if to_zone == "battle" and HeroAttributes.RANGED not in h.attributes:
            h.attributes.append(HeroAttributes.RANGED)
            # 走标准攻击路径：广播 hero attack 让敌方响应牌可触发
            h.owner.game.handle_event(HeroAttackEvent(h.owner, h))
            h.attributes.remove(HeroAttributes.RANGED)

    hero.on_move = (_on_move_attack,) + hero.on_move