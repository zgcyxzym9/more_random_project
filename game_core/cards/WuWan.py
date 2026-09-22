"""五丸（WuWan）专属卡牌

数据来源：tmp_cards_json/WuWan.json + WuWan.sources.md（百度百科/萌娘百科 OCR/TapTap 交叉核实）。
数值（勾玉/身材）与 game_core/cards/cards.json 一致。

实现说明：
- 五丸基础能力（对敌方牌手造成战斗伤害时烹饪）在 heroes.py 中实现；觉醒·五丸在其基础上
  将「战斗伤害→烹饪」扩展到任意目标（仅当受击目标是式神时由觉醒监听触发，牌手目标仍由
  基础能力触发，避免一次攻击重复烹饪）。
- 食材/佳肴是对五丸使用时以 GiveBuff 事件广播的中立 Token（source=食材/佳肴卡，
  target=[五丸]）。多张五丸卡需要统计/监听这些使用，故在玩家上注册一个幂等的
  「give buff」全局跟踪监听器（_ensure_usage_tracking）。
- 局限性：跟踪监听器在打出第一张五丸卡时才注册（游戏引擎无法在开局注册卡牌模块回调）。
  若玩家在打出任何五丸卡之前就手动对五丸使用食材/佳肴，该次使用不会被计入（增强/触发缺失）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener, CardEnhance

_TRACK_TAG = "wuwan_usage_tracking"


def _wuwan(owner):
    return next((h for h in owner.heroes if h.type_name == "WuWan"), None)


def _is_jiaoyao(card):
    return getattr(card, "eng_name", "") == "JiaYao"


def _is_ingredient(card):
    return getattr(card, "is_ingredient", False)


def _ensure_usage_tracking(player):
    """在玩家上注册（或刷新）五丸被使用食材/佳肴的全局跟踪监听器（幂等）。

    统计：
      - wuwan_ingredient_used_total（本局五丸被使用食材次数，持久）
      - wuwan_jiaoyao_used_total（本局五丸被使用佳肴次数，持久）
      - wuwan_jiaoyao_used_turn（本回合五丸被使用佳肴次数，每回合重置）
    同一张卡（时蔬含 atk+hp 两个 GiveBuff）只计一次（按卡对象 id 去重）。
    """
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != _TRACK_TAG]

    def cond(e, owner):
        src = getattr(e.event, "source", None)
        if getattr(src, "entity_type", None) != "card":
            return False
        if not (_is_ingredient(src) or _is_jiaoyao(src)):
            return False
        tgt = getattr(e.event, "target", None) or []
        wuwan = _wuwan(owner)
        return bool(wuwan) and wuwan in list(tgt)

    def effect(e, owner):
        src = e.event.source
        counted = getattr(owner, "_ww_usage_counted", None)
        if counted is None:
            counted = owner._ww_usage_counted = set()
        if id(src) in counted:
            return
        counted.add(id(src))
        counters = owner.game.counters
        if _is_jiaoyao(src):
            counters.ensure("wuwan_jiaoyao_used_total", initial=0, persistent=True)
            counters.inc("wuwan_jiaoyao_used_total")
            counters.ensure("wuwan_jiaoyao_used_turn", initial=0, reset_per_turn=True)
            counters.inc("wuwan_jiaoyao_used_turn")
        else:
            counters.ensure("wuwan_ingredient_used_total", initial=0, persistent=True)
            counters.inc("wuwan_ingredient_used_total")

    l = Listener("give buff", cond, (effect,))
    l._tag = _TRACK_TAG
    player.listeners.append(l)


def _use_jiaoyao_on(player):
    """从手牌取一张「佳肴」对五丸使用；无佳肴或五丸不可用时返回 False。"""
    wuwan = _wuwan(player)
    if wuwan is None or not wuwan.is_alive:
        return False
    jys = [c for c in player.hand.cards if _is_jiaoyao(c)]
    if not jys:
        return False
    _ensure_usage_tracking(player)
    jy = random_choice(player, jys, context="对五丸使用佳肴")
    if jy is None:
        return False
    # 效果联动使用不消耗鬼火（无消耗属性）
    jy.attributes.append(CardAttributes.NO_FIRE_CONSUMPTION)
    player.game.play_card(player, jy, target=[wuwan])
    return True


# ── 1勾 ────────────────────────────────────────────────────────────────────

def _jiaoyao_used_this_turn(player):
    """本回合是否使用过「佳肴」（五丸增强条件读取的跟踪计数；监听器随五丸卡注册）。"""
    _ensure_usage_tracking(player)
    return player.game.counters.get("wuwan_jiaoyao_used_turn", 0) > 0


class LiaoLiXiaoMao:
    """料理小猫：增强：本回合若你使用过「佳肴」，此牌获得瞬发。

    增强走引擎通用机制（#13 用户裁决）：can_play_card 以「满足条件增强后的复制体」
    判定（瞬发生效，0 鬼火且瞬发名额未用时可通过判定）；确定打出后 play_card 开头
    把瞬发写到这张卡上（占用每回合一次瞬发名额）。
    """
    id = 230
    type = "attack"
    hero = "WuWan"
    name = "料理小猫"
    level_req = 1
    buff_atk = 1
    buff_def = 1
    enhance = (CardEnhance(
        cond=lambda s: _jiaoyao_used_this_turn(s.owner),
        attributes=(CardAttributes.INSTANT,),
    ),)
    on_play = (lambda s: _liaoli_on_play(s),)


def _liaoli_on_play(s):
    # 增强走通用机制（#13），此处仅保证跟踪监听器已注册（与其他五丸卡一致）
    _ensure_usage_tracking(s.owner)


class ZuiQiangMaoShiYing:
    """最强猫侍应：增强：本局游戏五丸每被使用过一张「食材」，此牌便获得1力量；
    每被使用过一张「佳肴」，此牌便获得2力量。"""
    id = 231
    type = "attack"
    hero = "WuWan"
    name = "最强猫侍应"
    level_req = 1
    on_play = (lambda s: _zuiqiang_on_play(s),)


def _zuiqiang_on_play(s):
    player = s.owner
    _ensure_usage_tracking(player)
    counters = player.game.counters
    ing = counters.get("wuwan_ingredient_used_total", 0)
    jy = counters.get("wuwan_jiaoyao_used_total", 0)
    # 卡类未声明 buff_atk（增强动态决定），实例初始没有该属性，先补 0 再叠加增强值
    s.buff_atk = (getattr(s, "buff_atk", 0) or 0) + ing + 2 * jy


class WanNaoShiGuang:
    """玩闹时光：瞬发 随机从手牌对五丸使用一张「佳肴」，抽一张牌。"""
    id = 232
    type = "spell"
    hero = "WuWan"
    name = "玩闹时光"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _wannao_on_play(s),)


def _wannao_on_play(s):
    player = s.owner
    _ensure_usage_tracking(player)
    _use_jiaoyao_on(player)
    player.game.handle_event(DrawEvent(player, 1))


# ── 2勾 ────────────────────────────────────────────────────────────────────

class ChuYiYanXing:
    """厨艺研行：随机从手牌对五丸使用一张「佳肴」。"""
    id = 233
    type = "attack"
    hero = "WuWan"
    name = "厨艺研行"
    level_req = 2
    buff_atk = 1
    buff_def = 1
    on_play = (lambda s: _chuyi_on_play(s),)


def _chuyi_on_play(s):
    player = s.owner
    _ensure_usage_tracking(player)
    _use_jiaoyao_on(player)


class MaoMiRiHe:
    """猫咪日和：进场时烹饪。己方回合当五丸被使用「佳肴」时，获得屏障且发起一次攻击。"""
    id = 234
    type = "morph"
    hero = "WuWan"
    name = "猫咪日和"
    level_req = 2
    atk = 4
    hp = 5
    on_play = (lambda s: _maomirihe_on_play(s),)


def _maomirihe_on_play(s):
    hero = _wuwan(s.owner)
    if hero is None:
        return
    # 进场时烹饪
    s.owner.game.cook(s.owner, hero)
    tag = "maomirihe-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]
    # 重新进场时重置「同一张佳肴只触发一次」的去重集合
    hero._maomirihe_jy_used = set()

    def cond(e, h):
        src = getattr(e.event, "source", None)
        tgt = getattr(e.event, "target", None) or []
        return (h.is_alive and h.morphed_id == 234 and _is_jiaoyao(src)
                and h in list(tgt) and h.owner.game.current_player is h.owner)

    def effect(e, h):
        # 佳肴 on_play 会产生 atk+hp 两个 GiveBuff 事件（game.py _create_jiaoyao），
        # 同一张佳肴只触发一次效果
        seen = getattr(h, "_maomirihe_jy_used", None)
        if seen is None:
            seen = h._maomirihe_jy_used = set()
        if id(e.event.source) in seen:
            return
        seen.add(id(e.event.source))
        # 获得屏障且发起一次攻击
        if HeroAttributes.BARRIER not in h.attributes:
            h.attributes.append(HeroAttributes.BARRIER)
        if not h.is_alive or h.stunned:
            return
        # 追猎词条会干扰固定攻击目标（战斗区/牌手），本次攻击暂时移除
        had_hunting = HeroAttributes.HUNTING in h.attributes
        if had_hunting:
            h.attributes.remove(HeroAttributes.HUNTING)
        h.owner.game.handle_event(HeroAttackEvent(h.owner, h))
        if had_hunting and HeroAttributes.HUNTING not in h.attributes:
            h.attributes.append(HeroAttributes.HUNTING)

    l = Listener("give buff", cond, (effect,))
    l._tag = tag
    hero.listeners.append(l)


class MaoWeiYuGanQiang:
    """猫为鱼干强：贯通 增强：本回合若你使用过「佳肴」，此牌获得追猎。"""
    id = 235
    type = "attack"
    hero = "WuWan"
    name = "猫为鱼干强"
    level_req = 2
    buff_atk = 2
    buff_def = 1
    on_play = (lambda s: _maowei_on_play(s),)
    after_play = (lambda s: _maowei_after(s),)

    @staticmethod
    def select_target(card):
        """增强生效（本回合使用过佳肴）时进入目标选择（追猎需要选定目标）；否则跳过。"""
        player = card.owner
        if player is None:
            return None
        _ensure_usage_tracking(player)
        if player.game.counters.get("wuwan_jiaoyao_used_turn", 0) <= 0:
            return None
        enemies = [h for h in player.opponent.heroes
                   if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes]
        if not enemies:
            return None
        return (lambda s: select_target(player, enemies, s),)


def _maowei_on_play(s):
    hero = _wuwan(s.owner)
    player = s.owner
    _ensure_usage_tracking(player)
    if hero is None:
        return
    # 本次攻击赋予贯通
    s._maowei_had_penetrate = HeroAttributes.PENETRATE in hero.attributes
    if not s._maowei_had_penetrate:
        hero.attributes.append(HeroAttributes.PENETRATE)
    # 增强：本回合使用过佳肴 → 获得追猎（本次攻击）
    s._maowei_had_hunting = HeroAttributes.HUNTING in hero.attributes
    if player.game.counters.get("wuwan_jiaoyao_used_turn", 0) > 0:
        if not s._maowei_had_hunting:
            hero.attributes.append(HeroAttributes.HUNTING)


def _maowei_after(s):
    hero = _wuwan(s.owner)
    if hero is None:
        return
    if not getattr(s, "_maowei_had_penetrate", True) and HeroAttributes.PENETRATE in hero.attributes:
        hero.attributes.remove(HeroAttributes.PENETRATE)
    if not getattr(s, "_maowei_had_hunting", True) and HeroAttributes.HUNTING in hero.attributes:
        hero.attributes.remove(HeroAttributes.HUNTING)


# ── 3勾 ────────────────────────────────────────────────────────────────────

class ChiBaoZaiGanHuo:
    """吃饱再干活：当五丸被使用「佳肴」时，抽一张牌并获得1点鬼火。"""
    id = 236
    type = "morph"
    hero = "WuWan"
    name = "吃饱再干活"
    level_req = 3
    atk = 4
    hp = 7
    on_play = (lambda s: _chibao_on_play(s),)


def _chibao_on_play(s):
    hero = _wuwan(s.owner)
    if hero is None:
        return
    tag = "chibao-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]
    # 重新进场时重置「同一张佳肴只触发一次」的去重集合
    hero._chibao_jy_used = set()

    def cond(e, h):
        src = getattr(e.event, "source", None)
        tgt = getattr(e.event, "target", None) or []
        return h.is_alive and h.morphed_id == 236 and _is_jiaoyao(src) and h in list(tgt)

    def effect(e, h):
        # 佳肴 on_play 会产生 atk+hp 两个 GiveBuff 事件（game.py _create_jiaoyao），
        # 同一张佳肴只触发一次效果
        seen = getattr(h, "_chibao_jy_used", None)
        if seen is None:
            seen = h._chibao_jy_used = set()
        if id(e.event.source) in seen:
            return
        seen.add(id(e.event.source))
        h.owner.game.handle_event(DrawEvent(h.owner, 1))
        h.owner.fire_cnt += 1

    l = Listener("give buff", cond, (effect,))
    l._tag = tag
    hero.listeners.append(l)


class JueXingWuWan:
    """觉醒·五丸：觉醒：攻击时连击。当五丸造成战斗伤害时，烹饪。"""
    id = 237
    type = "spell"
    hero = "WuWan"
    name = "觉醒·五丸"
    level_req = 3
    on_play = (lambda s: _juexingwuwan_on_play(s),)


def _juexingwuwan_on_play(s):
    hero = _wuwan(s.owner)
    if hero is None:
        return
    _ensure_usage_tracking(s.owner)
    # 觉醒：永久 +1/+1（觉醒牌数值直接写在 on_play，同其它式神觉醒牌）
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    # 觉醒：攻击时连击
    if HeroAttributes.DOUBLE_STRIKE not in hero.attributes:
        hero.attributes.append(HeroAttributes.DOUBLE_STRIKE)
    # 当五丸造成战斗伤害时，烹饪。
    # 牌手目标由五丸基础能力（heroes.py）触发烹饪，此处只补式神目标，避免一次攻击重复烹饪。
    # 战斗/法术统一走 "damage dealt" 纯通知；仅过滤 combat（贯通过量走 spell 不烹饪）。
    tag = "juexingwuwan_cook"
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]
    l = Listener("damage dealt",
                 lambda e, h: (e.event.source is h
                               and getattr(e.event, "damage_type", None) == "combat"
                               and e.event.target
                               and getattr(e.event.target[0], "entity_type", None) == "hero"
                               and getattr(e.event, "value", 0) > 0),
                 (lambda e, h: h.owner.game.cook(h.owner, h),))
    l._tag = tag
    hero.listeners.append(l)
