from game_core import cards

from .action import *
from .utils import CardList
from .card import Card
from .hero import Hero
from .entity import Entity
from .enums import *
from .damage_immunity import clear_combat_immune
import os
import random as r


# Player: generic, can directly use for training
class Player():
    def __init__(self, deck: list[str], heroes: list[str]):
        from .game import Game
        from .agent import Agent
        self.game: Game = None
        self.entity_type = "player"
        self.opponent: Player = None
        self.agent: Agent = None
        self.is_first_player: bool = False
        self.heroes: list[Hero] = Hero.GetHeroes(heroes)
        self.starting_deck = deck
        self.state = PlayerState.WAITING
        self.hp: int = 30
        self.current_max_hp: int = 30
        self.defense: int = 0
        self.penetration: int = 0     # 破甲：受到伤害时足额加到伤害量上，然后清零（牌手在己方回合开始时自动清除）
        self.illusion_zone: list = []  # 幻境区：排序第一（最旧）的幻境承伤
        self.last_attacking_hero: Hero = None  # 己方回合最后一个攻击的式神（鸮之守护目标）
        self.deck: CardList = None
        self.hand: CardList = None
        self.used_card: CardList = None
        self.attack_zone: Hero = None
        self.attack_available: bool = False
        self.fire_cnt: int = 0
        self.instant_used: bool = True
        self.upgrade_remaining: int = 0
        self.candidate_targets = []
        self.pending_card: Card = None
        self.selected_targets = None
        self.selected_option = None
        self._pending_option_callback = None
        self.listeners = []
        self.initial_pick_reject_left = 3
        # 蓄力：按蓄力先后排序的式神列表（各卡挂在 hero.charging_card 上）
        self.charging_order: list = []
        self.inspiration_atk = 0   # 鼓舞攻击 (牌手加成, 己方任意式神出击时消耗)
        self.inspiration_def = 0   # 鼓舞护盾
        self.inspiration_hp = 0    # 鼓舞生命 (预留)
        # 鼓舞关键字/特殊效果池（如觉醒·不知火「本回合获得贯通」）：每项为
        # lambda(e)，e = 即将出击（或消耗鼓舞）的式神；与 atk/def 同在消耗点
        # 结算并清空（game.py 出击路径 / _buyezhiwu_inject 战斗牌路径）
        self.inspiration_effects: list = []

    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        if self.game:
            self.game.rng.shuffle(self.heroes)
        else:
            r.shuffle(self.heroes)
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
        if not self.is_first_player:
            self.defense = 5
        for i in range(5):
            self.draw()
        self.state = PlayerState.INITIAL_PICK

    def draw(self):
        if self.deck.is_empty():
            self.hp = 0
            self.state = PlayerState.LOST
            return
        drawn_card = self.deck.pop(0)
        if len(self.hand.cards) >= 12:
            self.used_card.append(drawn_card)
            return
        self.hand.append(drawn_card)
        # 初始替换手牌阶段不自动排序，进入正式出牌后每次抽牌整理手牌
        if self.initial_pick_reject_left == 0:
            self.sort_hand()

    def reject_initial_card(self, id):
        rejected_card = self.hand.pop(id - 1)
        self.deck.append(rejected_card)

    def sort_hand(self):
        """自动整理手牌：从左到右按场上式神顺序，同式神卡牌按 id 从小到大。

        响应牌判定依赖手牌顺序（同等优先度从左到右依次响应，faq）。
        """
        order = {h: i for i, h in enumerate(self.heroes)}
        self.hand.cards.sort(key=lambda c: (order.get(c.get_corresponding_hero(), len(self.heroes)), c.id))

    def assign_agent(self):
        from .agent import Agent, IOAgent
        self.agent = IOAgent(self.game, self)

    def advance_hero(self, hero: Hero) -> bool:
        """进入战斗区（替换已有占位者）。尘缚之阵替换锁拦截需替换的进入：
        返回 False 且不改变战斗区（空位进入/占位者本人/远程不受限）。"""
        if self.attack_zone is not None and self.attack_zone is not hero:
            if self.game._replace_blocked(self, hero):
                print(f"battle zone is locked: {hero.type_name} cannot "
                      f"replace {self.attack_zone.type_name}")
                return False
            if getattr(self.attack_zone, 'is_summoned', False):
                # 召唤物被其他式神进入战斗区替换时直接离场（非气绝）
                self.dismiss_summon(self.attack_zone)
            else:
                self.attack_zone.state = "pending"
        self.attack_zone = hero
        hero.state = "attacking"
        return True

    def dismiss_summon(self, summon: Hero):
        """召唤物直接离场：从己方式神列表移除，不视为气绝/死亡。"""
        if summon in self.heroes:
            self.heroes.remove(summon)
        if self.attack_zone is summon:
            self.attack_zone = None
        if self.last_attacking_hero is summon:
            self.last_attacking_hero = None

    def retract_hero(self):
        if self.attack_zone is not None:
            self.attack_zone.state = "pending"
            self.attack_zone = None

    def check_death(self):
        if self.hp <= 0:
            self.state = PlayerState.LOST

    def clear_round_effects(self):
        for hero in self.heroes:
            hero.round_buff_atk = 0
            hero.round_buff_spell_damage = 0
            hero.round_buff_player_damage = 0
            # 本回合免疫战斗伤害：移除临时 combat 免疫监听器（山童等被动的非战斗免疫用独立 tag，不受影响）
            clear_combat_immune(hero)

    def move_card_to_used(self, card: Card):
        if card in self.hand.cards:
            self.hand.remove(card)
        self.used_card.append(card)

    def receive_damage(self, damage: int) -> int:
        """结算一次伤害，返回实际扣除的生命值。

        结算次序：幻境承伤（排序第一幻境耐久受等量伤害，并行不减免）
        → 破甲加成 → 护甲减免 → 扣血。
        """
        # 幻境承伤：牌手受到伤害时，排序第一的幻境耐久受等量伤害；
        # 溢出伤害不转移到下一个幻境。先扣耐久 → 检查破碎 → 触发效果 → 再扣牌手血。
        if self.illusion_zone:
            from .event import IllusionDamageEvent, IllusionDestroyedEvent
            first = self.illusion_zone[0]
            first.durability -= damage
            if self.game is not None:
                self.game.handle_event(IllusionDamageEvent(first, damage))
            if first.durability <= 0:
                self.illusion_zone.pop(0)
                if self.game is not None:
                    self.game.handle_event(IllusionDestroyedEvent(self, first))

        # 破甲：伤害足额加成后全部消耗
        if self.penetration > 0:
            damage += self.penetration
            self.penetration = 0

        effective_damage = damage - self.defense
        if effective_damage < 0:
            self.defense -= damage
            return 0
        self.hp -= effective_damage
        self.defense = 0
        return effective_damage

    def GiveCardToHand(self, cards: list[str]):
        for card in cards:
            card_obj = Card.GetCard(card)
            card_obj.assign_owner(self)
            if len(self.hand.cards) >= 12:
                self.used_card.append(card_obj)
                return
            self.hand.append(card_obj)
            # 初始替换手牌阶段不自动排序
            if self.initial_pick_reject_left == 0:
                self.sort_hand()

    def GiveCardToDeck(self, cards: list[str]):
        for card in cards:
            card_obj = Card.GetCard(card)
            card_obj.assign_owner(self)
            self.deck.append(card_obj)

    def can_end_turn(self):
        return self.game.current_player is self and self.upgrade_remaining == 0

    def get_legal_actions(self):
        match self.state:
            case PlayerState.INITIAL_PICK:
                actions = [RejectInitialPick(card) for card in self.hand]
                actions.append(EndTurn())
                return actions

            case PlayerState.PLAYING:
                actions = []
                if self.upgrade_remaining > 0:
                    for hero in self.heroes:
                        if getattr(hero, 'is_summoned', False):
                            continue  # 召唤物不可升级
                        is_min_level = True
                        for hero_tmp in self.heroes:
                            if hero_tmp.level < hero.level:
                                is_min_level = False
                        if hero.level < 3 and is_min_level:
                            actions.append(UpgradeHero(hero))
                    return actions
                actions.append(EndTurn())
                for card in self.hand:
                    if card.require_target is not None and any(len(req(card)) == 0 for req in card.require_target):
                        continue
                    # 可打出性判定统一委托 can_play_card（增强视图 / 鬼火惩罚 / 式神
                    # 状态 / 空目标探测均与 step 的判定完全一致，动作列表不再与 step
                    # 脱节，如增强瞬发在 0 火时同样列入）。仅 require_target 而无
                    # select_target 的卡（腹满乾坤等）探测不覆盖，保留上方空候选预检。
                    if self.game.can_play_card(self, card)[0]:
                        actions.append(PlayCard(card, None))
                        self._append_blast_action(actions, card, None)
                        self._append_charge_action(actions, card, None)
                for hero in self.heroes:
                    # 激怒限制：己方有可出击的激怒式神时，只能让激怒式神出击
                    if self.game._enrage_blocks(self, hero):
                        continue
                    # 尘缚之阵替换锁：需替换被锁占位者的出击不列入动作
                    if self.game._replace_blocked(self, hero):
                        continue
                    if hero.is_alive and hero.level > 0 and self.attack_available and hero.can_act():
                        # 迅捷/昂扬 不需要鬼火
                        if HeroAttributes.AGILE in hero.attributes or HeroAttributes.VALIANT in hero.attributes:
                            actions.append(HeroAttack(hero))
                        elif self.fire_cnt > 0:
                            actions.append(HeroAttack(hero))
                return actions

            case PlayerState.SELECTING_TARGET:
                actions = [SelectTarget(target) for target in self.candidate_targets]
                return actions

            case PlayerState.LOST:
                return []

            case _:
                print(f"getting legal actions with an undefined state {self.state}, check code!")
                return []

    def _append_blast_action(self, actions, card, target):
        """若卡牌有爆能属性且能量足够，追加爆能版 PlayCard。

        让 agent/用户在普通版与爆能版之间选择，而非默认总是爆能。
        """
        if CardAttributes.BLAST not in card.attributes:
            return
        hero = card.get_corresponding_hero()
        if hero is not None and hero.counters.get("energy", 0) >= card.energy_cost:
            actions.append(PlayCard(card, target, use_blast=True))

    def _append_charge_action(self, actions, card, target):
        """若卡牌有蓄力属性且对应式神可蓄力，追加蓄力版 PlayCard。

        同一式神同时只能蓄一张（wiki）：已在蓄力时只出普通选项。
        蓄力版与爆能版不组合（当前无交集，遇到再说）。
        """
        if CardAttributes.CHARGE not in card.attributes:
            return
        hero = card.get_corresponding_hero()
        if hero is not None and hero.is_alive and hero.charging_card is None:
            actions.append(PlayCard(card, target, use_charge=True))


"""
InferencePlayer: for full game inference, DO NOT USE FOR TRAINING OR
PLAYING WITH THE SIMULATOR
"""
class InferencePlayer(Player):
    def __init__(self, deck: list[str], heroes: list[str]):
        super().__init__(deck, heroes)
        root_dict = "E:/more_random_project_vibe"
        with open(os.path.join(root_dict, "game_core/cards/card_names.txt"), 'r', encoding='utf-8') as file:
            self.card_names = [line.strip() for line in file if line.strip()]
        with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
            self.hero_names = [line.strip() for line in file if line.strip()]
        # True 时初始 5 张手牌自动从牌库抽取（用于 OCR 自动识别手牌），不再逐个弹输入。
        # 由 start_game() 结束后自动复位，不影响之后的正常手动输入。
        self.auto_initial_draw: bool = False

    # This version of start_game will not shuffle the hero list
    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
        if not self.is_first_player:
            self.defense = 5
        for i in range(5):
            self.draw()
        self.auto_initial_draw = False  # 初始发牌结束，恢复手动输入
        self.state = PlayerState.INITIAL_PICK

    """
    The implementation of this draw function will generate a card from
    nowhere and pop a random card from the deck, and therefore should only
    be used in circumstances where you will determine drawn cards manually.
    """
    def draw(self):
        from rl.utils import match_by_caps
        # 静默发牌模式（auto_initial_draw）：直接从牌库抽取，不弹输入
        if self.auto_initial_draw:
            Player.draw(self)
            return
        while True:
            _ = input(f"Please enter the name of the card you just drawn: ")
            card_name = match_by_caps(self.card_names, _)
            if card_name is not None:
                if len(self.hand.cards) >= 12:
                    print("Your hand is full, the drawn card will be discarded.")
                    self.used_card.append(Card.GetCard(card_name).assign_owner(self))
                else:
                    self.GiveCardToHand([card_name])
                break
        self.deck.pop()

"""
InferenceOpponent: for full game inference, DO NOT USE FOR TRAINING OR
PLAYING WITH THE SIMULATOR
"""
class InferenceOpponent(Player):
    def __init__(self, heroes: list[str]):
        super().__init__(["WuShiZhiQuan"] * 32, heroes)
        root_dict = "E:/more_random_project_vibe"
        with open(os.path.join(root_dict, "game_core/cards/card_names.txt"), 'r', encoding='utf-8') as file:
            self.card_names = [line.strip() for line in file if line.strip()]
        with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
            self.hero_names = [line.strip() for line in file if line.strip()]

    # This version of start_game will not shuffle the hero list
    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
        if not self.is_first_player:
            self.defense = 5
        for i in range(5):
            self.draw()
        self.state = PlayerState.INITIAL_PICK

    # get_legal_actions here will not consider PlayCard actions, which will
    # be dealt with in inference_full_game.py
    def get_legal_actions(self):
        match self.state:
            case PlayerState.INITIAL_PICK:
                actions = [RejectInitialPick(card) for card in self.hand]
                actions.append(EndTurn())
                return actions

            case PlayerState.PLAYING:
                actions = []
                if self.upgrade_remaining > 0:
                    for hero in self.heroes:
                        is_min_level = True
                        for hero_tmp in self.heroes:
                            if hero_tmp.level < hero.level:
                                is_min_level = False
                        if hero.level < 3 and is_min_level:
                            actions.append(UpgradeHero(hero))
                    return actions
                actions.append(EndTurn())
                for hero in self.heroes:
                    # 激怒限制：己方有可出击的激怒式神时，只能让激怒式神出击
                    if self.game._enrage_blocks(self, hero):
                        continue
                    # 尘缚之阵替换锁：需替换被锁占位者的出击不列入动作
                    if self.game._replace_blocked(self, hero):
                        continue
                    if hero.is_alive and hero.level > 0 and self.attack_available and hero.can_act():
                        if self.fire_cnt > 0 or HeroAttributes.AGILE in hero.attributes or HeroAttributes.VALIANT in hero.attributes:
                            actions.append(HeroAttack(hero))
                return actions

            case PlayerState.SELECTING_TARGET:
                actions = [SelectTarget(target) for target in self.candidate_targets]
                return actions

            case PlayerState.LOST:
                return []

            case _:
                print(f"getting legal actions with an undefined state {self.state}, check code!")
                return []
