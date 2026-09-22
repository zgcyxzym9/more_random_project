import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# ═══════════════════════════════════════════════════════════════════════════════
#  辉夜姬 (HuiYeJi) — 青岚派系，8 张专属卡牌（id 114-121）
#
#  幻境能力叠加约定：辉夜姬同时只能持有一个辉夜姬幻境（heroes.py 合并监听器）。
#  未觉醒时，只有当前驻场幻境的能力生效（旧幻境被替换后失效）；
#  觉醒后，被合并吸收的旧幻境能力随耐久一起叠加到新幻境上（能力叠加）。
#  _hyj_active(player, card) 判定某张幻境卡的能力是否生效。
# ═══════════════════════════════════════════════════════════════════════════════

_HYJ_ILLUSION_NAMES = ("YanZiAnBei", "HuoShuQiu", "FoQianShiBo", "LongShouZhiYu", "PengLaiYuZhi")


def _hyj_hero(player):
    for h in player.heroes:
        if h.type_name == "HuiYeJi":
            return h
    return None


def _hyj_zone_illusion(player):
    """幻境区中当前辉夜姬幻境（合并后至多一个）。"""
    for ill in player.illusion_zone:
        if getattr(ill, "hero", None) == "HuiYeJi":
            return ill
    return None


def _hyj_durability(player):
    """辉夜姬幻境总耐久（合并时耐久已叠加到驻场幻境上）。"""
    total = 0
    for ill in player.illusion_zone:
        if getattr(ill, "hero", None) == "HuiYeJi":
            total += getattr(ill, "durability", 0)
    return total


def _hyj_active(player, card):
    """该辉夜姬幻境卡的能力是否生效：驻场，或觉醒后被合并吸收叠加到当前幻境上。"""
    if card in player.illusion_zone:
        return True
    hero = _hyj_hero(player)
    if hero is not None and hero.is_awakened:
        cur = _hyj_zone_illusion(player)
        if cur is not None and card in getattr(cur, "absorbed", []):
            return True
    return False


def _hyj_summoned_count(player):
    """本局已召唤的不同辉夜姬幻境种类数（觉醒·辉夜姬增强条件）。"""
    return len(getattr(player, "_hyj_summoned", ()))


def _distinct_deck_illusions(player):
    """牌库中辉夜姬幻境各不同名的第一个实例（五道难题选择候选 / 增强判定）。"""
    seen = []
    names = set()
    for c in player.deck:
        if c.eng_name in _HYJ_ILLUSION_NAMES and c.eng_name not in names:
            names.add(c.eng_name)
            seen.append(c)
    return seen


def _fresh_hyj_illusions(player):
    """五种辉夜姬幻境的独立新实例（觉醒·辉夜姬选择候选）。"""
    from game_core.card import Card
    cards = []
    for name in _HYJ_ILLUSION_NAMES:
        cards.append(Card.GetCard(name).assign_owner(player))
    return cards


def _summon_hyj_illusion(player, eng_name, durability):
    """召唤一个辉夜姬幻境：跑 on_play → 入幻境区 → 广播 IllusionPlayedEvent（触发合并）。"""
    from game_core.card import Card
    card = Card.GetCard(eng_name).assign_owner(player)
    card.durability = durability
    if hasattr(card, "on_play"):
        for cb in card.on_play:
            result = cb(card)
            if isinstance(result, Event):
                player.game.handle_event(result)
    player.illusion_zone.append(card)
    player.game.handle_event(IllusionPlayedEvent(player, card))
    return card


# ═══════════════════════════════════════════════════════════════════════════════
#  114 燕子安贝 (YanZiAnBei)
#  自己回合结束时，使己方所有角色各回复1生命，使所有其他己方幻境各获得1耐久。
#  若此牌耐久≥10，敌方回合结束时，再触发上述效果。
# ═══════════════════════════════════════════════════════════════════════════════

def _yanzianbei_on_play(s):
    player = s.owner
    card = s
    l_own = Listener("end turn",
                     lambda e, s2: _hyj_active(s2, card) and s2.game.current_player is s2,
                     (lambda e, s2: _yanzianbei_effect(s2, card),))
    l_own._tag = "yanzianbei-own"
    l_enh = Listener("end turn",
                     lambda e, s2: _hyj_active(s2, card) and s2.game.current_player is not s2
                                   and _hyj_durability(s2) >= 10,
                     (lambda e, s2: _yanzianbei_effect(s2, card),))
    l_enh._tag = "yanzianbei-enemy"
    player.listeners.append(l_own)
    player.listeners.append(l_enh)


def _yanzianbei_effect(s, card):
    # 使己方所有角色各回复1生命（牌手 + 存活式神）
    targets = [s] + [h for h in s.heroes if h.is_alive]
    s.game.handle_event(Heal(1, card, targets))
    # 使所有其他己方幻境各获得1耐久（辉夜姬合并幻境视为「此牌」，不计入）
    for ill in list(s.illusion_zone):
        if getattr(ill, "hero", None) != "HuiYeJi":
            s.game.gain_illusion_durability(ill, 1)


class YanZiAnBei:
    id = 114
    type = "illusion"
    hero = "HuiYeJi"
    name = "燕子安贝"
    level_req = 1
    durability = 5
    on_play = (lambda s: _yanzianbei_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  115 火鼠裘 (HuoShuQiu)
#  当敌方式神对你造成战斗伤害时，他受到2点伤害。
#  若此牌耐久≥10，当敌方式神对你的式神造成战斗伤害时，他受到1点伤害。
# ═══════════════════════════════════════════════════════════════════════════════

def _huoshuqiu_on_play(s):
    player = s.owner
    card = s
    l = Listener("damage dealt",
                 lambda e, s2: _hyj_active(s2, card)
                               and getattr(e.event, "damage_type", None) == "combat"
                               and getattr(e.event.source, "owner", None) is not None
                               and getattr(e.event.source, "owner", None) is not s2,
                 (lambda e, s2: _huoshuqiu_effect(e, s2, card),))
    l._tag = "huoshuqiu"
    player.listeners.append(l)


def _huoshuqiu_effect(e, s, card):
    ev = e.event
    src = ev.source
    # damage dealt 的 target 恒为列表（战斗单目标为 [victim]）
    tgt = ev.target[0] if ev.target else None
    if tgt is s:
        # 敌方式神对你造成战斗伤害 → 他受到2点伤害
        s.game.handle_event(DealDamage(2, card, [src]))
    elif getattr(tgt, "owner", None) is s and _hyj_durability(s) >= 10:
        # 耐久≥10：敌方式神对你的式神造成战斗伤害 → 他受到1点伤害
        s.game.handle_event(DealDamage(1, card, [src]))


class HuoShuQiu:
    id = 115
    type = "illusion"
    hero = "HuiYeJi"
    name = "火鼠裘"
    level_req = 1
    durability = 5
    on_play = (lambda s: _huoshuqiu_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  116 五道难题 (WuDaoNanTi)
#  从你牌库选择一张辉夜姬的幻境牌置入手牌并使其获得5耐久，然后洗牌库。
#  增强：若你牌库有辉夜姬的五种不同名幻境牌，此牌获得瞬发。
# ═══════════════════════════════════════════════════════════════════════════════

def _wudao_on_play(s):
    player = s.owner
    game = player.game
    if player.selected_targets:
        sel = player.selected_targets[0]
        game.handle_event(DrawSelectedCardFromDeck(player, sel))
        game.gain_illusion_durability(sel, 5)
    # 然后洗牌库（集中化 RNG，保证可复现）
    game.rng.shuffle(player.deck.cards)


def _wudao_refresh_instant(card):
    """按牌库是否含五种不同名幻境牌，刷新本牌是否携带瞬发。

    监听器只挂在手牌中的本牌上（broadcast 仅遍历手牌），故在回合开始时刷新，
    覆盖本回合内打出所需的状态。
    """
    names = {c.eng_name for c in card.owner.deck if c.eng_name in _HYJ_ILLUSION_NAMES}
    has_all = len(names) >= 5
    if has_all and CardAttributes.INSTANT not in card.attributes:
        card.attributes.append(CardAttributes.INSTANT)
    elif not has_all and CardAttributes.INSTANT in card.attributes:
        card.attributes.remove(CardAttributes.INSTANT)


class WuDaoNanTi:
    id = 116
    type = "spell"
    hero = "HuiYeJi"
    name = "五道难题"
    level_req = 1
    attributes = (CardAttributes.ENHANCE,)
    listeners = (Listener("begin turn",
                          lambda e, s: getattr(s, "owner", None) is not None and e.next_player == s.owner,
                          (lambda e, s: _wudao_refresh_instant(s),)),)
    require_target = (lambda s: _distinct_deck_illusions(s.owner),)

    @staticmethod
    def select_target(card):
        return _distinct_deck_illusions(card.owner)

    on_play = (lambda s: _wudao_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  117 佛前石钵 (FoQianShiBo)
#  己方回合结束时若你战斗区没有式神，召唤一个「石钵」。
#  若此牌耐久≥10，便使其获得4力量。
#  补充约定：战斗区为残血石钵时不再召唤；满血石钵会被新石钵替换刷新。
# ═══════════════════════════════════════════════════════════════════════════════

def _foqianshibo_on_play(s):
    player = s.owner
    card = s
    l = Listener("end turn",
                 lambda e, s2: _hyj_active(s2, card) and s2.game.current_player is s2,
                 (lambda e, s2: _foqianshibo_effect(e, s2, card),))
    l._tag = "foqianshibo"
    player.listeners.append(l)


def _foqianshibo_effect(e, s, card):
    az = s.attack_zone
    if az is not None:
        is_shibo = getattr(az, "type_name", "") == "ShiBo"
        # 普通式神或残血石钵在战斗区 → 不召唤
        if not is_shibo or az.hp < az.current_max_hp:
            return
    # 战斗区无式神，或有满血石钵 → 召唤（新石钵替换旧的）
    s.game.handle_event(SummonEvent(s, "ShiBo"))
    if _hyj_durability(s) >= 10:
        new_shibo = s.attack_zone
        if new_shibo is not None and getattr(new_shibo, "type_name", "") == "ShiBo":
            s.game.handle_event(GiveBuff("atk", 4, card, [new_shibo]))


class FoQianShiBo:
    id = 117
    type = "illusion"
    hero = "HuiYeJi"
    name = "佛前石钵"
    level_req = 2
    durability = 5
    on_play = (lambda s: _foqianshibo_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  118 龙首之玉 (LongShouZhiYu)
#  每个回合结束时，投射:造成2点伤害。
#  若此牌耐久≥10，再对敌方准备区式神各造成1点伤害。
# ═══════════════════════════════════════════════════════════════════════════════

def _longshou_on_play(s):
    player = s.owner
    card = s
    l = Listener("end turn",
                 lambda e, s2: _hyj_active(s2, card),
                 (lambda e, s2: _longshou_effect(e, s2, card),))
    l._tag = "longshou"
    player.listeners.append(l)


def _longshou_effect(e, s, card):
    game = s.game
    opp = s.opponent
    # 投射:造成2点伤害（战斗区为空时由投射分支改打敌方牌手）
    game.handle_event(ProjectileEvent(2, card, [opp.attack_zone]))
    if _hyj_durability(s) >= 10:
        standby = [h for h in opp.heroes if h.is_alive and h.level > 0 and h.state == "pending"]
        if standby:
            game.handle_event(DealDamage(1, card, standby))


class LongShouZhiYu:
    id = 118
    type = "illusion"
    hero = "HuiYeJi"
    name = "龙首之玉"
    level_req = 2
    durability = 5
    on_play = (lambda s: _longshou_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  119 觉醒·辉夜姬 (JueXingHuiYeJi)
#  选择并召唤一个辉夜姬的幻境。增强：若本局游戏已召唤五个不同的辉夜姬幻境，
#  召唤她的五种幻境且耐久都为1。觉醒：辉夜姬的幻境同时只能存在一个但能力和耐久会叠加。
#  （buff_atk/buff_hp 永久 +1/+1 在此手动应用，同旧版 spell 觉醒牌实现。）
# ═══════════════════════════════════════════════════════════════════════════════

def _juexing_on_play(s):
    player = s.owner
    hero = s.get_corresponding_hero()
    if hero is not None:
        hero.is_awakened = True
        # 觉醒：永久 +1/+1（觉醒牌数值直接写在 on_play，同其它式神觉醒牌）
        hero.get_permanent_buff("atk", 1)
        hero.get_permanent_buff("hp", 1)
    if _hyj_summoned_count(player) >= 5:
        # 增强：召唤全部五种幻境，耐久都为1（合并后耐久 = 5）
        for name in _HYJ_ILLUSION_NAMES:
            _summon_hyj_illusion(player, name, 1)
    else:
        sel = player.selected_targets[0] if player.selected_targets else None
        if sel is not None:
            _summon_hyj_illusion(player, sel.eng_name, 5)


class JueXingHuiYeJi:
    id = 119
    type = "spell"
    hero = "HuiYeJi"
    name = "觉醒·辉夜姬"
    level_req = 3
    attributes = (CardAttributes.ENHANCE,)
    require_target = (lambda s: _fresh_hyj_illusions(s.owner),)

    @staticmethod
    def select_target(card):
        # 增强时跳过选择，直接召唤全部五种
        if _hyj_summoned_count(card.owner) >= 5:
            return None
        return _fresh_hyj_illusions(card.owner)

    on_play = (lambda s: _juexing_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  120 蓬莱玉枝 (PengLaiYuZhi)
#  每个回合开始前，抽一张牌并获得1点鬼火。若此牌耐久≥10，效果翻倍。
#  （注意：鬼火在 begin_turn 广播之前已重置，本效果增加的鬼火不会被覆盖。）
# ═══════════════════════════════════════════════════════════════════════════════

def _penglai_on_play(s):
    player = s.owner
    card = s
    l = Listener("begin turn",
                 lambda e, s2: _hyj_active(s2, card),
                 (lambda e, s2: _penglai_effect(e, s2, card),))
    l._tag = "penglai"
    player.listeners.append(l)


def _penglai_effect(e, s, card):
    mult = 2 if _hyj_durability(s) >= 10 else 1
    # 一次效果抽 mult 张（觉醒·书翁空牌库时整个效果只结算一次10点伤害）
    s.game.handle_event(DrawEvent(s, mult))
    s.fire_cnt += mult


class PengLaiYuZhi:
    id = 120
    type = "illusion"
    hero = "HuiYeJi"
    name = "蓬莱玉枝"
    level_req = 3
    durability = 5
    on_play = (lambda s: _penglai_on_play(s),)


# ═══════════════════════════════════════════════════════════════════════════════
#  121 竹取物语 (ZhuQuWuYu) — 形态 5/5
#  每个回合结束时，随机召唤一个辉夜姬的幻境。
#  若辉夜姬的幻境耐久≥15，每当辉夜姬受到伤害时，改为降低辉夜姬幻境等量的耐久
#  （最多降低5耐久）。
# ═══════════════════════════════════════════════════════════════════════════════

def _zhuqu_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None:
        return
    # 回合结束监听器按 tag 去重：重复打出竹取物语不会叠加多次召唤
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "zhuqu-end"]
    l_end = Listener("end turn",
                     lambda e, h: h.is_alive and getattr(h, "morphed_id", 0) == 121,
                     (lambda e, h: _zhuqu_end(e, h),))
    l_end._tag = "zhuqu-end"
    hero.listeners.append(l_end)
    # 伤害重定向：给辉夜姬实例的 receive_damage 打补丁——直接取消本次伤害，
    # 并改为削减辉夜姬幻境相应耐久（最多5）。补丁自校验形态与幻境耐久：
    # 形态丢失（气绝/更换形态）或耐久不足时转调原实现。战斗/法术/投射伤害都
    # 汇入 receive_damage，因此不需要修改 hero.py 核心文件。
    hero.receive_damage = _zhuqu_make_receive_damage(hero)


def _zhuqu_end(e, h):
    player = h.owner
    chosen = random_choice(player, list(_HYJ_ILLUSION_NAMES), context="竹取物语: 随机召唤一个辉夜姬幻境")
    if chosen is None:
        return
    _summon_hyj_illusion(player, chosen, 5)


def _zhuqu_make_receive_damage(hero):
    orig_receive = hero.receive_damage  # 原绑定方法（本次伤害的实际扣除逻辑）

    def _patched(damage):
        player = hero.owner
        if (getattr(hero, "morphed_id", 0) == 121 and hero.is_alive
                and player is not None and _hyj_durability(player) >= 15):
            ill = _hyj_zone_illusion(player)
            if ill is not None:
                reduce_amt = min(damage, 5)  # 最多降低5耐久
                ill.durability -= reduce_amt
                game = player.game
                if game is not None:
                    game.handle_event(IllusionDamageEvent(ill, reduce_amt))
                    if ill.durability <= 0:
                        player.illusion_zone.remove(ill)
                        game.handle_event(IllusionDestroyedEvent(player, ill))
                return 0  # 本次伤害取消（不扣生命）
        return orig_receive(damage)

    return _patched


class ZhuQuWuYu:
    id = 121
    type = "morph"
    hero = "HuiYeJi"
    name = "竹取物语"
    level_req = 3
    atk = 5
    hp = 5
    on_play = (lambda s: _zhuqu_on_play(s),)
