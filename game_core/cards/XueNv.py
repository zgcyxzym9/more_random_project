"""雪女卡牌（id 359-369）。

牌面文本以 cards.json 条目（359-369）为准。式神段（基础能力每回合一次雪球/
觉醒被动眩晕受伤式神）与召唤物冰墙（heroes.py BingQiang，与卡牌类同名——
Card.GetCard 与 Hero.GetHero 分属 card/hero 两个命名空间，互不冲突）在
heroes.py 雪女段；本文件实现卡牌打出侧逻辑。

口径与裁决记录（用户 2026-10-22，除注明外）：
- 雪球（雪女专属卡，非衍生 token；黄金羽同类：非免式神、受式神在场/等级门槛、
  用后进弃牌堆）：瞬发，对一个敌方式神造成1点伤害（排除帷幕）。打出时累计
  「本局从手牌使用过的雪球数」（xuenv_snowball_played_total，流霰重复口径）。
- 寒冬之心：+1 伤害可叠加（裁决 2）：雪女 hero.counters 持久计数，作用于
  所有「雪球」（含流霰的虚拟雪球）。
- 寒冰之盾：+2 护甲 +「本回合眩晕受到其战斗伤害的式神」——目标身上挂
  reset_per_turn 计数器（下个任意回合开始过期 =「本回合」）+ tagged 监听
  （damage dealt combat 通道仅实际伤害>0 时广播 → 护甲全吸不触发，冰风暴
  裁决1a同口径）；监听只挂运行时 listeners，目标气绝随死亡重置自然脱落。
  响应走引擎新机制（古尘之盾同款）：trigger "hero attack"、phase before
  （先上盾再结算本次攻击），条件=受击目标为我方战斗区式神（敌方攻击冰墙
  时正常触发，裁决 3）；on_response 先于 play_card 把响应目标写入
  selected_targets 供 on_play 使用（「自动对其使用」）。
- 吹雪：3点伤害目标=敌方角色（式神+牌手，裁决 2）。
- 冰墙卡：召唤走引擎 SummonEvent 通道（战斗区替换语义）；裁决 3/4 天然
  满足——进场不广播任何攻击事件，被攻击走正常战斗+响应流程。
- 崩雪：目标双方均可选（裁决 4，己方不受帷幕限制）；目标已眩晕→直接消灭
  （判官夺命同款，尊重尘缚之阵直接消灭免疫），未眩晕→眩晕（事件通道）。
- 觉醒·雪女：先设置被动（+2/+1、is_awakened）再造成3点伤害（裁决 5b，
  本次3点伤害即受新被动约束）。
- 流霰：虚拟结算（裁决 3）——不消耗手牌雪球、不广播使用牌事件、不计入
  xuenv_snowball_played_total；手牌无雪球也可打出；总命中次数 = 打出时
  xuenv_snowball_played_total + 1，每次独立 DealDamage（分别过护甲），
  目标=敌方角色（式神+牌手）。
- 冰霜永冻（协战）：选项按打出式神分支；雪童子-雪刃未实现（刃影鹤唳先例
  pass+TODO）。冰封的羁绊按 faq 协战羁绊门控（另一位协战式神存活且等级
  不为 0），防御式查找当前永不满足。
"""

from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener


# ── 目标与通用辅助 ──────────────────────────────────────────────────────────

def _xn_enemy_hero_targets(s):
    """敌方存活已升级式神，排除帷幕（帷幕：不能被敌方卡牌选为目标，判官同款）。"""
    return [h for h in s.owner.opponent.heroes
            if h.is_alive and h.level > 0
            and HeroAttributes.VEIL not in h.attributes]


def _xn_enemy_char_targets(s):
    """敌方角色：敌方式神 + 敌方牌手（用户裁决 2/3a）。"""
    return _xn_enemy_hero_targets(s) + [s.owner.opponent]


def _xn_friendly_hero_targets(s):
    return [h for h in s.owner.heroes if h.is_alive and h.level > 0]


def _xn_snowball_bonus(hero):
    """寒冬之心叠加的雪球伤害加成（本局游戏，可叠加，用户裁决 2）。"""
    if hero is None:
        return 0
    return hero.counters.get("xuenv_snowball_bonus", 0)


def _xn_give_xueqiu(s, n=1):
    s.owner.GiveCardToHand(["XueQiu"] * n)


def _xn_destroy(s, target):
    """直接消灭并归属雪女（判官夺命同款：尊重尘缚之阵直接消灭免疫）。"""
    if target is None or target.state == "dead":
        return
    game = s.owner.game
    if game._direct_destroy_immune(target):
        return
    hero = s.get_corresponding_hero()
    game._last_damage_source = hero
    target._last_damage_from = hero
    target.hp = 0
    game.resolve_deaths([target])


# ── 359 雪球 ────────────────────────────────────────────────────────────────

def _xueqiu_on_play(s):
    # 累计「本局从手牌使用过的雪球数」（流霰重复次数口径，用户裁决 3）；
    # 流霰的虚拟使用不经此处、不计入。
    hero = s.get_corresponding_hero()
    if hero is not None:
        hero.counters.ensure("xuenv_snowball_played_total",
                             initial=0, persistent=True)
        hero.counters.inc("xuenv_snowball_played_total")
    return DealDamage(1 + _xn_snowball_bonus(hero), s, s.owner.selected_targets)


class XueQiu:
    """雪球：瞬发 对一个敌方式神造成1点伤害。

    雪女专属卡（黄金羽同类，用户裁决 2026-10-22）：非 token——受式神在场/
    等级门槛约束，使用后进弃牌堆。
    """
    id = 359
    type = "spell"
    hero = "XueNv"
    name = "雪球"
    level_req = 1
    is_beginning_card = False
    attributes = (CardAttributes.INSTANT,)
    require_target = (lambda s: _xn_enemy_hero_targets(s),)
    select_target = (lambda s: select_target(s.owner, _xn_enemy_hero_targets(s), s),)
    on_play = (_xueqiu_on_play,)


# ── 360 寒冰之盾 ───────────────────────────────────────────────────────────

def _hbzd_stun_cond(e, s):
    # s=受盾式神：其造成的战斗伤害（combat 通道仅实际伤害>0 时广播，
    # 护甲全吸/免疫不触发）；「本回合」由 reset_per_turn 计数器保证
    return (s.counters.get("hbzd_stun_this_turn", 0) > 0
            and e.event.source is s
            and getattr(e.event, "damage_type", None) == "combat")


def _hbzd_stun_effect(e, s):
    for t in e.event.target:
        if getattr(t, "entity_type", None) == "hero" and t.is_alive:
            s.owner.game.handle_event(StunEvent(t, True))


def _hbzd_response(card, src, target):
    # 响应目标注入：on_response 先于 play_card 执行（引擎 _play_response_card
    # 顺序），把「被攻击的我方战斗区式神」交给 on_play（自动对其使用）
    if target is not None:
        card.owner.selected_targets = [target]


def _hbzd_on_play(s):
    target = s.owner.selected_targets[0]
    target.defense += 2
    # 「本回合」标记：reset_per_turn 计数器，下个任意回合开始自动过期；
    # persistent 使气绝 reset_all 不清零（同回合计数语义不受影响）
    target.counters.ensure("hbzd_stun_this_turn", initial=0,
                           persistent=True, reset_per_turn=True)
    target.counters.set("hbzd_stun_this_turn", 1)
    # tagged 监听只挂运行时 listeners：目标气绝即随死亡重置脱落（盾随气绝丢失）；
    # 先摘后挂保证重复施加幂等
    target.listeners = [l for l in target.listeners
                        if getattr(l, "_tag", "") != "hbzd_stun"]
    l = Listener("damage dealt", _hbzd_stun_cond, (_hbzd_stun_effect,))
    l._tag = "hbzd_stun"
    target.listeners.append(l)


class HanBingZhiDun:
    """寒冰之盾：使一个己方式神获得2点护甲且本回合获得「眩晕受到其战斗伤害的
    式神。」响应：当你战斗区式神被攻击时，自动对其使用。

    响应走引擎新机制（古尘之盾同款）：phase before，先上盾再结算本次攻击；
    敌方攻击冰墙（召唤物占战斗区）时同样触发（裁决 3）。
    """
    id = 360
    type = "spell"
    hero = "XueNv"
    name = "寒冰之盾"
    level_req = 1
    is_beginning_card = True
    require_target = (lambda s: _xn_friendly_hero_targets(s),)
    select_target = (lambda s: select_target(s.owner, _xn_friendly_hero_targets(s), s),)
    response_trigger = "hero attack"
    response_condition = (lambda card, src, target:
                          target is not None
                          and getattr(target, "owner", None) is card.owner
                          and card.owner.attack_zone is target,)
    on_response = (_hbzd_response,)
    on_play = (_hbzd_on_play,)


# ── 361 吹雪 ───────────────────────────────────────────────────────────────

def _chuixue_on_play(s):
    s.owner.game.handle_event(DealDamage(3, s, s.owner.selected_targets))
    _xn_give_xueqiu(s)


class ChuiXue:
    """吹雪：造成3点伤害（敌方角色，含牌手），将一张「雪球」置入手牌。"""
    id = 361
    type = "spell"
    hero = "XueNv"
    name = "吹雪"
    level_req = 1
    is_beginning_card = True
    require_target = (lambda s: _xn_enemy_char_targets(s),)
    select_target = (lambda s: select_target(s.owner, _xn_enemy_char_targets(s), s),)
    on_play = (_chuixue_on_play,)


# ── 362 冰墙（卡牌；召唤物在 heroes.py 冰墙段，同名不同命名空间） ─────────────

def _bingqiang_card_on_play(s):
    # 召唤走引擎通道：level=1、is_summoned、move_to_battle 替换语义
    # （裁决 3/4 天然满足：进场不广播攻击事件，被攻击走正常战斗+响应）
    s.owner.game.handle_event(SummonEvent(s.owner, "BingQiang"))


class BingQiang:
    """冰墙：在战斗区召唤一个冰墙。"""
    id = 362
    type = "spell"
    hero = "XueNv"
    name = "冰墙"
    level_req = 1
    is_beginning_card = True
    on_play = (_bingqiang_card_on_play,)


# ── 363 崩雪 ───────────────────────────────────────────────────────────────

def _bengxue_targets(s):
    # 双方均可选（用户裁决 4）；己方不受帷幕限制（帷幕只防敌方选目标）
    return _xn_friendly_hero_targets(s) + _xn_enemy_hero_targets(s)


def _bengxue_on_play(s):
    target = s.owner.selected_targets[0]
    if target.stunned:
        _xn_destroy(s, target)
    else:
        s.owner.game.handle_event(StunEvent(target, True))


class BengXue:
    """崩雪：消灭一个眩晕的式神或眩晕一个未眩晕的式神（双方均可选）。"""
    id = 363
    type = "spell"
    hero = "XueNv"
    name = "崩雪"
    level_req = 2
    is_beginning_card = True
    require_target = (lambda s: _bengxue_targets(s),)
    select_target = (lambda s: select_target(s.owner, _bengxue_targets(s), s),)
    on_play = (_bengxue_on_play,)


# ── 364 冰风暴（形态；持续效果在 heroes.py 雪女段，morphed_id==364 门控） ────

class BingFengBao:
    """冰风暴（形态 3/5）：每当敌方式神攻击后，对其造成1点伤害，然后眩晕
    受到此伤害的式神。"""
    id = 364
    type = "morph"
    hero = "XueNv"
    name = "冰风暴"
    level_req = 2
    atk = 3
    hp = 5
    is_beginning_card = True


# ── 365 寒冬之心 ───────────────────────────────────────────────────────────

def _hdzx_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is not None:
        hero.counters.ensure("xuenv_snowball_bonus", initial=0, persistent=True)
        hero.counters.inc("xuenv_snowball_bonus")   # 可叠加（用户裁决 2）
    _xn_give_xueqiu(s, 2)


class HanDongZhiXin:
    """寒冬之心：将两张「雪球」置入手牌。本局游戏你所有「雪球」的伤害+1。"""
    id = 365
    type = "spell"
    hero = "XueNv"
    name = "寒冬之心"
    level_req = 2
    is_beginning_card = True
    on_play = (_hdzx_on_play,)


# ── 366 觉醒·雪女 ──────────────────────────────────────────────────────────

def _juexing_xuenv_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 1)
    # 裁决 5b：先设置被动再结算伤害（本次3点伤害即受新被动约束）
    hero.is_awakened = True
    s.owner.game.handle_event(DealDamage(3, s, s.owner.selected_targets))


class JueXingXueNv:
    """觉醒·雪女：对一个敌方式神造成3点伤害。觉醒：眩晕受到雪女伤害的式神
    （heroes.py 雪女段监听，is_awakened 门控）。每回合一次，当你眩晕敌方式神
    时，将一张「雪球」置入手牌。"""
    id = 366
    type = "spell"
    hero = "XueNv"
    name = "觉醒·雪女"
    level_req = 3
    is_beginning_card = True
    require_target = (lambda s: _xn_enemy_hero_targets(s),)
    select_target = (lambda s: select_target(s.owner, _xn_enemy_hero_targets(s), s),)
    on_play = (_juexing_xuenv_on_play,)


# ── 367 流霰 ───────────────────────────────────────────────────────────────

def _liuxian_on_play(s):
    target = s.owner.selected_targets[0]
    game = s.owner.game
    hero = s.get_corresponding_hero()
    # 虚拟结算（用户裁决 3）：不消耗手牌雪球、不计入 played_total；
    # 总次数 = 打出时已从手牌使用过的雪球总数 + 1；每次独立 DealDamage
    #（分别过护甲/免疫），目标已死由引擎分支跳过
    dmg = 1 + _xn_snowball_bonus(hero)
    hits = 1
    if hero is not None:
        hits += hero.counters.get("xuenv_snowball_played_total", 0)
    for _ in range(hits):
        game.handle_event(DealDamage(dmg, s, [target]))


class LiuXian:
    """流霰：对一个敌方角色使用一张「雪球」，本局游戏你每从手牌使用过一张
    「雪球」额外重复一次。"""
    id = 367
    type = "spell"
    hero = "XueNv"
    name = "流霰"
    level_req = 3
    is_beginning_card = True
    require_target = (lambda s: _xn_enemy_char_targets(s),)
    select_target = (lambda s: select_target(s.owner, _xn_enemy_char_targets(s), s),)
    on_play = (_liuxian_on_play,)


# ── 368 冰霜永冻（协战） / 369 冰封 ────────────────────────────────────────

def _bingfeng_core(s):
    """冰封效果（独立打出，或经协战牌冰霜永冻选择「雪女-冰封」）。"""
    target = s.owner.selected_targets[0]
    s.owner.game.handle_event(StunEvent(target, True))
    _xn_give_xueqiu(s)
    # 羁绊：雪童子对其发动一次攻击（faq 协战羁绊：另一位协战式神存活且等级
    # 不为 0；雪童子未实现——防御式查找，永不满足，刃影叠岚先例）
    xtz = next((h for h in s.owner.heroes if h.type_name == "XueTongZi"), None)
    if xtz is not None and xtz.is_alive and xtz.level > 0:
        pass  # TODO（待雪童子实现）：令雪童子对 target 发动一次攻击


def _bingfeng_on_play(s):
    _bingfeng_core(s)


class BingFeng:
    """冰封：眩晕一个敌方式神，获得一张「雪球」。羁绊：雪童子对其发动一次攻击。"""
    id = 369
    type = "spell"
    hero = "XueNv"
    name = "冰封"
    level_req = 1
    is_beginning_card = False
    require_target = (lambda s: _xn_enemy_hero_targets(s),)
    select_target = (lambda s: select_target(s.owner, _xn_enemy_hero_targets(s), s),)
    on_play = (_bingfeng_on_play,)


def _bingshuang_on_play(s):
    """选择使用一项：雪女-冰封；雪童子-雪刃。"""
    hero = s.played_by if s.played_by is not None else s.get_corresponding_hero()
    if hero is None:
        return
    if hero.type_name == "XueNv":
        # 雪女-冰封：选项牌目标走自动选择（鸿运当头自动打出同款：
        # 快照/还原牌手选择状态，random_choice 推理由玩家手选/训练走 rng）
        owner = s.owner
        prev_selected, prev_state = owner.selected_targets, owner.state
        owner.selected_targets = None
        candidates = _xn_enemy_hero_targets(s)
        if candidates:
            picked = random_choice(owner, candidates,
                                   context="冰霜永冻: 冰封 选择目标")
            owner.selected_targets = [picked] if picked is not None else None
        owner.candidate_targets = []
        owner.pending_card = None
        owner.state = prev_state
        _bingfeng_core(s)
        owner.selected_targets = prev_selected
    elif hero.type_name == "XueTongZi":
        # 雪童子-雪刃：雪童子未实现，TODO（待雪童子实现后完成）
        pass


class BingShuangYongDong:
    """冰霜永冻（协战）：选择使用一项：雪女-冰封；雪童子-雪刃。"""
    id = 368
    type = "coop"
    hero = "XueNv"
    heroes = ["XueNv", "XueTongZi"]
    name = "冰霜永冻"
    level_req = 1
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner,
        [h for h in s.owner.heroes
         if h.type_name in s.heroes and h.is_alive
         and h.level >= s.level_req and not h.stunned],
        s),)
    on_play = (_bingshuang_on_play,)
