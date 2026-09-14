# 烹饪食材 / 佳肴 Token 卡（机制七：烹饪）
#
# 食材分三品：良（1勾/+1）、优（2勾/+2）、极（3勾/+3）
# 类型三种：山珍→攻击，海味→生命，时蔬→攻击+生命
# 佳肴：烹饪合成产物，效果 = 消耗的 3 食材之和（由 Game.cook 动态配置 on_play）
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import select_target


def _friendly_alive_heroes(owner):
    return [h for h in owner.heroes if h.is_alive]


def _yiwuyixin_active(owner):
    """一物一心（饴细工形态卡 id=216）是否激活：己方饴细工处于该形态且存活。"""
    return any(h.type_name == "YiXiGong" and h.morphed_id == 216 and h.is_alive
               for h in owner.heroes)


def _jiaoyao_friendly_targets(owner):
    """佳肴可用目标：一物一心激活时额外包含气绝（level>0）己方式神，供复活。

    只作用于佳肴（食材仍走 _friendly_alive_heroes，卡面仅提「佳肴」）。
    """
    targets = _friendly_alive_heroes(owner)
    if _yiwuyixin_active(owner):
        targets += [h for h in owner.heroes if not h.is_alive and h.level > 0]
    return targets


def _make_ingredient(cls_name, id_, name, ing_type, tier, buff_atk, buff_hp):
    """生成一个食材卡类。

    on_play 给所选目标己方式神加 buff；品阶 tier 决定勾级与数值。
    """
    def _make_on_play():
        effects = []
        if buff_atk > 0:
            effects.append(lambda s: GiveBuff("atk", buff_atk, s, s.owner.selected_targets))
        if buff_hp > 0:
            effects.append(lambda s: GiveBuff("hp", buff_hp, s, s.owner.selected_targets))
        return tuple(effects)

    return type(cls_name, (), {
        "id": id_,
        "type": "spell",
        "hero": "",           # 中立 Token：不属于任何式神，无需对应 hero
        "name": name,
        "level_req": tier,
        "is_token": True,
        "is_ingredient": True,
        "ingredient_tier": tier,
        "ingredient_type": ing_type,
        "attributes": (CardAttributes.IS_INGREDIENT, CardAttributes.INSTANT),
        "require_target": (lambda s: _friendly_alive_heroes(s.owner),),
        "select_target": (lambda s: select_target(s.owner, _friendly_alive_heroes(s.owner), s),),
        "on_play": _make_on_play(),
    })


# ── 山珍：攻击食材 ───────────────────────────────────────────────────────
ShanZhenLiang = _make_ingredient("ShanZhenLiang", 300, "山珍·良", "atk", 1, 1, 0)
ShanZhenYou = _make_ingredient("ShanZhenYou", 301, "山珍·优", "atk", 2, 2, 0)
ShanZhenJi = _make_ingredient("ShanZhenJi", 302, "山珍·极", "atk", 3, 3, 0)

# ── 海味：生命食材 ───────────────────────────────────────────────────────
HaiWeiLiang = _make_ingredient("HaiWeiLiang", 303, "海味·良", "hp", 1, 0, 1)
HaiWeiYou = _make_ingredient("HaiWeiYou", 304, "海味·优", "hp", 2, 0, 2)
HaiWeiJi = _make_ingredient("HaiWeiJi", 305, "海味·极", "hp", 3, 0, 3)

# ── 时蔬：攻击+生命食材 ──────────────────────────────────────────────────
ShiShuLiang = _make_ingredient("ShiShuLiang", 306, "时蔬·良", "keyword", 1, 1, 1)
ShiShuYou = _make_ingredient("ShiShuYou", 307, "时蔬·优", "keyword", 2, 2, 2)
ShiShuJi = _make_ingredient("ShiShuJi", 308, "时蔬·极", "keyword", 3, 3, 3)


class JiaYao:
    """佳肴：烹饪合成产物。效果由 Game.cook 动态填充 on_play。"""
    id = 309
    type = "spell"
    hero = ""
    name = "佳肴"
    level_req = 1
    is_token = True
    is_ingredient = False
    ingredient_tier = 0
    ingredient_type = ""
    attributes = (CardAttributes.INSTANT,)
    require_target = (lambda s: _jiaoyao_friendly_targets(s.owner),)
    select_target = (lambda s: select_target(s.owner, _jiaoyao_friendly_targets(s.owner), s),)
    on_play = ()
