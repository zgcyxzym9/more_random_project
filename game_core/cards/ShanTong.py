"""山童（ShanTong）专属卡牌

数据来源：tmp_cards_json/ShanTong.json + ShanTong.sources.md（9game/游侠/网易官方交叉核实）。
数值（勾玉/身材）与 game_core/cards/cards.json 一致。

实现说明：
- 山童基础能力即贯通（heroes.py base_attributes=PENETRATE），觉醒·山童无需重复授予贯通。
- 「免疫敌方非战斗伤害」由觉醒 on_play 挂「deal damage / projectile」监听器实现：判敌方来源+非战斗
  类型，命中时把山童加入事件底层的 immune_targets，引擎三条通道统一读取（战斗伤害不受影响）。
- 伺机（响应牌）：响应路径（敌方回合）通过 on_play 额外 +2 力量；同时置一次性
  反击贯通标记 _counter_penetrate（引擎 _penetrate_overflow 在反击结算时读取），
  本场战斗山童的反击造成贯通伤害（wiki：贯通默认仅主动攻击生效）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.damage_immunity import make_damage_immune_listener


def _shantong(owner):
    return next((h for h in owner.heroes if h.type_name == "ShanTong"), None)


# ── 1勾 ────────────────────────────────────────────────────────────────────

class LuMang:
    """鲁莽：己方回合开始时，山童自动发起攻击。"""
    id = 146
    type = "morph"
    hero = "ShanTong"
    name = "鲁莽"
    level_req = 1
    atk = 3
    hp = 6
    on_play = (lambda s: _lumang_on_play(s),)


def _lumang_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    tag = "lumang-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]

    def cond(e, h):
        return e.next_player is h.owner and h.morphed_id == 146 and h.is_alive and not h.stunned

    def effect(e, h):
        h.owner.game.handle_event(HeroAttackEvent(h.owner, h))

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    hero.listeners.append(l)


class GuaiLi:
    """怪力：山童永久获得1力量。"""
    id = 147
    type = "attack"
    hero = "ShanTong"
    name = "怪力"
    level_req = 1
    on_play = (lambda s: _guaili_on_play(s),)


def _guaili_on_play(s):
    hero = _shantong(s.owner)
    if hero is not None:
        hero.get_permanent_buff("atk", 1)


class NuHou:
    """怒吼：山童永久获得1力量，其他己方式神获得1力量。"""
    id = 148
    type = "spell"
    hero = "ShanTong"
    name = "怒吼"
    level_req = 1
    on_play = (lambda s: _nuhou_on_play(s),)


def _nuhou_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)
    others = [h for h in s.owner.heroes if h.is_alive and h is not hero]
    if others:
        s.owner.game.handle_event(GiveBuff("atk", 1, s, others))


# ── 2勾 ────────────────────────────────────────────────────────────────────

class BenZhuo:
    """笨拙：敌方回合时山童力量变为0。"""
    id = 149
    type = "morph"
    hero = "ShanTong"
    name = "笨拙"
    level_req = 2
    atk = 6
    hp = 9
    on_play = (lambda s: _benzhuo_on_play(s),)


def _benzhuo_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    tag = "benzhuo-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]

    def cond_enemy(e, h):
        return e.next_player is not h.owner and h.morphed_id == 149 and h.is_alive

    def eff_enemy(e, h):
        if getattr(h, "_benzhuo_saved_atk", None) is None:
            h._benzhuo_saved_atk = h.atk
        h.atk = 0

    def cond_own(e, h):
        return (e.next_player is h.owner and h.morphed_id == 149
                and getattr(h, "_benzhuo_saved_atk", None) is not None)

    def eff_own(e, h):
        h.atk = h._benzhuo_saved_atk
        del h._benzhuo_saved_atk

    l1 = Listener("begin turn", cond_enemy, (eff_enemy,))
    l2 = Listener("begin turn", cond_own, (eff_own,))
    l1._tag = tag
    l2._tag = tag
    hero.listeners.append(l1)
    hero.listeners.append(l2)


class SuiYan:
    """碎岩：穿刺"""
    id = 150
    type = "attack"
    hero = "ShanTong"
    name = "碎岩"
    level_req = 2
    buff_atk = 2
    buff_def = 2
    on_play = (lambda s: _suiyan_on_play(s),)
    after_play = (lambda s: _suiyan_after(s),)


def _suiyan_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    # 本次攻击赋予穿刺（移除目标护甲/屏障）
    s._suiyan_had_piercing = HeroAttributes.PIERCING in hero.attributes
    if not s._suiyan_had_piercing:
        hero.attributes.append(HeroAttributes.PIERCING)


def _suiyan_after(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    if not getattr(s, "_suiyan_had_piercing", True) and HeroAttributes.PIERCING in hero.attributes:
        hero.attributes.remove(HeroAttributes.PIERCING)


class JueXingShanTong:
    """觉醒·山童：觉醒：贯通。免疫敌方非战斗伤害。

    实现（damage_immunity 监听器）：觉醒 on_play 挂「deal damage / projectile」监听器，
    condition 判敌方来源+非战斗类型，命中时把山童加入底层事件 immune_targets。
    贯通为山童基础能力（heroes.py），无需重复授予。
    """
    id = 151
    type = "spell"
    hero = "ShanTong"
    name = "觉醒·山童"
    level_req = 2
    buff_atk = 1
    buff_hp = 1
    on_play = (lambda s: _juexingshantong_on_play(s),)


def _juexingshantong_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    hero.get_permanent_buff("atk", getattr(s, "buff_atk", 1))
    hero.get_permanent_buff("hp", getattr(s, "buff_hp", 1))
    hero.is_awakened = True

    # 免疫敌方非战斗伤害（法术/投射）。监听器判敌方来源 + 非战斗类型；命中时把自己加入
    # 底层事件的 immune_targets，由引擎三条伤害通道统一读取（战斗伤害不受影响）。
    # 挂到 listeners/原listeners：觉醒效果气绝后依旧保留。
    tag = "juexing_shantong_noncombat_immune"
    hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != tag]
    hero.original_listeners = [x for x in hero.original_listeners if getattr(x, "_tag", "") != tag]

    def is_enemy_noncombat(e, h):
        src = getattr(e.event, "source", None)
        enemy = getattr(src, "owner", None) is h.owner.opponent
        dt = getattr(e.event, "damage_type", "spell")
        return enemy and dt != "combat"

    l1 = make_damage_immune_listener("deal damage", is_enemy_noncombat)   # 法术（非战斗）
    l1._tag = tag
    l2 = make_damage_immune_listener("projectile", is_enemy_noncombat)   # 投射（非战斗）
    l2._tag = tag
    hero.listeners += [l1, l2]
    hero.original_listeners += [l1, l2]


class SiJi:
    """伺机：被攻击时也会造成贯通伤害。敌方回合时此牌获得+2力量。
    响应：当山童被攻击时，自动使用。"""
    id = 152
    type = "attack"
    hero = "ShanTong"
    name = "伺机"
    level_req = 2
    buff_atk = 2
    buff_def = 1
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: (
        event.hero.owner is s.owner.opponent
        and target is s.get_corresponding_hero()
    ),)
    on_play = (lambda s: _siji_on_play(s),)
    after_play = (lambda s: _siji_after_play(s),)


def _siji_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    # 「被攻击时也会造成贯通伤害」：置一次性反击贯通标记，引擎 _penetrate_overflow
    # 在反击结算时读取（getattr 带默认值保护）。清除统一走 after_play：主动打出在
    # play_card 的 attack 分支、响应打出在 _drain_response_cleanups（战斗未发生
    # 也会执行），两条路径均保证标记不跨战斗泄漏。
    hero._counter_penetrate = True
    # 敌方回合时此牌获得+2力量：响应打出（敌方回合）时额外 +2 攻击。
    # 响应路径的战斗结算后会统一还原战前 atk，故此处加成不会泄漏。
    if s.owner.game.current_player is s.owner.opponent:
        hero.atk += 2


def _siji_after_play(s):
    hero = _shantong(s.owner)
    if hero is not None:
        hero._counter_penetrate = False


# ── 3勾 ────────────────────────────────────────────────────────────────────

class BengShan:
    """崩山：对敌方战斗区式神造成4点伤害，对准备区式神造成1点伤害。
    增强：山童每永久提升1点力量，此牌便伤害+1。"""
    id = 153
    type = "spell"
    hero = "ShanTong"
    name = "崩山"
    level_req = 3
    on_play = (lambda s: _bengshan_on_play(s),)


def _bengshan_on_play(s):
    hero = _shantong(s.owner)
    if hero is None:
        return
    # 增强：山童每永久提升1点力量（怪力/怒吼/觉醒累计），此牌伤害+1
    bonus = hero.perm_buff_atk
    opp = s.owner.opponent
    battle = opp.attack_zone
    if battle is not None and battle.is_alive:
        s.owner.game.handle_event(DealDamage(4 + bonus, s, [battle]))
    standbys = [h for h in opp.heroes if h.is_alive and h.level > 0 and h is not battle]
    if standbys:
        s.owner.game.handle_event(DealDamage(1 + bonus, s, standbys))
