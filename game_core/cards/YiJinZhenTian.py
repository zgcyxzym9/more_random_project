"""以津真天 专属卡牌"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _countdown_reduce(hero, amount: int = 1):
    """倒计时能力 -X（妖琴师模式）：扣减 countdown，归零时重置并触发倒计时效果。"""
    if hero is None or hero.countdown_max <= 0 or hero.countdown <= 0:
        return
    hero.countdown -= amount
    if hero.countdown <= 0:
        hero.countdown = hero.countdown_max
        game = hero.owner.game
        game.handle_event(CountdownEvent(hero))
        for callback in hero.on_countdown:
            result = callback(hero)
            if result is not None and isinstance(result, Event):
                game.handle_event(result)


def _revive_countdown_reduce(hero, amount: int = 1):
    """气绝倒计时 -X：减少复活倒计时（round_until_alive），存活时无实际效果。"""
    if hero is None or hero.round_until_alive <= 0:
        return
    hero.round_until_alive = max(0, hero.round_until_alive - amount)


def _huangjinyu_used(card):
    """记录一次「黄金羽」（含金风流羽视为黄金羽）的使用。

    供风之舞增强 / 金风流羽不耗火 / 千羽风之舞 / 不可饶恕免疫等读取。
    """
    game = card.owner.game
    game.counters.ensure("huangjin_yu_used", persistent=True)
    game.counters.ensure("huangjin_yu_this_turn", reset_per_turn=True)
    game.counters.inc("huangjin_yu_used")
    game.counters.inc("huangjin_yu_this_turn")


# ── Token：黄金羽 ──────────────────────────────────────────────────────────

class HuangJinYu:
    """黄金羽：瞬发 对敌方牌手造成2点伤害。
    未觉醒时无需选择目标（直击敌方牌手）；觉醒后可以以敌方式神为目标。"""
    id = 52
    type = "spell"
    hero = "YiJinZhenTian"
    name = "黄金羽"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _huangjinyu_on_play(s),)

    @staticmethod
    def select_target(card):
        """觉醒后以敌方式神为目标；未觉醒返回 None → 完全跳过目标选择流程。"""
        if card.owner is None:
            return None
        hero = card.get_corresponding_hero()
        if hero is None or not hero.is_awakened:
            return None
        player = card.owner
        enemies = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
        return (lambda s: select_target(player, [player.opponent] + enemies, s),)


def _huangjinyu_on_play(s):
    _huangjinyu_used(s)
    hero = s.get_corresponding_hero()
    # 觉醒后目标可为敌方牌手或敌方式神；未觉醒默认直击敌方牌手
    target = s.owner.selected_targets[0] if s.owner.selected_targets else s.owner.opponent
    # 鎏金幻羽强化：伤害+1；使用后以津真天和鸩气绝倒计时-1
    if getattr(s, "liujin_buffed", False):
        damage = 3
        _revive_countdown_reduce(hero, 1)
        zhen = next((h for h in s.owner.heroes if h.type_name == "Zhen"), None)
        _revive_countdown_reduce(zhen, 1)
    else:
        damage = 2
    return DealDamage(damage, s, [target])


# ── 1勾卡牌 ───────────────────────────────────────────────────────────────

class JinYuHuanSheng:
    """金羽焕生：将两张「黄金羽」置入手牌。"""
    id = 53
    type = "spell"
    hero = "YiJinZhenTian"
    name = "金羽焕生"
    level_req = 1
    on_play = (lambda s: _jinyuhuansheng_on_play(s),)

def _jinyuhuansheng_on_play(s):
    s.owner.GiveCardToHand(["HuangJinYu", "HuangJinYu"])


class FengZhiWu:
    """风之舞：战斗 +0/+0。增强：本局游戏每使用过一次「黄金羽」，此牌获得+1攻+1甲。"""
    id = 54
    type = "attack"
    hero = "YiJinZhenTian"
    name = "风之舞"
    level_req = 1
    buff_atk = 0
    buff_def = 0
    on_play = (lambda s: _fengzhiwu_on_play(s),)

def _fengzhiwu_on_play(s):
    count = s.owner.game.counters.get("huangjin_yu_used")
    s.buff_atk += count
    s.buff_def += count


# ── 2勾卡牌 ───────────────────────────────────────────────────────────────

class JinFengLiuYu:
    """金风流羽：战斗 +1/+0。此牌使用时视为「黄金羽」。本回合若使用过「黄金羽」，此牌不消耗鬼火。"""
    id = 55
    type = "attack"
    hero = "YiJinZhenTian"
    name = "金风流羽"
    level_req = 2
    buff_atk = 1
    buff_def = 0
    on_play = (lambda s: _jinfl_on_play(s),)

def _jinfl_on_play(s):
    # 本回合使用过黄金羽 → 不消耗鬼火（返还1鬼火）
    if s.owner.game.counters.get("huangjin_yu_this_turn", 0) > 0:
        s.owner.fire_cnt += 1
    # 此牌使用时视为「黄金羽」
    _huangjinyu_used(s)


class BuKeRaoShu:
    """不可饶恕：形态 4/6。本回合若使用过「黄金羽」，以津真天免疫战斗伤害。"""
    id = 56
    type = "morph"
    hero = "YiJinZhenTian"
    name = "不可饶恕"
    level_req = 2
    atk = 4
    hp = 6
    on_play = (lambda s: _bukerashu_on_play(s),)

def _bukerashu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 免疫逻辑全部由监听器实现：动态读取“本回合使用过黄金羽”，
    # 因此黄金羽在打出本形态之前或之后使用均生效；式神气绝时监听器随
    # original_listeners 重置，形态离场即失效。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "bukerashu_immune"]
    l = Listener("hero attack", _bukerashu_immune_cond, (_bukerashu_immune,))
    l._tag = "bukerashu_immune"
    hero.listeners.append(l)

def _bukerashu_immune_cond(e, s):
    """本回合使用过黄金羽，且以津真天参与本场战斗（出击或受击）。"""
    if s.owner.game.counters.get("huangjin_yu_this_turn", 0) <= 0:
        return False
    if e.event.hero is s:
        return True   # 以津真天出击
    if e.event.hero.owner is s.owner:
        return False  # 己方其他式神出击，与以津真天无关
    # 敌方出击：目标是以津真天（HUNTING 目标或敌方攻击区）
    return getattr(e.event, "target", None) is s or e.event.hero.owner.opponent.attack_zone is s

def _bukerashu_immune(e, s):
    if e.event.hero is s:
        # 以津真天出击：防御方反击会伤害到她 → 加屏障拦截本次反击
        defender = s.owner.opponent.attack_zone or s.owner.opponent
        if getattr(defender, "atk", 0) > 0:
            if HeroAttributes.BARRIER not in s.attributes:
                s.attributes.append(HeroAttributes.BARRIER)
    else:
        # 敌方出击攻击以津真天：压制敌方本次攻击的战斗伤害（保留以津真天反击）
        e.event.hero._suppress_combat_damage = True


class SheGuaiNiaoShi:
    """射怪鸟事：瞬发 弃掉所有以津真天的专属牌，抽等量的牌。
    响应：当以津真天将气绝时，自动使用此牌。"""
    id = 57
    type = "spell"
    hero = "YiJinZhenTian"
    name = "射怪鸟事"
    level_req = 2
    attributes = (CardAttributes.INSTANT, CardAttributes.RESPONSE)
    response_trigger = "about to die"
    # 响应：以津真天将气绝时自动打出（敌方回合）。目标为将气绝的式神自身。
    response_condition = (lambda s, event, target: s.get_corresponding_hero() is target,)
    on_play = (lambda s: _sheguainiaoshi_on_play(s),)

def _sheguainiaoshi_on_play(s):
    player = s.owner
    # 弃掉手牌中其他以津真天专属牌（排除自身：射怪鸟事是被"打出"而非"弃掉"，
    # 由 play_card 的 move_card_to_used 统一进弃牌堆一次，避免弃牌堆出现两份）
    to_discard = [c for c in player.hand.cards if c.hero == "YiJinZhenTian" and c is not s]
    count = len(to_discard)
    for c in to_discard:
        player.hand.remove(c)
        player.used_card.append(c)
    # 抽等量的牌
    for _ in range(count):
        player.draw()


class JueXingYiJinZhenTian:
    """觉醒·以津真天：倒计时变为1，黄金羽可以以敌方式神为目标。"""
    id = 58
    type = "spell"
    hero = "YiJinZhenTian"
    name = "觉醒·以津真天"
    level_req = 2
    on_play = (lambda s: _juexing_yjzt_on_play(s),)

def _juexing_yjzt_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.countdown_max = 1
    hero.countdown = 1
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True


# ── 3勾卡牌 ───────────────────────────────────────────────────────────────

class QianYuFengZhiWu:
    """千羽风之舞：战斗 +3/+3。本回合若使用过黄金羽，将一张金风流羽置入手牌。"""
    id = 59
    type = "attack"
    hero = "YiJinZhenTian"
    name = "千羽风之舞"
    level_req = 3
    buff_atk = 3
    buff_def = 3
    on_play = (lambda s: s.owner.GiveCardToHand(["JinFengLiuYu"])
               if s.owner.game.counters.get("huangjin_yu_this_turn", 0) > 0 else None,)


class LiuLangZhiYu:
    """流浪之羽：形态 4/8。当以津真天使用「黄金羽」时，对所有敌方式神造成2点伤害，此效果执行2次。"""
    id = 60
    type = "morph"
    hero = "YiJinZhenTian"
    name = "流浪之羽"
    level_req = 3
    atk = 4
    hp = 8
    on_play = (lambda s: _liulangzhiyu_on_play(s),)

def _liulangzhiyu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "liulangzhiyu"]
    l = Listener("play card",
                 lambda e, h: e.event.card is not None and e.event.card.owner == h.owner
                              and e.event.card.eng_name in ("HuangJinYu", "JinFengLiuYu"),
                 (lambda e, h: _liulangzhiyu_trigger(e, h),))
    l._tag = "liulangzhiyu"
    hero.listeners.append(l)

def _liulangzhiyu_trigger(e, h):
    enemies = [h2 for h2 in h.owner.opponent.heroes if h2.is_alive and h2.level > 0]
    if not enemies:
        return
    # 此效果执行2次（敌方式神死亡后第二次自动跳过）
    for _ in range(2):
        h.owner.game.handle_event(DealDamage(2, h, enemies))


# ── 鎏金幻羽 & 协战牌 ─────────────────────────────────────────────────────

class LiuJinHuanYu:
    """鎏金幻羽：不消耗鬼火 使手牌所有「黄金羽」获得「气绝时可用，伤害+1，
    使用后以津真天和鸩气绝倒计时-1」（不可叠加） 羁绊：鸩倒计时-2。"""
    id = 62
    type = "spell"
    hero = "YiJinZhenTian"
    name = "鎏金幻羽"
    level_req = 2
    attributes = (CardAttributes.NO_FIRE_CONSUMPTION,)
    on_play = (lambda s: _liujinhuanyu_on_play(s),)

def _liujinhuanyu_on_play(s):
    player = s.owner
    # 使手牌所有黄金羽获得强化（不可叠加）
    for card in player.hand.cards:
        if card.eng_name == "HuangJinYu":
            card.liujin_buffed = True
            if CardAttributes.CAN_PLAY_WHEN_DEAD not in card.attributes:
                card.attributes.append(CardAttributes.CAN_PLAY_WHEN_DEAD)
    # 羁绊：鸩倒计时-2（打出鎏金幻羽时触发）
    zhen = next((h for h in player.heroes if h.type_name == "Zhen"), None)
    if zhen is not None and zhen.is_alive:
        _countdown_reduce(zhen, 2)


class ZhiMingZhiYu:
    """致命之羽（协战）：选择使用一项：鸩-蚀刃毒羽；以津真天-鎏金幻羽。"""
    id = 61
    type = "coop"
    hero = "YiJinZhenTian"
    heroes = ["YiJinZhenTian", "Zhen"]
    name = "致命之羽"
    level_req = 2
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes
         if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (lambda s: _zhimingzhiyu_on_play(s),)

def _zhimingzhiyu_on_play(s):
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "YiJinZhenTian":
        # 以津真天-鎏金幻羽（协战牌已消耗鬼火，不再额外消耗）
        _liujinhuanyu_on_play(s)
    elif hero.type_name == "Zhen":
        # 鸩-蚀刃毒羽：随鸩的卡牌实现一并完成（TODO）
        pass