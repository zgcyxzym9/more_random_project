"""源九郎狐卡牌（id 343-350）。

牌面文本以 cards.json 条目（343-350）为准。式神段（基础能力：当你使用其他
紫岩派系式神的牌时，源九郎狐获得1点生命）在 heroes.py 源九郎狐段；本文件
实现卡牌打出侧逻辑。

口径与裁决记录（用户 2026-10-11）：
- 「过量治疗」按 heal 结算口径预先计算：溢出 = 值 - min(值, 生命上限-当前生命)
  （heal 处理器把当前生命截在上限，game.py case "heal"）。
- 狐辞（344）「选择一项」= 目标定模式（用户裁决，零引擎改动）：候选混排全场
  角色（双方存活式神 + 双方牌手，青坊主「角色」口径）与全场幻境（含敌方，
  用户裁决「全部全场」），选中目标即选中模式；角色分支过量治疗转化为护甲
  （GiveBuff "defense" 给该目标）；幻境耐久走 gain_illusion_durability 统一入口。
- 觉醒·源九郎狐（345）：type=spell + on_play 手动 is_awakened，buff_atk/buff_hp
  走 get_permanent_buff（觉醒·青坊主/觉醒·辉夜姬先例）；「其他紫岩式神获得
  1力量1生命」= GiveBuff（死亡/0级由处理器跳过）；卡面第二句与基础能力文本
  相同，heroes.py 现有监听无 awaken 门控，无需改动。
- 御先狐（346）：「战斗伤害」= damage_type 为 combat 或 penetrate（用户裁决；
  贯通溢出段源自攻击也算，多段攻击每次伤害各计一次）；「敌方角色」含敌方
  牌手；破甲走 apply_penetration 统一入口（广播 armor break applied）；护甲 =
  GiveBuff "defense"。监听挂 hero.listeners（法界唯心式），morphed_id 门控，
  气绝随 listeners 重置脱落。
- 初音鼓（347）：先复活后加成（revive case 在复活完成后才广播 AfterRevive，
  后续 GiveBuff 不会因气绝跳过）；「己方式神都为紫岩派系」按阵容全量判定
  （含气绝式神）；移入战斗区走 player.advance_hero（尘缚之阵替换锁拦截时
  返回 False，式神留在准备区）。
- 狐狸六法（348）：幻境监听挂 player.listeners，活性检查 card in illusion_zone
  （火鼠球式：耐久耗尽离场后监听静默）；「场上最大」= 双方存活式神生命的
  最大值（含并列）；进场加成与进场抽牌判定都在 on_play 内（先加成后判定，
  按卡面语序），回合开始判定挂 begin turn（e.next_player is owner）。
- 灵狐之嗣（349）：增强在 on_play 内直接改卡牌实例 atk/hp（morph 分支在
  on_play 之后才按 card.atk/card.hp 替换身材；Card.GetCard 每次新建实例，
  改动不跨对局）；「其他未气绝的紫岩式神」不含源九郎狐自身；不屈照残心式
  形态属性授予（幂等）+ morph leave 摘除（换形态/被替换时失去，气绝随死亡
  流程处理）。
- 道行初音旅（350）：本局持久效果挂 player.listeners（燕子安贝式 end turn
  before：current_player 仍是结束回合的玩家）；「永久获得」= get_permanent_buff
  （对气绝式神生效、复活后保留，faq；perm_buff 累计即「此效果可以叠加」，
  多张副本各挂一份监听）；同一实例重复打出（弹回回手再打出）按实例去重。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _controller_of(x):
    """角色（式神/牌手）的操控者：牌手是自身（entity_type="player"），式神取 owner。"""
    if getattr(x, "entity_type", "") == "player":
        return x
    return getattr(x, "owner", None)


def _all_characters(s):
    """「角色」候选：双方存活式神 + 双方牌手（青坊主「角色」口径）。"""
    return ([h for h in s.owner.heroes if h.is_alive]
            + [h for h in s.owner.opponent.heroes if h.is_alive]
            + [s.owner, s.owner.opponent])


def _all_illusions(s):
    """「幻境」候选：双方幻境区全部幻境（用户裁决：狐辞不限于己方幻境）。"""
    return list(s.owner.illusion_zone) + list(s.owner.opponent.illusion_zone)


def _overflow(value, target):
    """过量治疗预计算：heal 处理器会把生命截在 current_max_hp，缺口之外的
    部分即溢出（仅对存活实体有意义，与处理器口径一致）。"""
    missing = max(0, target.current_max_hp - target.hp)
    return value - min(value, missing)


# ── 343 狐手：为源九郎狐恢复2生命，此牌造成的过量治疗会转化为力量 ──────────

def _hushou_on_play(s):
    fox = s.get_corresponding_hero()
    if fox is None or not fox.is_alive:
        return
    g = s.owner.game
    overflow = _overflow(2, fox)
    g.handle_event(Heal(2, s, [fox]))
    if overflow > 0:
        g.handle_event(GiveBuff("atk", overflow, s, [fox]))


class HuShou:
    id = 343
    type = "attack"
    hero = "YuanJiuLangHu"
    name = "狐手"
    level_req = 1
    is_beginning_card = True
    on_play = (_hushou_on_play,)


# ── 344 狐辞：瞬发 选择一项：为一个角色恢复3生命，过量治疗会转化为护甲；
#    使一个幻境获得3耐久 ─────────────────────────────────────────────────────

def _huci_candidates(s):
    """目标定模式（用户裁决）：候选混排全场角色与全场幻境，选中即选模式。"""
    return _all_characters(s) + _all_illusions(s)


def _huci_on_play(s):
    targets = s.owner.selected_targets or []
    if not targets:
        return
    t = targets[0]
    g = s.owner.game
    if getattr(t, "type", "") == "illusion":
        # 幻境分支：耐久增长走统一入口（广播 IllusionDurabilityGainEvent）
        g.gain_illusion_durability(t, 3)
        return
    # 角色分支：回复3，过量治疗转化为护甲（给该目标）
    overflow = _overflow(3, t)
    g.handle_event(Heal(3, s, [t]))
    if overflow > 0:
        g.handle_event(GiveBuff("defense", overflow, s, [t]))


class HuCi:
    id = 344
    type = "spell"
    hero = "YuanJiuLangHu"
    name = "狐辞"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    require_target = (_huci_candidates,)
    select_target = (lambda s: select_target(s.owner, _huci_candidates(s), s),)
    on_play = (_huci_on_play,)


# ── 345 觉醒·源九郎狐：己方所有其他紫岩式神获得1力量和1生命。
#    当你使用其他紫岩式神的牌时，源九郎狐获得1生命（= heroes.py 基础能力） ──

def _juexingyjhlh_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    # buff_atk/buff_hp = 觉醒永久加成（get_permanent_buff：不发事件、跨形态
    # 与死亡保留，faq；觉醒·辉夜姬先例）
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    # 觉醒状态（heroes.py 基础监听无 awaken 门控：觉醒第二句与基础能力相同）
    hero.is_awakened = True
    # 己方所有其他紫岩式神获得1力量和1生命（死亡/0级由 GiveBuff 处理器跳过）
    others = [h for h in s.owner.heroes if h is not hero and h.type == "earth"]
    g = s.owner.game
    g.handle_event(GiveBuff("atk", 1, s, others))
    g.handle_event(GiveBuff("hp", 1, s, others))


class JueXingYuanJiuLangHu:
    id = 345
    type = "spell"
    hero = "YuanJiuLangHu"
    name = "觉醒·源九郎狐"
    level_req = 2
    buff_atk = 1
    buff_hp = 1
    is_beginning_card = True
    on_play = (_juexingyjhlh_on_play,)


# ── 346 御先狐：形态 3/7。己方回合当源九郎狐对敌方角色造成战斗伤害时，
#    使该角色获得3破甲，自己获得3护甲 ────────────────────────────────────────

_YUXIANHU_TAG = "yuxianhu_combat_pen"


def _yuxianhu_cond(e, h):
    """己方回合、源九郎狐对敌方角色造成战斗伤害（combat 命中段或 penetrate
    溢出段，多段攻击每次伤害各触发一次）。"""
    if not (h.is_alive and getattr(h, "morphed_id", 0) == YuXianHu.id):
        return False
    ev = e.event
    if getattr(ev, "damage_type", "spell") not in ("combat", "penetrate"):
        return False
    if getattr(ev, "value", 0) <= 0:
        return False
    if getattr(ev, "source", None) is not h:
        return False
    if h.owner.game.current_player is not h.owner:
        return False
    targets = getattr(ev, "target", None) or ()
    return any(_controller_of(t) is h.owner.opponent for t in targets)


def _yuxianhu_effect(e, h):
    g = h.owner.game
    for t in (getattr(e.event, "target", None) or ()):
        if _controller_of(t) is h.owner.opponent:
            # 破甲统一入口（广播 armor break applied，寂寥心象等监听依赖）
            g.apply_penetration(h, t, 3)
    g.handle_event(GiveBuff("defense", 3, h, [h]))


def _yuxianhu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 形态被动挂 hero.listeners（法界唯心式：同 tag 先摘后挂，气绝随 listeners
    # 重置脱落）。on_play 阶段 morphed_id 尚未置位，监听只在之后的伤害事件生效。
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != _YUXIANHU_TAG]
    l = Listener("damage dealt", _yuxianhu_cond, (_yuxianhu_effect,))
    l._tag = _YUXIANHU_TAG
    hero.listeners.append(l)


class YuXianHu:
    id = 346
    type = "morph"
    hero = "YuanJiuLangHu"
    name = "御先狐"
    level_req = 2
    atk = 3
    hp = 7
    is_beginning_card = True
    on_play = (_yuxianhu_on_play,)


# ── 347 初音鼓：复活一个己方式神，并使该式神获得1力量，1生命和1护甲。
#    增强：若己方式神都为紫岩派系，再将该式神移入战斗区 ─────────────────────

def _chuyingu_on_play(s):
    targets = s.owner.selected_targets or []
    if not targets:
        return
    t = targets[0]
    g = s.owner.game
    # 先复活（复活完成后才广播，目标已存活，后续 GiveBuff 不会被跳过）
    g.handle_event(Revive(s, [t]))
    g.handle_event(GiveBuff("atk", 1, s, [t]))
    g.handle_event(GiveBuff("hp", 1, s, [t]))
    g.handle_event(GiveBuff("defense", 1, s, [t]))
    # 增强：己方式神都为紫岩派系（阵容全量判定，含气绝）→ 移入战斗区
    # （尘缚之阵替换锁拦截时 advance_hero 返回 False，式神留在准备区）
    if all(h.type == "earth" for h in s.owner.heroes):
        s.owner.advance_hero(t)


class ChuYinGu:
    id = 347
    type = "spell"
    hero = "YuanJiuLangHu"
    name = "初音鼓"
    level_req = 2
    is_beginning_card = True
    require_target = (lambda s: IsDead(s.owner.heroes),)
    select_target = (lambda s: select_target(s.owner, IsDead(s.owner.heroes), s),)
    on_play = (_chuyingu_on_play,)


# ── 348 狐狸六法：幻境 耐久6。进场时使一个己方式神获得+1生命和+2护甲。
#    进场和己方回合开始时，若己方任一式神的生命为场上最大或同为最大，抽一张牌 ─

def _liufa_max_hp_satisfied(player):
    """己方任一存活式神的生命达到场上（双方存活式神）最大值（含并列）。"""
    all_alive = [h for p in (player, player.opponent) for h in p.heroes if h.is_alive]
    if not all_alive:
        return False
    mx = max(h.hp for h in all_alive)
    return any(h.hp == mx for h in player.heroes if h.is_alive)


def _liufa_turn_draw(e, s2):
    if _liufa_max_hp_satisfied(s2):
        s2.game.handle_event(DrawEvent(s2, 1))


def _liufa_on_play(s):
    player = s.owner
    card = s
    g = player.game
    # 进场：使一个己方式神获得+1生命和+2护甲（GiveBuff "hp" = 当前与上限同加）
    targets = player.selected_targets or []
    if targets:
        t = targets[0]
        g.handle_event(GiveBuff("hp", 1, s, [t]))
        g.handle_event(GiveBuff("defense", 2, s, [t]))
    # 进场抽牌判定（先加成后判定，按卡面语序）
    if _liufa_max_hp_satisfied(player):
        g.handle_event(DrawEvent(player, 1))
    # 己方回合开始抽牌判定：挂 player.listeners，活性检查 card in illusion_zone
    # （火鼠球式：幻境耐久耗尽离场后监听静默）
    l = Listener("begin turn",
                 lambda e, s2: card in s2.illusion_zone and e.next_player is s2,
                 (_liufa_turn_draw,))
    l._tag = "huliliufa-draw"
    player.listeners.append(l)


class HuLiLiuFa:
    id = 348
    type = "illusion"
    hero = "YuanJiuLangHu"
    name = "狐狸六法"
    level_req = 2
    durability = 6
    is_beginning_card = True
    require_target = (lambda s: [h for h in s.owner.heroes if h.is_alive],)
    select_target = (lambda s: select_target(
        s.owner, [h for h in s.owner.heroes if h.is_alive], s),)
    on_play = (_liufa_on_play,)


# ── 349 灵狐之嗣：形态 4/4 不屈。增强：你每有一个其他未气绝的紫岩式神，
#    此牌便获得3力量和3生命 ──────────────────────────────────────────────────

_LINGHU_TAG = "linghuzhisi_tenacious"


def _linghuzhisi_leave(e, h):
    # 形态离场（被替换/换形态）：摘除不屈与清理监听（残心式）
    if HeroAttributes.TENACIOUS in h.attributes:
        h.attributes.remove(HeroAttributes.TENACIOUS)
    h.listeners = [l for l in h.listeners if getattr(l, "_tag", "") != _LINGHU_TAG]


def _linghuzhisi_on_play(s):
    fox = s.get_corresponding_hero()
    if fox is None:
        return
    # 增强：每有一个其他未气绝的紫岩式神 +3/+3（不含源九郎狐自身）。on_play
    # 阶段先于身材替换，直接改卡牌实例 atk/hp（morph 分支随后按 card.atk/card.hp
    # 结算；实例每次打出新建，改动不跨对局）
    n = sum(1 for h in s.owner.heroes
            if h is not fox and h.is_alive and h.type == "earth")
    if n:
        s.atk += 3 * n
        s.hp += 3 * n
    # 不屈（形态属性）：幂等授予；morph leave 时摘除
    if HeroAttributes.TENACIOUS not in fox.attributes:
        fox.attributes.append(HeroAttributes.TENACIOUS)
    fox.listeners = [l for l in fox.listeners if getattr(l, "_tag", "") != _LINGHU_TAG]
    l = Listener("morph leave",
                 lambda e, h: e.event.morph_id == LingHuZhiSi.id,
                 (_linghuzhisi_leave,))
    l._tag = _LINGHU_TAG
    fox.listeners.append(l)


class LingHuZhiSi:
    id = 349
    type = "morph"
    hero = "YuanJiuLangHu"
    name = "灵狐之嗣"
    level_req = 3
    atk = 4
    hp = 4
    is_beginning_card = True
    on_play = (_linghuzhisi_on_play,)


# ── 350 道行初音旅：复活己方所有紫岩式神。本局游戏每个己方回合结束时，
#    己方所有紫岩式神永久获得+1力量和+1生命。（此效果可以叠加，对气绝式神有效）──

def _daoxing_turn_end(e, p):
    # 永久 +1/+1：get_permanent_buff 对气绝式神也生效（perm_buff 累计，
    # 复活时 hp=current_max_hp，faq）；多张副本各挂一份监听即「可以叠加」。
    for h in p.heroes:
        if h.type == "earth":
            h.get_permanent_buff("atk", 1)
            h.get_permanent_buff("hp", 1)


def _daoxing_on_play(s):
    p = s.owner
    g = p.game
    # 复活己方所有紫岩式神（只复活气绝的：revive case 对非死亡目标打日志，
    # 桃华灼灼同款过滤）
    g.handle_event(Revive(s, [h for h in p.heroes
                              if h.type == "earth" and not h.is_alive]))
    # 本局每个己方回合结束时生效：玩家级监听常驻（end turn before 时
    # current_player 仍是结束回合的玩家，燕子安贝式）；同一实例重复打出
    # （弹回回手再打出）按实例去重，多张副本各自挂一份。
    p.listeners = [l for l in p.listeners if getattr(l, "_daoxing_card", None) is not s]
    l = Listener("end turn",
                 lambda e, s2: s2.game.current_player is s2,
                 (_daoxing_turn_end,))
    l._daoxing_card = s
    p.listeners.append(l)


class DaoXingChuYinLv:
    id = 350
    type = "spell"
    hero = "YuanJiuLangHu"
    name = "道行初音旅"
    level_req = 3
    is_beginning_card = True
    on_play = (_daoxing_on_play,)
