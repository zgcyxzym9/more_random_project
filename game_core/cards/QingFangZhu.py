"""青坊主卡牌（id 335-342）。

牌面文本以 cards.json 条目（335-342）为准。式神段（基础能力/觉醒/轮回增强计数）
在 heroes.py 青坊主段；本文件实现卡牌打出侧逻辑。

口径与裁决记录（用户 2026-10-10）：
- 「你恢复生命」（基础能力/禅心/觉醒）= 仅己方牌手实际恢复生命（满血/被生命
  上限截断不触发）；判定用 heroes.py 青坊主段在 heal before 的快照
  （qfz_hp_before），基础能力每回合一次、觉醒不限次且替换基础能力。
- 佛光（338）/佛印（335）的回复是 Heal 事件广播；佛光的「回复4」与「回复3」
  是两个独立事件（两次均触发青坊主效果）；佛光可指定牌手。
- 法界唯心（340）：「你对敌方的恢复生命效果改为伤害效果」在 heal before 相位
  把事件目标中的敌方角色（含敌方牌手）拆出、改为等值 DealDamage（独立事件，
  用户裁决：五谷丰壤触发对方运势4回复时对方扣3点生命）；进场回复写在
  after_play（morphed_id 已置位），指定敌方时同样被自身改写。改写与满血与否
  无关——改写的是「恢复生命的效果」本身。
- 舍生（339）：响应 trigger "deal damage" before（引擎 _auto_response 仅敌方
  回合扫描）；致命判定按 player.receive_damage 口径（伤害+自身破甲-自身护甲
  >= 当前生命；幻境承伤并行不减免，不计入）。on_response（引擎法术响应回调，
  已授权）把牌手加入触发事件的 immune_targets，使触发响应的那记致命伤本身被
  免疫；on_play 直接消灭青坊主（不屈不介入，凤覆岩先例）并挂玩家级「免疫所有
  deal damage」监听，下一回合 begin turn before 移除（"end turn" after 广播时
  下一回合 begin_turn 已完整执行，不能用作清理点，见 game.py 回合边界注释）。
- 觉醒·青坊主（341）：「恢复8点生命」目标为青坊主自身（假设，见汇报）；
  buff_hp:2 为觉醒永久加成（get_permanent_buff，不发 Heal 事件、不触发回复类
  效果，faq）；后置 is_awakened（heroes.py 觉醒监听器启用、基础监听器停用）。
- 轮回（342）：「你的生命变为10」是设值不是回复（用户裁决：不发 Heal 事件、
  不触发青坊主效果）；增强 +1 = heroes.py 的 qfz_attacked_count（仅对手战斗
  伤害打到己方牌手，开局起累计）；设值以 current_max_hp 封顶（防 hp>上限
  异常态）。
- 慈悲（337）：目标为存活己方式神（引擎目标惯例；气绝式神是否可选未裁决，
  见汇报）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *
from game_core.damage_immunity import make_damage_immune_listener


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _controller_of(x):
    """角色（式神/牌手）的操控者：牌手是自身（entity_type="player"），式神取 owner。"""
    if getattr(x, "entity_type", "") == "player":
        return x
    return getattr(x, "owner", None)


def _all_characters(s):
    """「角色」候选：双方存活式神 + 双方牌手（用户裁决：敌方角色含敌方牌手）。"""
    return ([h for h in s.owner.heroes if h.is_alive]
            + [h for h in s.owner.opponent.heroes if h.is_alive]
            + [s.owner, s.owner.opponent])


# ── 335 佛印：瞬发 为双方牌手恢复4点生命 ────────────────────────────────────

class FoYin:
    id = 335
    type = "spell"
    hero = "QingFangZhu"
    name = "佛印"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    # 单个 Heal 事件含双方牌手：法界唯心在 before 相位把敌方目标拆出改写为
    # 伤害，剩余己方部分照常回复；未进场形态时两人各回 4。
    on_play = (lambda s: Heal(4, s, [s.owner, s.owner.opponent]),)


# ── 336 禅心：形态 1/6。每回合一次，当你恢复生命时，抽一张牌 ────────────────

def _chanxin_draw(e, h):
    # 实际回血判定与基础能力同源：heroes.py 青坊主段在 heal before 已快照牌手
    # 回血前生命（qfz_hp_before），此处 after 相位比较判定「实际恢复」。
    if h.owner.hp <= h.counters.get("qfz_hp_before", h.owner.hp):
        return None
    # 每回合一次（persistent + reset_per_turn，与基础能力 qfz_heal_used 同语义）
    h.counters.ensure("chanxin_draw_used", initial=0,
                      persistent=True, reset_per_turn=True)
    if h.counters.get("chanxin_draw_used") >= 1:
        return None
    h.counters.inc("chanxin_draw_used", 1)
    h.owner.game.handle_event(DrawEvent(h.owner, 1))


def _chanxin_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 形态被动挂 hero.listeners（气绝随 listeners 重置脱落，wiki：气绝失去形态）；
    # 同 tag 先摘后挂，重复进场幂等（金运大吉先例）。
    hero.listeners = [l for l in hero.listeners
                      if getattr(l, "_tag", "") != "chanxin_heal_draw"]
    l = Listener("heal",
                 lambda e, h: (h.is_alive and h.morphed_id == 336
                               and h.owner in getattr(e.event, "target", ())),
                 (_chanxin_draw,), phase="after")
    l._tag = "chanxin_heal_draw"
    hero.listeners.append(l)


class ChanXin:
    id = 336
    type = "morph"
    hero = "QingFangZhu"
    name = "禅心"
    level_req = 1
    atk = 1
    hp = 6
    on_play = (_chanxin_on_play,)


# ── 337 慈悲：使一个己方式神获得不屈 ────────────────────────────────────────

def _cibei_on_play(s):
    for t in (s.owner.selected_targets or []):
        if HeroAttributes.TENACIOUS not in t.attributes:
            t.attributes.append(HeroAttributes.TENACIOUS)   # 幂等（黑白无常先例）


class CiBei:
    id = 337
    type = "spell"
    hero = "QingFangZhu"
    name = "慈悲"
    level_req = 1
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive],)
    select_target = (lambda s: select_target(
        s.owner, [h for h in s.owner.heroes if h.is_alive], s),)
    on_play = (_cibei_on_play,)


# ── 338 佛光：为一个角色恢复4点生命，然后为其操控者的所有角色恢复3点生命 ────

def _foguang_on_play(s):
    targets = s.owner.selected_targets or []
    if not targets:
        return
    t = targets[0]
    controller = _controller_of(t)
    g = s.owner.game
    # 两次回复 = 两个独立 Heal 事件（用户裁决：指定牌手时两次生命回复均触发
    # 青坊主效果）；第二次目标 = 其操控者的所有角色（存活式神 + 牌手自身）。
    g.handle_event(Heal(4, s, [t]))
    g.handle_event(Heal(3, s, list(controller.heroes) + [controller]))


class FoGuang:
    id = 338
    type = "spell"
    hero = "QingFangZhu"
    name = "佛光"
    level_req = 2
    require_target = (_all_characters,)
    select_target = (lambda s: select_target(s.owner, _all_characters(s), s),)
    on_play = (_foguang_on_play,)


# ── 339 舍生：瞬发。消灭青坊主，本回合你免疫所有伤害。
#    响应：当你将受到致命伤害时，自动使用。 ──────────────────────────────────

def _shesheng_lethal(card, src):
    """牌手将受致命伤判定（player.receive_damage 口径）：
    伤害 + 自身破甲 - 自身护甲 >= 当前生命。

    幻境承伤并行不减免（player.receive_damage 注释），不计入判定；
    src.value 为 before 相位各监听器改写后的最终伤害值（响应扫描在监听器后）。
    """
    p = card.owner
    incoming = src.value + getattr(p, "penetration", 0) - p.defense
    return incoming >= p.hp


def _shesheng_response_cond(card, src, target):
    # 响应条件：己方青坊主存活（牌面要消灭他）+ 牌手在本次伤害目标中 + 致命。
    # "deal damage" 不进引擎 _response_target 映射（target 恒 None），
    # 受击方从 src.target 列表取（狂啸同款）；敌方回合限制由引擎保证。
    hero = card.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return False
    return card.owner in getattr(src, "target", ()) and _shesheng_lethal(card, src)


def _shesheng_on_response(card, event, target):
    # 触发响应的那记致命伤本身也要被免疫（引擎法术响应 on_response 回调，
    # 先于 play_card 执行）：把牌手加入当前伤害事件的 immune_targets。
    event.immune_targets = getattr(event, "immune_targets", set()) | {card.owner}


def _shesheng_arm_immunity(p):
    """挂「本回合免疫所有伤害」：玩家级免疫监听 + 下一回合开始时清理。"""
    p.listeners = [l for l in p.listeners
                   if getattr(l, "_tag", "") not in ("shesheng_immune",
                                                     "shesheng_cleanup")]
    immune = make_damage_immune_listener("deal damage", lambda e, o: True)
    immune._tag = "shesheng_immune"
    p.listeners.append(immune)
    cleanup = Listener("begin turn", lambda e, o: True,
                       (_shesheng_cleanup,), phase="before")
    cleanup._tag = "shesheng_cleanup"
    p.listeners.append(cleanup)


def _shesheng_cleanup(e, p):
    # 下一回合 begin turn before（当前回合已结束、下回合效果未结算）解除。
    # 不能挂 "end turn" after——该广播点时下一回合 begin_turn 已完整执行。
    p.listeners = [l for l in p.listeners
                   if getattr(l, "_tag", "") not in ("shesheng_immune",
                                                     "shesheng_cleanup")]


def _shesheng_on_play(s):
    p = s.owner
    hero = s.get_corresponding_hero()
    # 消灭青坊主：直接消灭（不屈不介入），凤覆岩倒计时同款
    # （_last_damage_source 置来源 → hp=0 → resolve_deaths；直接消灭免疫照查）。
    if hero is not None and hero.is_alive:
        p.game._last_damage_source = hero
        if not p.game._direct_destroy_immune(hero):
            hero._last_damage_from = hero
            hero.hp = 0
            p.game.resolve_deaths([hero])
    _shesheng_arm_immunity(p)


class SheSheng:
    id = 339
    type = "spell"
    hero = "QingFangZhu"
    name = "舍生"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    response_trigger = "deal damage"
    response_phase = "before"
    response_condition = (_shesheng_response_cond,)
    on_response = (_shesheng_on_response,)
    on_play = (_shesheng_on_play,)


# ── 340 法界唯心：形态 5/6。进场时，为一个角色恢复4点生命。
#    你对敌方的恢复生命效果改为伤害效果。 ────────────────────────────────────

def _fjwx_convert_cond(e, h):
    # 改写条件：形态在场（morphed_id 门控）+ 效果来源操控者是青坊主一方
    # （「你的」恢复生命效果）+ 目标中含敌方角色（「对敌方的」）。
    if not (h.is_alive and h.morphed_id == 340):
        return False
    ev = e.event
    if _controller_of(getattr(ev, "source", None)) is not h.owner:
        return False
    return any(_controller_of(t) is h.owner.opponent
               for t in getattr(ev, "target", ()) or ())


def _fjwx_convert(e, h):
    ev = e.event
    me = h.owner
    targets = list(getattr(ev, "target", ()) or ())
    enemies = [t for t in targets if _controller_of(t) is me.opponent]
    # 目标改写为剩余的己方部分（就地改写事件：case "heal" 只结算剩余目标）；
    # 敌方部分转为等值伤害（改写的是「恢复生命的效果」本身，与是否满血无关）。
    ev.target = [t for t in targets if t not in enemies]
    me.game.handle_event(DealDamage(ev.value, getattr(ev, "source", h), enemies))


def _fjwx_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 形态被动挂 hero.listeners（同禅心：气绝脱落、同 tag 幂等）
    hero.listeners = [l for l in hero.listeners
                      if getattr(l, "_tag", "") != "fjwx_convert"]
    l = Listener("heal", _fjwx_convert_cond, (_fjwx_convert,))
    l._tag = "fjwx_convert"
    hero.listeners.append(l)


class FaJieWeiXin:
    id = 340
    type = "morph"
    hero = "QingFangZhu"
    name = "法界唯心"
    level_req = 3
    atk = 5
    hp = 6
    require_target = (_all_characters,)
    select_target = (lambda s: select_target(s.owner, _all_characters(s), s),)
    on_play = (_fjwx_on_play,)
    # 进场回复在 after_play：morphed_id 已置位（game.py 形态分支先跑身材替换），
    # 指定敌方角色时同样被自身改写为伤害
    after_play = (lambda s: Heal(4, s, list(s.owner.selected_targets or [])),)


# ── 341 觉醒·青坊主：恢复8点生命。觉醒：当你恢复生命时，对所有敌人造成1点伤害 ─

def _juexingqfz_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    # 恢复8点生命：青坊主自身（觉醒牌自益，按卡面语序先回复后觉醒）
    s.owner.game.handle_event(Heal(8, s, [hero]))
    # buff_hp:2 = 觉醒永久加成（get_permanent_buff：current_max_hp/hp/perm_buff_hp
    # 同加，不发 Heal 事件、不触发回复类效果，faq；觉醒·茨木童子先例）
    hero.get_permanent_buff("hp", 2)
    # 觉醒替换基础能力（wiki 关键字-觉醒）：heroes.py 觉醒监听器按 is_awakened
    # 启用、基础监听器停用；觉醒状态跨气绝保留
    hero.is_awakened = True


class JueXingQingFangZhu:
    id = 341
    type = "spell"
    hero = "QingFangZhu"
    name = "觉醒·青坊主"
    level_req = 3
    buff_hp = 2
    on_play = (_juexingqfz_on_play,)


# ── 342 轮回：你的生命变为10。增强：本局游戏你每被对手攻击过一次，此牌效果+1 ─

def _lunhui_on_play(s):
    p = s.owner
    hero = s.get_corresponding_hero()
    n = hero.counters.get("qfz_attacked_count", 0) if hero is not None else 0
    # 「你的生命变为10（+增强）」：设值不是回复（用户裁决：不发 Heal 事件、
    # 不触发青坊主效果）；当前生命高于设值时同样降到设值（「变为」）；
    # 以 current_max_hp 封顶（防 hp>上限异常态）。
    p.hp = min(10 + n, p.current_max_hp)


class LunHui:
    id = 342
    type = "spell"
    hero = "QingFangZhu"
    name = "轮回"
    level_req = 3
    on_play = (_lunhui_on_play,)
