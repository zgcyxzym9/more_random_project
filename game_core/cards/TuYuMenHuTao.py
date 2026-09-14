"""土御门胡桃（TuYuMenHuTao）专属卡牌

数据来源：tmp_cards_json/TuYuMenHuTao.json + TuYuMenHuTao.sources.md（8fe/萌娘百科/gamedog/TapTap 交叉核实）。
数值（勾玉/身材/幻境耐久）与 game_core/cards/cards.json 一致。

实现说明：
- 土御门胡桃基础能力（出击时若有气绝式神，倒计时-1 且本次攻击不造成战斗伤害）在 heroes.py 中实现。
- 「落物堆物品」（10 种，id 310-319）/「飓风客物品」（12 种，id 320-331）明细由用户提供，
  见文件末物品 Token 区块。「效果翻倍」实现为档位切换（回合不足只随机低档物品）；
  「随机三选一」暂以均匀随机选一近似（等 env「选择卡牌」操作后接入，见 LuoWuDui/JuFengKe 的 TODO）。
- 「蓄力」引擎机制已实现（CardAttributes.CHARGE + hero.charging_card + player.charging_order），
  身势·振刀的蓄力→消灭分支据此判定；当前卡池尚无带蓄力的卡牌，蓄力状态需测试/未来卡牌构造。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


def _tuyu(owner):
    return next((h for h in owner.heroes if h.type_name == "TuYuMenHuTao"), None)


def _attack_target(evt):
    """解析一次式神攻击的目标（与 game._resolve_attack_target 逻辑一致）。

    step 路径广播的 hero attack 已挂载 action.target；handle_event 直接广播时
    target 为空，此处按追击/直击/战斗区/牌手顺序重新解析。
    """
    t = getattr(evt, "target", None)
    if t is not None:
        return t
    hero = evt.hero
    player = hero.owner
    if HeroAttributes.HUNTING in hero.attributes:
        return player.selected_targets[0] if player.selected_targets else None
    if HeroAttributes.DIRECT_ATTACK in hero.attributes:
        return player.opponent
    return player.opponent.attack_zone if player.opponent.attack_zone is not None else player.opponent


# ── 1勾 ────────────────────────────────────────────────────────────────────

class BiHu:
    """庇护：进场时选择一个己方式神（可选择气绝式神）。进场和己方回合开始时，
    恢复所选择的式神3点生命或使其气绝倒计时-1。"""
    id = 138
    type = "morph"
    hero = "TuYuMenHuTao"
    name = "庇护"
    level_req = 1
    atk = 2
    hp = 6
    require_target = (lambda s: s.owner.heroes,)
    select_target = (lambda s: select_target(s.owner, s.owner.heroes, s),)
    on_play = (lambda s: _bihu_on_play(s),)


def _bihu_on_play(s):
    hero = _tuyu(s.owner)
    player = s.owner
    chosen = s.owner.selected_targets[0] if s.owner.selected_targets else None
    s._bihu_target = chosen
    _bihu_apply(player, s, chosen)
    if hero is None:
        return
    tag = "bihu-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]

    def cond(e, h):
        return (e.next_player is h.owner and h.morphed_id == 138
                and getattr(s, "_bihu_target", None) is not None)

    def effect(e, h):
        _bihu_apply(h.owner, s, getattr(s, "_bihu_target", None))

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    hero.listeners.append(l)


def _bihu_apply(player, card, chosen):
    if chosen is None:
        return
    if chosen.is_alive:
        player.game.handle_event(Heal(3, card, [chosen]))
    else:
        chosen.round_until_alive = max(0, chosen.round_until_alive - 1)


class RenWuZhuiJi:
    """任务·追击：随机标记一个敌方式神，该式神气绝时你抽两张牌。"""
    id = 139
    type = "spell"
    hero = "TuYuMenHuTao"
    name = "任务·追击"
    level_req = 1
    on_play = (lambda s: _renwuzhuiji_on_play(s),)


def _renwuzhuiji_on_play(s):
    player = s.owner
    opp = player.opponent
    candidates = [h for h in opp.heroes if h.is_alive and h.level > 0]
    if not candidates:
        return
    marked = random_choice(player, candidates, context="任务·追击")
    if marked is None:
        return
    player._renwuzhuiji_marked = marked
    tag = "renwuzhuiji-" + str(id(s))
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]

    def cond(e, owner):
        return getattr(e.event, "killed", None) is getattr(owner, "_renwuzhuiji_marked", None)

    def effect(e, owner):
        owner.draw()
        owner.draw()
        owner.listeners = [l for l in owner.listeners if getattr(l, "_tag", "") != tag]
        if hasattr(owner, "_renwuzhuiji_marked"):
            del owner._renwuzhuiji_marked

    l = Listener("hero kill", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


class LuoWuDui:
    """落物堆：进场和己方回合开始时，随机获得一个落物堆物品的效果。己方回合数大于等于5时，
    落物堆物品效果翻倍。

    「效果翻倍」按用户口径实现为档位切换：回合数<5 只随机普通档物品、回合数≥5 只随机
    良品档（配对见文件末 _LUOWUDUI_POOLS）。
    TODO（等 env「选择卡牌」操作，暂不修改 env）：真实流程为随机展示 3 张物品卡供玩家
    选择其一；当前引擎无该操作，暂以均匀随机选一近似（训练模式下分布与随机三选一一致；
    推理模式打印随机选中的物品）。
    """
    id = 140
    type = "illusion"
    hero = "TuYuMenHuTao"
    name = "落物堆"
    level_req = 1
    durability = 5
    on_play = (lambda s: _luowudui_on_play(s),)


def _luowudui_gain(player):
    """随机获得一个落物堆物品的效果（档位按己方回合数，见 _LUOWUDUI_POOLS）。"""
    pool = _LUOWUDUI_POOLS[1 if _self_round_count(player) >= 5 else 0]
    eng = random_choice(player, list(pool), context="落物堆物品")
    if eng is not None:
        _execute_item(player, eng)


def _luowudui_on_play(s):
    player = s.owner
    _luowudui_gain(player)
    tag = "luowudui-" + str(id(s))

    def cond(e, owner):
        return e.next_player is owner and s in owner.illusion_zone

    def effect(e, owner):
        _luowudui_gain(owner)

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


# ── 2勾 ────────────────────────────────────────────────────────────────────

class ShenShiZhenDao:
    """身势·振刀：当土御门胡桃攻击式神或被式神攻击时，运势4：对其造成3点伤害，
    若该式神处在蓄力状态，则改为消灭该式神。"""
    id = 141
    type = "morph"
    hero = "TuYuMenHuTao"
    name = "身势·振刀"
    level_req = 2
    atk = 4
    hp = 7
    on_play = (lambda s: _shenshizhendao_on_play(s),)


def _shenshizhendao_on_play(s):
    hero = _tuyu(s.owner)
    if hero is None:
        return
    tag = "shenshizhendao-" + str(id(s))
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag]

    def cond(e, h):
        if not (h.is_alive and h.morphed_id == 141):
            return False
        attacker = getattr(e.event, "hero", None)
        if attacker is None:
            return False
        if attacker is h:
            # 胡桃攻击：目标必须是式神
            return getattr(_attack_target(e.event), "entity_type", None) == "hero"
        if attacker.owner is h.owner:
            return False
        # 敌方式神攻击：目标是否为胡桃
        return _attack_target(e.event) is h

    def effect(e, h):
        evt = e.event
        if evt.hero is h:
            target = _attack_target(evt)
        else:
            target = evt.hero
        if getattr(target, "entity_type", None) != "hero" or not target.is_alive:
            return
        if h.owner.game.roll_fortune(h, 4):
            if getattr(target, "charging_card", None) is not None:
                # 目标处在蓄力状态：改为消灭（消灭模式同既有：置 0 血后走死亡结算）
                h.owner.game._last_damage_source = h
                target.hp = 0
                target.check_death()
            else:
                h.owner.game.handle_event(DealDamage(3, h, [target]))

    l = Listener("hero attack", cond, (effect,))
    l._tag = tag
    hero.listeners.append(l)


class JingTianDi:
    """净天地：进场和己方回合开始时，若此牌幻境耐久大于等于3，则恢复所有己方式神2生命，
    过量的治疗转化为护甲。否则自毁并对所有式神造成2点伤害。"""
    id = 142
    type = "illusion"
    hero = "TuYuMenHuTao"
    name = "净天地"
    level_req = 2
    durability = 6
    on_play = (lambda s: _jingtiandi_on_play(s),)


def _jingtiandi_on_play(s):
    player = s.owner
    _jingtiandi_effect(player, s)
    tag = "jingtiandi-" + str(id(s))

    def cond(e, owner):
        return e.next_player is owner and s in owner.illusion_zone

    def effect(e, owner):
        _jingtiandi_effect(owner, s)

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


def _jingtiandi_effect(player, card):
    game = player.game
    if card.durability >= 3:
        # 恢复所有己方式神2生命，过量治疗转化为护甲
        for h in player.heroes:
            if not h.is_alive or h.level == 0:
                continue
            before = h.hp
            gained = min(2, h.current_max_hp - before)
            h.hp = min(h.current_max_hp, h.hp + 2)
            excess = 2 - gained
            if excess > 0:
                h.defense += excess
    else:
        # 自毁并对所有式神造成2点伤害
        if card in player.illusion_zone:
            player.illusion_zone.remove(card)
        game.handle_event(IllusionDestroyedEvent(player, card))
        targets = [h for h in player.heroes if h.is_alive and h.level > 0]
        targets += [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
        if targets:
            game.handle_event(DealDamage(2, card, targets))


class DiShaFu:
    """地煞符：进场和己方回合开始时，随机选择一个敌方式神（包括已气绝式神），
    若该式神未气绝则对他造成4点伤害，然后降低3幻境耐久。"""
    id = 143
    type = "illusion"
    hero = "TuYuMenHuTao"
    name = "地煞符"
    level_req = 2
    durability = 7
    on_play = (lambda s: _dishafu_on_play(s),)


def _dishafu_on_play(s):
    player = s.owner
    _dishafu_effect(player, s)
    tag = "dishafu-" + str(id(s))

    def cond(e, owner):
        return e.next_player is owner and s in owner.illusion_zone

    def effect(e, owner):
        _dishafu_effect(owner, s)

    l = Listener("begin turn", cond, (effect,))
    l._tag = tag
    player.listeners.append(l)


def _dishafu_effect(player, card):
    opp = player.opponent
    candidates = opp.heroes  # 包括已气绝式神
    target = random_choice(player, candidates, context="地煞符")
    if target is None:
        return
    if target.is_alive:
        player.game.handle_event(DealDamage(4, card, [target]))
    # 降低3幻境耐久
    card.durability -= 3
    if card.durability <= 0:
        if card in player.illusion_zone:
            player.illusion_zone.remove(card)
        player.game.handle_event(IllusionDestroyedEvent(player, card))


# ── 3勾 ────────────────────────────────────────────────────────────────────

class JueXingTuYuMenHuTao:
    """觉醒·土御门胡桃：觉醒：迅捷 土御门胡桃攻击时，若己方有气绝的式神，复活所有己方气绝式神。"""
    id = 144
    type = "spell"
    hero = "TuYuMenHuTao"
    name = "觉醒·土御门胡桃"
    level_req = 3
    on_play = (lambda s: _juexingtyht_on_play(s),)


def _juexingtyht_on_play(s):
    hero = _tuyu(s.owner)
    if hero is None:
        return
    # 觉醒：永久 +2/+2（觉醒牌数值直接写在 on_play，同其它式神觉醒牌）
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)
    hero.is_awakened = True
    # 迅捷：引擎的 AGILE 在出击后被消耗，故在己方回合开始时重新授予，近似常驻迅捷
    if HeroAttributes.AGILE not in hero.attributes:
        hero.attributes.append(HeroAttributes.AGILE)
    tag_agi = "juexingtyht_agi"
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag_agi]
    l_agi = Listener("begin turn",
                     lambda e, h: e.next_player is h.owner and HeroAttributes.AGILE not in h.attributes,
                     (lambda e, h: h.attributes.append(HeroAttributes.AGILE),))
    l_agi._tag = tag_agi
    hero.listeners.append(l_agi)
    # 胡桃攻击时，若己方有气绝式神，复活所有己方气绝式神
    tag_rev = "juexingtyht_revive"
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != tag_rev]
    l_rev = Listener("hero attack",
                     lambda e, h: e.event.hero is h and any(x for x in h.owner.heroes if not x.is_alive),
                     (lambda e, h: h.owner.game.handle_event(
                         Revive(h, [x for x in h.owner.heroes if not x.is_alive])),))
    l_rev._tag = tag_rev
    hero.listeners.append(l_rev)


class JuFengKe:
    """飓风客：选择两个飓风客物品的效果。己方回合数大于等于10时，飓风客物品效果翻倍。

    「选择两个」= 执行两轮独立的「随机三选一」（用户口径：每轮随机展示 3 张物品卡
    供玩家选择其一）。档位切换：回合数<10 只随机优品档、回合数≥10 只随机极品档
    （配对见 _JUFENGKE_POOLS）；三选一 TODO 同 LuoWuDui。
    """
    id = 145
    type = "spell"
    hero = "TuYuMenHuTao"
    name = "飓风客"
    level_req = 3
    on_play = (lambda s: _jufengke_on_play(s),)


def _jufengke_on_play(s):
    player = s.owner
    pool = _JUFENGKE_POOLS[1 if _self_round_count(player) >= 10 else 0]
    for _ in range(2):
        eng = random_choice(player, list(pool), context="飓风客物品")
        if eng is not None:
            _execute_item(player, eng)


# ═══════════════════════════════════════════════════════════════════════════
#  落物堆 / 飓风客物品 Token 卡（id 310-331，明细由用户提供）
#
#  每种物品一张卡，中立 Token（hero=""、is_token，不入卡池/卡组，与食材/佳肴同
#  惯例）。物品由 LuoWuDui / JuFengKe 随机选中后经 _execute_item 直接执行
#  on_play：不经 play_card（不扣鬼火、不广播 "play card"，与涅槃业火自动使用的
#  口径一致）；效果目标全部自动指定（随机单体/全体/投射/胡桃攻击/治疗牌手），
#  不进入目标选择流程。eng_name 为项目自拟拼音（游戏内物品无官方英文名）。
# ═══════════════════════════════════════════════════════════════════════════

def _self_round_count(player):
    """当前是己方第几个回合（1 起）。

    game.turn_count 在 "begin turn" 广播中尚未自增、回合内出牌阶段已自增。
    先手第 n 个己方回合 = 全局第 2n-1 回合、后手第 n 个 = 全局第 2n 回合；
    下式对两种时机（turn_count = 全局当前回合号 或 其减一）结果一致。
    """
    tc = player.game.turn_count
    return (tc + 2) // 2 if player.is_first_player else (tc + 1) // 2


def _execute_item(player, eng_name):
    """实例化物品 Token 卡并执行其效果（LuoWuDui / JuFengKe 选中后调用）。"""
    from game_core.card import Card
    item = Card.GetCard(eng_name)
    item.assign_owner(player)
    for f in item.on_play:
        f(item)


def _friendly_field(player):
    """存活且已上场的己方式神（同净天地「所有己方式神」口径，不含气绝）。"""
    return [h for h in player.heroes if h.is_alive and h.level > 0]


def _buff_random_hero(attr, value):
    """使一个随机存活己方式神获得 attr +value（武器/护甲·普通/良品）。"""
    def _play(s):
        player = s.owner
        target = random_choice(player, _friendly_field(player), context=s.name)
        if target is not None:
            player.game.handle_event(GiveBuff(attr, value, s, [target]))
    return (_play,)


def _heal_player(value):
    """为你恢复 value 生命（凝血丸/大包凝血丸/返魂符）。"""
    def _play(s):
        s.owner.game.handle_event(Heal(value, s, [s.owner]))
    return (_play,)


def _defense_all(value):
    """所有己方角色（牌手 + 存活己方式神）获得 value 护甲（护甲粉末系）。"""
    def _play(s):
        player = s.owner
        player.game.handle_event(
            GiveBuff("defense", value, s, _friendly_field(player) + [player]))
    return (_play,)


def _divination(n):
    """占卜 n（武备匣/飞索线轴）。

    TODO（需引擎支持，等审批）：占卜（检视牌库顶 n 张并以任意顺序置于牌库顶/底）
    为玩家主动操作流程，引擎与 env 均未实现，暂无效果。按用户口径「占卜在敌方
    回合触发视为不生效」——落物堆/飓风客均在己方回合触发，该限定天然满足；
    机制实装后在此接入。
    """
    def _play(s):
        pass
    return (_play,)


def _damage_all_enemies(dmg):
    """对所有敌方式神造成 dmg 点伤害（喷火筒）。"""
    def _play(s):
        targets = [h for h in s.owner.opponent.heroes if h.is_alive and h.level > 0]
        if targets:
            s.owner.game.handle_event(DealDamage(dmg, s, targets))
    return (_play,)


def _projectile_repeat(times):
    """投射：造成1点伤害，重复 times 次（一窝蜂）。

    每次投射独立解析目标：敌方战斗区式神优先，无则敌方牌手；
    战斗区式神被消灭后，后续投射改打敌方牌手。
    """
    def _play(s):
        player = s.owner
        opp = player.opponent
        for _ in range(times):
            target = (opp.attack_zone
                      if opp.attack_zone is not None and opp.attack_zone.is_alive
                      else opp)
            player.game.handle_event(ProjectileEvent(1, s, [target]))
    return (_play,)


def _tuyu_attack(bonus):
    """土御门胡桃发起一次攻击，本次攻击获得 +bonus 力量，并免疫战斗伤害（万刃轮）。

    走 handle_event(HeroAttackEvent) 标准攻击路径（先入战斗区/目标解析/结算，
    同兄弟之忆）；+bonus 折入独立变量 combat_buff_atk（战斗结算经
    _get_attack_power 读取），战斗后清空——胡桃中途气绝时 check_death 同样
    只清零该变量，不再与战后回退叠加出幽灵数值。
    免疫战斗伤害用临时监听器（战斗伤害经 "deal damage" 广播，immune_targets 拦截）。
    胡桃未登场（level 0）/气绝时无法发起攻击，效果不生效。
    """
    def _play(s):
        hero = _tuyu(s.owner)
        if hero is None or not hero.is_alive or hero.level == 0:
            return
        player = s.owner
        hero.combat_buff_atk += bonus
        clear_combat_immune(hero)  # 去重
        hero.listeners.append(make_combat_immune_listener())
        player.game.handle_event(HeroAttackEvent(player, hero, s))
        clear_combat_immune(hero)
        hero.combat_buff_atk = 0
    return (_play,)


def _perm_all(field, value):
    """使所有存活己方式神永久获得 value 点 field（护甲/武器·优品/极品）。"""
    def _play(s):
        for h in _friendly_field(s.owner):
            h.get_permanent_buff(field, value)
    return (_play,)


def _make_item(cls_name, id_, name, effects):
    """生成一个物品 Token 卡类。"""
    return type(cls_name, (), {
        "id": id_,
        "type": "spell",
        "hero": "",           # 中立 Token：不属于任何式神
        "name": name,
        "level_req": 1,
        "is_token": True,
        "on_play": effects,
    })


# ── 落物堆物品（低档=普通 / 高档=良品） ─────────────────────────────────────
WuQiPuTong = _make_item("WuQiPuTong", 310, "武器·普通", _buff_random_hero("atk", 1))
WuQiLiangPin = _make_item("WuQiLiangPin", 311, "武器·良品", _buff_random_hero("atk", 2))
HuJiaPuTong = _make_item("HuJiaPuTong", 312, "护甲·普通", _buff_random_hero("hp", 1))
HuJiaLiangPin = _make_item("HuJiaLiangPin", 313, "护甲·良品", _buff_random_hero("hp", 2))
NingXueWan = _make_item("NingXueWan", 314, "凝血丸", _heal_player(2))
DaBaoNingXueWan = _make_item("DaBaoNingXueWan", 315, "大包凝血丸", _heal_player(4))
HuJiaFenMo = _make_item("HuJiaFenMo", 316, "护甲粉末", _defense_all(1))
GaoJiHuJiaFenMo = _make_item("GaoJiHuJiaFenMo", 317, "高级护甲粉末", _defense_all(2))
WuBeiXia = _make_item("WuBeiXia", 318, "武备匣", _divination(1))
FeiSuoXianZhou = _make_item("FeiSuoXianZhou", 319, "飞索线轴", _divination(2))

# ── 飓风客物品（低档=优品 / 高档=极品） ─────────────────────────────────────
PenHuoTongYouPin = _make_item("PenHuoTongYouPin", 320, "喷火筒·优品", _damage_all_enemies(2))
PenHuoTongJiPin = _make_item("PenHuoTongJiPin", 321, "喷火筒·极品", _damage_all_enemies(4))
YiWoFengYouPin = _make_item("YiWoFengYouPin", 322, "一窝蜂·优品", _projectile_repeat(5))
YiWoFengJiPin = _make_item("YiWoFengJiPin", 323, "一窝蜂·极品", _projectile_repeat(10))
WanRenLunYouPin = _make_item("WanRenLunYouPin", 324, "万刃轮·优品", _tuyu_attack(3))
WanRenLunJiPin = _make_item("WanRenLunJiPin", 325, "万刃轮·极品", _tuyu_attack(6))
HuJiaYouPin = _make_item("HuJiaYouPin", 326, "护甲·优品", _perm_all("hp", 3))
HuJiaJiPin = _make_item("HuJiaJiPin", 327, "护甲·极品", _perm_all("hp", 6))
WuQiYouPin = _make_item("WuQiYouPin", 328, "武器·优品", _perm_all("atk", 2))
WuQiJiPin = _make_item("WuQiJiPin", 329, "武器·极品", _perm_all("atk", 4))
FanHunFu = _make_item("FanHunFu", 330, "返魂符", _heal_player(6))
FanHunFuZengQiang = _make_item("FanHunFuZengQiang", 331, "返魂符（已增强）", _heal_player(12))


# 物品配对池：[低档, 高档]，下标 = 翻倍条件是否满足（1 为真）。
# 落物堆：己方回合数≥5 用良品档；飓风客：己方回合数≥10 用极品档（用户口径）。
_LUOWUDUI_POOLS = (
    ("WuQiPuTong", "HuJiaPuTong", "NingXueWan", "HuJiaFenMo", "WuBeiXia"),
    ("WuQiLiangPin", "HuJiaLiangPin", "DaBaoNingXueWan", "GaoJiHuJiaFenMo", "FeiSuoXianZhou"),
)
_JUFENGKE_POOLS = (
    ("PenHuoTongYouPin", "YiWoFengYouPin", "WanRenLunYouPin",
     "HuJiaYouPin", "WuQiYouPin", "FanHunFu"),
    ("PenHuoTongJiPin", "YiWoFengJiPin", "WanRenLunJiPin",
     "HuJiaJiPin", "WuQiJiPin", "FanHunFuZengQiang"),
)
