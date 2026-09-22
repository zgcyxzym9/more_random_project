"""书翁卡牌（id 290-297）。

牌面文本以 cards.json 为准（wiki.md 未收录书翁）。形态牌的持续效果不在本
文件：以 morphed_id 门控挂在 heroes.py 书翁的类级监听器里（仿兵俑的
morphed_id 模式，随气绝重置/复活恢复，与形态同步）。

依赖引擎钩子的卡牌（用户批准 2026-09-22）：
- 云游 291：中途调度复用 INITIAL_PICK 子状态（_sw_dispatch_active 标志，
  game.py step 在广播前拦截 EndTurn 收尾）；
- 明心 294：回合抽牌替换走 begin_turn 的 "turn draw" 事件钩子；
- 觉醒·书翁 297：空牌库被动由引擎 handle_event 的 "draw" 分支结算
  （DrawEvent 抽牌事件：一个事件=一次抽牌效果，空牌库时只结算一次
  10点伤害且不败北；未觉醒维持败北）。
"""
import json
import os
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.selector import *


# ═══════════════════════════════════════════════════════════════════════════════
#  290 纪行 (JiXing)
#  迅捷 当书翁对敌方牌手造成伤害时，抽一张牌。
# ═══════════════════════════════════════════════════════════════════════════════
def _jixing_on_play(s):
    # 迅捷：打出即得（本次出击免鬼火）。持续侧（每回合开始重授、形态离场
    # 移除未消耗的迅捷、伤害触发抽牌）在 heroes.py 书翁监听器，
    # morphed_id==290 门控。引擎在出击后消耗 AGILE，故用胡桃觉醒的既有近似：
    # 每回合第一个出击免鬼火。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    if HeroAttributes.AGILE not in hero.attributes:
        hero.attributes.append(HeroAttributes.AGILE)


class JiXing:
    """纪行：迅捷 当书翁对敌方牌手造成伤害时，抽一张牌。

    伤害触发含战斗/法术/投射/贯通过量等全部通道（damage dealt 结算后通知，
    value>0）；对手 LOST 后不再触发（觉醒·书翁空牌库「伤害→抽牌→伤害」
    链在对手死亡时自然终止）。
    """
    id = 290
    type = "morph"
    hero = "ShuWeng"
    name = "纪行"
    level_req = 1
    atk = 2
    hp = 5
    is_beginning_card = True
    on_play = (_jixing_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  291 云游 (YunYou)
#  瞬发 调度你的手牌，然后洗牌库。（3次调度次数）
# ═══════════════════════════════════════════════════════════════════════════════
def _yunyou_on_play(s):
    # 中途调度复用 INITIAL_PICK 子状态（用户裁决 2026-09-22「尽量复用
    # reject initial pick」）：计数器/动作/状态机全部复用开局调度流程，
    # 仅以 _sw_dispatch_active 标志区分——引擎 step 的两个出口点（调度次数
    # 用尽 / 主动结束调度）见标志则恢复 PLAYING、计数归零并洗牌库，不经过
    # EndTurn（不换对手、不广播 end turn，避免回合结束类监听器误触发）。
    # 洗牌在出口点统一执行：未调度任何牌时洗牌无可观察差异，等价牌面语义。
    player = s.owner
    player.initial_pick_reject_left = 3
    player._sw_dispatch_active = True
    player.state = PlayerState.INITIAL_PICK


class YunYou:
    id = 291
    type = "spell"
    hero = "ShuWeng"
    name = "云游"
    level_req = 1
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (_yunyou_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  292 开卷 (KaiJuan)
#  抽两张牌。
# ═══════════════════════════════════════════════════════════════════════════════
def _kaijuan_on_play(s):
    # 一个 DrawEvent = 一次抽牌效果（引擎 "draw" 分支逐张调用 draw()）：觉醒·
    # 书翁空牌库时整个效果只结算一次10点伤害（用户裁决 2026-09-22）。
    s.owner.game.handle_event(DrawEvent(s.owner, 2))


class KaiJuan:
    id = 292
    type = "spell"
    hero = "ShuWeng"
    name = "开卷"
    level_req = 2
    is_beginning_card = True
    on_play = (_kaijuan_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  293 墨染 (MoRan)
#  抽一张牌，对一个式神造成等同于你手牌数量一半的伤害。
# ═══════════════════════════════════════════════════════════════════════════════
def _moran_on_play(s):
    # 先抽牌后结算伤害：手牌数含刚抽的牌；墨染自身此刻仍在手中（引擎出牌
    # 流程在 on_play 之后才移入弃牌堆），故一并计入（次级默认，已报备）。
    # 伤害向下取整；为 0 时不结算伤害事件。抽牌走 DrawEvent（觉醒·书翁
    # 空牌库时经引擎分支结算为10点伤害而非败北）。
    s.owner.game.handle_event(DrawEvent(s.owner, 1))
    if not s.owner.selected_targets:
        return
    n = len(s.owner.hand.cards) // 2
    if n > 0:
        s.owner.game.handle_event(DealDamage(n, s, [s.owner.selected_targets[0]]))


class MoRan:
    id = 293
    type = "spell"
    hero = "ShuWeng"
    name = "墨染"
    level_req = 2
    is_beginning_card = True
    # 「一个式神」未限定敌我：双方存活且已升级的式神（妖狐 _all_heroes 先例）
    require_target = (lambda s: [h for side in (s.owner.heroes, s.owner.opponent.heroes)
                                 for h in side if h.is_alive and h.level > 0],)
    select_target = (lambda s: select_target(
        s.owner, [h for side in (s.owner.heroes, s.owner.opponent.heroes)
                  for h in side if h.is_alive and h.level > 0], s),)
    on_play = (_moran_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  294 明心 (MingXin)
#  回合开始的抽牌改为检视牌库顶三张牌然后选择一张置入手牌，然后洗牌库。
# ═══════════════════════════════════════════════════════════════════════════════
class MingXin:
    """明心：回合开始的抽牌改为检视牌库顶三张牌然后选择一张置入手牌，然后
    洗牌库。持续效果在 heroes.py 书翁监听器（morphed_id==294 门控），经
    begin_turn 的 "turn draw" 事件钩子替换回合抽牌（引擎在蓄力结算完成后
    进入 SELECTING_TARGET 复用既有选目标流程，选定后回调结算）。
    """
    id = 294
    type = "morph"
    hero = "ShuWeng"
    name = "明心"
    level_req = 2
    atk = 4
    hp = 5
    is_beginning_card = True


# ═══════════════════════════════════════════════════════════════════════════════
#  295 闻世 (WenShi)
#  每有一张其他手牌此牌便获得1点力量和1点生命。
# ═══════════════════════════════════════════════════════════════════════════════
def _wenshi_on_play(s):
    # on_play 先于 play_card morph 分支的身材替换（读 card.atk/card.hp 之前），
    # 直接加在卡实例上 → 只加成本形态的身材，不落入 perm_buff（不跨形态/复活）。
    # 蓄力等路径下本卡可能已离手，按「手牌中非本卡」计数。
    n = len([c for c in s.owner.hand.cards if c is not s])
    if n > 0:
        s.atk += n
        s.hp += n


class WenShi:
    id = 295
    type = "morph"
    hero = "ShuWeng"
    name = "闻世"
    level_req = 3
    atk = 1
    hp = 1
    is_beginning_card = True
    on_play = (_wenshi_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  296 万象之书 (WanXiangZhiShu)
#  瞬发 随机将其他己方式神的各一张牌置入手牌。
# ═══════════════════════════════════════════════════════════════════════════════
_SW_POOL_CACHE: dict | None = None


def _sw_hero_pool():
    """各式神的全卡池（eng_name 列表），自 cards.json 按 hero 字段构建并缓存。

    万象之书为「额外获得」：与牌库内容无关（牌库里没有对应卡也可能获得，
    用户裁决 2026-09-22），故直接读全卡池而非牌库。
    """
    global _SW_POOL_CACHE
    if _SW_POOL_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "cards.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        pool: dict = {}
        for c in data:
            hero = c.get("hero")
            if hero:
                pool.setdefault(hero, []).append(c["eng_name"])
        _SW_POOL_CACHE = pool
    return _SW_POOL_CACHE


def _wanxiang_on_play(s):
    player = s.owner
    for hero in player.heroes:
        if hero.type_name == "ShuWeng":
            continue
        pool = _sw_hero_pool().get(hero.type_name)
        if not pool:
            continue   # 召唤物等无卡池的式神跳过
        name = select_random_target(
            player, pool, context=f"万象之书：随机 {hero.name} 的一张牌")
        if name is None:
            continue
        # GiveCardToHand 新建卡实例 = 额外获得（不动牌库）；逐张调用使溢出
        # 手牌的卡逐张进弃牌堆（与抽牌溢出语义一致）
        player.GiveCardToHand([name])


class WanXiangZhiShu:
    id = 296
    type = "spell"
    hero = "ShuWeng"
    name = "万象之书"
    level_req = 3
    attributes = (CardAttributes.INSTANT,)
    is_beginning_card = True
    on_play = (_wanxiang_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  297 觉醒·书翁 (JueXingShuWeng)
#  觉醒：在本局游戏的剩余时间内，每当你抽牌时若牌库里没有牌，则改为对敌方
#  牌手造成10点伤害，你不会因此输掉游戏。
# ═══════════════════════════════════════════════════════════════════════════════
def _juexingsw_on_play(s):
    # 觉醒置位沿用现有觉醒卡惯例（觉醒·兵俑/觉醒·胡桃）：spell 型 + on_play
    # 手动 is_awakened；+2/+2 永久加成走 get_permanent_buff（wiki「关键字-
    # 觉醒」：法术觉醒牌自带力量/生命时永久获得）。空牌库被动由引擎
    # handle_event 的 "draw" 分支结算：觉醒的式神所在方经 DrawEvent 抽牌遇
    # 空牌库时，改为对敌方牌手造成10点伤害且不败北（用户批准 2026-09-22）。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    hero.get_permanent_buff("atk", 2)
    hero.get_permanent_buff("hp", 2)
    hero.is_awakened = True


class JueXingShuWeng:
    id = 297
    type = "spell"
    hero = "ShuWeng"
    name = "觉醒·书翁"
    level_req = 3
    is_beginning_card = True
    on_play = (_juexingsw_on_play,)