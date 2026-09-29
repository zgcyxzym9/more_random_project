"""日和坊 专属卡牌（cards 272-281）

沐浴阳光 / 祈晴 / 阳炎 / 冬日暖阳 / 滋养 / 日出有曜 / 觉醒·日和坊 / 晴雨 /
日霭相织(协战) / 煦日

数据来源：cards.json（描述逐字拷贝）+ 用户补充说明（晴天娃娃灵咒、生命代偿
实际表现、烟烟罗未实装裁决 2026-09-27）。

机制要点：
- 能量消耗（用户裁决 2026-09-27 架构）：每个耗能技能直接发起
  EnergySpendEvent（handle_event 前先判断剩余能量是否足够），扣费由事件的
  match 分支统一结算；觉醒免耗监听 before 阶段改写（amount=0 + revert）。
- 基础被动生命代偿（本文件 _pay_energy）：能量不足时自动判定——代偿不会使
  生命降到 0 才直接生效；先发 EnergySpendEvent 结算现有能量部分（供免耗
  被动整体免除），缺少部分以 DealDamage 自损结算（狂歌豪情自损为费先例）。
- 晴天娃娃：灵咒结附标记（非 cards.json 卡牌，规则来自用户补充说明）：
  不能叠加（同一时间唯一 holder）；每回合一次，当结附式神攻击或使用卡牌时
  结附式神获得 2 能量；结附式神将气绝时若日和坊存活则改结附于日和坊。
- 阳炎响应依赖引擎 HeroUpgradeEvent（"upgrade hero" 动作升级后广播）。

排列约定：全部效果函数定义在前、类定义在后（类体直接引用函数，
BingYong/Xun listener 先例）。
"""
import random
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *
from game_core.damage_immunity import clear_combat_immune, make_combat_immune_listener


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _rihefang(player):
    """己方日和坊（存活）。"""
    for h in player.heroes:
        if h.type_name == "RiHeFang" and h.is_alive:
            return h
    return None


def _charged_allies(player, exclude=None):
    """己方有充能的式神（存活、已升级）。"""
    return [h for h in player.heroes
            if h.is_alive and h.level > 0
            and HeroAttributes.ENERGY_CHARGE in h.attributes
            and h is not exclude]


def _pay_energy(player, hero, amount, source) -> bool:
    """日和坊支付能量。返回支付是否成功（失败则效果不结算）。

    发起方契约：能量足够时直接发 EnergySpendEvent 扣费（觉醒免耗可监听
    免除——置 revert，免费但效果照常结算）。能量不足时基础被动生命代偿
    （自动判定，见模块 docstring）：
    - 代偿会使生命降到 0 → 支付失败，返回 False
    - 否则先发 EnergySpendEvent 结算现有能量部分（供免耗被动整体免除，
      含生命部分），未被免除则缺少部分以 DealDamage 自损结算
    """
    cur = hero.counters.get("energy", 0)
    if cur >= amount:
        player.game.handle_event(EnergySpendEvent(hero, amount, source))
        return True
    missing = amount - cur
    if not hero.is_alive or hero.hp <= missing:
        return False
    evt = EnergySpendEvent(hero, cur, source)
    player.game.handle_event(evt)
    if getattr(evt, "revert", False):
        return True             # 免除：能量与生命部分都不再消耗
    player.game.handle_event(DealDamage(missing, hero, [hero]))
    return True


def _any_shikigami_targets(player):
    """任意式神：双方存活且已升级（敌方排除帷幕——帷幕只限制卡牌主动选目标）。"""
    mine = [h for h in player.heroes if h.is_alive and h.level > 0]
    theirs = [h for h in player.opponent.heroes
              if h.is_alive and h.level > 0
              and HeroAttributes.VEIL not in h.attributes]
    return mine + theirs


# ── 晴天娃娃（灵咒结附标记，非 cards.json 卡牌）────────────────────────────
# 规则来自用户补充说明（2026-09-27）：灵咒、不能叠加（同一时间唯一 holder）、
# 每回合一次当结附式神攻击或使用卡牌时结附式神获得2能量、结附式神将气绝时
# 若日和坊存活则改结附于日和坊（wiki：气绝将失去结附其上的灵咒）。

SUNNY_DOLL_KEY = "sunny_doll"
RFH_SUNNY_TURN_KEY = "rfh_sunny_used"


def _sunny_holder(player):
    """当前结附「晴天娃娃」的己方式神（同一时间唯一）。"""
    for h in player.heroes:
        if h.counters.get(SUNNY_DOLL_KEY, 0) > 0:
            return h
    return None


def _attach_sunny(player, target):
    """结附「晴天娃娃」（不能叠加：清除旧 holder，改结附于 target）。"""
    for h in player.heroes:
        if h.counters.get(SUNNY_DOLL_KEY, 0) > 0:
            h.counters.set(SUNNY_DOLL_KEY, 0)
    target.counters.ensure(SUNNY_DOLL_KEY, initial=0, persistent=True)
    target.counters.set(SUNNY_DOLL_KEY, 1)


def _sunny_attack_cond(e, s):
    holder = _sunny_holder(s.owner)
    return (holder is not None and holder.is_alive
            and e.event.hero is holder
            and s.counters.get(RFH_SUNNY_TURN_KEY, 0) == 0)


def _sunny_play_cond(e, s):
    holder = _sunny_holder(s.owner)
    if holder is None or not holder.is_alive:
        return False
    card = e.event.card
    if card is None:
        return False
    if s.counters.get(RFH_SUNNY_TURN_KEY, 0) != 0:
        return False
    # 协战牌的使用者是打出分支式神（played_by，2026-09-29 协战选择语义改为
    # 「选分支式神」）；get_corresponding_hero 对协战优先返回 played_by，
    # 未记录时（响应等特殊路径）回退任一列表式神，与旧行为一致。
    return card.get_corresponding_hero() is holder


def _sunny_energy_trigger(e, s):
    s.counters.ensure(RFH_SUNNY_TURN_KEY, initial=0, reset_per_turn=True)
    s.counters.set(RFH_SUNNY_TURN_KEY, 1)
    holder = _sunny_holder(s.owner)
    if holder is not None and holder.is_alive:
        holder.counters.inc("energy", 2)   # energy 上限 10（set 自动截断）
        s.owner.game.handle_event(EnergyGainEvent(holder, 2))


def _sunny_death_cond(e, s):
    holder = _sunny_holder(s.owner)
    return holder is not None and e.event.hero is holder


def _sunny_death_move(e, s):
    """结附式神将气绝时：日和坊存活则改结附于日和坊，否则灵咒消失。

    日和坊本人是 holder 时直接消失（结附于将气绝的自己等于失去，
    wiki：结附式神气绝将失去结附其上的灵咒）。
    """
    holder = _sunny_holder(s.owner)
    holder.counters.set(SUNNY_DOLL_KEY, 0)
    rf = _rihefang(s.owner)
    if rf is not None and rf is not holder:
        rf.counters.ensure(SUNNY_DOLL_KEY, initial=0, persistent=True)
        rf.counters.set(SUNNY_DOLL_KEY, 1)


def _install_sunny_listeners(player):
    """在日和坊身上安装晴天娃娃触发监听（幂等；结附期间持续生效，
    监听器条件自行过滤 holder 是否存在/存活）。"""
    rf = None
    for h in player.heroes:
        if h.type_name == "RiHeFang":
            rf = h
            break
    if rf is None or getattr(player, "_rfh_sunny_installed", False):
        return
    player._rfh_sunny_installed = True
    l_atk = Listener("hero attack", _sunny_attack_cond, (_sunny_energy_trigger,))
    l_atk._tag = RFH_SUNNY_TURN_KEY
    rf.listeners.append(l_atk)
    l_play = Listener("play card", _sunny_play_cond, (_sunny_energy_trigger,),
                      phase="after")
    l_play._tag = RFH_SUNNY_TURN_KEY
    rf.listeners.append(l_play)
    l_die = Listener("about to die", _sunny_death_cond, (_sunny_death_move,))
    l_die._tag = RFH_SUNNY_TURN_KEY
    rf.listeners.append(l_die)


# ── 各卡效果函数 ────────────────────────────────────────────────────────────

def _muyu_on_play(s):
    player = s.owner
    game = player.game
    for h in _charged_allies(player):
        if h.hp < h.current_max_hp:
            game.handle_event(Heal(h.current_max_hp - h.hp, s, [h]))
        h.counters.inc("energy", 1)
        game.handle_event(EnergyGainEvent(h, 1))


def _qiqing_on_play(s):
    _qiqing_draw(s)
    rf = s.get_corresponding_hero()
    rf.listeners = [l for l in rf.listeners if getattr(l, "_tag", "") != "qiqing"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 273,
                 (lambda e, h: _qiqing_turn(h),))
    l._tag = "qiqing"
    rf.listeners.append(l)


def _qiqing_draw(s):
    player = s.owner
    rf = s.get_corresponding_hero()
    if _pay_energy(player, rf, 3, s):
        player.game.handle_event(DrawEvent(player, 1))


def _qiqing_turn(h):
    # 己方回合开始触发：无卡牌对象，source 为 None
    if _pay_energy(h.owner, h, 3, None):
        h.owner.game.handle_event(DrawEvent(h.owner, 1))


def _yangyan_on_play(s):
    target = s.owner.selected_targets[0]
    target.stun()
    return DealDamage(1, s, [target])


def _yangyan_cond(e, s):
    return e.event.hero.owner is s.owner.opponent and e.event.hero.is_alive


def _yangyan_response(e, s):
    # 旧式响应（干扰投掷先例）：自动打出，目标固定为刚升级的敌方式神
    owner = s.owner
    can_play, _ = owner.game.can_play_card(owner, s)
    if not can_play:
        return
    owner.selected_targets = [e.event.hero]
    owner.game.play_card(owner, s)   # 鬼火由 play_card 内部统一扣除


def _dongri_on_play(s):
    player = s.owner
    game = player.game
    for h in _charged_allies(player):
        game.handle_event(GiveBuff("atk", 1, s, [h]))
        game.handle_event(GiveBuff("hp", 1, s, [h]))
        h.counters.inc("energy", 2)
        game.handle_event(EnergyGainEvent(h, 2))
    # 「然后再」：第二段在第一段结算后判定（充能式神可能恰好达到 7）
    for h in player.heroes:
        if h.is_alive and h.level > 0 and h.counters.get("energy", 0) >= 7:
            game.handle_event(GiveBuff("atk", 1, s, [h]))
            game.handle_event(GiveBuff("hp", 1, s, [h]))


def _ziyang_on_play(s):
    rf = s.get_corresponding_hero()
    _ziyang_give(s.owner, rf, s)
    rf.listeners = [l for l in rf.listeners if getattr(l, "_tag", "") != "ziyang"]
    l = Listener("begin turn",
                 lambda e, h: e.next_player == h.owner and h.morphed_id == 276,
                 (lambda e, h: _ziyang_give(h.owner, h, None),))
    l._tag = "ziyang"
    rf.listeners.append(l)


def _ziyang_give(player, rf, source):
    cands = _charged_allies(player, exclude=rf)
    if not cands:
        return                      # 无其他充能式神：不消耗，效果不结算
    if not _pay_energy(player, rf, 2, source):
        return
    lowest = min(h.counters.get("energy", 0) for h in cands)
    mins = [h for h in cands if h.counters.get("energy", 0) == lowest]
    tgt = select_random_target(player, mins, context="滋养：随机能量最低的己方充能式神")
    if tgt is None:
        return
    tgt.counters.inc("energy", 2)
    player.game.handle_event(EnergyGainEvent(tgt, 2))


def _richu_targets(player):
    return _any_shikigami_targets(player) + [player, player.opponent]


def _richu_on_play(s):
    target = s.owner.selected_targets[0]
    if hasattr(target, "type_name"):
        # 式神：力量、生命变为基础值（永久加成保留——桃花妖形态离场先例；
        # 形态仍在场，形态牌数值贡献一并清除）；护甲与破甲清零
        target.atk = target.original_atk + target.perm_buff_atk
        target.current_max_hp = target.original_hp + target.perm_buff_hp
        target.hp = target.current_max_hp
        target.defense = 0
        target.penetration = 0
    else:
        # 牌手：清除出击加成效果（不夜之舞清除先例）
        target.inspiration_atk = 0
        target.inspiration_def = 0
        target.inspiration_hp = 0
        target.inspiration_effects = []


def _juexing_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    hero.get_permanent_buff("hp", 3)
    hero.is_awakened = True
    # 日和坊觉醒加成标记（鬼使黑白 _awakened_hei 先例）：供「判断能否支付
    # 能量」的调用点（爆能选项/爆能扣费/鬼使黑白切白）查询免耗是否可用，
    # 见 heroes.py rfh_awaken_free_available
    hero._rfh_awaken_buff = True


def _qingyu_mass_heal(player, rf, source):
    if not _pay_energy(player, rf, 3, source):
        return
    game = player.game
    for h in player.heroes:
        if h is not rf and h.is_alive and h.level > 0:
            game.handle_event(Heal(3, source, [h]))
    game.handle_event(Heal(3, source, [player]))   # 「其他己方角色」含牌手


def _qingyu_dmg_cond(e, h):
    if h.morphed_id != 279 or not h.is_alive:
        return False
    player = h.owner
    for t in e.event.target:
        if t is h:
            continue               # 「己方其他角色」：日和坊自己受伤不触发
        if t is player or getattr(t, "owner", None) is player:
            return True
    return False


def _qingyu_dmg_effect(e, h):
    # 每次受伤事件恢复 3 点（多目标同时受伤只触发一次），上限由 Heal 结算
    h.owner.game.handle_event(Heal(3, h, [h]))


def _qingyu_on_play(s):
    rf = s.get_corresponding_hero()
    _qingyu_mass_heal(s.owner, rf, s)
    rf.listeners = [l for l in rf.listeners if getattr(l, "_tag", "") != "qingyu"]
    # 「每个回合开始时」：双方回合均触发（与祈晴/滋养的己方回合不同）
    l_turn = Listener("begin turn",
                      lambda e, h: h.morphed_id == 279,
                      (lambda e, h: _qingyu_mass_heal(h.owner, h, None),))
    l_turn._tag = "qingyu"
    rf.listeners.append(l_turn)
    l_dmg = Listener("deal damage", _qingyu_dmg_cond, (_qingyu_dmg_effect,))
    l_dmg._tag = "qingyu"
    rf.listeners.append(l_dmg)


def _xuri_targets(player):
    """一个其他己方式神：存活、已升级、非日和坊本人。"""
    rf = None
    for h in player.heroes:
        if h.type_name == "RiHeFang":
            rf = h
            break
    return [h for h in player.heroes
            if h.is_alive and h.level > 0 and h is not rf]


def _xuri_on_play(s):
    _xuri_apply(s, s.owner.selected_targets[0])


def _xuri_apply(s, recipient):
    player = s.owner
    game = player.game
    _install_sunny_listeners(player)
    recipient.counters.inc("energy", 2)
    game.handle_event(EnergyGainEvent(recipient, 2))
    _attach_sunny(player, recipient)
    # 羁绊：本回合免疫战斗伤害（回合结束 clear_round_effects 统一清除）
    clear_combat_immune(recipient)
    recipient.listeners.append(make_combat_immune_listener())


def _riai_on_play(s):
    # 协战分支派发（森佑灵矢先例）：played_by 即选定的分支式神
    # （play_card 在选目标完成后记录，见 RiAiXiangZhi docstring）。
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "YanYanLuo":
        # 烟烟罗-烟影：召唤分身后以正常打出流程使用当前等级的爆能法术
        # （目标选择由 play_card 承担，用户裁决 2026-09-29）
        from game_core.cards.YanYanLuo import _yyl_riai_yanying_effect
        _yyl_riai_yanying_effect(s.owner)
    elif hero.type_name == "RiHeFang":
        # 日和坊-煦日：单次选目标已用于选分支式神，受牌者取「其他存活已升级
        # 己方式神」中随机（用户裁决 2026-09-29）
        targets = _xuri_targets(s.owner)
        if targets:
            _xuri_apply(s, random.choice(targets))


# ── 1勾卡牌 ─────────────────────────────────────────────────────────────────

class MuYuYangGuang:
    """沐浴阳光：瞬发 恢复己方有充能的式神所有生命，并使他们各获得1点能量。"""
    id = 272
    type = "spell"
    hero = "RiHeFang"
    name = "沐浴阳光"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (_muyu_on_play,)


class QiQing:
    """祈晴：进场和己方回合开始时，消耗3能量，抽一张牌。"""
    id = 273
    type = "morph"
    hero = "RiHeFang"
    name = "祈晴"
    level_req = 1
    atk = 1
    hp = 7
    is_beginning_card = True
    on_play = (_qiqing_on_play,)


class YangYan:
    """阳炎：对一个式神造成1点伤害并眩晕它。
    响应：当一个敌方式神升级时，自动对其使用（监听 HeroUpgradeEvent，
    引擎在 "upgrade hero" 动作升级后广播）。"""
    id = 274
    type = "spell"
    hero = "RiHeFang"
    name = "阳炎"
    level_req = 2
    attributes = (CardAttributes.RESPONSE,)
    is_beginning_card = True
    require_target = (lambda s: _any_shikigami_targets(s.owner),)
    select_target = (lambda s: select_target(s.owner,
                                             _any_shikigami_targets(s.owner), s),)
    listeners = (Listener("hero upgrade", _yangyan_cond, (_yangyan_response,)),)
    on_play = (_yangyan_on_play,)


# ── 2勾卡牌 ─────────────────────────────────────────────────────────────────

class DongRiNuanYang:
    """冬日暖阳：使所有己方有充能的式神获得1力量、1生命与2能量，
    然后再使所有能量大于等于7的己方式神获得1力量与1生命。"""
    id = 275
    type = "spell"
    hero = "RiHeFang"
    name = "冬日暖阳"
    level_req = 2
    is_beginning_card = True
    on_play = (_dongri_on_play,)


class ZiYang:
    """滋养：进场和己方回合开始时，消耗2能量，
    随机使其他一名能量最低的己方充能式神获得2能量。"""
    id = 276
    type = "morph"
    hero = "RiHeFang"
    name = "滋养"
    level_req = 2
    atk = 2
    hp = 7
    is_beginning_card = True
    on_play = (_ziyang_on_play,)


class RiChuYouYao:
    """日出有曜：瞬发 使一个式神的力量、生命变为基础值，清除他的护甲与破甲；
    或清除一个牌手的出击加成效果。

    引擎无「选择使用一项」交互，以单次选目标派发：选中式神→前者，
    选中牌手→后者（目标列表为双方式神 + 双方牌手）。"""
    id = 277
    type = "spell"
    hero = "RiHeFang"
    name = "日出有曜"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    require_target = (lambda s: _richu_targets(s.owner),)
    select_target = (lambda s: select_target(s.owner, _richu_targets(s.owner), s),)
    on_play = (_richu_on_play,)


# ── 3勾卡牌 ─────────────────────────────────────────────────────────────────

class JueXingRiHeFang:
    """觉醒·日和坊：瞬发 觉醒：充能。日和坊能量不足时，可以消耗其生命代替。
    每回合一次己方式神消耗能量的效果不再消耗能量。

    充能为基础能力（觉醒重复词条，无操作）；生命代偿见 _pay_energy；
    免耗见 heroes.py 日和坊被动监听。"""
    id = 278
    type = "spell"
    hero = "RiHeFang"
    name = "觉醒·日和坊"
    level_req = 3
    buff_hp = 3
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (_juexing_on_play,)


class QingYu:
    """晴雨：当己方其他角色受到伤害时，日和坊恢复3点生命。
    进场和每个回合开始时，消耗3能量，恢复所有其他己方角色3点生命。"""
    id = 279
    type = "morph"
    hero = "RiHeFang"
    name = "晴雨"
    level_req = 3
    atk = 3
    hp = 8
    is_beginning_card = True
    on_play = (_qingyu_on_play,)


# ── 协战 / 煦日 ─────────────────────────────────────────────────────────────

class RiAiXiangZhi:
    """日霭相织（协战 日和坊×烟烟罗）：选择使用一项：烟烟罗-烟影；日和坊-煦日。

    森佑灵矢先例（用户裁决 2026-09-29）：单次选目标 = 选分支式神，
    play_card 把 played_by 记为选中者，on_play 按其派发：
    - 烟烟罗-烟影：召唤分身后按烟烟罗当前等级以正常打出流程使用爆能法术
      （免鬼火、爆能X为分身全部能量，目标选择由 play_card 挂起-重放承担；
      羁绊同烟影）。
    - 日和坊-煦日：受牌者为「其他存活已升级己方式神」中随机（单次选目标
      已用于选分支，无法手选受牌者）。
    """
    id = 280
    type = "coop"
    hero = "RiHeFang"
    heroes = ["RiHeFang", "YanYanLuo"]
    name = "日霭相织"
    level_req = 1
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (_riai_on_play,)


class XuRi:
    """煦日：使一个其他己方式神获得2能量，结附「晴天娃娃」。
    羁绊：使该式神本回合免疫战斗伤害。"""
    id = 281
    type = "spell"
    hero = "RiHeFang"
    name = "煦日"
    level_req = 1
    is_beginning_card = False
    require_target = (lambda s: _xuri_targets(s.owner),)
    select_target = (lambda s: select_target(s.owner, _xuri_targets(s.owner), s),)
    on_play = (_xuri_on_play,)
