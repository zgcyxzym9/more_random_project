"""白狼 专属卡牌（完整实现：id 174-183）

数据源：cards.json（id/type/level_req/数值/中文名/description）+ tmp_cards_json/BaiLang.sources.md（机制备注）。
规则冲突时以 cards.json 为准：
  - 起弓(174) description 为「穿刺」（PIERCING），sources 的「远程」不采用。
  - 文射(175) buff_def 按 JSON=2（sources 记 +4）。
  - 残心(176) 按 JSON 为 1勾 3/5（sources 记 2勾 5/7）。
  - 白狼有协战卡 森佑灵矢(182)/灵矢贯虹(183)（cards.json 收录，sources 声称无，以 cards.json 为准）。

实现要点：
- 白狼的法术强化（起弓/离/无我：+力量 与/或 关键字，直到下一次攻击后）统一写入
  hero.bailang_spell_buffs 注册表，并直接体现在 hero.atk / hero.attributes 上（Design A：
  强化对所有伤害生效；灵矢贯虹的「力量加成」因此自动满足）。攻击后由 on_after_damage
  清理（残心形态不清理）。迅捷(AGILE) 由引擎在出击结算时消耗，清理时只清追踪不删属性。
- 觉醒·白狼(180)：heroes.py 基础能力已加 not s.is_awakened 抑制；觉醒在己方回合白狼对
  敌方式神造成伤害时打敌方牌手 4 点（战斗 + 非战斗，含援护）。
- 会(178)：延迟 8 点伤害，监听「begin turn」在己方下个回合开始结算（目标已死则空过）；
  监听器挂白狼身上，白狼在下个回合开始前气绝时随 listeners 重置而失效。
  InferenceOpponent（GUI 同步真实对局时的模拟对手）打出时目标选择推迟到下个己方回合
  开始时经 input() 询问（真实对局中对手所选目标不可见、无法在打出瞬间同步），语义
  等价于「下个回合开始时，选择一个式神造成8点伤害」。
- 援护(179)：响应法术，对敌方战斗区式神造成等同白狼力量（hero.atk）的伤害。
- 森佑灵矢(182)：协战；萤草分支未实现（TODO）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener


# ── 白狼法术强化系统 ──────────────────────────────────────────────────────

def _bailang_spell_buffs(hero):
    """白狼法术强化注册表：记录未消耗的力量加成与关键字（直到下一次攻击后）。"""
    if not hasattr(hero, "bailang_spell_buffs"):
        hero.bailang_spell_buffs = {"atk": 0, "attrs": []}
    return hero.bailang_spell_buffs


def _bailang_add_spell_buff(hero, atk=0, attrs=()):
    """白狼获得法术强化：+力量 与/或 关键字（起弓/离/无我）。

    力量直接加在 hero.atk 上（Design A：强化对所有伤害生效，灵矢贯虹的
    「本次攻击获得法术强化力量加成」因此自动满足）；关键字加在 attributes 上。
    效果在 BaiLang 下一次攻击后清除（残心形态不消失）。
    """
    if hero is None:
        return
    reg = _bailang_spell_buffs(hero)
    if atk:
        reg["atk"] += atk
        hero.atk += atk
    for a in attrs:
        if a not in reg["attrs"]:
            reg["attrs"].append(a)
        if a not in hero.attributes:
            hero.attributes.append(a)
    _bailang_arm_spell_cleanup(hero)


def _bailang_clear_spell_buffs(hero):
    """清空白狼法术强化：减去力量加成、移除关键字（迅捷除外，由引擎消耗）。"""
    if hero is None:
        return
    reg = _bailang_spell_buffs(hero)
    if reg["atk"]:
        hero.atk = max(0, hero.atk - reg["atk"])
        reg["atk"] = 0
    for a in list(reg["attrs"]):
        # 迅捷在出击结算时由引擎消耗并返还鬼火，此处只清追踪、不删属性
        if a != HeroAttributes.AGILE and a in hero.attributes:
            hero.attributes.remove(a)
    reg["attrs"] = []
    hero._bailang_attacked_combat = False


def _bailang_clear_spell_buffs_after_attack(hero):
    """攻击后清理法术强化：残心形态下不因攻击而消失。"""
    if hero.morphed_id == CanXin.id:
        return
    _bailang_clear_spell_buffs(hero)


def _bailang_arm_spell_cleanup(hero):
    """确保『法术强化在攻击后清理（残心除外）』机制已挂载（幂等）。"""
    # 出击标记监听器：白狼发起攻击时标记（用于 after-damage 区分攻/守）。
    # 死亡后 listeners 重置为 original_listeners，需重新挂载 → 先按 tag 移除再挂。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "bailang_spell_cleanup_flag"]
    flag = Listener("hero attack",
                    lambda e, h: getattr(e.event, "hero", None) is h,
                    (lambda e, h: setattr(h, "_bailang_attacked_combat", True),))
    flag._tag = "bailang_spell_cleanup_flag"
    hero.listeners.append(flag)
    # 战后清理回调（on_after_damage 不随死亡重置，只挂载一次）
    if not getattr(hero, "_bailang_after_damage_hooked", False):
        def _after_combat(_other, _dmg, h=hero):
            if getattr(h, "_bailang_attacked_combat", False):
                h._bailang_attacked_combat = False
                _bailang_clear_spell_buffs_after_attack(h)
        hero.on_after_damage = hero.on_after_damage + (_after_combat,)
        hero._bailang_after_damage_hooked = True
    # 气绝时清空法术强化（挂 original_listeners 以在死亡后保留）
    if not getattr(hero, "_bailang_death_clear_hooked", False):
        death = Listener("hero kill",
                         lambda e, h: getattr(e.event, "killed", None) is h,
                         (lambda e, h: _bailang_clear_spell_buffs(h),))
        death._tag = "bailang_spell_cleanup_death"
        hero.original_listeners = [x for x in hero.original_listeners if getattr(x, "_tag", "") != "bailang_spell_cleanup_death"]
        hero.original_listeners.append(death)
        hero._bailang_death_clear_hooked = True


# ── 1勾 ────────────────────────────────────────────────────────────────────

class QiGong:
    """起弓：瞬发 抽1张牌，白狼获得1力量，穿刺直到下一次攻击后。"""
    id = 174
    type = "spell"
    hero = "BaiLang"
    name = "起弓"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (lambda s: _qigong_on_play(s),)


def _qigong_on_play(s):
    s.owner.game.handle_event(DrawEvent(s.owner, 1))
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _bailang_add_spell_buff(hero, atk=1, attrs=(HeroAttributes.PIERCING,))


class WenShe:
    """文射：连击（力量-2、护甲+2 后，额外先击中目标一次）。"""
    id = 175
    type = "attack"
    hero = "BaiLang"
    name = "文射"
    level_req = 1
    buff_atk = -2
    buff_def = 2
    is_beginning_card = True
    on_play = (lambda s: _wenshe_on_play(s),)
    after_play = (lambda s: _wenshe_after_play(s),)


def _wenshe_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    if HeroAttributes.DOUBLE_STRIKE not in hero.attributes:
        hero.attributes.append(HeroAttributes.DOUBLE_STRIKE)  # 连击


def _wenshe_after_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    if HeroAttributes.DOUBLE_STRIKE in hero.attributes:
        hero.attributes.remove(HeroAttributes.DOUBLE_STRIKE)


class CanXin:
    """残心：远程 白狼的法术强化效果不再因攻击而消失。"""
    id = 176
    type = "morph"
    hero = "BaiLang"
    name = "残心"
    level_req = 1
    atk = 3
    hp = 5
    is_beginning_card = True
    on_play = (lambda s: _canxin_on_play(s),)


def _canxin_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    if HeroAttributes.RANGED not in hero.attributes:
        hero.attributes.append(HeroAttributes.RANGED)  # 远程
    # 形态离场/被替换/随式神气绝时移除远程
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "canxin_cleanup"]
    l = Listener("morph leave",
                 lambda e, h: e.event.morph_id == CanXin.id,
                 (_canxin_leave,))
    l._tag = "canxin_cleanup"
    hero.listeners.append(l)


def _canxin_leave(e, h):
    if HeroAttributes.RANGED in h.attributes:
        h.attributes.remove(HeroAttributes.RANGED)
    h.listeners = [l for l in h.listeners if getattr(l, "_tag", "") != "canxin_cleanup"]


# ── 2勾 ────────────────────────────────────────────────────────────────────

class Li:
    """离：瞬发 白狼获得3力量直到下一次攻击后。"""
    id = 177
    type = "spell"
    hero = "BaiLang"
    name = "离"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (lambda s: _li_on_play(s),)


def _li_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _bailang_add_spell_buff(hero, atk=3)


class Hui:
    """会：选择一个敌方式神，你的下个回合开始时，对该式神造成8点伤害。（所选目标仅己方可见）

    InferenceOpponent 打出时跳过目标选择（select_target 解析为 None），改为在
    下个己方回合开始时经 input() 询问目标 —— 见 _hui_register_deferred_ask。
    """
    id = 178
    type = "spell"
    hero = "BaiLang"
    name = "会"
    level_req = 2
    is_beginning_card = True
    require_target = (lambda s: [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0],)
    on_play = (lambda s: _hui_on_play(s),)

    @staticmethod
    def select_target(card):
        """InferenceOpponent 打出时返回 None → 跳过目标选择（目标下回合开始再问）；
        其余情况正常进入选择流程（写法同黄金羽的按需解析）。"""
        if card.owner is not None and type(card.owner).__name__ == "InferenceOpponent":
            return None
        return (lambda s: select_target(s.owner, [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0], s),)


def _hui_on_play(s):
    # InferenceOpponent：目标选择已推迟（selected_targets 为空是预期状态），
    # 挂「下个己方回合开始时询问」的一次性监听器。
    if s.owner is not None and type(s.owner).__name__ == "InferenceOpponent":
        _hui_register_deferred_ask(s)
        return
    if not s.owner.selected_targets:
        return
    target = s.owner.selected_targets[0]
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 你的下个回合开始时，对该式神造成8点伤害（目标已气绝则空过）。
    # 监听器挂在白狼身上而非牌手身上：白狼在下个回合开始前气绝时，
    # check_death 会把 listeners 重置回 original_listeners，挂起的「会」
    # 随之失效（不再结算延迟伤害）。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "bailang_hui_delay"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner,
                 (lambda e, h: _hui_delayed(h, target),))
    l._tag = "bailang_hui_delay"
    hero.listeners.append(l)


def _hui_delayed(hero, target):
    # 一次性：结算后移除自身
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "bailang_hui_delay"]
    if target.is_alive and target.level > 0:
        hero.owner.game.handle_event(DealDamage(8, hero, [target]))


def _hui_register_deferred_ask(s):
    """InferenceOpponent 专用：目标选择推迟到下个己方回合开始时再问。

    真实对局中对手打「会」时所选目标不可见，GUI 同步无法在打出瞬间得知；
    改为语义等价的「下个回合开始时，选择一个式神造成8点伤害」。询问经
    input() 进行（GUI 同步工具把 input 重定向到界面，见
    rl_dqn/inference_full_game_gui_base.py 的 _make_gui_input）。
    监听器同样挂白狼身上：结算前白狼气绝则随 listeners 重置而失效。
    """
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "bailang_hui_delay"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner,
                 (lambda e, h: _hui_ask_and_resolve(h),))
    l._tag = "bailang_hui_delay"
    hero.listeners.append(l)


def _hui_ask_and_resolve(hero):
    # 一次性：结算后移除自身
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "bailang_hui_delay"]
    targets = [h for h in hero.owner.opponent.heroes if h.is_alive and h.level > 0]
    if not targets:
        return  # 可选目标已空 → 空过（与正常路径“目标已死空过”一致）
    names = " / ".join(f"{i}.{t.name}" for i, t in enumerate(targets, start=1))
    raw = input(f"[会] 你的下个回合开始：选择一个敌方式神造成8点伤害（{names}），0=空过：").strip()
    try:
        idx = int(raw)
    except ValueError:
        idx = 0
    if 1 <= idx <= len(targets):
        hero.owner.game.handle_event(DealDamage(8, hero, [targets[idx - 1]]))


class YuanHu:
    """援护：对敌方战斗区式神造成等同于白狼的力量的伤害。响应：当你的其他式神被攻击时，自动使用。"""
    id = 179
    type = "spell"
    hero = "BaiLang"
    name = "援护"
    level_req = 2
    attributes = (CardAttributes.RESPONSE,)
    is_beginning_card = True
    response_trigger = "hero attack"
    response_condition = (lambda s, event, target: _yuanhu_response_cond(s, event, target),)
    on_play = (lambda s: _yuanhu_on_play(s),)


def _yuanhu_response_cond(s, event, target):
    """当你的其他式神被攻击时：攻击方为敌方、被攻击目标是己方非白狼式神。"""
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return False
    attacker = getattr(event, "hero", None)
    if attacker is None or attacker.owner is s.owner:
        return False  # 己方攻击不响应
    if target is None or getattr(target, "entity_type", None) != "hero":
        return False
    return target.owner is s.owner and target is not hero


def _yuanhu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    target = s.owner.opponent.attack_zone
    if target is None or not target.is_alive or target.level <= 0:
        return
    # 等同于白狼的力量（hero.atk 已含法术强化）；以牌为来源（法术伤害，贯通不生效）
    s.owner.game.handle_event(DealDamage(hero.atk, s, [target]))


# ── 3勾 ────────────────────────────────────────────────────────────────────

class JueXingBaiLang:
    """觉醒·白狼：觉醒：己方回合当白狼对敌方式神造成伤害时，对敌方牌手造成4点伤害。"""
    id = 180
    type = "spell"
    hero = "BaiLang"
    name = "觉醒·白狼"
    level_req = 3
    is_beginning_card = True
    on_play = (lambda s: _juexing_bailang_on_play(s),)


def _juexing_bailang_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)
    hero.is_awakened = True
    # 觉醒效果气绝后保留（挂 original_listeners）；基础能力已被 heroes.py 用 is_awakened 抑制。
    # 战斗/法术伤害统一走 "damage dealt" 纯通知，合并为单个监听器。
    l1 = Listener("damage dealt", _juexing_bailang_cond, (_juexing_bailang_trigger,))
    l1._tag = "bailang_awaken"
    for tag in ("bailang_awaken",):
        hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != tag]
        hero.original_listeners = [x for x in hero.original_listeners if getattr(x, "_tag", "") != tag]
    hero.listeners += [l1]
    hero.original_listeners += [l1]


def _juexing_bailang_cond(e, s):
    """己方回合、白狼（或其卡牌）对敌方式神造成伤害（战斗或非战斗）。"""
    if not s.is_alive:
        return False
    if s.owner.game.current_player is not s.owner:
        return False
    src = getattr(e.event, "source", None)
    if src is s:
        pass
    elif hasattr(src, "get_corresponding_hero") and src.get_corresponding_hero() is s:
        pass
    else:
        return False
    targets = getattr(e.event, "target", None)
    if targets is None:
        return False
    tlist = targets if isinstance(targets, (list, tuple)) else [targets]
    return any(getattr(t, "entity_type", None) == "hero" and t.owner is s.owner.opponent for t in tlist)


def _juexing_bailang_trigger(e, s):
    s.owner.game.handle_event(DealDamage(4, s, [s.owner.opponent]))


class WuWo:
    """无我：瞬发 白狼获得3力量，不屈，贯通，迅捷直到下一次攻击后。"""
    id = 181
    type = "spell"
    hero = "BaiLang"
    name = "无我"
    level_req = 3
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (lambda s: _wuwo_on_play(s),)


def _wuwo_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _bailang_add_spell_buff(hero, atk=3,
                            attrs=(HeroAttributes.TENACIOUS, HeroAttributes.PENETRATE, HeroAttributes.AGILE))


# ── 协战：森佑灵矢（白狼×萤草） ──────────────────────────────────────────

class SenYouLingShi:
    """森佑灵矢：选择使用一项：萤草-森佑灵引；白狼-灵矢贯虹。"""
    id = 182
    type = "coop"
    hero = "BaiLang"
    heroes = ["BaiLang", "YingCao"]
    name = "森佑灵矢"
    level_req = 2
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (lambda s: _senyoulingshi_on_play(s),)


def _senyoulingshi_on_play(s):
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "BaiLang":
        # 白狼-灵矢贯虹
        _lingshiguanhong_on_play(s)
    elif hero.type_name == "YingCao":
        # 萤草-森佑灵引：萤草未实现，TODO（待萤草实现后完成）
        pass


class LingShiGuanHong:
    """灵矢贯虹：本次攻击白狼获得当前自身法术牌强化效果的力量加成。
    羁绊：攻击前触发萤草当前形态进场效果，你的出击加成效果在使用此牌时也会生效。"""
    id = 183
    type = "attack"
    hero = "BaiLang"
    name = "灵矢贯虹"
    level_req = 2
    buff_atk = 1
    buff_def = 1
    is_beginning_card = False
    on_play = (lambda s: _lingshiguanhong_on_play(s),)


def _lingshiguanhong_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 法术强化（起弓/离/无我）已直接加在 hero.atk 上（Design A），本次攻击天然继承其力量加成；
    # 残心形态下强化不消失，也一并生效。攻击后法术强化照常清除（残心除外）。
    # 羁绊（萤草当前形态进场效果）：萤草未实现，TODO（待萤草实现后完成）
