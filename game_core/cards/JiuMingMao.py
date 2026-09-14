"""九命猫 专属卡牌"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
# Hero 使用延迟导入以避免循环依赖


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _jiuming_count(hero) -> int:
    """读取九命猫当前结附的「九命」数量（计数器未定义时视为 0）。"""
    return hero.counters.get("jiu_ming", 0)


def _jiuming_attach(hero, n: int = 1):
    """为九命猫结附 n 个「九命」（计数器持久，不因气绝重置）。"""
    hero.counters.ensure("jiu_ming", initial=0, persistent=True)
    hero.counters.inc("jiu_ming", n)


def _enemy_attack_target(player):
    """对方战斗区式神；无则直击对方牌手。"""
    opp = player.opponent
    return opp.attack_zone if opp.attack_zone is not None else opp


# ── 1勾卡牌 ───────────────────────────────────────────────────────────────

class MaoZhua:
    """猫爪：战斗 +1/+0。增强：若已结附≥2个九命，此牌+2力量。"""
    id = 44
    type = "attack"
    hero = "JiuMingMao"
    name = "猫爪"
    level_req = 1
    buff_atk = 1
    buff_def = 0
    on_play = (lambda s: _maozhua_on_play(s),)

def _maozhua_on_play(s):
    hero = s.get_corresponding_hero()
    if _jiuming_count(hero) >= 2:
        s.buff_atk += 2


class LingDang:
    """铃铛：形态 3/4。增强：此牌获得等同于九命猫已结附九命数量的攻击力。"""
    id = 45
    type = "morph"
    hero = "JiuMingMao"
    name = "铃铛"
    level_req = 1
    atk = 3
    hp = 4
    on_play = (lambda s: _lingdang_on_play(s),)

def _lingdang_on_play(s):
    hero = s.get_corresponding_hero()
    s.atk = 3 + _jiuming_count(hero)
    s.hp = 4


# ── 2勾卡牌 ───────────────────────────────────────────────────────────────

class YanMing:
    """延命：形态 6/4。每个回合（一整轮）结束时，从九命猫上移除一个「九命」。"""
    id = 46
    type = "morph"
    hero = "JiuMingMao"
    name = "延命"
    level_req = 2
    atk = 6
    hp = 4
    on_play = (lambda s: _yanming_on_play(s),)

def _yanming_on_play(s):
    hero = s.get_corresponding_hero()
    owner = s.owner
    # 己方回合结束（= 对手回合开始）时移除一个九命：每个回合只结算一次。
    # 监听器挂到牌手身上而非 hero.listeners——九命猫气绝时 hero.listeners
    # 会被 check_death 整体重置为 original_listeners，挂在牌手上不会丢失。
    l = Listener("begin turn",
                 lambda e, p: (e.next_player != owner and
                               hero.morphed_id == 46 and     # 延命形态仍在生效
                               hero.owner is owner and hero.is_alive),
                 (lambda e, p: _yanming_remove_one(hero),))
    l._tag = "yanming"
    owner.listeners = [lst for lst in owner.listeners if getattr(lst, '_tag', '') != 'yanming']
    owner.listeners.append(l)

def _yanming_remove_one(hero):
    if _jiuming_count(hero) > 0:
        hero.counters.ensure("jiu_ming", initial=0, persistent=True)
        hero.counters.inc("jiu_ming", -1)


class MaoChe:
    """猫车：形态 3/3 瞬发。你战斗区其他式神获得「遗愿：复活该式神并为九命猫结附
    一个「九命」，然后使九命猫发起一次攻击，若本次攻击目标为敌方式神，+2护甲」。"""
    id = 47
    type = "morph"
    hero = "JiuMingMao"
    name = "猫车"
    level_req = 2
    atk = 3
    hp = 3
    attributes = (CardAttributes.INSTANT,)
    on_play = (lambda s: _maoche_on_play(s),)

def _maoche_on_play(s):
    owner = s.owner
    jmm = s.get_corresponding_hero()
    battle = owner.attack_zone
    # 遗愿只结附给战斗区「其他」式神：战斗区为空或九命猫自己在战斗区时不触发
    if battle is None or battle is jmm:
        return
    bearer = battle
    state = {"used": False}

    def _on_kill(e, p):
        if state["used"] or e.event.killed is not bearer:
            return
        state["used"] = True
        if not bearer.is_alive:
            bearer.revive()
        _jiuming_attach(jmm, 1)
        _maoche_attack(jmm)

    l = Listener("hero kill", lambda e, p: True, (_on_kill,))
    l._tag = "maoche"
    # 去重：同一牌手重复打出猫车时替换旧的遗愿监听（遗愿一次性，触发即消耗）
    owner.listeners = [lst for lst in owner.listeners if getattr(lst, '_tag', '') != 'maoche']
    owner.listeners.append(l)

def _maoche_attack(jmm):
    """遗愿中的攻击：九命猫发起一次攻击；若本次攻击目标为敌方式神，+2护甲。"""
    opp = jmm.owner.opponent
    target = opp.attack_zone if opp.attack_zone is not None else opp
    is_hero = getattr(target, 'entity_type', None) == 'hero'
    # 临时移除追猎：触发式攻击没有选目标环节，走 HUNTING 分支会因 selected_targets
    # 为空而让目标解析返回 None，攻击将不会发生。
    had_hunting = HeroAttributes.HUNTING in jmm.attributes
    if had_hunting:
        jmm.attributes.remove(HeroAttributes.HUNTING)
    try:
        jmm.owner.game.handle_event(HeroAttackEvent(jmm.owner, jmm))
    finally:
        if had_hunting:
            jmm.attributes.append(HeroAttributes.HUNTING)
    if is_hero:
        jmm.defense += 2


class BaoFu:
    """报复：战斗 +1/+0。若本次战斗后气绝，复活并立刻发动攻击，本次攻击免疫战斗伤害。
    响应：当九命猫被攻击时，自动使用。"""
    id = 48
    type = "attack"
    hero = "JiuMingMao"
    name = "报复"
    level_req = 2
    buff_atk = 1
    buff_def = 0
    attributes = (CardAttributes.RESPONSE,)
    response_trigger = "hero attack"
    # 响应：九命猫（战斗区或追猎选中目标）被敌方式神攻击时自动打出。
    # 战斗牌响应只施加力量/护甲，不使九命猫发起攻击（wiki「响应」）。
    response_condition = (lambda s, event, target: (
        event.hero.owner is s.owner.opponent
        and target is s.get_corresponding_hero()
    ),)
    on_play = (lambda s: _baofu_on_play(s),)
    after_play = (lambda s: _baofu_after(s),)

def _baofu_on_play(s):
    """记录本次战斗前的九命数，用于 after_play 判断九命猫是否在本场战斗后气绝。"""
    hero = s.get_corresponding_hero()
    s._jm_before = _jiuming_count(hero)

def _baofu_after(s):
    hero = s.get_corresponding_hero()
    before = getattr(s, "_jm_before", None)
    if before is None or not hero.is_alive:
        if hasattr(s, "_jm_before"):
            del s._jm_before
        return
    if _jiuming_count(hero) > before:
        # 本次战斗后气绝：基础能力已将她复活。气绝流程末尾已把 atk 重置为基础值
        # +永久加成，战斗牌加成折在 combat_buff_atk（战后由引擎清零，不回退 atk），
        # 这里直接用重置后的 atk 造成直伤，近似「免疫战斗伤害的攻击」。
        dmg = hero.atk
        target = _enemy_attack_target(hero.owner)
        hero.owner.game.handle_event(DealDamage(dmg, hero, [target]))
    if hasattr(s, "_jm_before"):
        del s._jm_before


class MaoLuanBu:
    """猫乱步：战斗 +1/+0 追猎。攻击两次。"""
    id = 49
    type = "attack"
    hero = "JiuMingMao"
    name = "猫乱步"
    level_req = 2
    buff_atk = 1
    buff_def = 0
    require_target = (lambda s: [h for h in s.owner.opponent.heroes
                                 if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes],)
    select_target = (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes
                                                       if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes], s),)
    on_play = (lambda s: _maoluanbu_on_play(s),)
    after_play = (lambda s: _maoluanbu_after(s),)

def _maoluanbu_on_play(s):
    hero = s.get_corresponding_hero()
    s._mlb_had_hunting = HeroAttributes.HUNTING in hero.attributes
    s._mlb_had_double = HeroAttributes.DOUBLE_STRIKE in hero.attributes
    if not s._mlb_had_hunting:
        hero.attributes.append(HeroAttributes.HUNTING)
    if not s._mlb_had_double:
        hero.attributes.append(HeroAttributes.DOUBLE_STRIKE)

def _maoluanbu_after(s):
    hero = s.get_corresponding_hero()
    # 只移除本次加的词条，避免误删任侠等其他来源的追猎/连击
    if not getattr(s, "_mlb_had_hunting", True) and HeroAttributes.HUNTING in hero.attributes:
        hero.attributes.remove(HeroAttributes.HUNTING)
    if not getattr(s, "_mlb_had_double", True) and HeroAttributes.DOUBLE_STRIKE in hero.attributes:
        hero.attributes.remove(HeroAttributes.DOUBLE_STRIKE)


# ── 3勾卡牌 ───────────────────────────────────────────────────────────────

class XiangSiErSheng:
    """向死而生：仅在你场上九命猫无法复活时可用。此牌不因「九命」效果移除。
    移除九命猫的不能复活能力，使其复活并结附2个「九命」，且永久获得+1力量、+1生命和
    迅捷，随机获得两张九命猫的战斗牌。"""
    id = 50
    type = "spell"
    hero = "JiuMingMao"
    name = "向死而生"
    level_req = 3
    require_target = (lambda s: [s.get_corresponding_hero()] if s.get_corresponding_hero().round_until_alive >= 999 else [],)
    on_play = (lambda s: _xiangsiersheng_on_play(s),)

def _xiangsiersheng_on_play(s):
    hero = s.get_corresponding_hero()
    # 1. 移除「不能复活能力」：九命猫之后不再因九命≥5而永久气绝（替换而非叠加）
    hero.on_death = (_on_death_jmm_immortal,)
    # 2. 复活（revive 同时清除永久气绝状态 round_until_alive=999）
    hero.revive()
    # 3. 结附2个九命（覆盖旧计数）
    hero.counters.ensure("jiu_ming", initial=0, persistent=True)
    hero.counters.set("jiu_ming", 2)
    # 4. 永久 +1/+1 与迅捷
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    if HeroAttributes.AGILE not in hero.attributes:
        hero.attributes.append(HeroAttributes.AGILE)
    # 5. 随机获得两张九命猫的战斗牌（attack 类：猫爪/报复/猫乱步）
    combat_cards = ["MaoZhua", "BaoFu", "MaoLuanBu"]
    picked = random_sample(s.owner, combat_cards, 2, context="向死而生")
    if picked:
        s.owner.GiveCardToHand(picked)

def _on_death_jmm_immortal(h):
    """向死而生之后的九命猫：气绝时 +1 九命并复活，永不再永久气绝。"""
    h.counters.ensure("jiu_ming", initial=0, persistent=True)
    h.counters.inc("jiu_ming", 1)
    h.revive()


# ── 觉醒 ────────────────────────────────────────────────────────────────────

class JueXingJiuMingMao:
    """觉醒·九命猫：觉醒：当九命猫气绝时，复活她并结附一个「九命」，然后立刻发动攻击。"""
    id = 51
    type = "spell"
    hero = "JiuMingMao"
    name = "觉醒·九命猫"
    level_req = 3
    on_play = (lambda s: _juexing_jmm_on_play(s),)

def _juexing_jmm_on_play(s):
    hero = s.get_corresponding_hero()
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)

    def _on_death_jmm(h):
        h.counters.ensure("jiu_ming", initial=0, persistent=True)
        h.counters.inc("jiu_ming", 1)
        if h.counters.get("jiu_ming") >= 5:
            h.owner.game.handle_event(PermanentDeathEvent(h))
            return
        h.revive()
        # 立刻发动攻击
        h.owner.game.handle_event(HeroAttackEvent(h.owner, h))

    # 替换而非叠加：觉醒自带完整的九命结算，避免与基础能力重复计九命
    hero.on_death = (_on_death_jmm,)
