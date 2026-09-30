"""青行灯卡牌（id 326-334）。

牌面文本以 cards.json 条目（326-334）为准。式神段（基础被动获得明灯、觉醒的
鬼火不清除/上限 4）在 heroes.py 青行灯段；本文件实现卡牌打出侧逻辑。

口径与裁决记录（用户 2026-09-29）：
- 「你每有1点鬼火便重复一次」（青灯夜谈/吸魂灯）：包括打出消耗的 1 点鬼火，
  每点鬼火执行一次，直到清空——即 1 + 扣费后剩余；执行完毕清空剩余鬼火。
- 鬼火获取经 _qxd_gain_fire：觉醒后封顶 4（「最大可储存4点」），未觉醒不设限。
- 觉醒·青行灯（333）：on_play 置 is_awakened + 永久 +1/+1（辉夜姬觉醒先例）；
  「鬼火不会自动清除」由 heroes.py 的快照（begin turn before）/恢复（after）
  监听实现（引擎鬼火重置已移至第一次广播之后，2026-09-29 用户方案）。
- 百闻一得（329）：手牌无「明灯」时候选为空 → play_card 放弃打出（不扣鬼火）；
  候选 = 己方最低等级的式神（并列全部可选，含气绝——等级是永久属性）；
  等级已为 3 的目标改为抽一张牌。
- 不灭之火（331）：「被消灭时消耗1点鬼火返回场上」用 on_before_death 协议实现
  （狂啸先例）：有鬼火则消耗 1 点并阻止死亡。战斗结算顺序为 伤害→不屈→必杀
  置 hp=0→check_death 守护，守护运行在必杀之后（2026-09-30 实测：hp=10 承受
  必杀攻击，伤害后 hp>0 走必杀置 0 分支，守护消耗鬼火救回）。
- 幽光之火（328）/百物语之火（330）：形态效果以 hero listener + morphed_id
  门控实现（金运大吉先例），形态离场（气绝/换形态）自动失效。
- 烛火重燃（334，2026-09-30 用户要求补全，取代此前暂缓裁决）：引擎暂无启悟区
  ——当前法术全部从手牌打出，「从手牌使用法术」即全部可表达触发路径（响应牌
  经 play_card 直调不广播，不触发，与涅槃业火同口径）；「唯一」= 进场前移除
  己方同名幻境（旧实例监听一并换挂）；「气绝时可用」= CAN_PLAY_WHEN_DEAD 属性；
  「非战斗伤害+1直到回合结束」= round_buff_spell_damage（天邪鬼团火先例；法术
  打出通道自动附加、clear_round_effects 回合清零，投射等手动路径不自动附加——
  焚羽同款引擎限制）；持续效果监听挂玩家 listeners + 幻境在区守卫（辉夜姬
  幻境同款），随幻境离场自动失效；「羁绊：进场时获得一张凤火」按 faq 协战
  羁绊规则门控（凤凰火存活且等级不为 0）；涅槃明灯的青行灯选项可选中气绝的
  青行灯（2026-09-30 用户裁决，选项沿用「气绝时可用」）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _qxd_gain_fire(player, n):
    """获得 n 点鬼火：觉醒·青行灯存在（is_awakened）时封顶 4（最大可储存4点）。"""
    hero = next((h for h in player.heroes if h.type_name == "QingXingDeng"), None)
    if hero is not None and hero.is_awakened:
        player.fire_cnt = min(4, player.fire_cnt + n)
    else:
        player.fire_cnt += n


# ── 326 明灯 (MingDeng) ─────────────────────────────────────────────────────
# 瞬发 你获得1点鬼火。
# 英雄被动「敌方回合开始时若你有剩余鬼火，获得一张明灯」经 GiveCardToHand
# 自动入手（heroes.py 监听）；本类实装后该监听的 TODO 门自动打开。

def _mingdeng_on_play(s):
    _qxd_gain_fire(s.owner, 1)


class MingDeng:
    id = 326
    type = "spell"
    hero = "QingXingDeng"
    name = "明灯"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (lambda s: _mingdeng_on_play(s),)


# ── 327 青灯夜谈 (QingDengYeTan) ────────────────────────────────────────────
# 检视牌库顶三张牌然后选择一张置入手牌，然后洗牌库。
# 你每有1点鬼火便重复一次。清空你的鬼火。
#
# 检视三选一复用明心的挂起回调机制（candidate_targets + _pending_option_callback
# + SELECTING_TARGET，无挂起动作的纯回调选择，见 game.step "select target"）。
# 执行次数（用户裁决 2026-09-29）：1 + 扣费后剩余鬼火；执行完毕鬼火清空（=0）。

def _qingdengyatan_on_play(s):
    player = s.owner
    rounds = 1 + player.fire_cnt
    player.fire_cnt = 0                      # 次数已锁定，清空鬼火
    state = {"left": rounds}

    def _next_round():
        cands = list(player.deck.cards[:3])
        if not cands:
            return                           # 牌库空：剩余轮次无从执行
        player.candidate_targets = cands
        player._pending_option_callback = _choose
        player.state = PlayerState.SELECTING_TARGET

    def _choose(chosen):
        # 选中的一张置入手牌，然后洗牌库（含未选的两张）
        if chosen in player.deck.cards:
            player.deck.cards.remove(chosen)
        chosen.assign_owner(player)
        if len(player.hand.cards) >= 12:     # 手牌上限（GiveCardToHand 同款）
            player.used_card.append(chosen)
        else:
            player.hand.append(chosen)
            if player.initial_pick_reject_left == 0:
                player.sort_hand()
        player.deck.shuffle()
        state["left"] -= 1
        if state["left"] > 0:
            _next_round()

    _next_round()


class QingDengYeTan:
    id = 327
    type = "spell"
    hero = "QingXingDeng"
    name = "青灯夜谈"
    level_req = 1
    is_beginning_card = True
    on_play = (_qingdengyatan_on_play,)


# ── 328 幽光之火 (YouGuangZhiHuo) ───────────────────────────────────────────
# 形态 4/5。当青行灯攻击时，获得一张「明灯」。
# （形态效果以 hero listener + morphed_id 门控：气绝/换形态自动失效；
#  「攻击」含出击与战斗牌——两条路径都广播 hero attack。）

def _youguang_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "youguang"]
    # e 为 broadcast 的 wrapper 事件，原始 HeroAttackEvent 在 e.event（既有监听同款）
    l = Listener("hero attack",
                 lambda e, h: (e.event.hero is h and h.is_alive
                               and h.morphed_id == YouGuangZhiHuo.id),
                 (lambda e, h: h.owner.GiveCardToHand(["MingDeng"]),))
    l._tag = "youguang"
    hero.listeners.append(l)


class YouGuangZhiHuo:
    id = 328
    type = "morph"
    hero = "QingXingDeng"
    name = "幽光之火"
    level_req = 1
    atk = 4
    hp = 5
    is_beginning_card = True
    on_play = (_youguang_on_play,)


# ── 329 百闻一得 (BaiWenYiDe) ───────────────────────────────────────────────
# 弃掉一张「明灯」，使一个己方最低等级的式神等级+1。
# 若其等级已为3则改为抽一张牌。

def _baiwenyide_select(s):
    """select_target 解析（黄金羽 callable 形式）：手牌无「明灯」时候选为空
    → play_card 放弃本次打出（不扣鬼火）。候选 = 己方最低等级的式神
    （并列全部可选；含气绝——等级是永久属性，升级对气绝式神同样有意义）。"""
    player = s.owner
    if not any(c.eng_name == "MingDeng" for c in player.hand.cards):
        return
    lowest = min(h.level for h in player.heroes)
    player.candidate_targets = [h for h in player.heroes if h.level == lowest]


def _baiwenyide_on_play(s):
    player = s.owner
    # 先弃掉一张「明灯」（打出前提已由 select_target 校验）
    for c in list(player.hand.cards):
        if c.eng_name == "MingDeng":
            player.hand.remove(c)
            break
    chosen = player.selected_targets[0] if player.selected_targets else None
    if chosen is None:
        return
    if chosen.level >= 3:
        # 等级已为 3：改为抽一张牌
        player.game.handle_event(DrawEvent(player, 1))
    else:
        chosen.Upgrade()


class BaiWenYiDe:
    id = 329
    type = "spell"
    hero = "QingXingDeng"
    name = "百闻一得"
    level_req = 2
    is_beginning_card = True
    select_target = (_baiwenyide_select,)
    on_play = (_baiwenyide_on_play,)


# ── 330 百物语之火 (BaiWuYuZhiHuo) ──────────────────────────────────────────
# 形态 4/5。己方回合结束时，你获得1点鬼火。
# （end turn 的 after 广播发生在下一回合 begin_turn 完整执行之后：
#  current_player 已切换为下一玩家 → 刚结束回合者是 current_player.opponent；
#  此刻本方鬼火尚未被下一次重置触及，+1 正常保留到本方下回合开始。）

def _baiwuyu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "baiwuyu"]
    # phase="after"：绑定 step 末尾的 "end turn" after 广播（回合切换完成后），
    # before 阶段的本事件广播点无此语义。
    l = Listener("end turn",
                 lambda e, h: (h.is_alive and h.morphed_id == BaiWuYuZhiHuo.id
                               and h.owner is not None
                               and h.owner is h.owner.game.current_player.opponent),
                 (lambda e, h: _qxd_gain_fire(h.owner, 1),),
                 phase="after")
    l._tag = "baiwuyu"
    hero.listeners.append(l)


class BaiWuYuZhiHuo:
    id = 330
    type = "morph"
    hero = "QingXingDeng"
    name = "百物语之火"
    level_req = 2
    atk = 4
    hp = 5
    is_beginning_card = True
    on_play = (_baiwuyu_on_play,)


# ── 331 不灭之火 (BuMieZhiHuo) ──────────────────────────────────────────────
# 形态 4/5。当此牌被消灭时，消耗1点鬼火，返回场上。
# （on_before_death 协议（狂啸先例）：check_death 是三条伤害通道共用的唯一
#  死亡结算点；有鬼火则消耗 1 点并阻止死亡（=「返回场上」，形态保持）。
#  时点：战斗结算 伤害→不屈→必杀置 hp=0→check_death，守护已在必杀之后运行
#  （2026-09-30 实测确认；AboutToDieEvent 在守护未救回时才广播且无法中止
#  死亡流程，故不采用）。）

def _bumiezhihuo_guard(hero):
    def cb(h):
        if h.morphed_id != BuMieZhiHuo.id:
            return False                     # 非本形态（气绝复位/换形态后）放行
        if h.owner is None or h.owner.fire_cnt < 1:
            return False                     # 无鬼火：正常气绝
        h.owner.fire_cnt -= 1                # 消耗 1 点鬼火
        return True                          # 阻止死亡 = 返回场上
    cb._bumiezhihuo_guard = True
    return cb


def _bumiezhihuo_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    if not any(getattr(c, "_bumiezhihuo_guard", False)
               for c in hero.on_before_death):
        hero.on_before_death = hero.on_before_death + (_bumiezhihuo_guard(hero),)


class BuMieZhiHuo:
    id = 331
    type = "morph"
    hero = "QingXingDeng"
    name = "不灭之火"
    level_req = 3
    atk = 4
    hp = 5
    is_beginning_card = True
    on_play = (_bumiezhihuo_on_play,)


# ── 332 吸魂灯 (XiHunDeng) ──────────────────────────────────────────────────
# 投射：造成5点伤害。你每有1点鬼火便重复一次。清空你的鬼火。
# （投射目标由引擎自动指定：优先敌方战斗区式神，为空改打敌方牌手；
#  每次重复独立投射，目标随战场实时解析。）

def _xihundeng_on_play(s):
    player = s.owner
    opp = player.opponent
    times = 1 + player.fire_cnt            # 次数裁决同青灯夜谈
    player.fire_cnt = 0
    for _ in range(times):
        player.game.handle_event(ProjectileEvent(5, s, [opp.attack_zone]))


class XiHunDeng:
    id = 332
    type = "spell"
    hero = "QingXingDeng"
    name = "吸魂灯"
    level_req = 3
    is_beginning_card = True
    on_play = (_xihundeng_on_play,)


# ── 333 觉醒·青行灯 (JueXingQingXingDeng) ───────────────────────────────────
# 觉醒：敌方回合开始时若你有剩余鬼火，获得一张「明灯」。
# 你的鬼火不会自动清除，最大可储存4点。
# （基础被动本就监听敌方回合开始（heroes.py），觉醒后同一监听继续生效、不
#  重复挂载；「鬼火不会自动清除，最大可储存4点」由 heroes.py 的快照（begin
#  turn before）/恢复（after）监听实现，is_awakened 门控。）

def _juexingqxd_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.is_awakened = True
    # 觉醒永久 +1/+1（同旧版 spell 觉醒牌：buff_atk/buff_hp 在 on_play 手动应用）
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)


class JueXingQingXingDeng:
    id = 333
    type = "spell"
    hero = "QingXingDeng"
    name = "觉醒·青行灯"
    level_req = 3
    is_beginning_card = True
    on_play = (_juexingqxd_on_play,)


# ── 334 烛火重燃 (ZhuHuoChongRan) ───────────────────────────────────────────
# 幻境 lv2，耐久5，唯一，气绝时可用。每回合每个己方式神一次，从手牌或启悟区
# 使用法术后复活青行灯，该式神造成的非战斗伤害+1直到回合结束。
# 羁绊：进场时获得一张凤火。

def _zhuhuochongran_on_play(s):
    """进场：唯一（移除己方已有同名幻境）+ 持续效果监听 + 羁绊获得一张凤火。"""
    player = s.owner
    card = s
    for ill in list(player.illusion_zone):
        if getattr(ill, "eng_name", "") == "ZhuHuoChongRan":
            player.illusion_zone.remove(ill)
    player.listeners = [l for l in player.listeners
                        if getattr(l, "_tag", "") != "zhuhuochongran"]
    l = Listener("play card",
                 lambda e, s2: (card in s2.illusion_zone
                                and e.event.card.owner is s2
                                and e.event.card.card_type == CardType.SPELL),
                 (_zhuhuochongran_trigger,), phase="after")
    l._tag = "zhuhuochongran"
    player.listeners.append(l)
    # 羁绊：进场时获得一张凤火（faq 协战羁绊规则：另一位协战式神——凤凰火
    # 存活且等级不为 0 时生效）
    partner = next((h for h in player.heroes
                    if h.type_name == "FengHuangHuo"
                    and h.is_alive and h.level > 0), None)
    if partner is not None:
        player.GiveCardToHand(["FengHuo"])


def _zhuhuochongran_trigger(e, s2):
    # 每回合每个己方式神一次（reset_per_turn：begin_turn 对双方式神统一重置）
    caster = e.event.card.get_corresponding_hero()
    if caster is None:
        return
    caster.counters.ensure("zhuhuochongran_cast", initial=0, reset_per_turn=True)
    if caster.counters.get("zhuhuochongran_cast") > 0:
        return
    caster.counters.set("zhuhuochongran_cast", 1)
    # 复活气绝的青行灯（未气绝时无复活，+1 照常生效——用户裁决口径）
    qxd = next((h for h in s2.heroes if h.type_name == "QingXingDeng"), None)
    if qxd is not None and qxd.state == "dead":
        s2.game.handle_event(Revive(e.event.card, [qxd]))
    # 该式神造成的非战斗伤害+1直到回合结束（clear_round_effects 回合清零）
    s2.game.handle_event(GiveBuff("round_buff_spell_damage", 1, e.event.card, [caster]))


def _zhuhuochongran_summon(player):
    """召唤一个烛火重燃幻境：跑 on_play → 入幻境区 → 广播 IllusionPlayedEvent
    （辉夜姬 _summon_hyj_illusion 同款；供协战牌涅槃明灯的青行灯选项复用）。"""
    from game_core.card import Card
    card = Card.GetCard("ZhuHuoChongRan").assign_owner(player)
    if hasattr(card, "on_play"):
        for cb in card.on_play:
            result = cb(card)
            if isinstance(result, Event):
                player.game.handle_event(result)
    player.illusion_zone.append(card)
    player.game.handle_event(IllusionPlayedEvent(player, card))
    return card


class ZhuHuoChongRan:
    id = 334
    type = "illusion"
    hero = "QingXingDeng"
    name = "烛火重燃"
    level_req = 2
    durability = 5
    # 气绝时可用：青行灯气绝时仍可打出（can_play_card 的 CAN_PLAY_WHEN_DEAD 通道）
    attributes = (CardAttributes.CAN_PLAY_WHEN_DEAD,)
    is_beginning_card = False
    on_play = (lambda s: _zhuhuochongran_on_play(s),)
