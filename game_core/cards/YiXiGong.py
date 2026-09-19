"""饴细工 专属卡牌（cards 212-219）

大火熬糖 / 糖人大师 / 回炉成浆 / 融芯化火 / 一物一心 /
觉醒·饴细工 / 苦中作甜 / 甘如暖阳

数据来源：cards.json + tmp_cards_json/YiXiGong.json（描述逐字拷贝）。
引擎缺失/语义无法核实的机制一律标注 TODO（需引擎支持，等审批）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener, CardEnhance
from game_core.selector import *
from game_core.cards._ingredients import _yiwuyixin_active


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _count_hand_yvg(player):
    """手牌中「食材」或「佳肴」的数量（大火熬糖/融芯化火按张数加成）。"""
    return sum(1 for c in player.hand.cards
               if getattr(c, "is_ingredient", False) or getattr(c, "eng_name", "") == "JiaYao")


def _count_hand_jiaoyao(player):
    """手牌中「佳肴」的数量。"""
    return sum(1 for c in player.hand.cards if getattr(c, "eng_name", "") == "JiaYao")


def _enemy_characters(player):
    """敌方所有角色：存活且已升级的式神（无帷幕）+ 敌方牌手。"""
    enemies = [h for h in player.opponent.heroes
               if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes]
    enemies.append(player.opponent)
    return enemies


def _enemy_heroes(player):
    """敌方存活且已升级的式神（无帷幕）。"""
    return [h for h in player.opponent.heroes
            if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes]


# ── 佳肴获得跟踪 ────────────────────────────────────────────────────────────
# 「本局游戏获得了 X 张佳肴」的计数由 heroes.py 饴细工英雄层的监听器维护
# （开局即生效，烹饪以手牌增量计、直接获得经 _yxg_gain_jiaoyao 同步），
# 此处只读取计数。

def _yvg_jiaoyao_gained(player):
    """本局累计获得「佳肴」张数（跟踪未初始化时返回 0）。"""
    return getattr(player, "_yxg_jiaoyao_total", 0)


def _gain_jiaoyao(player, buff_atk, buff_hp):
    """获得一张「佳肴」入手牌（甘如暖阳用），并同步佳肴跟踪。

    甘如暖阳所得佳肴的具体加成数值待核实（src 未给出），此处以 +buff_atk/+buff_hp 占位。
    """
    jy = player.game._create_jiaoyao(player, buff_atk, buff_hp)
    from game_core.heroes import _yxg_gain_jiaoyao
    if len(player.hand.cards) < 12:
        player.hand.append(jy)
        player.sort_hand()
        _yxg_gain_jiaoyao(player)
    else:
        player.used_card.append(jy)
        _yxg_gain_jiaoyao(player, in_hand=False)


# ── 1勾卡牌 ─────────────────────────────────────────────────────────────────

class DaHuoAoTang:
    """大火熬糖：对一名敌方角色造成3点伤害，恢复你2生命。
    你手牌中每有一张「食材」或「佳肴」便额外恢复你1生命。"""
    id = 212
    type = "spell"
    hero = "YiXiGong"
    name = "大火熬糖"
    level_req = 1
    require_target = (lambda s: _enemy_characters(s.owner),)
    select_target = (lambda s: select_target(s.owner, _enemy_characters(s.owner), s),)
    on_play = (lambda s: _dahuoaotang_on_play(s),)


def _dahuoaotang_on_play(s):
    player = s.owner
    target = player.selected_targets[0]
    player.game.handle_event(DealDamage(3, s, [target]))
    heal = 2 + _count_hand_yvg(player)
    player.game.handle_event(Heal(heal, s, [player]))


class TangRenDaShi:
    """糖人大师：进场时召唤一个「小糖人」；当你从手牌使用「佳肴」时，召唤一个「大糖人」。

    召唤走引擎 SummonEvent（进战斗区、不可升级、替换离场）；融合（FUSE）由
    summon 分支结算（#13）：小/大糖人互相合并（身材相加、关键词并集）。
    「从手牌使用」以 "play card" 广播近似：手牌打出与响应打出均广播，
    效果联动自动使用（如五丸佳肴）不广播、不触发。
    """
    id = 213
    type = "morph"
    hero = "YiXiGong"
    name = "糖人大师"
    level_req = 1
    atk = 2
    hp = 6
    on_play = (lambda s: _tangrendashi_on_play(s),)


def _tangrendashi_on_play(s):
    player = s.owner
    player.game.handle_event(SummonEvent(player, "XiaoTangRen"))
    hero = next((h for h in player.heroes if h.type_name == "YiXiGong"), None)
    if hero is None:
        return
    tag = "tangrendashi-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]

    def cond(e, h):
        card = getattr(e.event, "card", None)
        return (h.is_alive and h.morphed_id == 213
                and card is not None and getattr(card, "eng_name", "") == "JiaYao"
                and getattr(card, "owner", None) is h.owner)

    def effect(e, h):
        h.owner.game.handle_event(SummonEvent(h.owner, "DaTangRen"))

    l = Listener("play card", cond, (effect,), phase="after")
    l._tag = tag
    hero.listeners.append(l)


# ── 2勾卡牌 ─────────────────────────────────────────────────────────────────

class HuiLuChengJiang:
    """回炉成浆：抽两张牌，恢复你2生命。
    增强：若你本局游戏获得了3张「佳肴」，此牌得瞬发，且额外恢复你2生命。

    增强走引擎通用机制（#13 用户裁决）：can_play_card 以「满足条件增强后的
    复制体」判定（瞬发生效，0 鬼火也可打出）；确定打出后由 play_card 开头把
    增强写到这张卡上（占用每回合一次瞬发名额、结算追加恢复2生命）。
    """
    id = 214
    type = "spell"
    hero = "YiXiGong"
    name = "回炉成浆"
    level_req = 2
    enhance = (CardEnhance(
        cond=lambda s: _yvg_jiaoyao_gained(s.owner) >= 3,
        attributes=(CardAttributes.INSTANT,),
        on_play=(lambda s: Heal(2, s, [s.owner]),),
    ),)
    on_play = (lambda s: s.owner.draw(),
               lambda s: s.owner.draw(),
               lambda s: Heal(2, s, [s.owner]),)


class RongXinHuaHuo:
    """融芯化火：对一个式神造成4点伤害，
    你手牌中每有一张「食材」或「佳肴」便伤害+1。"""
    id = 215
    type = "spell"
    hero = "YiXiGong"
    name = "融芯化火"
    level_req = 2
    require_target = (lambda s: _enemy_heroes(s.owner),)
    select_target = (lambda s: select_target(s.owner, _enemy_heroes(s.owner), s),)
    on_play = (lambda s: _rongxinhuahuo_on_play(s),)


def _rongxinhuahuo_on_play(s):
    player = s.owner
    target = player.selected_targets[0]
    dmg = 4 + _count_hand_yvg(player)
    player.game.handle_event(DealDamage(dmg, s, [target]))


class YiWuYiXin:
    """一物一心：己方回合开始时烹饪。你的「佳肴」可以对气绝状态式神使用并使其复活。

    烹饪部分已实现；「佳肴复活气绝式神」需要引擎/卡牌数据（_ingredients.py 的佳肴
    require_target/select_target）支持在气绝式神上使用并复活，暂不实现。
    """
    id = 216
    type = "morph"
    hero = "YiXiGong"
    name = "一物一心"
    level_req = 2
    atk = 3
    hp = 6
    on_play = (lambda s: _yiwuyixin_on_play(s),)


def _yiwuyixin_buff_cond(e, h):
    """一物一心：佳肴给 buff 且目标含气绝式神 → 先复活再叠 buff。

    挂点选 "give buff" 广播：此时目标（selected_targets）已定，且广播先于
    handle_event 的 give buff case 结算，复活后式神 state 变为非 dead，
    buff 正常叠加。对任意时刻合成的佳肴生效（按 source 判定，与创建时机无关）。
    """
    buff = getattr(e.event, "source", None)
    return (getattr(buff, "eng_name", "") == "JiaYao"
            and getattr(buff, "owner", None) is h.owner
            and _yiwuyixin_active(h.owner)
            and any(not t.is_alive for t in e.event.target))


def _yiwuyixin_buff_revive(e, h):
    dead = [t for t in e.event.target if not t.is_alive]
    if dead:
        h.owner.game.handle_event(Revive(e.event.source, dead))


def _yiwuyixin_on_play(s):
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners
                      if getattr(l, "_tag", "") not in ("yiwuyixin", "yiwuyixin_buff")]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 216,
                 (lambda e, h: h.owner.game.cook(h.owner, h),))
    l._tag = "yiwuyixin"
    hero.listeners.append(l)
    l2 = Listener("give buff", _yiwuyixin_buff_cond, (_yiwuyixin_buff_revive,))
    l2._tag = "yiwuyixin_buff"
    hero.listeners.append(l2)


class JueXingYiXiGong:
    """觉醒·饴细工：觉醒：每回合一次，当己方式神使用法术牌时，烹饪。"""
    id = 217
    type = "spell"
    hero = "YiXiGong"
    name = "觉醒·饴细工"
    level_req = 2
    on_play = (lambda s: _juexing_yxg_on_play(s),)


def _juexing_yxg_on_play(s):
    hero = s.get_corresponding_hero()
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    player = s.owner
    # 觉醒：每回合一次，当己方式神使用法术牌时，烹饪。
    # 挂在牌手上（觉醒是永久能力，不随式神气绝重置）；与基础能力共用
    # "yixigong_cooked" 每回合一次计数，避免同一法术触发两次烹饪。
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != "yxg_awaken"]
    l = Listener("play card", _yxg_awaken_cond, (_yxg_awaken_cook,), phase="after")
    l._tag = "yxg_awaken"
    player.listeners.append(l)


def _yxg_awaken_cond(e, p):
    card = getattr(e.event, "card", None)
    if card is None or card.owner is not p:
        return False
    if not getattr(card, "hero", ""):               # 无归属式神的卡（食材/佳肴等 Token）不算式神法术
        return False
    if getattr(card, "card_type", None) != CardType.SPELL:
        return False
    yxg = next((h for h in p.heroes if h.type_name == "YiXiGong"), None)
    if yxg is None or not yxg.is_alive:
        return False
    return yxg.counters.get("yixigong_cooked", 0) == 0


def _yxg_awaken_cook(e, p):
    yxg = next((h for h in p.heroes if h.type_name == "YiXiGong"), None)
    if yxg is None:
        return
    yxg.counters.ensure("yixigong_cooked", initial=0, reset_per_turn=True)
    yxg.counters.set("yixigong_cooked", 1)
    p.game.cook(p, yxg)


# ── 3勾卡牌 ─────────────────────────────────────────────────────────────────

class KuZhongZuoTian:
    """苦中作甜：你手牌中每有一张「食材」，召唤一个「小糖人」。
    你手牌中每有一张「佳肴」，召唤一个「大糖人」。

    逐个召唤（融合由引擎逐次结算：2 张食材 → 2/2+2/2 合并为 4/4 单体）。
    食材/佳肴计数在结算时读取；逐个召唤不改变手牌，计数即最终值。
    """
    id = 218
    type = "spell"
    hero = "YiXiGong"
    name = "苦中作甜"
    level_req = 3
    on_play = (lambda s: _kuzhongzuotian_on_play(s),)


def _kuzhongzuotian_on_play(s):
    player = s.owner
    n_ingredient = sum(1 for c in player.hand.cards if getattr(c, "is_ingredient", False))
    n_jiaoyao = _count_hand_jiaoyao(player)
    for _ in range(n_ingredient):
        player.game.handle_event(SummonEvent(player, "XiaoTangRen"))
    for _ in range(n_jiaoyao):
        player.game.handle_event(SummonEvent(player, "DaTangRen"))


class GanRuNuanYang:
    """甘如暖阳：瞬发 获得一张「佳肴」，为你恢复4生命。
    若你本局游戏获得了6张「佳肴」，使你的所有式神永久获得5力量和5生命，为你恢复10生命。"""
    id = 219
    type = "spell"
    hero = "YiXiGong"
    name = "甘如暖阳"
    level_req = 3
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _ganrunuanyang_on_play(s),)


def _ganrunuanyang_on_play(s):
    player = s.owner
    # 获得一张「佳肴」。所得佳肴数值 src 未给出，此处按 3/3 占位（详见 _gain_jiaoyao）。
    _gain_jiaoyao(player, 3, 3)
    player.game.handle_event(Heal(4, s, [player]))
    if _yvg_jiaoyao_gained(player) >= 6:
        for h in player.heroes:
            h.get_permanent_buff("atk", 5)
            h.get_permanent_buff("hp", 5)
        player.game.handle_event(Heal(10, s, [player]))
