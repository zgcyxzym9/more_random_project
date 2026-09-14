"""妖狐 专属卡牌（8 张：id 89-96，对应 cards.json）"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.heroes import _yaohu_boost_basic_damage, _yaohu_awaken_listeners


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _enemy_characters(player):
    """敌方角色候选：存活且已升级的敌方式神 + 敌方牌手。"""
    opp = player.opponent
    return [h for h in opp.heroes if h.is_alive and h.level > 0] + [opp]


def _all_heroes(player):
    """所有存活且已升级的式神（含己方与敌方，不含牌手）。"""
    return [h for side in (player.heroes, player.opponent.heroes)
            for h in side if h.is_alive and h.level > 0]


def _yaohu_spell_damage(card, base: int) -> int:
    """妖狐法术牌的基础伤害。

    爱意绵绵（id=91）形态下：你手牌中所有妖狐的法术牌伤害效果 +1。
    通过 hero.morphed_id 判断形态，避免改动引擎的 spell 伤害结算。
    """
    hero = card.get_corresponding_hero()
    if hero is not None and hero.morphed_id == 91:
        return base + 1
    return base


# ── 1勾卡牌 ─────────────────────────────────────────────────────────────────

class FengRen:
    """风刃：瞬发。对一个敌方角色造成2点伤害。"""
    id = 89
    type = "spell"
    hero = "YaoHu"
    name = "风刃"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    require_target = (lambda s: _enemy_characters(s.owner),)
    select_target = (lambda s: select_target(s.owner, _enemy_characters(s.owner), s),)
    on_play = (lambda s: _fengren_on_play(s),)

def _fengren_on_play(s):
    hero = s.get_corresponding_hero()
    s.owner.game.handle_event(DealDamage(_yaohu_spell_damage(s, 2), hero, s.owner.selected_targets))


class JuQi:
    """聚气：瞬发。使妖狐的基础能力造成的伤害永久+1，抽一张牌。"""
    id = 90
    type = "spell"
    hero = "YaoHu"
    name = "聚气"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _juqi_on_play(s),)

def _juqi_on_play(s):
    _yaohu_boost_basic_damage(s.get_corresponding_hero())
    s.owner.draw()


class AiYiMianMian:
    """爱意绵绵：形态 4/5。你手牌中所有妖狐的法术牌伤害效果+1。

    效果通过 _yaohu_spell_damage 读取 hero.morphed_id == 91 实现，无需监听器。
    """
    id = 91
    type = "morph"
    hero = "YaoHu"
    name = "爱意绵绵"
    level_req = 1
    atk = 4
    hp = 5


# ── 2勾卡牌 ─────────────────────────────────────────────────────────────────

def _mingyunzhiren_on_play(s):
    hero = s.get_corresponding_hero()

    def _on_begin_turn(e, s2):
        # 己方回合开始时，将一张「风刃」置入手牌
        if s2.is_alive and s2.morphed_id == 92 and e.next_player is s2.owner:
            s2.owner.GiveCardToHand(["FengRen"])

    l = Listener("begin turn",
                 lambda e, s2: s2.is_alive and s2.morphed_id == 92,
                 (_on_begin_turn,))
    l._tag = "mingyunzhiren"
    # 同名牌重复打出时去重，避免监听器叠加（双生/明澈同款模式）
    hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != "mingyunzhiren"]
    hero.listeners.append(l)


class MingYunZhiRen:
    """命运之人：形态 4/6。己方回合开始时，将一张「风刃」置入手牌。"""
    id = 92
    type = "morph"
    hero = "YaoHu"
    name = "命运之人"
    level_req = 2
    atk = 4
    hp = 6
    on_play = (lambda s: _mingyunzhiren_on_play(s),)


def _wujifengdan_on_play(s):
    hero = s.get_corresponding_hero()
    dmg = _yaohu_spell_damage(s, 2)
    for _ in range(10):
        # 「随机对一个其他式神」：含己方与敌方所有存活式神，除妖狐自身
        candidates = [h for h in _all_heroes(s.owner) if h is not hero]
        if not candidates:
            break
        target = select_random_target(s.owner, candidates, context="无羁风弹: 随机式神")
        if target is None:
            break
        s.owner.game.handle_event(DealDamage(dmg, hero, [target]))
        if not target.is_alive:
            break  # 任一式神气绝 → 停止重复


class WuJiFengDan:
    """无羁风弹：随机对一个其他式神（含己方，不含妖狐自身）造成2点伤害，重复此效果，直到任一式神气绝或此效果作用10次。"""
    id = 93
    type = "spell"
    hero = "YaoHu"
    name = "无羁风弹"
    level_req = 2
    on_play = (lambda s: _wujifengdan_on_play(s),)


def _diefengzhan_on_play(s):
    hero = s.get_corresponding_hero()
    targets = s.owner.selected_targets
    if not targets:
        return
    # 对一个式神造成2点伤害
    s.owner.game.handle_event(DealDamage(_yaohu_spell_damage(s, 2), hero, targets))
    # 对其再次使用此牌（目标已气绝则第二段无效果，由 deal damage 分支跳过）
    s.owner.game.handle_event(DealDamage(_yaohu_spell_damage(s, 2), hero, targets))


class DieFengZhan:
    """叠风斩：对一个式神（含己方）造成2点伤害，然后对其再次使用此牌。"""
    id = 94
    type = "spell"
    hero = "YaoHu"
    name = "叠风斩"
    level_req = 2
    require_target = (lambda s: _all_heroes(s.owner),)
    select_target = (lambda s: select_target(s.owner, _all_heroes(s.owner), s),)
    on_play = (lambda s: _diefengzhan_on_play(s),)


# ── 3勾卡牌 ─────────────────────────────────────────────────────────────────

def _kuangfengrenjuan_on_play(s):
    hero = s.get_corresponding_hero()
    dmg = _yaohu_spell_damage(s, 2)
    # 增强：若本局游戏妖狐造成过20次伤害，额外重复5次
    repeat = 5
    if hero.counters.get("yaohu_damage_dealt", 0) >= 20:
        repeat += 5
    for _ in range(repeat):
        candidates = _enemy_characters(s.owner)
        if not candidates:
            break
        target = select_random_target(s.owner, candidates, context="狂风刃卷: 随机角色")
        if target is None:
            break
        s.owner.game.handle_event(DealDamage(dmg, hero, [target]))


class KuangFengRenJuan:
    """狂风刃卷：随机对一个敌方角色造成2点伤害，重复5次。增强：若本局游戏妖狐造成过20次伤害，额外重复5次。"""
    id = 95
    type = "spell"
    hero = "YaoHu"
    name = "狂风刃卷"
    level_req = 3
    on_play = (lambda s: _kuangfengrenjuan_on_play(s),)


def _juexingyaohu_on_play(s):
    hero = s.get_corresponding_hero()
    # 觉醒：妖狐永久 +2/+2（跨形态/气绝/复活保留）
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)
    hero.is_awakened = True
    # 基础能力升级为觉醒版：移除基础「yaohu_spell」监听器与旧觉醒监听器，
    # 换上觉醒监听器（使用法术牌 / 运势判定成功 均触发基础伤害）。
    # 同步更新 original_listeners，保证气绝→复活后仍保持觉醒状态。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") not in ("yaohu_spell", "yaohu_awaken")]
    hero.original_listeners = [l for l in hero.original_listeners if getattr(l, "_tag", "") not in ("yaohu_spell", "yaohu_awaken")]
    for l in _yaohu_awaken_listeners():
        hero.listeners.append(l)
        hero.original_listeners.append(l)


class JueXingYaoHu:
    """觉醒·妖狐：妖狐永久+2/+2。基础能力升级为「使用法术牌或运势判定成功时，
    随机对一个敌方角色造成基础伤害」（聚气加成仍生效）。"""
    id = 96
    type = "spell"
    hero = "YaoHu"
    name = "觉醒·妖狐"
    level_req = 3
    buff_atk = 2
    buff_hp = 2
    on_play = (lambda s: _juexingyaohu_on_play(s),)