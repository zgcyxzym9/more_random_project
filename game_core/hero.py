from .heroes import *
from .entity import Entity
from .enums import HeroAttributes
from .counters import CounterManager


class Hero(Entity):
    original_hp: int = 0
    original_atk: int = 0
    hp: int = 0
    atk: int = 0
    current_max_hp: int = 0
    defense: int = 0
    round_buff_atk: int = 0
    combat_buff_atk: int = 0
    level: int = 0
    state: str = None
    is_alive: bool = False
    round_until_alive: int = 0

    def __init__(self, hero_obj):
        self.id = hero_obj.id
        self.morphed_id = 0
        self.entity_type = "hero"
        self.type_name = type(hero_obj).__name__
        self.form = getattr(hero_obj, "form", None)   # 切换式神当前形态；非切换式神为 None
        self.name = hero_obj.name
        self.type = hero_obj.type
        self.owner = None
        self.original_hp = hero_obj.hp
        self.original_atk = hero_obj.atk
        self.current_max_hp = hero_obj.hp
        self.hp = hero_obj.hp
        self.atk = hero_obj.atk
        self.round_buff_atk = 0
        # 本场战斗的战斗牌力量加成：独立变量不并入 atk（伤害结算经
        # _get_attack_power 单独读取），战斗结束或气绝时清零——攻击方中途气绝
        # 时 check_death 的 atk 重置不会与战后回退叠加出幽灵数值
        self.combat_buff_atk = 0
        self.round_buff_spell_damage = 0
        self.round_buff_player_damage = 0   # 本回合对牌手造成的伤害 +X
        self.defense = 0
        self.penetration = 0
        # 本次出击的鼓舞生效攻击力：出击路径从牌手转移到式神身上的独立变量，
        # 不并入 atk（伤害结算时由 attack() 单独读取），出击结束后归零——
        # 攻击方中途气绝时 check_death 的 atk 重置不会与之叠加出幽灵数值。
        self.inspiration_atk = 0
        self.level = 0
        self.state = "pending"
        self.is_alive = True
        self.round_until_alive = 0
        self.listeners = list(hero_obj.listeners) if hasattr(hero_obj, "listeners") else []
        self.original_listeners = list(hero_obj.listeners) if hasattr(hero_obj, "listeners") else []
        # 初始 HeroAttributes（充能 ENERGY_CHARGE 等）：英雄类用 base_attributes 声明；
        # 未声明的英雄保持空列表，与原有行为一致。卡牌效果仍可在运行时增删。
        self.attributes = list(getattr(hero_obj, "base_attributes", ()))
        self.counters = CounterManager(self)
        self.counter = hero_obj.counter.copy() if hasattr(hero_obj, "counter") else {}
        # 永久加成（觉醒牌等 get_permanent_buff 累计），形态/气绝/复活时保留
        self.perm_buff_atk = 0
        self.perm_buff_hp = 0
        self.on_upgrade = hero_obj.on_upgrade if hasattr(hero_obj, "on_upgrade") else []
        self.on_death = hero_obj.on_death if hasattr(hero_obj, "on_death") else []
        self.on_revive = hero_obj.on_revive if hasattr(hero_obj, "on_revive") else []

        # ── 倒计时 ────────────────────────────────────────────────────────
        self.countdown = hero_obj.countdown if hasattr(hero_obj, "countdown") else 0
        self.countdown_max = hero_obj.countdown_max if hasattr(hero_obj, "countdown_max") else 0
        self.on_countdown = hero_obj.on_countdown if hasattr(hero_obj, "on_countdown") else ()

        # ── 移动 ──────────────────────────────────────────────────────────
        self.on_move = hero_obj.on_move if hasattr(hero_obj, "on_move") else ()

        # ── 觉醒 ──────────────────────────────────────────────────────────
        self.is_awakened = False

        # ── 眩晕 ──────────────────────────────────────────────────────────
        self.stunned = False
        self.on_stun = hero_obj.on_stun if hasattr(hero_obj, "on_stun") else ()
        self.on_unstun = hero_obj.on_unstun if hasattr(hero_obj, "on_unstun") else ()

        # ── 蓄力 ──────────────────────────────────────────────────────────
        # 正在蓄力的卡（蓄力打出时卡离手进弃牌堆，气绝不返还）；蓄力顺序在
        # owner.charging_order 上维护
        self.charging_card = None

        # ── 不死保护 ─────────────────────────────────────────────────────
        self.on_before_death = hero_obj.on_before_death if hasattr(hero_obj, "on_before_death") else ()

        # ── 伤害回调 ─────────────────────────────────────────────────────
        self.on_before_damage = hero_obj.on_before_damage if hasattr(hero_obj, "on_before_damage") else ()
        self.on_after_damage = hero_obj.on_after_damage if hasattr(hero_obj, "on_after_damage") else ()

        # ── 召唤物 / 特殊攻击 ───────────────────────────────────────────
        self.is_summoned = getattr(hero_obj, "is_summoned", False)
        # 融合组（wiki 关键字-融合）：同组融合体进场时互相合并（如小/大糖人同属 TangRen 组）
        self.fuse_group = getattr(hero_obj, "fuse_group", None)
        # 特殊攻击回调：出击时替代正常战斗流程（如烬染不夜）。签名为 special_attack(hero)
        # 必须从类上取未绑定函数：special_attack 是英雄类的类属性（函数），
        # 经实例 getattr 会被描述符协议绑定成 bound method，调用时多传 self 导致参数错误
        self.special_attack = getattr(type(hero_obj), "special_attack", None)

        # ── 充能：能量计数（上限 10，持久）────────────────────────────────
        self.counters.ensure("energy", initial=0, persistent=True, max_val=10)

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"{self.name}"

    def GetHero(id: str):
        hero_class = globals()[id]
        hero_obj = hero_class()
        hero = Hero(hero_obj)
        for attr_name, attr_value in vars(hero_obj).items():
            setattr(hero, attr_name, attr_value)
        return hero

    def GetHeroes(ids: list[str]):
        heroes = []
        for id in ids:
            heroes.append(Hero.GetHero(id))
        return heroes

    def Upgrade(self):
        self.level += 1

    def can_act(self) -> bool:
        """眩晕时不能行动。"""
        return not self.stunned

    # ── 倒计时 ──────────────────────────────────────────────────────────────

    def tick_countdown(self):
        """倒计时 -1；归零时触发 on_countdown 回调并重置。"""
        if self.countdown_max <= 0 or self.countdown <= 0:
            return
        self.countdown -= 1
        if self.countdown <= 0:
            self.countdown = self.countdown_max
            from .event import CountdownEvent
            self.owner.game.handle_event(CountdownEvent(self))
            for callback in self.on_countdown:
                result = callback(self)
                if result is not None:
                    from .event import Event
                    if isinstance(result, Event):
                        self.owner.game.handle_event(result)

    # ── 眩晕 ──────────────────────────────────────────────────────────────

    def stun(self):
        self.stunned = True
        for callback in self.on_stun:
            callback(self)

    def unstun(self):
        self.stunned = False
        for callback in self.on_unstun:
            callback(self)

    # ── 移动 ──────────────────────────────────────────────────────────────

    def move_to_battle(self):
        """移入战斗区。"""
        from .event import MoveEvent
        player = self.owner
        if player.attack_zone is not None and player.attack_zone is not self:
            if getattr(player.attack_zone, 'is_summoned', False):
                player.dismiss_summon(player.attack_zone)
            else:
                player.attack_zone.state = "pending"
        player.attack_zone = self
        self.state = "attacking"
        for callback in self.on_move:
            callback(self, "standby", "battle")
        player.game.handle_event(MoveEvent(self, "standby", "battle"))

    def move_to_standby(self):
        """移出战斗区。"""
        from .event import MoveEvent
        player = self.owner
        if player.attack_zone == self:
            player.attack_zone = None
        self.state = "pending"
        for callback in self.on_move:
            callback(self, "battle", "standby")
        player.game.handle_event(MoveEvent(self, "battle", "standby"))

    # ── 死亡与复活 ──────────────────────────────────────────────────────

    def check_death(self):
        if self.hp <= 0:
            # 不死保护：on_before_death 返回 True 则阻止死亡
            prevented = False
            for callback in self.on_before_death:
                if callback(self):
                    prevented = True
            if prevented:
                return

            # 「将气绝」事件：在置死亡态之前广播，供响应牌（如「射怪鸟事」）触发。
            # 响应牌打出后死亡仍照常发生。局部导入避免循环依赖（同 199 行模式）。
            from .event import AboutToDieEvent, MorphLeaveEvent
            game = getattr(self.owner, "game", None)
            if game is not None:
                game.handle_event(AboutToDieEvent(self))
                # 「形态牌被消灭」：式神气绝时形态随其消灭。在置死亡态之前广播，
                # 让一目连等被动能在式神真正气绝前结算倒计时（与 wiki 行为一致）。
                if self.morphed_id != 0:
                    game.handle_event(MorphLeaveEvent(self, self.morphed_id, "destroy"))

            self.is_alive = False
            self.state = "dead"
            # 召唤物气绝即离场：衍生物不走复活倒计时（#13 用户裁决⑤；JinRanBuYe/
            # ShiBo 同受影响），从 heroes 移除见本函数末尾
            self.round_until_alive = 0 if self.is_summoned else 3
            # 蓄力式神气绝：离开蓄力状态，已蓄力的卡不返还（已在弃牌堆）
            if self.charging_card is not None:
                self.charging_card = None
                if self.owner is not None and self in self.owner.charging_order:
                    self.owner.charging_order.remove(self)
            self.round_buff_atk = 0
            self.combat_buff_atk = 0
            self.round_buff_player_damage = 0
            self.listeners = list(self.original_listeners)
            self.morphed_id = 0
            self.stunned = False
            # 迅捷被式神死亡消耗（faq）：气绝时移除，复活不恢复
            if HeroAttributes.AGILE in self.attributes:
                self.attributes.remove(HeroAttributes.AGILE)
            if self.owner.attack_zone == self:
                self.owner.attack_zone = None
            # 重置非持久计数器
            self.counters.reset_all()

            # 击杀事件广播（妖刀姬等监听 "hero kill"）
            # 在 on_death 回调前广播，保证击杀相关效果先于式神死亡效果结算
            from .event import Event, HeroKillEvent
            game = getattr(self.owner, "game", None)
            if game is not None:
                killer = getattr(game, "_last_damage_source", None)
                game.handle_event(HeroKillEvent(killer, self))

            for event in self.on_death:
                if isinstance(event(self), Event):
                    self.owner.game.handle_event(event(self))

            # 召唤物气绝即离场：死亡流程（响应/击杀事件/on_death）结算完后从
            # heroes 移除，begin_turn 不再倒计时复活
            if self.is_summoned and self.owner is not None:
                self.owner.dismiss_summon(self)

            # hp/atk 重置：气绝流程（响应/击杀事件/on_death）全部结算完后执行，
            # 而非复活时（原在 revive() 中）——与实际游戏一致：气绝后面板即为基础
            # 值+永久加成，复活时触发的加成（如桃花妖被动）不会再被复活重置覆写。
            # 放在末尾也覆盖死亡流程中被中途复活的情形（如九命猫 on_death 自复活）
            self.hp = self.original_hp + self.perm_buff_hp
            self.current_max_hp = self.original_hp + self.perm_buff_hp
            self.atk = self.original_atk + self.perm_buff_atk

    def assign_owner(self, player):
        self.owner = player

    def revive(self):
        # hp/atk 已在气绝流程末尾（check_death）重置，这里不再重复设置
        self.is_alive = True
        self.defense = 0
        self.round_until_alive = 0
        self.state = "pending"
        from .event import Event
        for event in self.on_revive:
            if isinstance(event(self), Event):
                self.owner.game.handle_event(event(self))

    def receive_damage(self, damage: int) -> int:
        """结算一次伤害，返回实际扣除的生命值。"""
        # 鸮之守护：受到的所有伤害 -1（每段独立，最小值 0）
        if self.counters.get("hawk_protection", 0) > 0:
            damage = max(0, damage - 1)
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

    def get_permanent_buff(self, field: str, value):
        """永久加成（觉醒牌等）。累加到 perm_buff 追踪字段，不修改 original。

        与 GiveBuff 的区别：GiveBuff 修改 atk/hp 但不追踪，死亡后丢失；
        get_permanent_buff 的加成在形态替换和复活后均保留。
        """
        if field == "hp":
            self.current_max_hp += value
            self.hp += value
            self.perm_buff_hp += value
        elif field == "atk":
            self.atk += value
            self.perm_buff_atk += value
