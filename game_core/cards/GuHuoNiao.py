"""姑获鸟 专属卡牌（id 370-378）

数据源：cards.json（id 370-378）。式神段（基础能力「攻击后，移回准备区」、
影翼/慈乌稚子形态被动、瞬发增强触发标记、觉醒标记门控）在 heroes.py 姑获鸟段。

口径与裁决记录（用户 2026-10-22）：
- 瞬发增强（370/373/377「当其他己方式神攻击后，本回合此牌获得瞬发」）：
  妖刀姬同款——式神监听器写 reset_per_turn 计数（ghn_enh_instant），卡牌
  CardEnhance 读取，不修改手牌/牌库。触发是卡牌词条而非式神基础能力：
  姑获鸟存活与否、所在形态均不影响，仅排除其本人攻击（「其他」）。
- 丛云鹤舞：直击=本次战斗改为攻击敌方牌手（DIRECT_ATTACK 战后摘除）；
  牌手无力量 → 天然不被敌方战斗区式神反击（用户补充 1，无引擎改动）。
- 天翔鹤斩（用户终裁 2026-10-22：以牌面为准实装「免疫战斗伤害」，早前
  「正常受反击」的补充信息来自过时版本、作废）：贯通与免疫战斗伤害均为
  牌面固有，本次战斗临时授予、战后摘除（见切同款
  make_combat_immune_listener/clear_combat_immune；授予持续到整条战斗链
  结束——觉醒追击等场内再攻击期间仍免疫，地狱之手追猎持久同口径）。
  目标改写=敌方有未气绝的准备区式神时改为攻击之：地狱之手同款
  select_target（存活、level>0、不在敌方战斗区；帷幕不限制追猎式选目标），
  无候选时走正常攻击。
- 偷袭（用户裁决 Q1：「战斗区没有式神」= 敌方战斗区没有式神，含召唤物
  ——attack_zone 为 None）：引擎响应扫描不覆盖「回合结束」时刻，以卡面
  Listener("end turn", before) 实现（此广播发生时 current_player 仍是敌方，
  「敌方回合结束」语义成立；after 广播时回合已切换，由 phase 单选天然
  排除）。循环重检：打完一张后重新检测下一张是否仍可响应（用户裁决 Q1
  追问），经 can_play_card + play_card 完整打出=真实发起攻击；「在敌方回合
  获得瞬发」由敌方回合 CardEnhance 天然满足（占用本方瞬发名额，与手打
  一致；第二张通常因鬼火不足而不可响应）。
- 觉醒·姑获鸟（377）：替换基础能力（heroes.py ghn_awaken 标记门控，
  faq「使用不同的觉醒牌只保留最后使用的觉醒牌效果」）；远程跨气绝保留
  （attributes + original_attributes 双写，觉醒·酒吞贯通同款）；「消灭敌方
  式神时，再发起攻击」监听 hero kill after 相位（死亡结算清理完成后补
  广播，追击时目标读到结算后场面；自身同批气绝则 is_alive 已为 False，
  同归于尽不追击）；再攻击经 HeroAttackEvent 标准通道，击杀链经事件递归、
  无击杀即停；「敌方式神」含召唤物（判官/雪女口径）。
- 鹤唳回风（378）：增强基础能力（ghn_awaken=378，heroes.py 基础监听器
  分支：回准备区后 +1 力量（GiveBuff 非永久，酒吞「获得力量」口径）并
  恢复所有生命）。觉醒固定作用于姑获鸟本体——协战牌
  get_corresponding_hero 会返回任一合格协战式神，故显式按 type_name 查找
  （含气绝期间：faq 觉醒效果不因死亡回退）。羁绊：妖刀姬存活且等级>0 →
  经 HeroAttackEvent 发起一次攻击（faq 协战羁绊门控；冰封/正义之刺同款；
  眩晕不拦截效果强制攻击，wiki「与攻击的交互」）。
"""

from game_core.event import *
from game_core.enums import *
from game_core.selector import *
from game_core.manager import Listener, CardEnhance
from game_core.damage_immunity import make_combat_immune_listener, clear_combat_immune


# ── 瞬发增强（370/373/377 共用） ────────────────────────────────────────────

def _ghn_enh_instant_active(card):
    """「当其他己方式神攻击后，本回合此牌获得瞬发」标记是否生效。

    标记挂在姑获鸟 counters（ghn_enh_instant，reset_per_turn）上，由
    heroes.py 姑获鸟段的 hero attack after 监听器写入；判定时读取，
    不修改卡牌本身（妖刀姬 _ydj_instant_mark_active 同款）。
    """
    if getattr(card, "owner", None) is None:
        return False
    hero = next((h for h in card.owner.heroes if h.type_name == "GuHuoNiao"), None)
    return hero is not None and hero.counters.get("ghn_enh_instant", 0) > 0


_GHN_INSTANT_ENHANCE = (
    CardEnhance(cond=_ghn_enh_instant_active,
                attributes=(CardAttributes.INSTANT,)),
)


# ── 370 伞剑 ────────────────────────────────────────────────────────────────

class SanJian:
    """伞剑：增强：当其他己方式神攻击后，本回合此牌获得瞬发。"""
    id = 370
    type = "attack"
    hero = "GuHuoNiao"
    name = "伞剑"
    level_req = 1
    buff_atk = 2
    is_beginning_card = True
    enhance = _GHN_INSTANT_ENHANCE


# ── 371 影翼（形态；被动「每次攻击前获得1点力量」在 heroes.py，
#    morphed_id==371 门控，before 相位使加成对本次攻击生效） ────────────────

class YingYi:
    """影翼（形态 4/4）：姑获鸟每次攻击前获得1点力量。"""
    id = 371
    type = "morph"
    hero = "GuHuoNiao"
    name = "影翼"
    level_req = 1
    atk = 4
    hp = 4
    is_beginning_card = True


# ── 372 丛云鹤舞 ────────────────────────────────────────────────────────────

def _cyhw_on_play(s):
    # 直击：本次战斗改为攻击敌方牌手（引擎 DIRECT_ATTACK 通道；
    # 牌手无力量 → 不被反击，用户补充 1）
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if HeroAttributes.DIRECT_ATTACK not in hero.attributes:
        hero.attributes.append(HeroAttributes.DIRECT_ATTACK)
        setattr(s, "_cyhw_granted", True)


def _cyhw_after_play(s):
    if not getattr(s, "_cyhw_granted", False):
        return
    hero = s.get_corresponding_hero()
    if hero is not None and HeroAttributes.DIRECT_ATTACK in hero.attributes:
        # 中途气绝时 check_death 已把属性还原，in 判断天然跳过
        hero.attributes.remove(HeroAttributes.DIRECT_ATTACK)
    setattr(s, "_cyhw_granted", False)


class CongYunHeWu:
    """丛云鹤舞：直击。（不会被敌方战斗区的式神反击，用户补充 1）"""
    id = 372
    type = "attack"
    hero = "GuHuoNiao"
    name = "丛云鹤舞"
    level_req = 2
    is_beginning_card = True
    on_play = (_cyhw_on_play,)
    after_play = (_cyhw_after_play,)


# ── 373 金鸾（形态；瞬发增强为卡牌词条，与形态无关） ────────────────────────

class JinLuan:
    """金鸾（形态 6/4）：增强：当其他己方式神攻击后，本回合此牌获得瞬发。"""
    id = 373
    type = "morph"
    hero = "GuHuoNiao"
    name = "金鸾"
    level_req = 2
    atk = 6
    hp = 4
    is_beginning_card = True
    enhance = _GHN_INSTANT_ENHANCE


# ── 374 天翔鹤斩 ────────────────────────────────────────────────────────────

def _txhz_on_play(s):
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    # 免疫战斗伤害（见切同款）：本次战斗免疫，战后摘除；先去重保证幂等
    clear_combat_immune(hero)
    hero.listeners.append(make_combat_immune_listener())
    setattr(s, "_txhz_immune", True)
    # 牌面固有贯通：本次战斗临时授予（战后摘除，妖刀万华/丛云鹤舞同款）
    if HeroAttributes.PENETRATE not in hero.attributes:
        hero.attributes.append(HeroAttributes.PENETRATE)
        setattr(s, "_txhz_penetrated", True)
    # 目标改写：select_target 已把敌方准备区式神写入 selected_targets，
    # 授予追猎供引擎 _resolve_attack_target 读取（地狱之手同款）
    if s.owner.selected_targets and HeroAttributes.HUNTING not in hero.attributes:
        hero.attributes.append(HeroAttributes.HUNTING)
        setattr(s, "_txhz_hunting", True)


def _txhz_after_play(s):
    hero = s.get_corresponding_hero()
    if getattr(s, "_txhz_immune", False):
        if hero is not None:
            clear_combat_immune(hero)
        setattr(s, "_txhz_immune", False)
    if hero is not None:
        if getattr(s, "_txhz_penetrated", False):
            if HeroAttributes.PENETRATE in hero.attributes:
                hero.attributes.remove(HeroAttributes.PENETRATE)
            setattr(s, "_txhz_penetrated", False)
        if getattr(s, "_txhz_hunting", False):
            if HeroAttributes.HUNTING in hero.attributes:
                hero.attributes.remove(HeroAttributes.HUNTING)
            setattr(s, "_txhz_hunting", False)


class TianXiangHeZhan:
    """天翔鹤斩：贯通 免疫战斗伤害。敌方有未气绝的准备区式神时，本次战斗
    改为攻击一个敌方准备区式神。

    免疫战斗伤害按牌面实装（用户终裁 2026-10-22，见模块 docstring 口径）：
    本次战斗姑获鸟不受反击等战斗伤害，战后摘除。目标改写走追猎通道：帷幕
    不限制（地狱之手口径）；「未气绝的准备区式神」= 存活、level>0、不在
    敌方战斗区（召唤物恒在战斗区，天然排除）；无候选时不选目标、走正常攻击。
    """
    id = 374
    type = "attack"
    hero = "GuHuoNiao"
    name = "天翔鹤斩"
    level_req = 2
    buff_atk = 3
    is_beginning_card = True

    @staticmethod
    def select_target(card):
        player = card.owner
        if player is None:
            return None
        cands = [h for h in player.opponent.heroes
                 if h.is_alive and h.level > 0
                 and player.opponent.attack_zone is not h]
        if not cands:
            return None
        return (lambda s: select_target(player, cands, s),)

    on_play = (_txhz_on_play,)
    after_play = (_txhz_after_play,)


# ── 375 偷袭 ────────────────────────────────────────────────────────────────

def _touxi_enemy_turn_instant(card):
    """「在敌方回合获得瞬发」：当前回合属于敌方时判定成立。"""
    owner = getattr(card, "owner", None)
    return (owner is not None
            and owner.game.current_player is not owner)


_TOUXI_ENEMY_TURN_INSTANT = (
    CardEnhance(cond=_touxi_enemy_turn_instant,
                attributes=(CardAttributes.INSTANT,)),
)


def _touxi_zone_clear(s):
    """敌方战斗区没有式神（用户裁决 Q1=敌方战斗区；含召唤物：
    attack_zone 为 None 即空）。"""
    return s.owner.opponent.attack_zone is None


def _touxi_auto_effect(e, s):
    """敌方回合结束时自动使用（响应扫描不覆盖回合结束，卡面监听实现）。

    循环重检：手牌按序取偷袭 → can_play_card（式神状态/替换锁/瞬发免耗）
    → 区条件仍满足才打出（打完一张后重新检测下一张，用户裁决 Q1 追问）；
    经 play_card 完整打出=真实发起攻击，与 wiki「响应」的自动打出语义一致
    （响应的战斗牌不发起攻击的特例不适用——本牌响应语义即「自动使用」）。
    """
    game = s.owner.game
    for _ in range(len(s.owner.hand.cards) + 1):
        card = next((c for c in s.owner.hand.cards
                     if getattr(c, "id", None) == TouXi.id), None)
        if card is None:
            return
        ok, _msg = game.can_play_card(s.owner, card)
        if not ok or not _touxi_zone_clear(s):
            return
        game.play_card(s.owner, card)


class TouXi:
    """偷袭：在敌方回合获得瞬发。响应：当敌方回合结束且战斗区没有式神时，
    自动使用。（「战斗区」= 敌方战斗区，用户裁决 Q1；逐张重检自动使用）"""
    id = 375
    type = "attack"
    hero = "GuHuoNiao"
    name = "偷袭"
    level_req = 2
    buff_atk = 3
    is_beginning_card = True
    enhance = _TOUXI_ENEMY_TURN_INSTANT
    listeners = (
        Listener("end turn",
                 lambda e, s: (getattr(s, "owner", None) is not None
                               and s.owner.game.current_player is not s.owner),
                 (_touxi_auto_effect,)),
    )


# ── 376 慈乌稚子（形态；被动「其他己方式神攻击后获得迅捷」在 heroes.py，
#    morphed_id==376 门控） ──────────────────────────────────────────────────

class CiWuZhiZi:
    """慈乌稚子（形态 8/6）：当其他己方式神攻击后，姑获鸟获得迅捷。"""
    id = 376
    type = "morph"
    hero = "GuHuoNiao"
    name = "慈乌稚子"
    level_req = 3
    atk = 8
    hp = 6
    is_beginning_card = True


# ── 377 觉醒·姑获鸟 ────────────────────────────────────────────────────────

def _ghn_reattack_cond(e, s):
    # after 相位：死亡结算清理完成后补广播，追击目标读到结算后场面；
    # 自身同批气绝（同归于尽）时 is_alive 已为 False，天然不追击
    killed = getattr(e.event, "killed", None)
    return (s.is_alive
            and s.counters.get("ghn_awaken", 0) == 377
            and getattr(e.event, "killer", None) is s
            and killed is not None
            and getattr(killed, "owner", None) is s.owner.opponent)


def _ghn_reattack_effect(e, s):
    # 再发起一次攻击（标准引擎通道；远程：从准备区发起、不被反击；
    # 再击杀则经 hero kill 事件递归，无击杀即停）
    s.owner.game.handle_event(HeroAttackEvent(s.owner, s))


def _juexing_ghn_on_play(s):
    # 觉醒固定作用于姑获鸟本体（协战牌 get_corresponding_hero 会返回任一
    # 合格协战式神，故显式按 type_name 查找）
    hero = next((h for h in s.owner.heroes if h.type_name == "GuHuoNiao"), None)
    if hero is None:
        return
    hero.get_permanent_buff("atk", 2)   # json buff_atk=2 永久（faq 属性增加保留）
    # faq：使用不同的觉醒牌只保留最后使用的觉醒牌效果（377↔378 互相覆盖，
    # heroes.py 基础监听器按标记门控）
    hero.counters.ensure("ghn_awaken", initial=0, persistent=True)
    hero.counters.set("ghn_awaken", 377)
    hero.is_awakened = True
    # 远程跨气绝保留：attributes + original_attributes 双写（觉醒·酒吞贯通同款）
    if HeroAttributes.RANGED not in hero.attributes:
        hero.attributes.append(HeroAttributes.RANGED)
        hero.original_attributes.append(HeroAttributes.RANGED)
    # 击杀追击监听（faq 觉醒不因死亡回退 → listeners + original_listeners，
    # tag 先摘后挂保证重复觉醒幂等）
    l = Listener("hero kill", _ghn_reattack_cond, (_ghn_reattack_effect,),
                 phase="after")
    l._tag = "ghn_awaken_reattack"
    hero.listeners = [x for x in hero.listeners
                      if getattr(x, "_tag", "") != "ghn_awaken_reattack"]
    hero.original_listeners = [x for x in hero.original_listeners
                               if getattr(x, "_tag", "") != "ghn_awaken_reattack"]
    hero.listeners.append(l)
    hero.original_listeners.append(l)


class JueXingGuHuoNiao:
    """觉醒·姑获鸟：增强：当其他己方式神攻击后，本回合此牌获得瞬发。
    觉醒：远程。姑获鸟消灭敌方式神时，再发起攻击。"""
    id = 377
    type = "spell"
    hero = "GuHuoNiao"
    name = "觉醒·姑获鸟"
    level_req = 3
    is_beginning_card = True
    enhance = _GHN_INSTANT_ENHANCE
    on_play = (_juexing_ghn_on_play,)


# ── 378 鹤唳回风（协战） ────────────────────────────────────────────────────

def _helihuifeng_core(s, hero):
    """鹤唳回风觉醒核心（独立打出 / 刃影鹤唳「姑获鸟-鹤唳回风」共用）。

    觉醒增强部分（攻击后移回准备区+1力量并回满）在 heroes.py 基础监听器的
    ghn_awaken==378 分支；此处仅落标记/永久属性并发起羁绊攻击。
    """
    if hero is None:
        return
    hero.get_permanent_buff("atk", 1)   # json buff_atk=1 / buff_hp=1 永久
    hero.get_permanent_buff("hp", 1)
    # faq：最后使用的觉醒牌生效（覆盖 377 的替换型觉醒，恢复增强型基础）
    hero.counters.ensure("ghn_awaken", initial=0, persistent=True)
    hero.counters.set("ghn_awaken", 378)
    hero.is_awakened = True
    # 羁绊：妖刀姬发起一次攻击（faq 协战羁绊门控：另一位协战式神存活且
    # 等级不为 0；眩晕不拦截效果强制攻击，wiki「与攻击的交互」）
    ydj = next((h for h in s.owner.heroes if h.type_name == "YaoDaoJi"), None)
    if ydj is not None and ydj.is_alive and ydj.level > 0:
        s.owner.game.handle_event(HeroAttackEvent(s.owner, ydj))


def _helihuifeng_on_play(s):
    # 觉醒固定作用于姑获鸟本体（显式按 type_name 查找，含气绝期间：
    # faq 觉醒效果不因死亡回退）
    hero = next((h for h in s.owner.heroes if h.type_name == "GuHuoNiao"), None)
    _helihuifeng_core(s, hero)


class HeLiHuiFeng:
    """鹤唳回风（协战）：觉醒：姑获鸟攻击后，移回准备区，获得+1力量并恢复
    所有生命。羁绊：妖刀姬发起一次攻击。"""
    id = 378
    type = "spell"
    hero = "GuHuoNiao"
    heroes = ["GuHuoNiao", "YaoDaoJi"]
    coop = True
    name = "鹤唳回风"
    level_req = 2
    is_beginning_card = False
    on_play = (_helihuifeng_on_play,)
