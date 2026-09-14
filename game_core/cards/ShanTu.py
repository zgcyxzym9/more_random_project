import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# ═══════════════════════════════════════════════════════════════════════════════
#  山兔 专属卡牌（9 张）
#
#  增强共同基础：「本局游戏你骰子每投出一次6点」。6点计数由 heroes.py 中
#  山兔的 fortune success 监听器写入其持久计数器 sixes_rolled（计入己方所有
#  式神的最终掷骰结果，含座敷童子；气绝不重置）。
# ═══════════════════════════════════════════════════════════════════════════════

def _sixes(player):
    """本局游戏该牌手投出6点的次数（山兔持久计数器）。"""
    for h in player.heroes:
        if getattr(h, "type_name", "") == "ShanTu":
            return h.counters.get("sixes_rolled", 0)
    return 0


# ── 105 谁还不听话 ────────────────────────────────────────────────────────────

def _shuihaibutinghua_on_play(s):
    """瞬发 投射：造成2点伤害。增强：本局游戏你骰子每投出一次6点，此牌效果+1。"""
    dmg = 2 + _sixes(s.owner)
    s.owner.game.handle_event(ProjectileEvent(dmg, s, [s.owner.opponent.attack_zone]))


class ShuiHaiBuTingHua:
    id = 105
    type = "spell"
    hero = "ShanTu"
    name = "谁还不听话"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    on_play = (_shuihaibutinghua_on_play,)


# ── 106 送祝福 ────────────────────────────────────────────────────────────────

def _songzhufu_on_play(s):
    """使一个己方式神获得1力量与1生命，抽一张牌。
    增强：本局游戏若你骰子投出三次6点，该式神额外获得2力量、2生命和迅捷。"""
    if not s.owner.selected_targets:
        return
    target = s.owner.selected_targets[0]
    game = s.owner.game
    game.handle_event(GiveBuff("atk", 1, s, [target]))
    game.handle_event(GiveBuff("hp", 1, s, [target]))
    s.owner.draw()
    if _sixes(s.owner) >= 3:
        game.handle_event(GiveBuff("atk", 2, s, [target]))
        game.handle_event(GiveBuff("hp", 2, s, [target]))
        if HeroAttributes.AGILE not in target.attributes:
            target.attributes.append(HeroAttributes.AGILE)


class SongZhuFu:
    id = 106
    type = "spell"
    hero = "ShanTu"
    name = "送祝福"
    level_req = 1
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(s.owner,
                                             [h for h in s.owner.heroes if h.is_alive and h.level > 0], s),)
    on_play = (_songzhufu_on_play,)


# ── 形态遗留清理（快来保护我 / 萌即正义 共用）───────────────────────────────────

def _morph_replaced_cond(e, s):
    """同一式神身上打出另一张形态牌 → 旧形态离场。"""
    card = getattr(e.event, "card", None)
    if card is None or getattr(card, "type", None) != "morph":
        return False
    return card.get_corresponding_hero() is s


def _about_to_die_cond(e, s):
    return getattr(e.event, "hero", None) is s


def _st_morph_cleanup(e, s):
    """清除山兔形态遗留：快来保护我的不屈、萌即正义的强制6 及清理监听器。

    e 为触发事件（on_play 直接调用时传 None），s 为山兔式神。
    幂等：可被形态替换、式神死亡、重复调用多次执行。
    """
    hero = s
    if getattr(hero, "_kuailai_tenacious", False):
        if HeroAttributes.TENACIOUS in hero.attributes:
            hero.attributes.remove(HeroAttributes.TENACIOUS)
        hero._kuailai_tenacious = False
    hero.listeners = [l for l in hero.listeners
                      if getattr(l, "_tag", "") not in ("_st_mengji_force6", "_st_morph_cleanup")]


def _st_morph_attach_cleanup(hero):
    """挂载形态离场/气绝时的清理监听器（统一 tag）。"""
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "_st_morph_cleanup"]
    l_play = Listener("play card", _morph_replaced_cond, (_st_morph_cleanup,))
    l_play._tag = "_st_morph_cleanup"
    l_die = Listener("about to die", _about_to_die_cond, (_st_morph_cleanup,))
    l_die._tag = "_st_morph_cleanup"
    hero.listeners.append(l_play)
    hero.listeners.append(l_die)


# ── 107 快来保护我 ────────────────────────────────────────────────────────────

def _kuailaibaohuwo_on_play(s):
    """增强：本局游戏若你骰子投出三次6点，此牌获得不屈。

    形态身材（6/6）由引擎在 on_play 之后按 card.atk/hp 应用；不屈在
    形态结算前加到式神 attributes 上（与死亡/离场清理由 _st_morph_cleanup 负责）。
    """
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _st_morph_cleanup(None, hero)
    if _sixes(s.owner) >= 3:
        if HeroAttributes.TENACIOUS not in hero.attributes:
            hero.attributes.append(HeroAttributes.TENACIOUS)
        hero._kuailai_tenacious = True
    _st_morph_attach_cleanup(hero)


class KuaiLaiBaoHuWo:
    id = 107
    type = "morph"
    hero = "ShanTu"
    name = "快来保护我"
    level_req = 2
    atk = 6
    hp = 6
    on_play = (_kuailaibaohuwo_on_play,)


# ── 108 觉醒·山兔 ─────────────────────────────────────────────────────────────

def _juexing_shantu_begin(e, s):
    """觉醒·山兔：己方回合开始时，运势6：其他己方式神倒计时-1（含气绝倒计时）
    并获得2力量，然后重复一次。"""
    game = s.owner.game
    for _ in range(2):
        if not game.roll_fortune(s, 6):
            continue
        others = [h for h in s.owner.heroes if h is not s]
        alive = [h for h in others if h.is_alive]
        if alive:
            game.handle_event(GiveBuff("atk", 2, s, alive))
        for h in others:
            if not h.is_alive:
                if h.round_until_alive > 0:
                    h.round_until_alive -= 1
                    if h.round_until_alive <= 0:
                        h.revive()
                continue
            if h.countdown > 0:
                h.countdown -= 1
                if h.countdown <= 0 and h.countdown_max > 0:
                    h.countdown = h.countdown_max
                    game.handle_event(CountdownEvent(h))
                    for cb in h.on_countdown:
                        result = cb(h)
                        if isinstance(result, Event):
                            game.handle_event(result)


def _create_juexing_shantu_listener():
    l = Listener("begin turn",
                 lambda e, s: s.is_alive and e.next_player == s.owner,
                 (_juexing_shantu_begin,))
    l._tag = "_st_juexing"
    return l


def _juexingshantu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True
    # 觉醒效果替换基础能力（wiki「关键字-觉醒」），且不因死亡恢复（faq）：
    # 监听器同时加入 listeners 与 original_listeners（死亡重置时保留）
    awake = _create_juexing_shantu_listener()
    for lst in (hero.listeners, hero.original_listeners):
        lst[:] = [l for l in lst if getattr(l, "_tag", "") != "_st_juexing"]
        lst.append(awake)


class JueXingShanTu:
    id = 108
    type = "spell"
    hero = "ShanTu"
    name = "觉醒·山兔"
    level_req = 2
    on_play = (_juexingshantu_on_play,)


# ── 109 这把算我赢 ────────────────────────────────────────────────────────────

def _st_next_roll_6_cond(e, s):
    return (getattr(e.event, "source_hero", None) is s
            and getattr(s, "_st_next_roll_6", False))


def _st_next_roll_6_effect(e, s):
    e.event.result = 6
    s._st_next_roll_6 = False


def _zhebasuanwoying_on_play(s):
    """瞬发 山兔下一次投骰子必定会投出6点。
    增强：本局游戏若你骰子投出十次6点，则你获得本局游戏的胜利。"""
    owner = s.owner
    shantu = s.get_corresponding_hero()
    if shantu is not None:
        # 下次投骰子必定6：设置一次性标记 + 覆写监听器（用后即焚）
        shantu._st_next_roll_6 = True
        shantu.listeners = [l for l in shantu.listeners if getattr(l, "_tag", "") != "_st_next_roll_6"]
        l = Listener("fortune roll", _st_next_roll_6_cond, (_st_next_roll_6_effect,))
        l._tag = "_st_next_roll_6"
        shantu.listeners.append(l)
    if _sixes(owner) >= 10:
        owner.opponent.state = PlayerState.LOST
        owner.state = PlayerState.WON


class ZheBaSuanWoYing:
    id = 109
    type = "spell"
    hero = "ShanTu"
    name = "这把算我赢"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    on_play = (_zhebasuanwoying_on_play,)


# ── 110 戏谑套索 ─────────────────────────────────────────────────────────────

# 纸人/小纸人变形期间被置空的式神状态字段
_XIXUE_SNAP_FIELDS = ("atk", "current_max_hp", "hp", "defense", "penetration",
                      "round_buff_atk", "round_buff_spell_damage", "round_buff_player_damage")
# 式神自身效果回调（与 listeners 一起被压制）
_XIXUE_CALLBACK_FIELDS = ("on_before_death", "on_death", "on_countdown", "on_move",
                          "on_before_damage", "on_after_damage", "on_stun", "on_unstun",
                          "on_upgrade", "on_revive")


def _xixue_response_cond(card, src, target):
    """当山兔被攻击时自动使用。"""
    shantu = card.get_corresponding_hero()
    return shantu is not None and target is shantu


def _xixue_restore_cond(e, p):
    return True  # 下一个 begin turn（本回合结束）即恢复


def _xixue_restore(e, p):
    """本回合结束后变回原式神：还原快照。已气绝的纸人随死亡结束，仅清标记。"""
    for h in p.heroes:
        if not getattr(h, "_xixue_paper", False):
            continue
        snap = getattr(h, "_xixue_snapshot", None)
        if h.is_alive and snap is not None:
            for f in _XIXUE_SNAP_FIELDS:
                setattr(h, f, snap[f])
            h.attributes = list(snap["attributes"])
            h.listeners = list(snap["listeners"])
            for f in _XIXUE_CALLBACK_FIELDS:
                setattr(h, f, snap[f])
            for k, v in snap["counters"].items():
                h.counters.set(k, v)
        h._xixue_paper = False
        h._xixue_snapshot = None
    p.listeners = [l for l in p.listeners if getattr(l, "_tag", "") != "_xixue_restore"]


def _xixuetaosuo_on_play(s):
    """将敌方战斗区式神变成「纸人」，抽一张牌。
    增强：本局游戏若你骰子投出三次6点，改为将其变成「小纸人」。
    响应：当山兔被攻击时，自动使用。

    纸人（3/3）/小纸人（0/1）期间，式神自身效果与所有增益、减益、护盾、
    破甲全部失效（attributes/listeners/回调/counters 全部置空），本回合结束后
    变回原式神。恢复监听器挂在目标所属牌手（式神监听器已被清空）。
    """
    s.owner.draw()  # 抽一张牌（无论是否成功变成纸人）
    target = s.owner.opponent.attack_zone
    if target is None or not target.is_alive:
        return
    small = _sixes(s.owner) >= 3
    paper_atk, paper_hp = (0, 1) if small else (3, 3)
    snap = {"attributes": list(target.attributes),
            "listeners": list(target.listeners),
            "counters": dict(target.counters._values)}
    for f in _XIXUE_SNAP_FIELDS:
        snap[f] = getattr(target, f)
    for f in _XIXUE_CALLBACK_FIELDS:
        snap[f] = getattr(target, f)
    target._xixue_snapshot = snap
    target._xixue_paper = True
    target.atk = paper_atk
    target.current_max_hp = paper_hp
    target.hp = paper_hp
    target.defense = 0
    target.penetration = 0
    target.round_buff_atk = 0
    target.round_buff_spell_damage = 0
    target.round_buff_player_damage = 0
    target.attributes = []
    target.listeners = []
    for f in _XIXUE_CALLBACK_FIELDS:
        setattr(target, f, ())
    for k in list(target.counters._values):
        cd = target.counters._defs.get(k)
        target.counters.set(k, cd.initial if cd else 0)
    p = target.owner
    p.listeners = [l for l in p.listeners if getattr(l, "_tag", "") != "_xixue_restore"]
    l = Listener("begin turn", _xixue_restore_cond, (_xixue_restore,))
    l._tag = "_xixue_restore"
    p.listeners.append(l)


class XiXueTaoSuo:
    id = 110
    type = "spell"
    hero = "ShanTu"
    name = "戏谑套索"
    level_req = 2
    on_play = (_xixuetaosuo_on_play,)
    response_trigger = "hero attack"
    response_condition = (_xixue_response_cond,)


# ── 111 来打我呀 ──────────────────────────────────────────────────────────────

def _laidawoya_on_play(s):
    """使一个敌方式神立刻发动攻击。
    增强：本局游戏你骰子每投出一次6点，本回合该式神便降低1力量。"""
    if not s.owner.selected_targets:
        return
    target = s.owner.selected_targets[0]
    game = s.owner.game
    sixes = _sixes(s.owner)
    if sixes > 0:
        # 本回合降力量：round_buff_atk 在回合开始被 clear_round_effects 清除
        target.round_buff_atk -= sixes
    # 立刻发动攻击：远程（RANGED）在准备区攻击，其余进入战斗区（handle_event 分支处理）
    game.handle_event(HeroAttackEvent(target.owner, target))


class LaiDaWoYa:
    id = 111
    type = "spell"
    hero = "ShanTu"
    name = "来打我呀"
    level_req = 2
    require_target = (lambda s: [h for h in s.owner.opponent.heroes
                                 if h.is_alive and h.level > 0 and not h.stunned
                                 and HeroAttributes.VEIL not in h.attributes],)
    select_target = (lambda s: select_target(s.owner,
                                             [h for h in s.owner.opponent.heroes
                                              if h.is_alive and h.level > 0 and not h.stunned
                                              and HeroAttributes.VEIL not in h.attributes], s),)
    on_play = (_laidawoya_on_play,)


# ── 112 萌即正义 ─────────────────────────────────────────────────────────────

def _st_mengji_force6(e, h):
    e.event.result = 6


def _mengjizhengyi_on_play(s):
    """你投骰子总是会投出6点。
    增强：本局游戏你骰子每投出一次6点，此牌便获得+1力量与+1生命。

    形态身材在 on_play 中修改 card.atk/hp（引擎形态分支在 on_play 后按
    card 身材应用）；强制6 监听器由 _st_morph_cleanup 在形态离场/死亡时移除。
    """
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    _st_morph_cleanup(None, hero)
    sixes = _sixes(s.owner)
    s.atk = 6 + sixes
    s.hp = 6 + sixes
    l = Listener("fortune roll",
                 lambda e, h: (getattr(e.event, "source_hero", None) is not None
                               and e.event.source_hero.owner == h.owner),
                 (_st_mengji_force6,))
    l._tag = "_st_mengji_force6"
    hero.listeners.append(l)
    _st_morph_attach_cleanup(hero)


class MengJiZhengYi:
    id = 112
    type = "morph"
    hero = "ShanTu"
    name = "萌即正义"
    level_req = 3
    atk = 6
    hp = 6
    on_play = (_mengjizhengyi_on_play,)


# ── 113 幸运兔兔 ─────────────────────────────────────────────────────────────

def _apply_fire_penalty(enemy):
    """敌方下回合所有卡牌鬼火消耗+1。

    状态机（监听器挂敌方牌手）：挂 pending → 敌方回合开始激活为
    fire_cost_penalty → 敌方回合结束（我方回合开始）清除。引擎的
    can_play_card / _consume_fire 读取 fire_cost_penalty。
    """
    enemy._st_fire_penalty_pending = getattr(enemy, "_st_fire_penalty_pending", 0) + 1
    l = Listener("begin turn", lambda e, p: True, (_fire_penalty_sync,))
    l._tag = "_st_fire_penalty"
    enemy.listeners = [l for l in enemy.listeners if getattr(l, "_tag", "") != "_st_fire_penalty"]
    enemy.listeners.append(l)


def _fire_penalty_sync(e, p):
    if e.next_player == p:
        # 敌方自己的回合开始：激活惩罚
        p.fire_cost_penalty = getattr(p, "_st_fire_penalty_pending", 0)
        p._st_fire_penalty_pending = 0
    else:
        # 敌方回合结束（我方回合开始）：清除
        p.fire_cost_penalty = 0


def _zero_enemy_heroes(owner, enemy):
    """直到敌方回合结束，所有敌方式神力量变为0（快照-清零-恢复）。"""
    snap = {}
    for h in enemy.heroes:
        if h.is_alive and h.level > 0:
            snap[h] = h.atk
            h.atk = 0
    if not snap:
        return
    enemy._st_zero_snap = dict(getattr(enemy, "_st_zero_snap", {}))
    enemy._st_zero_snap.update(snap)
    l = Listener("begin turn",
                 lambda e, p: e.next_player == p.opponent and getattr(p, "_st_zero_snap", None),
                 (_zero_restore,))
    l._tag = "_st_zero_restore"
    enemy.listeners = [l for l in enemy.listeners if getattr(l, "_tag", "") != "_st_zero_restore"]
    enemy.listeners.append(l)


def _zero_restore(e, p):
    for h, atk in getattr(p, "_st_zero_snap", {}).items():
        if getattr(h, "is_alive", False):
            h.atk = atk
    p._st_zero_snap = {}
    p.listeners = [l for l in p.listeners if getattr(l, "_tag", "") != "_st_zero_restore"]


def xingyuntutu_effect(s):
    """幸运兔兔效果（独立打出，或经协战牌福星高照选择「山兔-幸运兔兔」）。
    瞬发 增强：本局游戏你骰子投出三次6点。敌方下回合所有卡牌鬼火消耗+1。
    羁绊：座敷童子运势4：直到敌方回合结束，所有敌方式神力量变为0。"""
    owner = s.owner
    if _sixes(owner) >= 3:
        _apply_fire_penalty(owner.opponent)
    # 羁绊：另一位协战式神（座敷童子）存活且等级不为0 即生效（faq）
    zft = [h for h in owner.heroes
           if h.type_name == "ZuoFuTongZi" and h.is_alive and h.level > 0]
    if zft and owner.game.roll_fortune(zft[0], 4):
        _zero_enemy_heroes(owner, owner.opponent)


class XingYunTuTu:
    id = 113
    type = "spell"
    hero = "ShanTu"
    name = "幸运兔兔"
    level_req = 3
    attributes = (CardAttributes.INSTANT,)
    on_play = (xingyuntutu_effect,)
