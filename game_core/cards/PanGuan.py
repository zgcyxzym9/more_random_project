"""判官卡牌（id 351-358）。

牌面文本以 cards.json 条目（351-358）为准。式神段（击杀计数/基础与觉醒被动/
无情倒计时/夺命增强消灭）在 heroes.py 判官段；本文件实现卡牌打出侧逻辑。

口径与裁决记录（用户 2026-10-21，除注明外）：
- 击杀计数（夺命/断罪增强条件「本局游戏你消灭过的式神」）从开局累计：
  game.py broadcast 例外名单含 PanGuan（青坊主同款），计数监听在 heroes.py
  不限等级与存活。
- 墨笔夺魂：GiveBuff 力量-2 / 生命-1（hp 同时降上限与当前生命，狂啸不在
  判官回合守护 → 可降至 0 气绝）；生命归 0 归属判官并结算死亡（基础效果
  正常触发；复活后 GiveBuff 效果随死亡清理自然移除）。
- 勾诀：打出时力量≤2 即可消灭（用户裁决 3）；尘缚之阵直接消灭免疫照查。
- 生死无常：先消灭己方战斗区式神再消灭敌方战斗区式神（判官归属）；响应
  trigger "hero attack"（引擎 _auto_response 仅敌方回合扫描），条件=本次
  攻击结算目标为己方战斗区式神——响应先于攻击结算消灭己方战斗区式神，
  引擎 _resolve_attack_target 兜底改打牌手（白狼起弓/黑焰之手等远程同
  语义，用户裁决 4）。
- 无情：敌方式神气绝倒计时+1 在 heroes.py（hero kill after 相位）；
  疯魔琴心操作的是待机倒计时（countdown）且只选存活式神，与气绝倒计时
  无关（用户裁决 9）。
- 觉醒·判官：先墨笔夺魂效果后觉醒（get_permanent_buff +1/+1 + 标记）；
  觉醒后被动「你消灭」= 己方任意式神击杀（heroes.py cond 分支）。
- 夺命：必杀/穿刺 on_play 授予、after_play 移除（狂气同款，仅限本次战斗）；
  增强（≥13 消灭）完全替换必杀/穿刺（用户裁决）→ 只置 _duoming_enhanced
  标记，消灭效果在 heroes.py 监听 damage dealt 战斗广播（实际伤害>0 才
  广播，未造成伤害不触发，用户裁决 10）；直接消灭尊重尘缚之阵免疫。
- 死之宣告：双方存活已升级式神均可为目标（敌方排除帷幕）；不查尘缚之阵
  直接消灭免疫（用户裁决 12：无视除帷幕外一切增益）；死亡走自然流程，
  on_before_death 替代效果（狂啸/九命猫）仍按引擎语义介入。
- 断罪：morph 分支在 on_play 后按 card.atk 结算面板（game.py 形态分支
  「on_play 可能按实例改写」通道），on_play 按击杀数改写力量（4+击杀数，
  0 击杀时与基础面板一致）。
"""

import sys
from game_core.event import *
from game_core.enums import *
from game_core.selector import *


def _pg_kill_count(player):
    """本局己方消灭过的式神数（heroes.py 判官段从开局累计）。"""
    return getattr(player, "_pg_kill_total", 0)


def _pg_enemy_targets(s):
    """敌方存活已升级式神，排除帷幕（帷幕：不能被敌方卡牌选为目标）。"""
    return [h for h in s.owner.opponent.heroes
            if h.is_alive and h.level > 0
            and HeroAttributes.VEIL not in h.attributes]


def _pg_all_hero_targets(s):
    """死之宣告：双方存活已升级式神（己方不受帷幕限制——帷幕只防敌方选目标）。"""
    own = [h for h in s.owner.heroes if h.is_alive and h.level > 0]
    return own + _pg_enemy_targets(s)


def _pg_destroy_by_panguan(s, target, respect_immune=True):
    """直接消灭并归属判官（基础效果按「判官消灭」触发）。"""
    if target is None or target.state == "dead":
        return
    game = s.owner.game
    if respect_immune and game._direct_destroy_immune(target):
        return
    hero = s.get_corresponding_hero()
    game._last_damage_source = hero
    target._last_damage_from = hero
    target.hp = 0
    game.resolve_deaths([target])


# ── 351 墨笔夺魂 / 355 觉醒·判官共用的削弱效果 ──────────────────────────────

def _pg_soulbrush(s):
    target = (s.owner.selected_targets or [None])[0]
    if target is None or target.state == "dead":
        return
    game = s.owner.game
    game.handle_event(GiveBuff("atk", -2, s, [target]))
    game.handle_event(GiveBuff("hp", -1, s, [target]))
    # 生命归 0 归属判官并结算（hp 事件已落定，无需再置 0）
    if target.hp <= 0:
        hero = s.get_corresponding_hero()
        game._last_damage_source = hero
        target._last_damage_from = hero
        game.resolve_deaths([target])


def _pg_awaken_self(s):
    """觉醒：永久 +1/+1 并标记（觉醒后被动见 heroes.py 判官段 cond 分支）。"""
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True


# ── 351 墨笔夺魂：使一个敌方式神降低2点力量与1点生命 ────────────────────────

class MoBiDuoHun:
    id = 351
    type = "spell"
    hero = "PanGuan"
    name = "墨笔夺魂"
    level_req = 1
    is_beginning_card = True
    require_target = (lambda s: _pg_enemy_targets(s),)
    select_target = (lambda s: select_target(s.owner, _pg_enemy_targets(s), s),)
    on_play = (_pg_soulbrush,)


# ── 352 勾诀：消灭一个力量小于等于2的敌方式神 ──────────────────────────────

def _pg_goujue_targets(s):
    # 力量≤2 在打出时判定（用户裁决 3）
    return [h for h in _pg_enemy_targets(s) if h.atk <= 2]


def _pg_goujue(s):
    target = (s.owner.selected_targets or [None])[0]
    _pg_destroy_by_panguan(s, target)


class GouJue:
    id = 352
    type = "spell"
    hero = "PanGuan"
    name = "勾诀"
    level_req = 1
    is_beginning_card = True
    require_target = (_pg_goujue_targets,)
    select_target = (lambda s: select_target(s.owner, _pg_goujue_targets(s), s),)
    on_play = (_pg_goujue,)


# ── 353 生死无常：消灭己方战斗区的式神，然后消灭敌方战斗区的式神。
#    响应：当己方战斗区式神被攻击时，自动使用。 ─────────────────────────────

def _pg_shengsi_on_play(s):
    # 先己方后敌方（按牌面顺序）。判官在己方战斗区时先被消灭并先结算基础
    # 效果，之后敌方消灭不触发（用户裁决 5：同批/先后结算由 is_alive 门控）。
    _pg_destroy_by_panguan(s, s.owner.attack_zone)
    _pg_destroy_by_panguan(s, s.owner.opponent.attack_zone)


def _pg_shengsi_response_cond(card, src, target):
    # 响应条件：本次攻击的结算目标 = 己方战斗区式神（打牌手/追猎指定准备区
    # 目标不响应；敌方回合限制由引擎 _auto_response 保证）
    return target is not None and target is card.owner.attack_zone


class ShengSiWuChang:
    id = 353
    type = "spell"
    hero = "PanGuan"
    name = "生死无常"
    level_req = 2
    is_beginning_card = True
    response_trigger = "hero attack"
    response_condition = (_pg_shengsi_response_cond,)
    on_play = (_pg_shengsi_on_play,)


# ── 354 无情：形态 4/5。敌方式神进入气绝的倒计时+1（heroes.py 判官段） ──────

class WuQing:
    id = 354
    type = "morph"
    hero = "PanGuan"
    name = "无情"
    level_req = 2
    is_beginning_card = True
    atk = 4
    hp = 5


# ── 355 觉醒·判官：使一个敌方式神降低2点力量与1点生命。觉醒：当你消灭
#    一个式神时，对敌方牌手造成1点伤害且你恢复1点生命。 ─────────────────────

class JueXingPanGuan:
    id = 355
    type = "spell"
    hero = "PanGuan"
    name = "觉醒·判官"
    level_req = 2
    is_beginning_card = True
    require_target = (lambda s: _pg_enemy_targets(s),)
    select_target = (lambda s: select_target(s.owner, _pg_enemy_targets(s), s),)
    on_play = (_pg_soulbrush, _pg_awaken_self)


# ── 356 夺命：必杀，穿刺。增强：本局游戏若你消灭过13个式神，改为
#    「消灭受到判官战斗伤害的角色。」 ────────────────────────────────────────

def _pg_duoming_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if _pg_kill_count(s.owner) >= 13:
        # 增强：完全替换必杀/穿刺（用户裁决 2026-10-21），只标记本次战斗的
        # 消灭效果（heroes.py 判官段监听 damage dealt 战斗广播）
        hero._duoming_enhanced = True
    else:
        granted = []
        for attr in (HeroAttributes.FATAL, HeroAttributes.PIERCING):
            if attr not in hero.attributes:
                hero.attributes.append(attr)
                granted.append(attr)
        s._duoming_granted = granted


def _pg_duoming_after_play(s):
    # 移除本牌授予的必杀/穿刺并解除增强标记（幂等；狂气 after_play 同款）
    hero = s.get_corresponding_hero()
    if hero is not None:
        for attr in getattr(s, "_duoming_granted", ()):
            if attr in hero.attributes:
                hero.attributes.remove(attr)
        s._duoming_granted = ()
        hero._duoming_enhanced = False


class DuoMing:
    id = 356
    type = "attack"
    hero = "PanGuan"
    name = "夺命"
    level_req = 2
    is_beginning_card = True
    on_play = (_pg_duoming_on_play,)
    after_play = (_pg_duoming_after_play,)


# ── 357 死之宣告：消灭一个式神 ──────────────────────────────────────────────

def _pg_death_sentence(s):
    target = (s.owner.selected_targets or [None])[0]
    # 裁决 12：无视除帷幕外一切增益——不查尘缚之阵直接消灭免疫（帷幕已在
    # 候选过滤）；死亡走自然流程
    _pg_destroy_by_panguan(s, target, respect_immune=False)


class SiZhiXuanGao:
    id = 357
    type = "spell"
    hero = "PanGuan"
    name = "死之宣告"
    level_req = 3
    is_beginning_card = True
    require_target = (lambda s: _pg_all_hero_targets(s),)
    select_target = (lambda s: select_target(
        s.owner, _pg_all_hero_targets(s), s),)
    on_play = (_pg_death_sentence,)


# ── 358 断罪：形态 4/8。增强：本局游戏你每消灭过一个式神，此牌便获得
#    1点力量。 ────────────────────────────────────────────────────────────────

def _pg_duanzui_on_play(s):
    s.atk = 4 + _pg_kill_count(s.owner)


class DuanZui:
    id = 358
    type = "morph"
    hero = "PanGuan"
    name = "断罪"
    level_req = 3
    is_beginning_card = True
    atk = 4
    hp = 8
    on_play = (_pg_duanzui_on_play,)
