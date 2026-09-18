from .player import Player
from .action import *
from .hero import Hero
from .card import Card
from .enums import *
from .event import *
from .rng import GameRNG
from .counters import CounterManager


class Game:
    def __init__(self, players: list[Player], seed: int = None):
        self.player1: Player = players[0]
        self.player2: Player = players[1]
        self.turn_count = 0
        self.current_player: Player = None
        self.state: str = None
        self.action_queue: list = []
        self.pending_action: Action = None
        self.rng = GameRNG(seed)
        self.counters = CounterManager(self)   # 全局计数器
        self._last_damage_source = None        # 最近一次造成伤害的来源（击杀事件 killer）
        self._pending_response_cleanups = []   # 响应战斗牌 buff 的战斗后清理暂存（见 _play_response_card）


    def pick_first_player(self):
        x = self.rng.random()
        if x < 0.5:
            return self.player1, self.player2
        else:
            return self.player2, self.player1


    def begin_turn(self):
        # 薰：last_attacking_hero 需要区分"本回合最后攻击者"，故在回合开始复位
        self.current_player.last_attacking_hero = None
        # 鬼火在广播 begin turn 之前重置：回合开始类效果（如辉夜姬·蓬莱玉枝）在
        # begin-turn 广播中增加的鬼火需要保留，否则会被此处的无条件覆盖抹掉。
        # 条件从 turn_count > 1 改为 >= 1：广播时 turn_count 尚未自增，二者等价。
        self.current_player.fire_cnt = 2 if self.turn_count >= 1 else 1
        # 先清除上一回合临时加成，再广播 begin turn，让式神（如泷夜叉姬）按当前状态生成本回合加成
        self.player1.clear_round_effects()
        self.player2.clear_round_effects()
        self.broadcast("begin turn", next_player=self.current_player)
        self.current_player.state = PlayerState.PLAYING if self.current_player.initial_pick_reject_left == 0 else PlayerState.INITIAL_PICK
        self.current_player.opponent.state = PlayerState.WAITING
        if self.player1.state != PlayerState.INITIAL_PICK and self.player2.state != PlayerState.INITIAL_PICK:
            self.turn_count += 1
        if self.turn_count == 1:
            self.player1.upgrade_remaining, self.player2.upgrade_remaining = 1, 1
            self.step(self.current_player, UpgradeHero(self.current_player.heroes[0]))
            self.current_player = self.current_player.opponent
            self.step(self.current_player, UpgradeHero(self.current_player.heroes[0]))
            self.current_player = self.current_player.opponent
        self.current_player.attack_available = True
        # 瞬发预算每回合一次，回合开始对双方重置：己方获得新的瞬发配额，
        # 敌方也重置——敌方回合内响应牌（瞬发）可获得免费打出机会。
        # 鬼火不重置：敌方响应使用上回合结余。
        self.current_player.instant_used = False
        self.current_player.opponent.instant_used = False
        self.current_player.upgrade_remaining = 1
        self.current_player.retract_hero()
        if self.current_player.is_first_player and self.turn_count == 13:
            self.current_player.upgrade_remaining += 1
        if not self.current_player.is_first_player and self.turn_count == 6:
            self.current_player.upgrade_remaining += 1
        avail_upgrades = 0
        for hero in self.current_player.heroes:
            avail_upgrades += 3 - hero.level
        self.current_player.upgrade_remaining = min(self.current_player.upgrade_remaining, avail_upgrades)
        # 牌手护甲/破甲在己方回合开始时清除（后手初始 5 护甲在其首个回合清除）
        if self.turn_count > 0:
            self.current_player.defense = 0
        self.current_player.penetration = 0
        # ── 倒计时 / 眩晕 / 计数器 ───────────────────────────────────────
        for hero in self.current_player.heroes:
            if hero.state == "dead":
                hero.round_until_alive -= 1
                if hero.round_until_alive <= 0:
                    hero.revive()
            else:
                hero.tick_countdown()
                if hero.stunned:
                    hero.unstun()
            hero.defense = 0
            hero.penetration = 0
            hero.counters.reset_per_turn()

        for hero in self.current_player.opponent.heroes:
            hero.counters.reset_per_turn()

        self.counters.reset_per_turn()

        # ── 充能：有 ENERGY_CHARGE 词条且未气绝的式神获得 1 能量 ──────────
        for hero in self.current_player.heroes:
            if HeroAttributes.ENERGY_CHARGE in hero.attributes and hero.is_alive:
                hero.counters.inc("energy")
                self.handle_event(EnergyGainEvent(hero, 1))

        if self.current_player.state != PlayerState.INITIAL_PICK:
            self.current_player.draw()

        # ── 蓄力结算：本回合开始时，正在蓄力的式神按蓄力顺序打出所蓄之卡。
        # 位于倒计时/眩晕块之后：自动解除后的眩晕不再阻止结算，只有 begin turn
        # 广播中新施加的眩晕才会令该式神保留蓄力、下回合再试（wiki「尝试打出时
        # 若眩晕则无法打出」）。费用已在发起蓄力时支付，结算走 use_charge 免扣费。──
        for charge_hero in list(self.current_player.charging_order):
            if not charge_hero.is_alive or charge_hero.charging_card is None:
                # 气绝时已清理，双保险跳过
                if charge_hero in self.current_player.charging_order:
                    self.current_player.charging_order.remove(charge_hero)
                continue
            if charge_hero.stunned:
                continue   # 眩晕等无法出牌：保留蓄力，下回合再试（wiki）
            card = charge_hero.charging_card
            # 先摘除蓄力状态再结算：挂起重放 / 结算中死亡均不需要蓄力状态仍在
            charge_hero.charging_card = None
            self.current_player.charging_order.remove(charge_hero)
            self.play_card(self.current_player, card, use_charge=True)
            # 结算挂起选目标（SELECTING_TARGET）时跳出：余下蓄力式神下回合再试
            if self.current_player.state == PlayerState.SELECTING_TARGET:
                break


    def check_end_condition(self):
        if self.player1.state == PlayerState.LOST or self.player2.state == PlayerState.LOST:
            return True
        return False


    def broadcast(self, event_type, check_response=True, **kwargs):
        event = Event(event_type, **kwargs)
        for entity in self.iter_entities():
            # 0 级式神的被动技能不生效
            if isinstance(entity, Hero) and entity.level == 0:
                continue
            for listener in entity.listeners:
                if listener.matches(event, entity):
                    listener.trigger(event, entity)
        # ── 响应机制：与监听器同一广播点 ──────────────────────────────────
        # 响应牌也是「事件触发被动」：敌方回合、在手牌、满足条件时自动打出。
        # step 的广播传 check_response=False —— step 的 hero attack 会再经
        # handle_event 二次广播同一攻击，只在 handle_event 的广播点扫描，
        # 保证一次攻击至多打出一张响应。
        if not check_response:
            return
        # 事件被监听器 revert（如鸦羽疾走）后不再触发响应
        if getattr(kwargs.get("event"), "revert", False):
            return
        self._auto_response(event)


    def iter_entities(self):
        yield self.player1
        yield self.player2
        yield from self.player1.hand
        yield from self.player2.hand
        yield from self.player1.heroes
        yield from self.player2.heroes


    # ═══════════════════════════════════════════════════════════════════════════
    #  响应机制（keyword：响应）
    # ═══════════════════════════════════════════════════════════════════════════

    def _auto_response(self, event: Event):
        """响应检查：敌方回合、响应牌在手牌、条件满足时自动打出一张。

        由 broadcast 在监听器全部触发后调用（check_response=True 时）。
        响应规则（wiki「关键字-响应」）：只在敌方回合触发；卡牌必须在手牌；
        满足条件时自动消耗所需鬼火并自动打出。至多打出一张（手牌顺序，确定性）。
        response_condition / on_response 收到的 event 是原始事件（经 event= 传入），
        与监听器看到的 `e.event` 一致，因此条件可直接访问 event.hero / event.player 等。
        """
        responder = self.current_player.opponent
        src = getattr(event, "event", event)   # 解包：broadcast 包装了一层 Event
        target = self._response_target(event)
        responder.sort_hand()  # 响应扫描按整理后的手牌顺序（同优先度从左到右依次响应）
        for card in responder.hand.cards:
            # 必须同时声明 response_trigger + response_condition 才走新机制
            if card.response_trigger is None or card.response_condition is None:
                continue
            if card.response_trigger != src.type:
                continue
            conds = card.response_condition
            conds = conds if isinstance(conds, tuple) else (conds,)
            if not all(c(card, src, target) for c in conds):
                continue
            can_play, _ = self.can_play_card(responder, card)
            if not can_play:
                continue
            self._play_response_card(responder, card, src, target)
            return  # 每事件至多一张响应

    def _response_target(self, event: Event):
        """防御式提取响应扫描的上下文目标。

        只对 "hero attack" / "about to die" 有定义；其余事件类型返回 None。
        src = event.event 兼容经 event= 传入的原始事件（如手工广播的攻击事件）。
        不把 target 挂到 event.target 上：handle_event 的 deal damage 等分支把
        event.target 当列表遍历，且 step 路径二次广播会让读 event.target 的
        监听器双触发；守护重定向走 selected_targets 通道，互不干扰。
        """
        src = getattr(event, "event", event)
        if event.type == "hero attack":
            t = getattr(src, "target", None)
            if t is not None:
                return t
            if hasattr(src, "player") and hasattr(src, "hero"):
                return self._resolve_attack_target(src.player, src.hero)
            return None
        if event.type == "about to die":
            return getattr(src, "hero", None)
        return None

    def _play_response_card(self, player, card, event, target):
        """自动打出一张响应牌。

        战斗牌响应（wiki 规则）：只施加卡牌效果与力量/护甲，不使对应式神发起
        攻击（不广播 HeroAttackEvent）。buff 暂存于 _pending_response_cleanups，
        由 handle_event 的 "hero attack" 分支在战斗结算后统一排空。
        法术响应：走正常 play_card（如射怪鸟事）。
        """
        # 响应战斗牌不经过 play_card（只加 buff 不重新发起攻击），费用在此统一扣
        # （先于广播：被魔音扰心拦截时费用同样消耗——既有语义）；法术响应走
        # play_card，由 play_card 内部统一扣费。
        if card.type == "attack":
            self._consume_fire(player, card)
            # 响应牌出牌也广播前置事件（PrePlayCardEvent，response=True；
            # step 之外的出牌通道），供监听器在生效前介入（魔音扰心主动效果
            # 依赖此点拦截敌方响应牌）。check_response=False：响应牌自身不再
            # 触发其它响应（响应不可再响应）。
            use_evt = PrePlayCardEvent(player, card, response=True)
            self.broadcast("pre play card", event=use_evt, check_response=False)
            if getattr(use_evt, "revert", False):
                return   # 被监听器拦截（如魔音扰心）：响应牌不生效（费用处理见上方注释）
            hero = card.get_corresponding_hero()
            # 记录战前 atk/defense，战斗结算后整体还原：响应牌是防御方，战斗过程中
            # defense（护甲）会被伤害消耗，对称相减会把 defense 减成负数泄漏到后续回合。
            pre_atk, pre_def = hero.atk, hero.defense
            hero.atk += card.buff_atk
            hero.defense += card.buff_def
            if hasattr(card, "on_play"):
                for cb in card.on_play:
                    result = cb(card)
                    if isinstance(result, Event):
                        self.handle_event(result)
            resp = card.on_response
            for cb in (resp if isinstance(resp, tuple) else (resp,) if resp else ()):
                result = cb(card, event, target)
                if isinstance(result, Event):
                    self.handle_event(result)
            player.move_card_to_used(card)
            self._pending_response_cleanups.append((card, hero, pre_atk, pre_def))
            # 结算完成事件：与 play_card 末尾一致，「使用牌时」类触发被动
            # （凤凰火投射等）同样监听响应打出的完成。
            self.broadcast("play card",
                           event=PlayCardEvent(player, card, response=True),
                           check_response=False)
        else:
            self.play_card(player, card, via_response=True)

    def _consume_fire(self, player, card):
        """打出一张牌的鬼火消耗（主动打出 / 响应打出统一走此实现）。

        fire_cost_penalty：幸运兔兔增强「敌方下回合所有卡牌鬼火消耗+1」。
        无消耗属性只免基础消耗，仍需支付惩罚；瞬发免费同样只免基础消耗。
        """
        penalty = getattr(player, "fire_cost_penalty", 0)
        if CardAttributes.NO_FIRE_CONSUMPTION in card.attributes:
            if penalty > 0:
                player.fire_cnt -= penalty
            return
        if CardAttributes.INSTANT in card.attributes and not player.instant_used:
            player.instant_used = True
            if penalty > 0:
                player.fire_cnt -= penalty
            return
        player.fire_cnt -= 1 + penalty

    def _drain_response_cleanups(self):
        """执行并清空响应战斗牌的战后清理（幂等）。

        响应战斗牌在广播期间暂存战前 atk/defense，战斗结算后还原为战前值。
        若战斗未发生（事件被 revert / 攻击方已死），也在此处恢复，避免 buff 泄漏。
        """
        for card, hero, pre_atk, pre_def in self._pending_response_cleanups:
            if hasattr(card, "after_play"):
                for cb in card.after_play:
                    result = cb(card)
                    if isinstance(result, Event):
                        self.handle_event(result)
            hero.atk = pre_atk
            hero.defense = pre_def
        self._pending_response_cleanups = []


    # ═════════════════════════════════════════════════════════════════════════
    #  增强（wiki 关键字-增强）通用机制
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _passing_enhances(card):
        """卡牌声明（CardEnhance）中当前满足条件的增强项。"""
        return [enh for enh in (getattr(card, "enhance", None) or ())
                if enh.cond(card)]

    @staticmethod
    def _enhanced_view(card):
        """判定用视图（#13 用户裁决）：满足条件的增强属性追加在复制体上重新判定，
        原卡不被修改。can_play_card 以此视图判定，瞬发等可打出性属性因此能在
        0 鬼火时通过判定。

        不走 Card.__copy__：其经 Card.__init__ 重建会把 owner/played_by 硬编码
        重置为 None；此处浅拷贝 __dict__ 并只替换 attributes 列表。
        """
        enhances = Game._passing_enhances(card)
        if not enhances:
            return card
        view = object.__new__(Card)
        view.__dict__ = dict(card.__dict__)
        view.attributes = list(card.attributes)
        for enh in enhances:
            for attr in enh.attributes:
                if attr not in view.attributes:
                    view.attributes.append(attr)
        return view

    def _apply_enhance(self, card):
        """确定打出后（play_card 开头）把满足条件的增强写到即将打出的卡上（幂等）。

        属性追加（瞬发等参与随后的鬼火结算）、效果回调续在 on_play 尾部（随类型
        正常结算、可返回事件）。不还原（#13 用户裁决）：增强只写在确认打出的这
        张卡上，打出后随卡进入弃牌堆。已实装项以卡上 _enhance_applied（enhance
        对象 id 集合）记录，防止挂起选目标重放时重复追加效果。
        """
        applied = getattr(card, "_enhance_applied", None)
        if applied is None:
            applied = set()
            card._enhance_applied = applied
        for enh in self._passing_enhances(card):
            if id(enh) in applied:
                continue
            applied.add(id(enh))
            for attr in enh.attributes:
                if attr not in card.attributes:
                    card.attributes.append(attr)
            if enh.on_play:
                card.on_play = tuple(getattr(card, "on_play", ())) + enh.on_play

    def can_play_card(self, player: Player, card: Card):
        msg = None
        # 增强（wiki 关键字-增强）：以「满足条件增强后的复制体」判定，原卡不被
        # 修改；确定打出后在 play_card 开头实装（#13 用户裁决）。
        card = self._enhanced_view(card)
        if not card.owner == player:
            msg = "trying to play a card doesn't owned"
        need_fire = True
        if CardAttributes.NO_FIRE_CONSUMPTION in card.attributes:
            need_fire = False
        elif CardAttributes.INSTANT in card.attributes and player.instant_used == False:
            need_fire = False
        # 鬼火消耗惩罚（幸运兔兔增强）：本局敌方下回合所有卡牌鬼火消耗+1。
        # 无消耗属性只免基础消耗，仍需满足惩罚所需的鬼火。
        penalty = getattr(player, "fire_cost_penalty", 0)
        required = (1 if need_fire else 0) + penalty
        if required > 0 and player.fire_cnt < required:
            msg = f"trying to play {card} when there's no fire remaining"
        hero = card.get_corresponding_hero()
        if not card.is_token:
            # 非 token 卡必须属于场上式神；无对应式神视为不可打出
            if hero is None:
                msg = "trying to play a card without a corresponding hero"
            elif card.level_req > hero.level:
                msg = "trying to play a card when corresponding hero level is not enough"
            elif hero.state == "dead" and CardAttributes.CAN_PLAY_WHEN_DEAD not in card.attributes:
                msg = "trying to play a card whose corresponding hero is dead without the ability to play when dead"
            elif hero.stunned:
                msg = "trying to play a card whose corresponding hero is stunned"
            elif getattr(card, "form", "") and getattr(hero, "form", None) and card.form != hero.form:
                msg = "trying to play a card whose form doesn't match the current hero form"
        # token 卡（食材/佳肴等）无对应式神，跳过式神等级/状态检查，可随时打出
        # ── 目标候选为空的牌判定为不可打出（#13 用户裁决）：手牌打出在判定阶段
        # 即拦截，play_card 内的「放弃打出」分支仅作引擎内部自动使用路径的兜底。
        # 探测以快照/还原方式运行 select_target 回调，不污染牌手选择状态。──
        if msg is None and card.select_target is not None and player.selected_targets is None:
            prev_state = player.state
            prev_candidates = player.candidate_targets
            prev_pending_card = player.pending_card
            for select in card.select_target:
                select(card)
            empty = not player.candidate_targets
            player.state = prev_state
            player.candidate_targets = prev_candidates
            player.pending_card = prev_pending_card
            if empty:
                msg = "trying to play a card with no valid targets"
        if msg is not None:
            return False, msg
        return True, msg


    def step(self, player: Player, action: Action):
        """
        The step function should only be used for handling actions directly from players, e.g. playing card.
        All the effects triggered by a card should be handled by handle_event function below.
        """
        if action is None:
            return
        # hero attack 事件广播前解析并挂载攻击目标，供 e.event.target 类监听器使用。
        # 目标解析逻辑与 handle_event 的 "hero attack" 分支保持一致。
        if action.type == "hero attack":
            action.target = self._resolve_attack_target(player, action.hero)
            # 复位离殇之舞的一次性标记：上一次出击若被拒绝（眩晕/鬼火不足等）可能泄漏
            player._skip_inspiration_consume = False
        # check_response=False：step 的 hero attack 会再经 handle_event 二次广播
        # 同一攻击；响应只在 handle_event 的广播点扫描（见 broadcast），保证一次
        # 攻击至多打出一张响应、且监听器先于响应结算。
        # play card 动作广播为 "play card action"；事件层 "pre play card"
        # （结算前，否定/注入）与 "play card"（结算后，触发被动）均由
        # play_card / _play_response_card 在对应时机广播。
        self.broadcast(action.type, event=action, check_response=False)
        if hasattr(action, "revert") and action.revert == True:
            return
        match action.type:
            case "reject initial pick":
                if player.state != PlayerState.INITIAL_PICK:
                    print("trying to reject initial pick while playing, will ignore")
                    return
                if type(action.card) is not Card:
                    print("target to reject is not a card")
                    return
                player.hand.remove(action.card)
                player.deck.append(action.card)
                player.draw()
                player.initial_pick_reject_left -= 1
                if player.initial_pick_reject_left == 0:
                    self.step(player, EndTurn())

            case "end turn":
                if player.state == PlayerState.INITIAL_PICK:
                    player.state = PlayerState.WAITING
                    player.initial_pick_reject_left = 0
                    self.current_player = self.current_player.opponent
                    self.begin_turn()
                    return
                if not self.current_player == player:
                    print("trying to end a turn when it's not his turn, will ignore")
                    return
                for hero in self.current_player.heroes:
                    if hasattr(hero, "on_self_round_end"):
                        for event in hero.on_self_round_end:
                            if isinstance(event(hero), Event):
                                self.handle_event(event(hero))
                self.current_player = self.current_player.opponent
                self.begin_turn()

            case "upgrade hero":
                if not self.current_player == player:
                    print("trying to upgrade a hero when it's not his turn, will ignore")
                    return
                if self.current_player.upgrade_remaining <= 0:
                    print("trying to upgrade multiple heroes, will ignore")
                    return
                if action.hero.level >= 3:
                    print("trying to upgrade a hero already at level 3, will ignore")
                    return
                if getattr(action.hero, 'is_summoned', False):
                    print("trying to upgrade a summoned hero, will ignore")
                    return
                if type(action.hero) != Hero:
                    print("target to upgrade is not a hero")
                    return
                if action.hero.owner is not player:
                    print(f"hero to upgrade does not belong to player, hero belongs to {action.hero.owner} but player is {player}")
                    return
                for hero in player.heroes:
                    if hero.level < action.hero.level:
                        print("trying to upgrade a hero whose current level is not lowest")
                        return
                action.hero.Upgrade()
                if hasattr(action.hero, "on_upgrade"):
                    for event in action.hero.on_upgrade:
                        if isinstance(event(action.hero), Event):
                            self.handle_event(event(action.hero))
                self.current_player.upgrade_remaining -= 1

            case "play card action":
                if not self.current_player == player:
                    print("trying to play a card when it's not his turn, will ignore")
                    return
                can_play, msg = self.can_play_card(player, action.card)
                if not can_play:
                    print(msg)
                    return
                # ── 蓄力打出（发起）：等量消耗此刻支付（wiki：消耗与直接出牌等量的
                # 鬼火/瞬发消耗），卡离手进弃牌堆（气绝不返还），式神进入蓄力状态；
                # 本回合不结算，下个己方回合开始由 begin_turn 统一打出。不进 play_card。──
                if getattr(action, "use_charge", False) and CardAttributes.CHARGE in action.card.attributes:
                    charge_hero = action.card.get_corresponding_hero()
                    if charge_hero is None or not charge_hero.is_alive or charge_hero.charging_card is not None:
                        print("trying to charge a card without a valid hero, or hero is already charging")
                        return
                    self._consume_fire(player, action.card)
                    player.move_card_to_used(action.card)
                    charge_hero.charging_card = action.card
                    player.charging_order.append(charge_hero)
                    return
                # 鬼火扣除 / 爆能 / 目标选择统一在 play_card 内结算
                self.play_card(player, action.card, action.target, action.use_blast)

            case "hero attack":
                if not self.current_player == player:
                    print("trying to attack when it's not his turn")
                    return
                if not action.hero.is_alive:
                    print("trying to attack with a dead hero")
                    return
                if action.hero.stunned:
                    print("trying to attack with a stunned hero")
                    return
                if player.attack_available == False:
                    print("trying to attack when attack is not available")
                    return
                if not HeroAttributes.AGILE in action.hero.attributes and not HeroAttributes.VALIANT in action.hero.attributes and player.fire_cnt <= 0:
                    print("trying to attack when there's no fire left")
                    return
                if not action.hero.owner == player:
                    print("trying to let a non-friendly hero attack")
                    return
                if HeroAttributes.HUNTING in action.hero.attributes and player.selected_targets is None:
                    candidates = [h for h in player.opponent.heroes if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes]
                    if len(candidates) > 1:
                        self.pending_action = action
                        player.candidate_targets = candidates
                        player.state = PlayerState.SELECTING_TARGET
                        return
                    player.selected_targets = [candidates[0]] if len(candidates) == 1 else None
                # 鼓舞：牌手加成，己方任意式神出击时消耗
                # 记录攻击来源，供击杀事件归属 killer；鸮之守护记录最后攻击的式神
                self._last_damage_source = action.hero
                player.last_attacking_hero = action.hero
                # 鼓舞生效数值经 InspireEvent 广播：觉醒·不知火等监听器可在
                # 应用前修改本次生效值（卡牌层逻辑，引擎不做任何特判）。
                # 生效值转移到式神身上的独立变量（不并入 atk），伤害结算时由
                # attack() 单独读取，出击结束后归零——攻击方中途气绝时
                # check_death 的 atk 重置不再与之叠加出幽灵数值。
                evt = InspireEvent(player, action.hero, player.inspiration_atk, player.inspiration_def)
                self.handle_event(evt)
                action.hero.inspiration_atk = evt.atk
                # 一次性标记：离殇之舞等卡牌让本次出击不消耗鼓舞（仿 _suppress_combat_damage）
                if not getattr(player, '_skip_inspiration_consume', False):
                    player.inspiration_atk = 0
                    player.inspiration_def = 0
                    # 鼓舞关键字/特殊效果随池消耗：逐个作用于即将出击的式神
                    # （如「本回合获得贯通」给 e 叠加贯通），须在战斗结算前生效
                    _effects, player.inspiration_effects = player.inspiration_effects, []
                    for _f in _effects:
                        _f(action.hero)
                player._skip_inspiration_consume = False
                try:
                    special_attack = getattr(action.hero, 'special_attack', None)
                    if special_attack is not None:
                        # 特殊攻击（召唤物等）：不走正常战斗流程，由回调自行结算
                        # 伤害，直接读取式神身上的鼓舞生效值；鼓舞护盾不用于特殊
                        # 攻击（既有行为维持不变）
                        special_attack(action.hero)
                    else:
                        # 鼓舞护盾并入 defense（战斗结束不回退，既有行为维持不变）
                        action.hero.defense += evt.defense
                        self.handle_event(HeroAttackEvent(player, action.hero))
                finally:
                    action.hero.inspiration_atk = 0
                if HeroAttributes.AGILE in action.hero.attributes:
                    player.fire_cnt += 1
                    action.hero.attributes.remove(HeroAttributes.AGILE)
                if not HeroAttributes.VALIANT in action.hero.attributes:
                    player.attack_available = False
                if not HeroAttributes.AGILE in action.hero.attributes:
                    player.fire_cnt -= 1
                player.selected_targets = None

            case "select target":
                player.selected_targets = [action.target]
                player.state = PlayerState.PLAYING
                player.candidate_targets = []
                player.pending_card = None
                pending_action = self.pending_action
                self.pending_action = None
                if pending_action.type == "hero attack":
                    self.step(player, pending_action)
                else:
                    # 保留 use_blast：爆能卡在目标选择后仍要触发爆能
                    # 保留 use_charge：蓄力卡在目标选择后仍走蓄力结算（免扣费）
                    self.play_card(player, pending_action.card, None,
                                   getattr(pending_action, "use_blast", False),
                                   getattr(pending_action, "use_charge", False))
                player.selected_targets = None

            # ── 新增：移动式神 ──────────────────────────────────────────
            case "move hero":
                if not self.current_player == player:
                    print("trying to move a hero when it's not his turn")
                    return
                if action.hero.stunned:
                    print("trying to move a stunned hero")
                    return
                if action.hero.owner is not player:
                    print("trying to move a non-friendly hero")
                    return
                if not action.hero.is_alive:
                    print("trying to move a dead hero")
                    return
                if action.to_battle:
                    action.hero.move_to_battle()
                else:
                    action.hero.move_to_standby()

            # ── 新增：多选一 ──────────────────────────────────────────
            case "select option":
                player.selected_option = action.option_index
                player.state = PlayerState.PLAYING
                if player._pending_option_callback:
                    cb = player._pending_option_callback
                    player._pending_option_callback = None
                    cb(action.option_index)

            case _:
                print(f"stepping with the game with undefined action type {action.type}, check code!")

        while len(self.action_queue) > 0:
            self.handle_event(self.action_queue.pop(0))


    def handle_event(self, event: Event):
        """
        This function is used for handling small events. Inputs directly from the player should be handled in the step function above.
        """
        if event is None:
            return
        self.broadcast(event.type, event=event)
        if hasattr(event, "revert") and event.revert == True:
            # 事件被 revert（如鸦羽疾走取消攻击）：响应战斗牌暂存的 buff 未被战斗
            # 结算消费，防御性排空，避免泄漏。
            self._drain_response_cleanups()
            return
        match event.type:
            case "give buff":
                for e in event.target:
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                    if event.attr == "hp":
                        setattr(e, "hp", getattr(e, "hp") + event.value)
                        setattr(e, "current_max_hp", getattr(e, "current_max_hp") + event.value)
                    else:
                        setattr(e, event.attr, getattr(e, event.attr) + event.value)

            case "heal":
                for e in event.target:
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                    e.hp += event.value
                    if e.hp > e.current_max_hp:
                        e.hp = e.current_max_hp

            case "deal damage":
                self._last_damage_source = event.source
                for e in event.target:
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                    hp_before = getattr(e, "hp", 0)
                    dmg = event.value
                    # 对牌手造成的非战斗伤害 +X（来源式神本回合的 round_buff_player_damage）
                    if isinstance(e, Player):
                        dmg += getattr(event.source, "round_buff_player_damage", 0)
                    # 免疫此伤害：监听器（卡牌/式神层）把 e 加入 event.immune_targets → 不扣血，
                    # 但贯通的“理论过量”仍按下方逻辑转移（默认机制，免疫不阻断溢出）。
                    if e not in getattr(event, "immune_targets", ()):
                        e.receive_damage(dmg)
                    e.check_death()
                    # 贯通（法术/幻境等非战斗伤害）：理论过量转移给受击式神所属牌手
                    if isinstance(e, Hero) and HeroAttributes.PENETRATE in getattr(event.source, "attributes", []):
                        excess = dmg - hp_before
                        if excess > 0:
                            owner_player = e.owner
                            if owner_player is not None:
                                self.handle_event(DealDamage(excess, event.source, [owner_player]))
                # 结算后广播 DamageDealt（纯通知）：非战斗伤害通道的统一点，供
                # 「造成伤害」类监听（五丸/镰鼬/妖狐计数/妖刀姬等）统一接收。
                self.broadcast("damage dealt",
                               event=DamageDealt(event.value, event.source, event.target,
                                                 getattr(event, "damage_type", "spell")),
                               check_response=False)

            case "revive":
                for e in event.target:
                    if e.state != "dead":
                        print("trying to revive a non-dead target")
                        continue
                    e.revive()
                    # 复活完成后再广播 AfterRevive：监听器（桃花妖被动等）看到的
                    # 目标已存活，give buff 不再因气绝跳过而丢失。
                    # 注意不放 revive() 内——死亡流程中被中途自复活的式神
                    # （九命猫 on_death）随后还会执行 check_death 末尾的 hp/atk
                    # 重置，会把加成再冲掉
                    self.handle_event(AfterRevive(event.source, [e]))

            case "hero attack":
                player = event.player
                if not event.hero.is_alive:
                    print("trying to attack with a dead hero")
                    # 响应战斗牌（守护/报复）的 buff 若未被战斗结算消费，防御性排空
                    self._drain_response_cleanups()
                    return

                # RANGED: 远程式神不进入战斗区，从准备区攻击
                is_ranged = HeroAttributes.RANGED in event.hero.attributes
                if not is_ranged:
                    player.advance_hero(event.hero)

                target = self._resolve_attack_target(player, event.hero)
                if target is not None:
                    self.attack(event.hero, target, event.card)
                # 响应战斗牌 buff 只作用于本次战斗：战斗结算后排空（运行 after_play、
                # 移除 buff）。若响应牌在广播时被打出但战斗未发生，也在此处恢复。
                self._drain_response_cleanups()

            case "summon":
                player = event.player
                hero = Hero.GetHero(event.hero_class)
                hero.assign_owner(player)
                hero.is_summoned = True
                hero.level = 1
                # ── 融合（wiki 关键字-融合）：带融合的新召唤物进场时，若己方场上
                # 已有同组（fuse_group）存活融合体，则合并入既有者——身材相加、
                # 关键词并集，既有者留场，新召唤物不单独进场。──
                fused = False
                if HeroAttributes.FUSE in hero.attributes:
                    for other in player.heroes:
                        if (other is not hero and other.is_alive
                                and HeroAttributes.FUSE in other.attributes
                                and getattr(other, "fuse_group", None) == getattr(hero, "fuse_group", None)):
                            self._fuse_summon(other, hero)
                            fused = True
                            break
                if not fused:
                    player.heroes.append(hero)
                    # 召唤物直接进战斗区（原战斗区式神由 move_to_battle 处理：召唤物离场/普通式神撤回准备区）
                    hero.move_to_battle()

            case "draw selected card from deck":
                if event.card not in event.player.deck.cards:
                    # 推理模式下牌组为假牌，允许直接置入手牌
                    if type(event.player).__name__ in ("InferencePlayer", "InferenceOpponent"):
                        event.player.hand.append(event.card)
                        event.player.sort_hand()
                        return
                    print("trying to draw a card not in deck")
                    return
                event.player.deck.remove(event.card)
                event.player.hand.append(event.card)
                event.player.sort_hand()

            # ── 新增：倒计时事件 ────────────────────────────────────
            case "countdown":
                pass  # 倒计时的副作用由 hero.tick_countdown() 中的 on_countdown 回调处理

            # ── 新增：移动事件 ────────────────────────────────────────
            case "move":
                pass  # 移动的副作用由 on_move 回调处理，此处仅做广播

            # ── 新增：投射事件 ────────────────────────────────────────
            case "projectile":
                self._last_damage_source = event.source
                dealt = []
                for e in event.target:
                    if e is None:
                        # 战斗区为空时，投射改为直接打敌方牌手
                        e = event.source.owner.opponent if event.source.owner else None
                    if e is None:
                        continue
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                    # 免疫此伤害：监听器（卡牌/式神层）把 e 加入 event.immune_targets → 不扣血
                    if e not in getattr(event, "immune_targets", ()):
                        e.receive_damage(event.value)
                        e.check_death()
                        dealt.append(e)
                # 投射结算后广播 DamageDealt（纯通知）：此前投射通道无伤害事件，
                # 导致「造成伤害」类监听（五丸/镰鼬/妖狐计数/魂狩反射等）漏触发。
                if dealt:
                    self.broadcast("damage dealt",
                                   event=DamageDealt(event.value, event.source, dealt, "projectile"),
                                   check_response=False)

            # ── 新增：眩晕事件 ──────────────────────────────────────
            case "stun":
                if isinstance(event.target, Hero):
                    event.target.stun()

            case "unstun":
                if isinstance(event.target, Hero):
                    event.target.unstun()

            # ── 新增：永久死亡 ──────────────────────────────────────
            case "permanent death":
                hero = event.hero
                hero.is_alive = False
                hero.state = "dead"
                hero.round_until_alive = 999  # 永不复活
                # 移除该式神在玩家手牌和牌库中的所有专属牌
                # 豁免「向死而生」：它专用于永久气绝时救回九命猫，见 heroes.py 九命猫注释
                player = hero.owner
                if player:
                    to_remove_hand = [c for c in player.hand.cards
                                      if c.hero == hero.type_name and getattr(c, 'name', '') != '向死而生']
                    for c in to_remove_hand:
                        player.hand.remove(c)
                    to_remove_deck = [c for c in player.deck.cards
                                      if c.hero == hero.type_name and getattr(c, 'name', '') != '向死而生']
                    for c in to_remove_deck:
                        player.deck.remove(c)

            # ── 新增：机制事件（仅广播，副作用由监听器处理）───────────────
            case "fortune roll":
                pass
            case "fortune success":
                pass
            case "illusion played":
                pass
            case "illusion destroyed":
                pass
            case "illusion damage":
                pass
            case "illusion durability gain":
                pass  # 仅广播，由 Game.gain_illusion_durability 派发（月坠等监听）
            case "cook":
                pass
            case "energy gain":
                pass
            case "energy spend":
                pass
            case "armor break applied":
                pass
            case "inspire":
                pass  # 仅广播：鼓舞生效数值事件（觉醒·不知火等监听器可修改 atk/defense）
            case "hero kill":
                pass
            case "about to die":
                pass  # 仅广播，供「射怪鸟事」等响应牌在死亡结算前触发；死亡仍照常发生
            case "morph leave":
                pass  # 仅广播，供「形态牌离场/被消灭时触发 XXX」被动（如一目连）监听
            case "after revive":
                pass  # 仅广播，供复活加成类被动（桃花妖）监听；广播点在 case "revive" 内

            case _:
                print(f"handling event with undefined event type {event.type}, check code!")


    def play_card(self, player: Player, card: Card, target=None, use_blast: bool = False,
                  use_charge: bool = False, via_response: bool = False):
        # ── 增强（wiki 关键字-增强）：判定通过、确定打出后，在结算开头把增强
        # 写到这张即将打出的卡上（不还原，#13 用户裁决，见 _apply_enhance）──
        self._apply_enhance(card)
        # ── 爆能：先于选目标与鬼火结算（on_blast 授予的瞬发可免本张鬼火并占用
        # 瞬发名额，授予的追猎可参与下方选目标）。处理后置 use_blast=False：
        # 挂起重放（select target → play_card）携带的是 False，不会二次爆能。──
        if use_blast and CardAttributes.BLAST in card.attributes:
            hero = card.get_corresponding_hero()
            if hero is not None and hero.counters.get("energy", 0) >= card.energy_cost:
                hero.counters.dec("energy", card.energy_cost)
                for callback in getattr(card, "on_blast", ()):
                    result = callback(card)
                    if isinstance(result, Event):
                        self.handle_event(result)
                self.handle_event(EnergySpendEvent(hero, card.energy_cost, card))
            use_blast = False   # 爆能选择已消费（无论是否成功），重放不再触发
        # ── 追猎选目标门：战斗牌攻击式神带追猎且未指定目标时，先任选一名敌方式神
        # （存活、等级>0，含准备区；帷幕只限制卡牌主动选目标，不影响追猎）──
        attack_hero = card.get_corresponding_hero() if card.type == "attack" else None
        if (attack_hero is not None and attack_hero.is_alive
                and HeroAttributes.HUNTING in attack_hero.attributes
                and player.selected_targets is None):
            candidates = [h for h in player.opponent.heroes if h.is_alive and h.level > 0]
            if len(candidates) > 1:
                # 挂起本次打出，进入 SELECTING_TARGET（重放时鬼火/爆能/蓄力均不再重复结算）
                self.pending_action = PlayCard(card, use_blast=use_blast, use_charge=use_charge)
                player.candidate_targets = candidates
                player.state = PlayerState.SELECTING_TARGET
                return
            # 单候选自动选定；零候选保持 None → 目标解析为不攻击（打出照常结算）
            player.selected_targets = [candidates[0]] if len(candidates) == 1 else None
        if card.select_target is not None:
            if player.selected_targets is None:
                target_valid = False
                if target is not None:
                    if card.require_target is not None:
                        target_valid = (
                            len(target) == len(card.require_target)
                            and all(t in req(card) for t, req in zip(target, card.require_target))
                        )
                    else:
                        target_valid = True
                if target_valid:
                    player.selected_targets = target
                else:
                    self.pending_action = PlayCard(card, use_blast=use_blast, use_charge=use_charge)
                    for event in card.select_target:
                        event(card)
                    if player.candidate_targets:
                        player.state = PlayerState.SELECTING_TARGET
                        return
                    # 可选目标为空（如自动打出的牌目标已失效）：放弃本次打出，
                    # 避免卡在 SELECTING_TARGET 且无合法动作。
                    self.pending_action = None
                    player.pending_card = None
                    player.candidate_targets = []
                    player.state = PlayerState.PLAYING
                    return

        # ── 使用牌前置事件（PrePlayCardEvent）：目标选择已完成，此后确定结算。
        # 仅供需在结算生效前介入的监听器：否定（魔音扰心 revert）与注入
        # （不夜之舞/心技一体写入 buff）。「使用牌时」类触发被动听结算后的
        # "play card"（PlayCardEvent，函数末尾）。被拒绝/放弃的打出不会走到
        # 这里；check_response=False 与既有出牌通道一致（出牌不触发响应扫描）。
        # 被拦截则整体放弃结算。──
        play_evt = PrePlayCardEvent(player, card, response=via_response)
        self.broadcast("pre play card", event=play_evt, check_response=False)
        if getattr(play_evt, "revert", False):
            player.selected_targets = None
            return

        # ── 鬼火消耗：主动打出 / 响应打出统一走此实现。置于全部挂起点之后——
        # select target 重放只会到达这里一次，不会二次扣费；放弃出牌发生在
        # 扣费之前，无需退款。蓄力结算（use_charge）的费用已在发起蓄力时由
        # step 支付，此处免扣并执行蓄力强化（on_charge 先于类型结算调整卡牌）。──
        if use_charge:
            for callback in getattr(card, "on_charge", ()):
                result = callback(card)
                if isinstance(result, Event):
                    self.handle_event(result)
        else:
            self._consume_fire(player, card)

        # 协战牌：目标选择（选定打出式神）完成后，记录 played_by。
        # 之后 get_corresponding_hero 直接返回该式神（决定派系、分支与羁绊）。
        if getattr(card, "coop", False) and player.selected_targets:
            card.played_by = player.selected_targets[0]

        match card.type:
            case "attack":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)
                for hero in player.heroes:
                    if hero.type_name == card.hero:
                        attacking_hero = hero
                if hasattr(card, "buff_atk"):
                    # 战斗牌力量加成折入独立变量 combat_buff_atk（对标
                    # round_buff_atk）：伤害结算经 _get_attack_power 读取；
                    # 中途气绝时 check_death 直接清零，与战后回退不再有算术冲突
                    attacking_hero.combat_buff_atk += card.buff_atk
                if hasattr(card, "buff_def"):
                    attacking_hero.defense += card.buff_def

                # 战斗牌默认不触发鼓舞（不应用、不消耗）；鼓舞与战斗牌的交互由不夜之舞等卡牌监听器负责
                self.handle_event(HeroAttackEvent(player, attacking_hero, card))

                if hasattr(card, "after_play"):
                    for event in card.after_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)
                # 战后清空（而非 -= buff_atk）：若式神已气绝，check_death 已清零，
                # 再减会得到负数
                attacking_hero.combat_buff_atk = 0

            case "spell" | "coop":
                # 协战牌与法术牌同走 on_play；协战牌的“选择打出式神”已在上面通过 select_target 完成
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        result = event(card)
                        if isinstance(result, Event):
                            if isinstance(result, DealDamage):
                                if hasattr(card.get_corresponding_hero(), "round_buff_spell_damage"):
                                    result.value += card.get_corresponding_hero().round_buff_spell_damage
                            self.handle_event(result)

            case "illusion":
                # 幻境牌：跑 on_play 后进入幻境区驻场，不进入 used_card
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)
                player.illusion_zone.append(card)
                self.handle_event(IllusionPlayedEvent(player, card))

            case "awaken":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)
                hero = card.get_corresponding_hero()
                hero.is_awakened = True
                if hasattr(card, "after_play"):
                    for event in card.after_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)

            case "morph":
                hero = card.get_corresponding_hero()
                # 形态牌离场：已有形态被新形态替换时，先广播旧形态离场，供「形态牌
                # 离场/被消灭时触发 XXX」类被动（如一目连倒计时）监听。必须在跑新形态
                # on_play 之前广播，否则新形态会覆盖 hero.on_countdown 等旧形态状态。
                if hero.morphed_id != 0:
                    self.handle_event(MorphLeaveEvent(hero, hero.morphed_id, "replace"))
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)
                # 保留所有现有加成，叠加在形态牌的新基础值之上
                # perm_buff  = get_permanent_buff 累计（觉醒等，可跨越形态与死亡）
                # give_buff  = GiveBuff 效果（不修改 original，死亡后丢失，但形态时保留）
                give_buff_atk = hero.atk - hero.original_atk - hero.perm_buff_atk
                give_buff_hp = hero.current_max_hp - hero.original_hp - hero.perm_buff_hp
                # 形态牌不修改 original（original 是真·基础身材，用于死亡→复活时还原）
                hero.atk = card.atk + hero.perm_buff_atk + give_buff_atk
                hero.current_max_hp = card.hp + hero.perm_buff_hp + give_buff_hp
                hero.hp = hero.current_max_hp  # 形态牌满血
                hero.morphed_id = card.id
                if hasattr(card, "after_play"):
                    for event in card.after_play:
                        result = event(card)
                        if isinstance(result, Event):
                            self.handle_event(result)

        # 幻境/Token 卡牌使用后不进入 used_card
        if card.type == "illusion":
            # 幻境已在 illusion_zone 中，只需从手牌移除
            if card in player.hand.cards:
                player.hand.remove(card)
        elif card.is_token:
            player.hand.remove(card)
        elif getattr(card, "bounce", False):
            card.bounce = False   # 弹回一次性（wiki 关键字-弹回）：使用后回手并失去此能力
            # 保留在手牌，不进入弃牌堆
        else:
            player.move_card_to_used(card)
        player.selected_targets = None

        # ── 使用牌完成事件（PlayCardEvent）：结算与卡牌去向均已落定。
        # 「使用牌时」类触发被动（凤凰火投射/火取魔计数等）在此广播——
        # 监听器读到的是结算后的战场状态（投射目标按结算后的对手战斗区
        # 解析等）。此处不再处理 revert：牌已实际打出。──
        self.broadcast("play card", event=PlayCardEvent(player, card, response=via_response),
                       check_response=False)


    # ═══════════════════════════════════════════════════════════════════════════
    #  运势 / 烹饪
    # ═══════════════════════════════════════════════════════════════════════════

    def roll_fortune(self, source_hero, threshold: int) -> bool:
        """运势判定：d6 >= threshold 则成功。

        骰子结果取自 self.rng.randint(1, 6)——推理模式下可 push_override 手动指定。
        广播 FortuneRollEvent 供监听器修改 event.result（座敷童子重投 / 萌即正义强制 6）。
        成功则广播 FortuneSuccessEvent 并返回 True。
        """
        result = self.rng.randint(1, 6)
        event = FortuneRollEvent(source_hero, threshold, result)
        self.handle_event(event)
        result = event.result   # 监听器可能已修改
        if result >= threshold:
            # 统计全局运势成功次数（福满乾坤「本局游戏双方运势成功12次」条件）
            self.counters.ensure("fortune_success_total", persistent=True)
            self.counters.inc("fortune_success_total")
            self.handle_event(FortuneSuccessEvent(source_hero, result))
            return True
        return False


    def cook(self, player: Player, hero: Hero):
        """烹饪：生成食材 Token 入手牌；若手牌已有 ≥2 食材则消耗 3 食材合成 1 佳肴。

        品阶由 hero.level 决定：1→良(+1)，2→优(+2)，3→极(+3)。
        类型随机：山珍→atk，海味→hp，时蔬→atk+hp。佳肴效果 = 3 食材之和。
        """
        tier = max(1, min(3, hero.level))
        tier_suffix = {1: "Liang", 2: "You", 3: "Ji"}[tier]
        ing_name = self.rng.choice(["ShanZhen", "HaiWei", "ShiShu"])
        card_name = ing_name + tier_suffix

        # 食材是中立 Token，不属于任何式神（hero 保持空字符串）
        card = Card.GetCard(card_name)
        card.assign_owner(player)

        # 佳肴合成：手牌已有食材数 ≥2 → 消耗 2 旧食材 + 新食材 合成为佳肴
        existing = [c for c in player.hand.cards if c.is_ingredient]
        if len(existing) >= 2:
            consume = existing[:2] + [card]
            total_atk = sum(self._ingredient_buffs(c)[0] for c in consume)
            total_hp = sum(self._ingredient_buffs(c)[1] for c in consume)
            for c in consume:
                if c in player.hand.cards:
                    player.hand.remove(c)
            jy = self._create_jiaoyao(player, total_atk, total_hp)
            if len(player.hand.cards) < 12:
                player.hand.append(jy)
                player.sort_hand()
            else:
                player.used_card.append(jy)
        else:
            if len(player.hand.cards) < 12:
                player.hand.append(card)
                player.sort_hand()
            else:
                player.used_card.append(card)

        self.handle_event(CookEvent(player, hero, card_name))

    @staticmethod
    def _ingredient_buffs(card):
        """食材 buff：返回 (atk, hp)。山珍→atk，海味→hp，时蔬→atk+hp。"""
        tier = card.ingredient_tier
        itype = card.ingredient_type
        if itype == "atk":
            return tier, 0
        if itype == "hp":
            return 0, tier
        return tier, tier   # keyword

    def _create_jiaoyao(self, player: Player, buff_atk: int, buff_hp: int):
        """创建合成佳肴：效果 = 消耗的 3 食材之和。"""
        jy = Card.GetCard("JiaYao")
        jy.assign_owner(player)
        effects = []
        if buff_atk > 0:
            effects.append(lambda s, ba=buff_atk: GiveBuff("atk", ba, s, s.owner.selected_targets))
        if buff_hp > 0:
            effects.append(lambda s, bh=buff_hp: GiveBuff("hp", bh, s, s.owner.selected_targets))
        jy.on_play = tuple(effects)
        return jy


    # ═══════════════════════════════════════════════════════════════════════════
    #  战斗系统（完全重写）
    # ═══════════════════════════════════════════════════════════════════════════

    def _resolve_attack_target(self, player, hero):
        """解析一次式神攻击的结算目标。

        与 handle_event 的 "hero attack" 分支保持一致：
        HUNTING 且已选定目标 → 选中目标；具有直击 → 直接攻击敌方牌手；
        否则 → 对方战斗区式神；都没有 → 牌手。
        目标尚未确定时（如 HUNTING 待选目标）返回 None。
        """
        if HeroAttributes.HUNTING in hero.attributes:
            return player.selected_targets[0] if player.selected_targets else None
        # 直击（DIRECT_ATTACK）：即使敌方战斗区有式神，也直接攻击敌方牌手。
        # wiki「关键字-直击」：追猎优先级高于直击，故在追猎之后判断。
        if HeroAttributes.DIRECT_ATTACK in hero.attributes:
            return player.opponent
        if player.opponent.attack_zone is not None:
            return player.opponent.attack_zone
        return player.opponent

    def attack(self, attacker, defender, card=None):
        """结算一次完整的战斗。

        结算顺序：
        1. on_before_damage 回调
        2. DOUBLE_STRIKE (连击) / FIRST_STRIKE (先攻) — 额外攻击
        3. BARRIER (屏障) — 免疫一次伤害
        4. 护甲减免
        5. CRITICAL (暴击) — 伤害 ×2
        6. 实际扣血 + RANGED 反伤检查
        7. LIFESTEAL (吸血) — 恢复生命
        8. TENACIOUS (不屈) — 降至 1 血
        9. FATAL (必杀) — 直接消灭
        10. PENETRATE (贯通) — 过量伤害转移
        11. on_after_damage 回调
        12. check_death()

        穿刺 (PIERCING) 不在本层结算：wiki 为「即将造成伤害时，移除目标的
        护甲和屏障」，按伤害实例在 _resolve_single_hit 中判定来源生效，
        连击的额外一击、先攻的反击同样覆盖（防御方的穿刺要等它真正还手的
        那一刻才移除攻击方的护甲）。
        """
        # 本次攻击不造成战斗伤害（如土御门胡桃出击时有气绝式神）：一次性标记，结算后清除
        suppress_damage = getattr(attacker, "_suppress_combat_damage", False)
        if suppress_damage:
            setattr(attacker, "_suppress_combat_damage", False)
        # 鼓舞力量：出击路径转移到 attacker.inspiration_atk 的独立变量，此处单独
        # 参与计算（不并入 atk，见 Hero.__init__ 注释）；非主动出击方恒为 0。
        atk_val = (self._get_attack_power(attacker)
                   + getattr(attacker, 'inspiration_atk', 0)) if not suppress_damage else 0
        def_val = self._get_attack_power(defender) if not self._is_ranged(attacker) else 0

        # 记录战斗伤害来源，供击杀事件归属 killer
        self._last_damage_source = attacker

        # ── 1. on_before_damage ──────────────────────────────────────────
        for cb in getattr(defender, 'on_before_damage', ()):
            cb(attacker, atk_val)
        for cb in getattr(attacker, 'on_before_damage', ()):
            cb(defender, def_val)

        # ── 2. DOUBLE_STRIKE / FIRST_STRIKE ─────────────────────────────
        if HeroAttributes.DOUBLE_STRIKE in getattr(attacker, 'attributes', []):
            # 连击：先额外攻击一次（此击不受反击）
            self._resolve_single_hit(attacker, defender, atk_val, is_extra=True)
            # 第一下即气绝则战斗就此结束（wiki 连击语义）：第二击不再发生，贯通的
            # 第二次过量转移与防御方反击均不存在。判定用 hp 而非 is_alive——
            # is_alive 要到 check_death 才翻转，战斗中途恒为 True（原实现因此
            # 失效：第一击击杀后仍会结算第二击并吃到反击）。气绝流程本身仍由
            # _post_attack_cleanup 的 check_death 统一执行。
            if isinstance(defender, Hero) and defender.hp <= 0:
                self._post_attack_cleanup(attacker, defender)
                return

        attacker_has_first = HeroAttributes.FIRST_STRIKE in getattr(attacker, 'attributes', [])
        defender_has_first = HeroAttributes.FIRST_STRIKE in getattr(defender, 'attributes', [])

        if attacker_has_first and not defender_has_first:
            # 只有攻击方有先攻：先结算攻击方伤害
            self._resolve_single_hit(attacker, defender, atk_val)
            if hasattr(defender, 'is_alive') and not defender.is_alive:
                self._post_attack_cleanup(attacker, defender)
                return
            # 防御方还击（反击：贯通默认不生效，见 _penetrate_overflow）
            if def_val > 0:
                self._resolve_single_hit(defender, attacker, def_val, is_counter=True)
        elif defender_has_first and not attacker_has_first:
            # 只有防御方有先攻
            self._resolve_single_hit(defender, attacker, def_val, is_counter=True)
            if hasattr(attacker, 'is_alive') and not attacker.is_alive:
                self._post_attack_cleanup(attacker, defender)
                return
            self._resolve_single_hit(attacker, defender, atk_val)
        else:
            # 双方同时造成伤害
            self._resolve_single_hit(attacker, defender, atk_val)
            if def_val > 0:
                self._resolve_single_hit(defender, attacker, def_val, is_counter=True)

        # ── 12-13. 清理 ────────────────────────────────────────────────
        self._post_attack_cleanup(attacker, defender)


    def _resolve_single_hit(self, source, target, raw_damage, is_extra=False, is_counter=False):
        """结算单次攻击伤害。

        穿刺 (PIERCING)：即将造成伤害时，移除目标的护甲和屏障（wiki）。
        按伤害实例判定来源——主动攻击的每一击、连击的额外一击、防御方的
        反击各自结算：防御方的穿刺只在反击命中前移除攻击方的护甲（先攻
        反击则相应提前），连击的额外一击时防御方尚未还手，不会预移其护甲。

        is_counter：本次命中为防御方的反击。贯通只作用于主动攻击（wiki），
        反击是否转移过量由 _penetrate_overflow 依据来源的 _counter_penetrate
        标记（卡牌层运行时置位/清除，如山童伺机）决定。
        """
        if raw_damage <= 0:
            return

        actual_damage = raw_damage

        # ── 穿刺 (PIERCING)：移除目标护甲和屏障 ─────────────────────────
        if HeroAttributes.PIERCING in getattr(source, 'attributes', []):
            if hasattr(target, 'defense'):
                target.defense = 0
            if HeroAttributes.BARRIER in getattr(target, 'attributes', []):
                target.attributes.remove(HeroAttributes.BARRIER)

        # ── 4. BARRIER ─────────────────────────────────────────────────
        if HeroAttributes.BARRIER in getattr(target, 'attributes', []):
            target.attributes.remove(HeroAttributes.BARRIER)
            return  # 免疫这一次伤害，完全不扣血

        # ── 5. 护甲减免 ────────────────────────────────────────────────
        if hasattr(target, 'defense') and target.defense > 0:
            absorbed = min(target.defense, actual_damage)
            target.defense -= absorbed
            actual_damage -= absorbed

        # ── 6. CRITICAL ────────────────────────────────────────────────
        if HeroAttributes.CRITICAL in getattr(source, 'attributes', []):
            actual_damage *= 2

        # 对牌手造成的战斗伤害 +X（来源式神本回合的 round_buff_player_damage）
        if isinstance(target, Player):
            actual_damage += getattr(source, 'round_buff_player_damage', 0)

        if actual_damage <= 0:
            return

        # ── 8. 实际扣血前记录 ──────────────────────────────────────────
        hp_before = getattr(target, 'hp', 0)

        # 免疫战斗伤害（本回合）：完全不扣血，但贯通的“理论过量”依旧转移给牌手
        # （wiki 贯通与免疫战斗伤害交互）。由卡牌/式神层的监听器在 pre-damage 广播里
        # 把 target 加入 combo.immune_targets；引擎侧不做任何来源/类型判断。
        combo = DealDamage(actual_damage, source, [target], "combat")
        self.broadcast("deal damage", event=combo, check_response=False)
        if target in getattr(combo, "immune_targets", ()):
            self._penetrate_overflow(source, target, actual_damage, hp_before, is_counter)
            return

        # 实际扣血：统一走 receive_damage，应用破甲/幻境/鸮之守护等机制。
        # 战斗路径此处 defense 已为 0，receive_damage 内的护甲减免为 no-op。
        if hasattr(target, 'hp') and hasattr(target, 'receive_damage'):
            damage_dealt = target.receive_damage(actual_damage)
        elif hasattr(target, 'hp'):
            target.hp -= actual_damage
            damage_dealt = actual_damage
        else:
            damage_dealt = 0

        # 记录式神在战斗中实际造成的伤害：战斗路径不广播 deal damage，
        # 单独广播 damage dealt（结算后纯通知），供「本局造成伤害 N 次」类条件计数
        # （如妖狐狂风刃卷增强）。value 取实际 damage_dealt，target 为单元素列表。
        if damage_dealt > 0:
            self.broadcast("damage dealt",
                           event=DamageDealt(damage_dealt, source, [target], "combat"),
                           check_response=False)

        # ── 8. LIFESTEAL ──────────────────────────────────────────────
        if HeroAttributes.LIFESTEAL in getattr(source, 'attributes', []):
            owner = getattr(source, 'owner', None)
            if owner and damage_dealt > 0:
                self.handle_event(Heal(damage_dealt, source, [owner]))

        # ── 9. TENACIOUS ───────────────────────────────────────────────
        if hasattr(target, 'hp') and target.hp <= 0:
            if HeroAttributes.TENACIOUS in getattr(target, 'attributes', []):
                if hp_before > 1:
                    target.hp = 1
                    target.attributes.remove(HeroAttributes.TENACIOUS)

        # ── 10. FATAL ──────────────────────────────────────────────────
        if hasattr(target, 'hp') and target.hp > 0:
            if isinstance(target, Hero) and HeroAttributes.FATAL in getattr(source, 'attributes', []):
                if actual_damage > 0 or is_extra:
                    target.hp = 0

        # ── 11. PENETRATE（贯通）──────────────────────────────────────
        # 理论过量 = 造成伤害 - 受击前生命，与目标是否死亡无关：
        # 目标带不屈（生命被钳到 1）或免疫战斗伤害（完全不受伤）时，理论过量依旧转移。
        self._penetrate_overflow(source, target, actual_damage, hp_before, is_counter)

    def _penetrate_overflow(self, source, target, actual_damage, hp_before, is_counter=False):
        """贯通：将“理论过量伤害”转移给受击式神所属的牌手。

        过量 = max(0, actual_damage - hp_before)，只对式神目标生效。
        仅当来源具有贯通（PENETRATE）时转移；目标是否真正死亡不影响转移。
        反击命中（is_counter）默认不转移（wiki：贯通仅「主动」对式神造成时生效）；
        来源带 _counter_penetrate 标记时例外（卡牌层运行时置位/清除，如山童伺机，
        引擎只读标记，不管理其生命周期）。
        注意：受击式神属于对方，过量转移给对方牌手 = target.owner（不是 owner.opponent）。
        """
        if not isinstance(target, Hero):
            return
        if HeroAttributes.PENETRATE not in getattr(source, 'attributes', []):
            return
        if is_counter and not getattr(source, "_counter_penetrate", False):
            return
        excess = actual_damage - hp_before
        if excess > 0:
            owner_player = target.owner
            if owner_player:
                self.handle_event(DealDamage(excess, source, [owner_player]))

    def apply_penetration(self, source, target, amount):
        """破甲结附：施加破甲并广播通知（供寂寥心象等「获得破甲」类监听）。

        破甲是实体上的普通属性，直接 `target.penetration += X` 不会触发任何事件；
        卡牌若要监听「获得破甲」（寂寥心象/碧羽散华），必须统一走此入口。
        清除破甲（=0，如回合重置/死亡）不算结附，不走此入口。
        """
        if amount <= 0:
            return
        target.penetration += amount
        self.broadcast("armor break applied",
                       event=ArmorBreakApplyEvent(source, target, amount),
                       check_response=False)

    def _post_attack_cleanup(self, attacker, defender):
        """攻击后清理：on_after_damage 和 check_death。"""
        for cb in getattr(attacker, 'on_after_damage', ()):
            cb(defender, 0)
        for cb in getattr(defender, 'on_after_damage', ()):
            cb(attacker, 0)

        if hasattr(attacker, 'check_death'):
            attacker.check_death()
        if hasattr(defender, 'check_death'):
            defender.check_death()


    @staticmethod
    def _get_attack_power(entity):
        atk = 0
        if hasattr(entity, "atk"):
            atk += entity.atk
        if hasattr(entity, "round_buff_atk"):
            atk += entity.round_buff_atk
        if hasattr(entity, "combat_buff_atk"):
            atk += entity.combat_buff_atk
        return atk

    @staticmethod
    def _is_ranged(entity):
        return HeroAttributes.RANGED in getattr(entity, 'attributes', [])


    # ═══════════════════════════════════════════════════════════════════════════
    #  幻境耐久（增长统一入口）
    # ═══════════════════════════════════════════════════════════════════════════

    def gain_illusion_durability(self, card, amount: int):
        """幻境耐久增长的统一入口（#5 apply_penetration 同模式）：修改耐久并广播
        IllusionDurabilityGainEvent，供「当此牌获得幻境耐久时…」类被动监听（月坠）。
        承伤侧在 Player.receive_damage（IllusionDamageEvent）。

        所有耐久增长效果必须走此入口：直接 `durability +=` 不会触发监听。
        """
        if amount <= 0:
            return
        card.durability += amount
        self.handle_event(IllusionDurabilityGainEvent(card, amount))


    # ═══════════════════════════════════════════════════════════════════════════
    #  召唤融合（wiki 关键字-融合）
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _fuse_summon(base, incoming):
        """融合合并：incoming 并入 base（base 留场，incoming 不再单独进场）。

        身材相加（力量 / 生命上限 / 当前生命——已受伤残量一并带入）；
        关键词取并集（小糖人并入大糖人 → 不屈保留，#13 用户裁决默认）。
        「属于同一个式神」由双方 fuse_group 相等表达。
        """
        base.atk += incoming.atk
        base.current_max_hp += incoming.current_max_hp
        base.hp += incoming.hp
        for attr in incoming.attributes:
            if attr not in base.attributes:
                base.attributes.append(attr)


    # ═══════════════════════════════════════════════════════════════════════════
    #  游戏流程
    # ═══════════════════════════════════════════════════════════════════════════

    def start_game(self):
        self.player1.opponent = self.player2
        self.player2.opponent = self.player1
        self.player1.game = self
        self.player2.game = self
        self.turn_count = 0

        first, second = self.pick_first_player()
        self.player1 = first
        self.player2 = second
        self.player1.is_first_player = True
        self.player2.is_first_player = False
        self.current_player = first

        self.player1.start_game()
        self.player2.start_game()
        self.player1.assign_agent()
        self.player2.assign_agent()

        self.state = "playing"


    def play(self):
        self.start_game()
        self.begin_turn()

        while True:
            action = self.current_player.agent.act()
            self.step(self.current_player, action)


    # ═══════════════════════════════════════════════════════════════════════════
    #  观测接口（保持与 env 的兼容性）
    # ═══════════════════════════════════════════════════════════════════════════

    def get_observations(self, player: Player):
        player_state = player.state
        game_state = self.state
        turn_count = self.turn_count
        player_hp = player.hp
        player_defense = player.defense
        opponent_hp = player.opponent.hp
        opponent_defense = player.opponent.defense
        player_heroes = player.heroes.copy()
        opponent_heroes = player.opponent.heroes.copy()
        player_deck_size = len(player.deck)
        opponent_deck_size = len(player.opponent.deck)
        # 手牌排序：按己方式神顺序 → 等级需求 → 到手顺序（稳定排序保留原始相对顺序）
        hero_order = {h.type_name: i for i, h in enumerate(player.heroes)}
        player_hand = sorted(
            player.hand.cards,
            key=lambda c: (hero_order.get(c.hero, len(hero_order)), c.level_req)
        )
        opponent_hand_size = len(player.opponent.hand)
        player_starting_deck = player.starting_deck
        fire_remaining = player.fire_cnt
        attack_available = player.attack_available
        is_first_player = player.is_first_player
        pending_card = player.pending_card
        player_used_card = player.used_card
        opponent_used_card = player.opponent.used_card
        player_inspiration_atk = player.inspiration_atk
        player_inspiration_def = player.inspiration_def
        return {
            "player_state": player_state,
            "game_state": game_state,
            "turn_count": turn_count,
            "player_hp": player_hp,
            "player_defense": player_defense,
            "opponent_hp": opponent_hp,
            "opponent_defense": opponent_defense,
            "player_heroes": player_heroes,
            "opponent_heroes": opponent_heroes,
            "player_deck_size": player_deck_size,
            "opponent_deck_size": opponent_deck_size,
            "player_hand": player_hand,
            "opponent_hand_size": opponent_hand_size,
            "player_starting_deck": player_starting_deck,
            "fire_remaining": fire_remaining,
            "attack_available": attack_available,
            "is_first_player": is_first_player,
            "pending_card": pending_card,
            "player_used_card": player_used_card,
            "opponent_used_card": opponent_used_card,
            "player_inspiration_atk": player_inspiration_atk,
            "player_inspiration_def": player_inspiration_def,
        }


    def get_obs_tensor(self, player: Player, device) -> "torch.Tensor":
        """
        用 numpy 数组在 CPU 上完成所有赋值，最后一次 .to(device)。
        布局与 env/actions.py::ObsIdx 保持一致 (709 维, HERO_BLOCK=29)。
        """
        import torch
        import numpy as np
        opponent = player.opponent

        from env.actions import OBS_DIM, MAX_CARD_ID, HERO_BLOCK, NUM_HEROES
        from env.actions import ObsIdx as o, HeroField as hf

        buf = np.zeros(OBS_DIM, dtype=np.float32)

        def _fill_hero(buf, base, h):
            """写入 29 维式神块"""
            buf[base + hf.ID]                = h.id
            buf[base + hf.MORPHED_ID]        = h.morphed_id
            buf[base + hf.CURRENT_MAX_HP]    = h.current_max_hp
            buf[base + hf.HP]                = h.hp
            buf[base + hf.ATK]               = h.atk
            buf[base + hf.ROUND_BUFF_ATK]    = h.round_buff_atk
            buf[base + hf.DEFENSE]           = h.defense
            buf[base + hf.LEVEL]             = h.level
            buf[base + hf.ROUND_UNTIL_ALIVE] = h.round_until_alive
            # position_state
            state = h.state
            if state == "attacking":
                buf[base + hf.POSITION_STATE] = 1.0
            elif state == "dead":
                buf[base + hf.POSITION_STATE] = 2.0
            else:
                buf[base + hf.POSITION_STATE] = 0.0
            buf[base + hf.IS_STUNNED]  = 1.0 if h.stunned else 0.0
            buf[base + hf.IS_AWAKENED] = 1.0 if h.is_awakened else 0.0
            # countdown_ratio
            if h.countdown_max > 0:
                buf[base + hf.COUNTDOWN_RATIO] = h.countdown / h.countdown_max
            else:
                buf[base + hf.COUNTDOWN_RATIO] = 0.0
            # 16 HeroAttributes
            for attr in h.attributes:
                attr_val = int(attr)
                if 1 <= attr_val <= 16:
                    buf[base + hf.ATTR_START + attr_val - 1] = 1.0

        # ── 基础标量 ─────────────────────────────────────────────────
        buf[o.PLAYER_STATE] = player.state
        buf[o.TURN_COUNT]   = self.turn_count
        buf[o.PLAYER_HP]    = player.hp
        buf[o.OPPONENT_HP]  = opponent.hp

        # ── 己方英雄 (4 × 29) ────────────────────────────────────────
        # 召唤物会作为额外式神加入 heroes，obs 槽位固定为 NUM_HEROES，截断避免越界写入
        for i, h in enumerate(player.heroes[:NUM_HEROES]):
            _fill_hero(buf, o.PLAYER_HERO_START + i * HERO_BLOCK, h)

        # ── 对手英雄 (4 × 29) ────────────────────────────────────────
        for i, h in enumerate(opponent.heroes[:NUM_HEROES]):
            _fill_hero(buf, o.OPP_HERO_START + i * HERO_BLOCK, h)

        # ── 牌手标量 ─────────────────────────────────────────────────
        buf[o.PLAYER_DECK]        = len(player.deck)
        buf[o.OPPONENT_DECK]      = len(opponent.deck)
        buf[o.OPPONENT_HAND_SIZE] = len(opponent.hand)
        buf[o.FIRE_REMAINING]     = player.fire_cnt
        buf[o.ATTACK_AVAILABLE]   = 1.0 if player.attack_available else 0.0
        buf[o.IS_FIRST_PLAYER]    = 1.0 if player.is_first_player   else 0.0
        buf[o.PENDING_CARD]       = player.pending_card.id if player.pending_card is not None else 0.0
        buf[o.PLAYER_INSP_ATK]    = player.inspiration_atk
        buf[o.PLAYER_INSP_DEF]    = player.inspiration_def
        buf[o.PLAYER_DEFENSE]     = player.defense
        buf[o.OPPONENT_DEFENSE]   = opponent.defense
        buf[o.UPGRADE_REMAINING]  = player.upgrade_remaining
        buf[o.INSTANT_USED]       = 1.0 if player.instant_used else 0.0
        buf[o.OPPONENT_FIRE]      = opponent.fire_cnt

        # ── 手牌 multi-hot ───────────────────────────────────────────
        for c in player.hand.cards:
            cid = Card.get_id_by_name(c.eng_name) if hasattr(c, 'eng_name') else c.id
            if cid == 0:
                cid = c.id
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.PLAYER_HAND_START + cid - 1] += 1.0

        # ── 起始牌组 multi-hot ───────────────────────────────────────
        for name in player.starting_deck:
            cid = Card.get_id_by_name(name)
            if cid == 0:
                try:
                    cid = Card.GetCard(name).id
                except Exception:
                    cid = 0
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.STARTING_DECK_START + cid - 1] += 1.0

        # ── 己方已用牌 multi-hot ─────────────────────────────────────
        for c in player.used_card:
            cid = Card.get_id_by_name(c.eng_name) if hasattr(c, 'eng_name') else c.id
            if cid == 0:
                cid = c.id
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.PLAYER_USED_START + cid - 1] += 1.0

        # ── 对手已用牌 multi-hot ─────────────────────────────────────
        for c in opponent.used_card:
            cid = Card.get_id_by_name(c.eng_name) if hasattr(c, 'eng_name') else c.id
            if cid == 0:
                cid = c.id
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.OPP_USED_START + cid - 1] += 1.0

        # ── 正在攻击的己方英雄 ──────────────────────────────────────
        for h in player.heroes:
            if h.state == "attacking":
                _fill_hero(buf, o.PLAYER_ATTACKING_START, h)
                break

        # ── 正在攻击的对手英雄 ──────────────────────────────────────
        for h in opponent.heroes:
            if h.state == "attacking":
                _fill_hero(buf, o.OPP_ATTACKING_START, h)
                break

        return torch.from_numpy(buf).to(device)
