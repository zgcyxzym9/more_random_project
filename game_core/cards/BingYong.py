"""兵俑卡牌（id 282-289）。

牌面文本以 tmp_cards_json/BingYong.json 为准（已迁移至 cards.json 末尾）。
形态牌的持续效果不在本文件：以 morphed_id 门控挂在 heroes.py 兵俑的类级
监听器里（仿焚羽的 morphed_id 模式，随气绝重置/复活恢复，与形态同步）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


def _bingyong_hero(player):
    """player 存活的兵俑；没有则 None。"""
    return next((h for h in player.heroes
                 if h.type_name == "BingYong" and h.is_alive), None)


# ═══════════════════════════════════════════════════════════════════════════════
#  282 尘刀 (ChenDao)
#  每有1点护甲兵俑便获得1点力量。
# ═══════════════════════════════════════════════════════════════════════════════
def _chendao_on_play(s):
    # on_play 先于 play_card attack 分支的 combat_buff_atk 结算与本次战斗的
    # 护甲消耗，此刻读到的 defense 即打出时的护甲值。力量折入 buff_atk，
    # 经 combat_buff_atk 只在本次战斗生效（战斗牌力量规则）。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    s.buff_atk = getattr(s, "buff_atk", 0) + hero.defense


class ChenDao:
    id = 282
    type = "attack"
    hero = "BingYong"
    name = "尘刀"
    level_req = 1
    is_beginning_card = True
    on_play = (_chendao_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  283 古尘之盾 (GuChenZhiDun)
#  使一个己方式神得5点护甲。响应：当兵俑被攻击时，自动对其使用。
# ═══════════════════════════════════════════════════════════════════════════════
def _guchendun_select(card):
    """select_target 解析函数形态（card.py 的黄金羽先例）：访问时求值。

    己方回合：手动打出，返回友方存活候选，正常进入目标选择；
    敌方回合：即响应上下文（响应方恒为 current_player.opponent，见
    game._auto_response），「自动对其使用」目标隐式为被攻击的兵俑 →
    返回 None 跳过目标选择流程（can_play_card 的空目标探测与 play_card
    的选择门共用此 property，二者同时被跳过）。
    """
    if card.owner is not card.owner.game.current_player:
        return None
    return (lambda s: select_target(
        s.owner, [h for h in s.owner.heroes if h.is_alive], s),)


def _guchendun_on_play(s):
    # 手动打出：目标来自 select_target 选择流程；响应打出（敌方回合，
    # select_target 解析为 None、无选择流程）：目标隐式为被攻击的兵俑，
    # 即卡牌对应式神（response_condition 已保证被攻击者是对应式神）。
    target = (s.owner.selected_targets[0] if s.owner.selected_targets
              else s.get_corresponding_hero())
    if target is None:
        return
    s.owner.game.handle_event(GiveBuff("defense", 5, s, [target]))


class GuChenZhiDun:
    """古尘之盾：使一个己方式神得5点护甲。响应：当兵俑被攻击时，自动对其使用。

    响应走引擎现成机制（game._auto_response）；response_phase 默认 "before"，
    handle_event 的 before 广播先于 attack() 伤害结算，+5 甲可吸收本次攻击。
    眩晕/气绝/鬼火不足由 can_play_card 拦截，与 wiki「眩晕式神无法响应」一致。
    """
    id = 283
    type = "spell"
    hero = "BingYong"
    name = "古尘之盾"
    level_req = 1
    is_beginning_card = True
    # staticmethod：与「会」/黄金羽的解析函数写法一致——类属性经实例访问
    # 会绑定为方法多传 card_obj，staticmethod 则保持纯函数（card.py callable 分支）
    select_target = staticmethod(_guchendun_select)
    response_trigger = "hero attack"
    response_condition = (lambda card, src, target:
                          target is not None
                          and target is card.get_corresponding_hero(),)
    on_play = (_guchendun_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  284 不动如山 (BuDongRuShan)
#  进场时将兵俑移入战斗区。己方回合开始时若兵俑在战斗区，则获得3点力量。
# ═══════════════════════════════════════════════════════════════════════════════
def _budongru_on_play(s):
    # 进场移入战斗区（已在战斗区时 move_to_battle 无操作）。持续效果
    # （回合开始+3力量）在 heroes.py 兵俑监听器，morphed_id==284 门控。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    hero.move_to_battle()


class BuDongRuShan:
    id = 284
    type = "morph"
    hero = "BingYong"
    name = "不动如山"
    level_req = 2
    atk = 1
    hp = 9
    is_beginning_card = True
    on_play = (_budongru_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  285 冲撞 (ChongZhuang)
#  增强：己方回合开始时若兵俑在战斗区，此牌获得+1点力量与+1点护甲。
# ═══════════════════════════════════════════════════════════════════════════════
def _chongzhuang_cond(e, s):
    # 兵俑在战斗区的判定须在 before 广播点：begin_turn 的 retract_hero 在
    # after 前 已清空 attack_zone，after 读到的恒为空。
    hero = _bingyong_hero(s.owner)
    return (hero is not None
            and e.next_player == s.owner
            and s.owner.attack_zone is hero)


def _chongzhuang_eff(e, s):
    s.buff_atk += 1
    s.buff_def += 1


class ChongZhuang:
    """冲撞：增强——己方回合开始时若兵俑在战斗区，此牌获得+1点力量与+1点护甲。

    增强监听器挂在卡牌上：手牌是广播实体（iter_entities 遍历双方手牌），
    卡牌监听不受式神 0 级门控，手牌中每张冲撞独立累积。buff 在 Card 实例上
    累积，打出时按战斗牌规则结算（力量仅本次战斗、护甲持续）。
    """
    id = 285
    type = "attack"
    hero = "BingYong"
    name = "冲撞"
    level_req = 2
    buff_atk = 2
    buff_def = 2
    is_beginning_card = True
    listeners = (Listener("begin turn", _chongzhuang_cond, (_chongzhuang_eff,),
                          phase="before"),)


# ═══════════════════════════════════════════════════════════════════════════════
#  286 森罗之阵 (SenLuoZhiZhen)
#  进场时使兵俑获得2点护甲。兵俑有护甲时，至多只会受到等于其护甲值的伤害。
# ═══════════════════════════════════════════════════════════════════════════════
def _senluo_on_play(s):
    # 进场 +2 护甲。持续效果（受伤封顶）在 heroes.py 兵俑监听器，
    # morphed_id==286 门控。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    s.owner.game.handle_event(GiveBuff("defense", 2, s, [hero]))


class SenLuoZhiZhen:
    """森罗之阵：进场时使兵俑获得2点护甲。兵俑有护甲时，至多只会受到等于其
    护甲值的伤害。封顶语义为用户裁决（2026-09-22）：伤害最多只能移除护甲，
    有护甲时气血损失为 0（见 heroes.py _bingyong_senluo_cap；战斗与效果伤害
    均覆盖，多目标 AOE 的共享数值不封顶）。
    """
    id = 286
    type = "morph"
    hero = "BingYong"
    name = "森罗之阵"
    level_req = 2
    atk = 4
    hp = 7
    is_beginning_card = True
    on_play = (_senluo_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  287 觉醒·兵俑 (JueXingBingYong)
#  兵俑获得3点护甲。觉醒：己方回合开始时，兵俑得3点护甲。他的护甲不会在回合
#  开始移除。
# ═══════════════════════════════════════════════════════════════════════════════
def _juexingby_on_play(s):
    # 觉醒置位沿用现有觉醒卡惯例：spell 型 + on_play 手动 is_awakened（引擎
    # play_card 的 case "awaken" 分支无卡使用）。觉醒后的回合开始+3护甲与
    # 「护甲不在回合开始移除」由 heroes.py 兵俑监听器承担（is_awakened 门控）。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    s.owner.game.handle_event(GiveBuff("defense", 3, s, [hero]))
    hero.is_awakened = True


class JueXingBingYong:
    id = 287
    type = "spell"
    hero = "BingYong"
    name = "觉醒·兵俑"
    level_req = 2
    is_beginning_card = True
    on_play = (_juexingby_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  288 古尘之壁 (GuChenZhiBi)
#  进场时兵俑每有1点护甲，己方所有其他式神获得1点生命。
# ═══════════════════════════════════════════════════════════════════════════════
def _guchenbi_on_play(s):
    # morph 分支中 on_play 先于形态身材替换，读到的 defense 即打出时的护甲。
    # 永久生命走 get_permanent_buff（白狼觉醒等惯例：形态替换与复活后保留，
    # 区别于 GiveBuff 的死亡即失）。
    hero = s.get_corresponding_hero()
    if hero is None or not hero.is_alive:
        return
    n = hero.defense
    if n <= 0:
        return
    for h in s.owner.heroes:
        if h is not hero and h.is_alive:
            h.get_permanent_buff("hp", n)


class GuChenZhiBi:
    id = 288
    type = "morph"
    hero = "BingYong"
    name = "古尘之壁"
    level_req = 3
    atk = 5
    hp = 10
    is_beginning_card = True
    on_play = (_guchenbi_on_play,)


# ═══════════════════════════════════════════════════════════════════════════════
#  289 尘缚之阵 (ChenFuZhiZhen)
#  使一个敌方式神获得激怒。当兵俑在战斗区时免疫直接消灭效果，敌方战斗区式神
#  无法被其他式神替换。
# ═══════════════════════════════════════════════════════════════════════════════
def _chenfu_on_play(s):
    # 激怒：标记字段 target.enraged。限制/清除在引擎（game.py _enrage_blocks、
    # step hero attack 校验、attack() 收口清除；用户裁决 2026-09-20 批准①）。
    # 替换锁在引擎（game.py _replace_locked/_replace_blocked；空位进入允许、
    # 仅禁替换，响应战斗牌豁免；用户裁决 2026-09-20 批准②）。
    # 直接消灭免疫在引擎（game.py _direct_destroy_immune；FATAL/一目连凤覆岩/
    # 胡桃振刀三个消灭站点接入；仅免消灭不免伤害，免疫时无事发生；
    # 用户裁决 2026-09-22 批准③）。
    if not s.owner.selected_targets:
        return
    target = s.owner.selected_targets[0]
    target.enraged = True


class ChenFuZhiZhen:
    """尘缚之阵：使一个敌方式神获得激怒。当兵俑在战斗区时免疫直接消灭效果，
    敌方战斗区式神无法被其他式神替换。（三项效果均已实装，见各引擎钩子注释）
    """
    id = 289
    type = "morph"
    hero = "BingYong"
    name = "尘缚之阵"
    level_req = 3
    atk = 5
    hp = 9
    is_beginning_card = True
    select_target = (lambda s: select_target(
        s.owner, [h for h in s.owner.opponent.heroes
                  if h.is_alive and h.level > 0], s),)
    on_play = (_chenfu_on_play,)
