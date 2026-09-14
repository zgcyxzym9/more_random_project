from .cards import *
from .entity import Entity
from .enums import get_card_enum, CardType
import copy
import json
import os

_name_to_id_cache: dict[str, int] | None = None


class Card(Entity):
    def __init__(self, card_obj):
        self.id = card_obj.id
        self.entity_type = "card"
        self.type = card_obj.type          # 保留原始字符串以向后兼容
        self.card_type = get_card_enum(card_obj.type)  # 新增：CardType 枚举
        self.hero = card_obj.hero
        self.form = getattr(card_obj, "form", "")   # 切换式神卡：所属形态（"Hei"/"Bai"）；其余卡为空串
        self.heroes = list(getattr(card_obj, "heroes", (card_obj.hero,)))  # 协战牌：共享的式神集合
        self.coop = getattr(card_obj, "coop", False) or card_obj.type == "coop"  # 协战牌：由 type 推断
        self.played_by = None                                               # 协战牌打出时选定的式神
        self.level_req = card_obj.level_req
        self.name = card_obj.name
        self.eng_name = type(card_obj).__name__
        if self.card_type == CardType.ATTACK:
            if hasattr(card_obj, "buff_atk"):
                self.buff_atk = card_obj.buff_atk
            if hasattr(card_obj, "buff_def"):
                self.buff_def = card_obj.buff_def
        if hasattr(card_obj, "on_play"):
            self.on_play = card_obj.on_play
        if hasattr(card_obj, "on_blast"):
            # 爆能钩子：在能量扣除后、鬼火/目标选择结算前由 play_card 调用（见 game.py）
            self.on_blast = card_obj.on_blast
        if hasattr(card_obj, "on_charge"):
            # 蓄力强化钩子：蓄力卡下个己方回合开始结算时、on_play 之前调用（见 game.py）
            self.on_charge = card_obj.on_charge
        if hasattr(card_obj, "after_play"):
            self.after_play = card_obj.after_play
        if self.card_type == CardType.MORPH:
            self.hp = card_obj.hp
            self.atk = card_obj.atk
        self.attributes = list(card_obj.attributes) if hasattr(card_obj, "attributes") else []
        self.require_target = card_obj.require_target if hasattr(card_obj, "require_target") else None
        # select_target 支持两种形态：
        #  1) 静态 tuple（现有卡牌）：打出时固定进入目标选择流程；
        #  2) 解析函数（如黄金羽）：打出时按需返回 tuple（进入选择）或 None（跳过选择）。
        # 解析依赖 owner / 觉醒状态等运行时信息，故用 property 在访问时求值。
        _sel = getattr(card_obj, "select_target", None)
        if callable(_sel):
            self._select_target_resolver = _sel
            self._select_target_static = None
        else:
            self._select_target_resolver = None
            self._select_target_static = _sel
        self.listeners = card_obj.listeners if hasattr(card_obj, "listeners") else []
        self.owner = None

        # ── 新增字段 ──────────────────────────────────────────────────────
        self.is_token = card_obj.is_token if hasattr(card_obj, "is_token") else False
        self.bounce = getattr(card_obj, "bounce", False)   # 弹回（一次性）：使用后回手并失去此能力
        self.response_condition = card_obj.response_condition if hasattr(card_obj, "response_condition") else None
        # 响应机制：response_trigger 匹配广播的事件类型；on_response 为响应打出时的回调。
        # 与 response_condition 同时存在时走新机制（见 game.Game._auto_response）。
        self.response_trigger = card_obj.response_trigger if hasattr(card_obj, "response_trigger") else None
        self.on_response = card_obj.on_response if hasattr(card_obj, "on_response") else ()
        self.enhance_condition = card_obj.enhance_condition if hasattr(card_obj, "enhance_condition") else None
        # 增强（wiki 关键字-增强）声明：CardEnhance 元组，判定/结算由 Game 的
        # 增强通用机制消费（can_play_card 复制视图 / play_card 开头实装）
        self.enhance = getattr(card_obj, "enhance", None)

        # ── 机制扩展字段 (Phase 2) ────────────────────────────────────────
        self.durability = card_obj.durability if hasattr(card_obj, "durability") else 0          # 幻境卡耐久
        self.energy_cost = card_obj.energy_cost if hasattr(card_obj, "energy_cost") else 0       # 爆能消耗（0 = 无爆能）
        self.is_ingredient = card_obj.is_ingredient if hasattr(card_obj, "is_ingredient") else False
        self.ingredient_tier = card_obj.ingredient_tier if hasattr(card_obj, "ingredient_tier") else 0  # 1=良, 2=优, 3=极
        self.ingredient_type = card_obj.ingredient_type if hasattr(card_obj, "ingredient_type") else ""  # "atk"/"hp"/"keyword"

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"{self.name}"

    def __copy__(self):
        return Card(copy.copy(self))

    def GetCard(id: str):
        card_class = globals()[id]
        card_obj = card_class()
        return Card(card_obj)

    def GetCards(ids: list[str]):
        cards = []
        for id in ids:
            cards.append(Card.GetCard(id))
        return cards.copy()

    @staticmethod
    def get_id_by_name(name: str) -> int:
        """返回卡牌名称对应的 id。首次调用时从 cards.json 加载并缓存。"""
        global _name_to_id_cache
        if _name_to_id_cache is None:
            json_path = os.path.join(os.path.dirname(__file__), "cards", "cards.json")
            with open(json_path, "r", encoding="utf-8") as f:
                card_data = json.load(f)
            _name_to_id_cache = {c["eng_name"]: c["id"] for c in card_data}
        return _name_to_id_cache.get(name, 0)

    def assign_owner(self, player):
        self.owner = player
        return self

    @property
    def select_target(self):
        """打出时解析目标候选。返回 None 表示完全跳过目标选择流程。"""
        if self._select_target_resolver is not None:
            return self._select_target_resolver(self)
        return self._select_target_static

    def get_corresponding_hero(self):
        from .hero import Hero
        # 协战牌：若已选定打出式神，优先返回
        if getattr(self, "played_by", None) is not None:
            return self.played_by
        if getattr(self, "coop", False):
            # 存活、等级达标、未眩晕的任一协战式神（“任意一式神满足条件即可打出”）
            for hero in self.owner.heroes:
                if hero.type_name in self.heroes and hero.is_alive \
                        and hero.level >= self.level_req and not hero.stunned:
                    return hero
            # 兜底：任一堆叠式神（供响应/特殊路径判断）
            for hero in self.owner.heroes:
                if hero.type_name in self.heroes:
                    return hero
            return None
        # 原逻辑：单归属
        for hero in self.owner.heroes:
            if self.hero == hero.type_name:
                return hero
