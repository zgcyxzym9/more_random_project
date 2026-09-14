"""免疫伤害监听器 helper（引擎层，独立于 cards 包以免循环导入）。

供「免疫 xxx 伤害」类卡牌/式神复用：判断逻辑由卡牌/式神的 condition 决定，
命中时把 owner（受击方）加入底层事件 event.event 的 immune_targets 集合，
由 game.game 三条伤害通道统一读取——目标在集合中则跳过扣血（贯通理论过量仍转移）。

事件广播包装约定：监听器收到的 event 是包装器（Event(type, event=<底层事件>)），
故读取/写入底层伤害事件须用 e.event.<attr>（见 game.Game.handle_event 的 broadcast）。
"""
from .manager import Listener


# 临时战斗免疫监听器的统一 tag（回合开始/死亡/切形态时统一清理）
COMBAT_IMMUNE_TAG = "temp_combat_immune"


def make_damage_immune_listener(event_type, condition):
    """构造「对 event_type 伤害免疫」的监听器。

    condition(event, owner) -> bool：event 为广播包装器，用 event.event.<attr>
    读取底层伤害事件；决定 owner 是否免疫本次伤害（如判敌方/非战斗）。
    命中时把 owner 加入底层事件的 immune_targets（仅当 owner 是本次伤害目标）。
    """
    def effect(event, owner):
        base = event.event
        base.immune_targets = getattr(base, "immune_targets", set()) | {owner}
        return None
    return Listener(event_type,
                    lambda e, o: o in e.event.target and condition(e, o),
                    (effect,))


def make_combat_immune_listener():
    """临时免疫战斗伤害监听器（本回合对任意战斗伤害免疫，无来源限制）。"""
    l = make_damage_immune_listener(
        "deal damage", lambda e, o: getattr(e.event, "damage_type", "spell") == "combat")
    l._tag = COMBAT_IMMUNE_TAG
    return l


def clear_combat_immune(hero):
    """移除 hero 上的临时战斗免疫监听器（回合开始/死亡/切形态时清理）。"""
    hero.listeners = [x for x in hero.listeners if getattr(x, "_tag", "") != COMBAT_IMMUNE_TAG]


def has_combat_immune(hero):
    """hero 当前是否佩戴临时战斗免疫监听器（供测试/调试断言）。"""
    return any(getattr(l, "_tag", "") == COMBAT_IMMUNE_TAG for l in hero.listeners)
