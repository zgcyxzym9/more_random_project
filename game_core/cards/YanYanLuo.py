"""烟烟罗卡牌（id 317-325）。

牌面文本以 cards.json 条目（317-325）为准。式神段（基础能力/觉醒倍增/爆能X
消耗改写/烟雾缭绕同步/无孔不入复制暂存派发）在 heroes.py 烟烟罗段；本文件
实现卡牌打出侧逻辑与「分身使用法术」的执行器。

口径与裁决记录（用户 2026-09-29）：
- 分身（YanYanLuoFenShen, id 204）：atk2/hp4/青岚/充能。召唤时复制烟烟罗当前
  力量/生命（含永久加成）并获得其一半能量（向下取整，直接赋值不算「获得」）；
  分身是召唤物，直接进战斗区，新分身进场自动替换旧分身，至多一个在场。
- 爆能X 三牌（顽皮鬼/贪食鬼/暴躁鬼）energy_cost=1：能量≥1 即提供爆能选项；
  发起消耗时 heroes.py 监听把消耗改写为全部能量并在卡牌上记录 X，on_play 把
  X 并入同一次伤害结算（「额外造成X点」与本体的击杀/必杀等判定合一）。
- 烟雾缭绕（320）：进场时分身召唤放 after_play（形态 on_play 阶段身材尚未
  替换，after 阶段才能复制到新形态 3/4）。形态在场时分身力量 = 召唤时复制值
  + 分身当前能量（持续同步，消耗回落；监听在 heroes.py 以 morphed_id 门控）。
- 无孔不入（323）：进场选择一张烟烟罗的爆能牌置入手牌（新实例，无需手牌/
  牌库存在此牌）；进场与己方回合开始时召唤分身；形态在场时分身复制她使用的
  法术牌——同目标、是否爆能与原打出一致但复制的爆能不再消耗能量，且不消耗
  鬼火（heroes.py 暂存/派发监听 → _yyl_dispatch_copy）。
- 烟影（325）：召唤分身并使其使用一张等同于烟烟罗当前等级的爆能法术
  （1=顽皮鬼 2=贪食鬼 3=暴躁鬼）：不消耗鬼火但消耗分身能量（X=分身全部能量）；
  1/2 勾法术目标手动选择（烟影自身的 select_target 按等级给候选；3 勾暴躁鬼
  为投射，目标自动解析不进选择）。羁绊：打出时日和坊存活且等级不为 0 时，
  己方所有具有充能的式神各+1能量（含分身）。
- 觉醒·烟烟罗（322）：先获得2能量（此时未觉醒，不翻倍）再觉醒；觉醒替换
  基础能力（0 起点额外不再叠加），获得两倍 = 实际增量之外再补一份。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *
from game_core.heroes import _YYL_BLAST_X_NAMES


def _yyl_hero(player):
    """player 存活的烟烟罗；没有则 None。"""
    return next((h for h in player.heroes
                 if h.type_name == "YanYanLuo" and h.is_alive), None)


def _yyl_clone(player):
    """player 当前在场的烟烟罗分身；没有则 None。"""
    return next((h for h in player.heroes
                 if h.type_name == "YanYanLuoFenShen" and h.is_alive), None)


def _yyl_summon_clone(player):
    """召唤一个烟烟罗的分身并定制面板。

    复制烟烟罗当前力量/生命（含永久加成，用户裁决①）、获得其一半能量
    （向下取整，直接赋值——初始赋予不算「获得」，不触发获得类监听）。
    召唤物直接进战斗区：旧分身被新分身替换离场（引擎 move_to_battle），
    至多一个在场。烟烟罗不存活时不召唤。返回新分身或 None。
    """
    game = player.game
    yyl = _yyl_hero(player)
    if yyl is None:
        return None
    before = list(player.heroes)
    game.handle_event(SummonEvent(player, "YanYanLuoFenShen"))
    new = [h for h in player.heroes if h not in before]
    if not new:
        return None
    clone = new[0]
    clone.atk = yyl.atk
    clone.original_atk = yyl.atk
    clone._yyl_copy_atk = yyl.atk          # 烟雾缭绕持续同步的复制值基准
    clone.hp = yyl.hp
    clone.current_max_hp = yyl.current_max_hp
    clone.original_hp = yyl.hp
    clone.counters.set("energy", yyl.counters.get("energy", 0) // 2)
    # 烟雾缭绕（320）形态在场：同步效果即时生效，进场力量即按公式
    # （复制值 + 当前能量）取值，与后续能量事件的持续同步同口径
    if yyl.morphed_id == 320:
        clone.atk = clone._yyl_copy_atk + clone.counters.get("energy", 0)
    return clone


def _take_blast_extra(s):
    """读取并清除本次打出的爆能 X（on_blast 置位 → on_play 单次消费）。

    正常打出路径：heroes.py 爆能X 监听在 EnergySpendEvent 时记录
    _yyl_blast_x，引擎随后跑 on_blast（置位 _yyl_blast_active）；分身使用
    路径：_yyl_run_cast 直接置位。非爆能打出读不到置位即 0，历史残留标记
    不会生效。
    """
    if getattr(s, "_yyl_blast_active", False):
        s._yyl_blast_active = False
        x = getattr(s, "_yyl_blast_x", 0)
        s._yyl_blast_x = 0
        return x
    return 0


def _yyl_run_cast(player, caster, card, target, blast_x=None,
                  spend_from=None, is_copy=False):
    """让分身 caster 直接使用一张法术 card（不走 play_card 结算）。

    - 不消耗鬼火、不进入弃牌堆、不广播 "play card"（复制不再递归触发复制）。
    - blast_x 非 None 表示本次为爆能使用：先按需支付能量（spend_from 非 None
      时发 EnergySpendEvent，支付失败放弃），X 记临时标记供 on_play 折算；
      is_copy=True 标记复制上下文（复制内的烟影再使用不再消耗能量）。
    - 目标经 selected_targets 通道传入（与引擎打出路径一致），用后还原；
      caster 经 played_by 注入，效果内 get_corresponding_hero 指向使用者。
    """
    game = player.game
    if blast_x is not None:
        if spend_from is not None and blast_x > 0:
            ev = EnergySpendEvent(spend_from, blast_x, card)
            game.handle_event(ev)
            if getattr(ev, "revert", False):
                return
        card._yyl_blast_x = blast_x
        card._yyl_blast_active = True
    if is_copy:
        card._yyl_is_copy = True
    prev_targets = player.selected_targets
    prev_played_by = card.played_by
    if caster is not None:
        card.played_by = caster
    player.selected_targets = [target] if target is not None else None
    try:
        if getattr(card, "_yyl_blast_active", False):
            for cb in getattr(card, "on_blast", ()):
                result = cb(card)
                if isinstance(result, Event):
                    game.handle_event(result)
        for cb in getattr(card, "on_play", ()):
            result = cb(card)
            if isinstance(result, Event):
                # 法术伤害的回合力加成与引擎 spell 分支同口径
                if isinstance(result, DealDamage):
                    hero = card.get_corresponding_hero()
                    if hasattr(hero, "round_buff_spell_damage"):
                        result.value += hero.round_buff_spell_damage
                game.handle_event(result)
    finally:
        player.selected_targets = prev_targets
        card.played_by = prev_played_by
        for a in ("_yyl_blast_x", "_yyl_blast_active", "_yyl_is_copy"):
            if a in card.__dict__:
                del card.__dict__[a]


def _yyl_dispatch_copy(player, card, targets, blast_x):
    """无孔不入（323）复制派发：在场分身补放她刚使用的法术（heroes.py 调用）。

    同目标（用户裁决③a）、是否爆能与原打出一致但不再消耗能量（③b）、
    不耗鬼火（③c）。原目标已气绝时伤害类效果按引擎口径空过。
    """
    clone = _yyl_clone(player)
    if clone is None:
        return
    target = targets[0] if targets else None
    _yyl_run_cast(player, clone, card, target,
                  blast_x=blast_x, spend_from=None, is_copy=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  317 顽皮鬼 (WanPiGui)
#  对一个敌方式神造成2点伤害。爆能X：额外造成X点伤害，X为全部能量。
# ═══════════════════════════════════════════════════════════════════════════════
def _yyl_enemy_candidates(player):
    return [h for h in player.opponent.heroes if h.is_alive and h.level > 0]


def _wanpigu_on_play(s):
    targets = getattr(s.owner, "selected_targets", None) or []
    if not targets:
        return
    extra = _take_blast_extra(s)
    s.owner.game.handle_event(DealDamage(2 + extra, s, [targets[0]]))


class WanPiGui:
    id = 317
    type = "spell"
    hero = "YanYanLuo"
    name = "顽皮鬼"
    level_req = 1
    is_beginning_card = True
    attributes = (CardAttributes.BLAST,)
    energy_cost = 1
    require_target = (lambda s: _yyl_enemy_candidates(s.owner),)
    select_target = (lambda s: select_target(
        s.owner, _yyl_enemy_candidates(s.owner), s),)
    on_play = (_wanpigu_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  318 扑朔迷离 (PuShuoMiLi)
#  在战斗区召唤一个烟烟罗的分身。响应：当你被攻击时，自动使用。
# ═══════════════════════════════════════════════════════════════════════════════
def _pushuomili_response_cond(s, event, target):
    """当你被攻击时：攻击方为敌方，且本次攻击的解析目标是我方牌手
    （战斗区为空被直接攻击，用户裁决⑤；战斗区有式神时不响应）。"""
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return False
    attacker = getattr(event, "hero", None)
    if attacker is None or attacker.owner is s.owner:
        return False
    return target is s.owner


def _pushuomili_on_play(s):
    # 分身在攻击结算前进场：攻击目标随后重新解析，会被分身阻挡
    _yyl_summon_clone(s.owner)


class PuShuoMiLi:
    id = 318
    type = "spell"
    hero = "YanYanLuo"
    name = "扑朔迷离"
    level_req = 1
    is_beginning_card = True
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    response_condition = (_pushuomili_response_cond,)
    on_play = (_pushuomili_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  319 烟雾升腾 (YanWuShengTeng)
#  瞬发 获得3能量。
# ═══════════════════════════════════════════════════════════════════════════════
def _yanwushengteng_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    hero.counters.inc("energy", 3)
    s.owner.game.handle_event(EnergyGainEvent(hero, 3))


class YanWuShengTeng:
    id = 319
    type = "spell"
    hero = "YanYanLuo"
    name = "烟雾升腾"
    level_req = 1
    is_beginning_card = True
    attributes = (CardAttributes.INSTANT,)
    on_play = (_yanwushengteng_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  320 烟雾缭绕 (YanWuLiaoRao)
#  进场时，在战斗区召唤一个烟烟罗的分身。烟烟罗的分身每有1能量便获得1力量。
#  （3/4；持续同步监听在 heroes.py 以 morphed_id 门控）
# ═══════════════════════════════════════════════════════════════════════════════
def _yanwuliaorao_after_play(s):
    # after_play 阶段形态身材已替换（3/4 满血），分身复制到新形态面板
    _yyl_summon_clone(s.owner)


class YanWuLiaoRao:
    id = 320
    type = "morph"
    hero = "YanYanLuo"
    name = "烟雾缭绕"
    level_req = 2
    atk = 3
    hp = 4
    is_beginning_card = True
    after_play = (_yanwuliaorao_after_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  321 贪食鬼 (TanShiGui)
#  对敌方战斗区式神造成3点伤害，你恢复3点生命。爆能X：额外造成X点伤害，X为全部能量。
# ═══════════════════════════════════════════════════════════════════════════════
def _tanshigui_on_play(s):
    player = s.owner
    game = player.game
    extra = _take_blast_extra(s)
    tz = player.opponent.attack_zone
    if tz is not None and tz.is_alive and tz.level > 0:
        game.handle_event(DealDamage(3 + extra, s, [tz]))
    # 「你恢复3点生命」独立于伤害结算（战斗区为空时仍恢复）
    game.handle_event(Heal(3, s, [player]))


class TanShiGui:
    id = 321
    type = "spell"
    hero = "YanYanLuo"
    name = "贪食鬼"
    level_req = 2
    is_beginning_card = True
    attributes = (CardAttributes.BLAST,)
    energy_cost = 1
    on_play = (_tanshigui_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  322 觉醒·烟烟罗 (JueXingYanYanLuo)
#  获得2能量。觉醒：充能。当烟烟罗获得能量时，获得两倍的能量。
#  （buff_atk/buff_hp 1/1 = 觉醒永久加成，跨形态/死亡保留；倍增监听在 heroes.py）
# ═══════════════════════════════════════════════════════════════════════════════
def _juexingyanyanluo_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    # 先获得2能量再置觉醒标记：本次获得不翻倍（按牌面顺序，觉醒在获得之后）
    hero.counters.inc("energy", 2)
    s.owner.game.handle_event(EnergyGainEvent(hero, 2))
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True


class JueXingYanYanLuo:
    id = 322
    type = "spell"
    hero = "YanYanLuo"
    name = "觉醒·烟烟罗"
    level_req = 3
    buff_atk = 1
    buff_hp = 1
    is_beginning_card = True
    on_play = (_juexingyanyanluo_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  323 无孔不入 (WuKongBuRu)
#  进场时，选择一张烟烟罗的爆能牌置入手牌。进场和己方回合开始时，在战斗区
#  召唤一个烟烟罗的分身。烟烟罗的分身会复制她使用的法术牌。
#  （3/6；回合开始召唤与复制派发监听在 heroes.py 以 morphed_id 门控）
# ═══════════════════════════════════════════════════════════════════════════════
def _wukongburu_candidates(player):
    """三张爆能法术的独立新实例（五道难题/觉醒·辉夜姬选择候选先例）。"""
    from game_core.card import Card
    return [Card.GetCard(n).assign_owner(player) for n in _YYL_BLAST_X_NAMES]


def _wukongburu_on_play(s):
    player = s.owner
    sel = getattr(player, "selected_targets", None) or []
    if sel:
        player.hand.append(sel[0])


def _wukongburu_after_play(s):
    _yyl_summon_clone(s.owner)


class WuKongBuRu:
    id = 323
    type = "morph"
    hero = "YanYanLuo"
    name = "无孔不入"
    level_req = 3
    atk = 3
    hp = 6
    is_beginning_card = True

    @staticmethod
    def select_target(card):
        player = card.owner
        if player is None:
            return None
        return (lambda s: select_target(
            player, _wukongburu_candidates(player), s),)

    on_play = (_wukongburu_on_play,)
    after_play = (_wukongburu_after_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  324 暴躁鬼 (BaoZaoGui)
#  投射：造成4点伤害。爆能X：额外造成X点伤害，X为全部能量。若击杀式神，获得4点能量。
# ═══════════════════════════════════════════════════════════════════════════════
def _baozaogui_on_play(s):
    player = s.owner
    game = player.game
    extra = _take_blast_extra(s)
    # 投射：优先敌方战斗区式神，战斗区为空改打敌方牌手（引擎 projectile 分支）
    before = [h for h in player.opponent.heroes if h.is_alive]
    game.handle_event(ProjectileEvent(4 + extra, s, [player.opponent.attack_zone]))
    # 若击杀式神，获得4点能量（投射打牌手时不获得）
    if any(not h.is_alive for h in before):
        hero = s.get_corresponding_hero()
        if hero is not None and hero.is_alive:
            hero.counters.inc("energy", 4)
            game.handle_event(EnergyGainEvent(hero, 4))


class BaoZaoGui:
    id = 324
    type = "spell"
    hero = "YanYanLuo"
    name = "暴躁鬼"
    level_req = 3
    is_beginning_card = True
    attributes = (CardAttributes.BLAST,)
    energy_cost = 1
    on_play = (_baozaogui_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  325 烟影 (YanYing)
#  召唤一个烟烟罗的分身并使其使用一张等同于烟烟罗当前等级的爆能法术。
#  羁绊：日和坊为己方具有充能式神+1能量。
# ═══════════════════════════════════════════════════════════════════════════════
_YYL_LEVEL_BLAST = {1: "WanPiGui", 2: "TanShiGui", 3: "BaoZaoGui"}


def _yanying_cast_candidates(player, yyl):
    """烟影使用法术的目标候选（1/2 勾手动选择；3 勾暴躁鬼投射自动，不选）。"""
    if yyl.level >= 3:
        return None
    if yyl.level == 2:
        tz = player.opponent.attack_zone
        return [tz] if (tz is not None and tz.is_alive and tz.level > 0) else []
    return _yyl_enemy_candidates(player)


def _yanying_bond(player):
    """烟影羁绊：打出时另一位协战式神（日和坊）存活且等级不为 0 →
    己方所有具有充能的式神各+1能量（含分身；先使用后羁绊，按牌面顺序）。"""
    game = player.game
    partner = next((h for h in player.heroes
                    if h.type_name == "RiHeFang"
                    and h.is_alive and h.level > 0), None)
    if partner is not None:
        for h in player.heroes:
            if h.is_alive and HeroAttributes.ENERGY_CHARGE in h.attributes:
                h.counters.inc("energy", 1)
                game.handle_event(EnergyGainEvent(h, 1))


def _yanying_on_play(s):
    player = s.owner
    yyl = _yyl_hero(player)
    if yyl is None:
        return
    clone = _yyl_summon_clone(player)
    if clone is not None:
        from game_core.card import Card
        targets = getattr(player, "selected_targets", None) or []
        name = _YYL_LEVEL_BLAST[max(1, min(3, yyl.level))]
        spell = Card.GetCard(name).assign_owner(player)
        is_copy = getattr(s, "_yyl_is_copy", False)
        x = clone.counters.get("energy", 0)
        if yyl.level < 3 and not targets:
            # 需手动目标的等级无可用目标：跳过使用（不空耗分身能量）
            spell = None
        if spell is not None:
            _yyl_run_cast(player, clone, spell, targets[0] if targets else None,
                          blast_x=x,
                          spend_from=None if is_copy else clone,
                          is_copy=is_copy)
    _yanying_bond(player)


def _yyl_riai_yanying_effect(player):
    """日霭相织-烟影分支（用户裁决 2026-09-29）：召唤分身后以正常打出流程
    （play_card）使用当前等级的爆能法术——目标选择由 play_card 的挂起-重放
    承担（1/2 勾需选目标，3 勾暴躁鬼投射自动）；免鬼火（裁决④a，打出的
    实例临时附加 NO_FIRE_CONSUMPTION）；爆能X 为分身全部能量（裁决④a，
    由 heroes.py 爆能X 监听覆盖分身）。分身能量在爆能结算时点锁定，羁绊在
    打出发起后结算，不放大本次 X（与烟影单独打出「先使用后羁绊」一致）。"""
    yyl = _yyl_hero(player)
    if yyl is None:
        return
    clone = _yyl_summon_clone(player)
    if clone is None:
        return
    from game_core.card import Card
    name = _YYL_LEVEL_BLAST[max(1, min(3, yyl.level))]
    spell = Card.GetCard(name).assign_owner(player)
    spell.played_by = clone   # 伤害与「击杀获得能量」归分身
    spell.attributes = tuple(spell.attributes) + (CardAttributes.NO_FIRE_CONSUMPTION,)
    # 清掉协战的分支选择，让法术走自己的 select_target 挂起选目标
    player.selected_targets = None
    player.game.play_card(player, spell, use_blast=True)
    _yanying_bond(player)


class YanYing:
    id = 325
    type = "spell"
    hero = "YanYanLuo"
    name = "烟影"
    level_req = 1
    is_beginning_card = False

    @staticmethod
    def select_target(card):
        """1/2 勾等级需为目标选择（分身使用法术的目标手动选择，用户裁决④a）；
        3 勾（暴躁鬼投射）或无可用候选时跳过选择。"""
        player = card.owner
        if player is None:
            return None
        yyl = _yyl_hero(player)
        if yyl is None:
            return None
        cands = _yanying_cast_candidates(player, yyl)
        if not cands:
            return None
        return (lambda s: select_target(player, cands, s),)

    on_play = (_yanying_on_play,)
