from .enums import PlayerState


def _owner_tag(entity, player):
    """返回实体的归属标签（用于打印时区分敌我）。

    若实体有 owner 属性，返回 '[我方]' 或 '[敌方]'；
    若无法判断（无 owner），返回空字符串。
    """
    owner = getattr(entity, 'owner', None)
    if owner is None:
        return ""
    return "[我方]" if owner == player else "[敌方]"


def _is_inference_mode(player) -> bool:
    """检测当前是否处于推理模式。"""
    return type(player).__name__ in ("InferencePlayer", "InferenceOpponent")


def select_target(player, target_list, card):
    # 推理模式下若目标列表为空（通常因为对手牌组是假的），回退到所有存活且已升级的式神
    if not target_list and _is_inference_mode(player):
        target_list = [h for h in player.heroes + player.opponent.heroes
                       if h.is_alive and h.level > 0]
        if not target_list:
            print("[Warning] No valid targets available even with fallback.")
        else:
            print("[Warning] Card's normal target list is empty. "
                  "Using fallback: all alive leveled heroes from both sides.")

    player.candidate_targets = target_list
    player.state = PlayerState.SELECTING_TARGET
    player.pending_card = card


def select_random_target(player, target_list, context: str = ""):
    """从目标列表中随机选择一个。

    推理模式下始终弹出提示让用户手动选择（与真实对局同步）。
    训练模式下使用 Game 的集中化 RNG。
    """
    # 推理模式：列表为空时（通常因为对手牌组是假的），提示用户手动输入
    if not target_list:
        if _is_inference_mode(player):
            print(f"\n[Random Selection - Empty List] {context}" if context else
                  "\n[Random Selection - Empty List]")
            print("  (Target list is empty, likely due to fake deck in inference mode.)")
            from .card import Card
            while True:
                name = input("  Please enter the actual randomly selected card name (eng_name): ").strip()
                if name:
                    try:
                        return Card.GetCard(name)
                    except Exception:
                        print(f"  Card '{name}' not found, try again.")
                else:
                    print("  Empty input, try again.")
        return None

    # 推理模式：始终提示用户，不依赖 game.rng
    if _is_inference_mode(player):
        print(f"\n[Random Selection] {context}" if context else "\n[Random Selection]")
        for i, t in enumerate(target_list):
            tag = _owner_tag(t, player)
            print(f"  [{i+1}] {tag} {t}")
        while True:
            try:
                target_id = int(input("Which target was chosen randomly?\n")) - 1
                if 0 <= target_id < len(target_list):
                    return target_list[target_id]
                print(f"Invalid selection. Please enter 1-{len(target_list)}.")
            except ValueError:
                print(f"Please enter a number 1-{len(target_list)}.")

    # 训练模式：使用集中化 RNG
    game = getattr(player, 'game', None)
    if game and hasattr(game, 'rng'):
        return game.rng.choice(target_list, context=context)

    # 安全网（不应到达）
    import random as _r
    return _r.choice(target_list)


def IsDamaged(target_list):
    sel = []
    for target in target_list:
        if target.hp < target.current_max_hp and target.hp > 0:
            sel.append(target)
    return sel


def IsDead(target_list):
    sel = []
    for target in target_list:
        if not target.is_alive:
            sel.append(target)
    return sel


def random_choice(player, seq, context: str = ""):
    """通用随机选择（任意对象列表）。

    推理模式下弹出提示让用户手动选择；训练模式使用 game.rng。
    """
    if not seq:
        return None

    if _is_inference_mode(player):
        print(f"\n[Random Choice] {context}" if context else "\n[Random Choice]")
        for i, item in enumerate(seq):
            tag = _owner_tag(item, player)
            print(f"  [{i+1}] {tag} {item}")
        while True:
            try:
                idx = int(input("Which option was chosen randomly?\n")) - 1
                if 0 <= idx < len(seq):
                    return seq[idx]
                print(f"Invalid. Please enter 1-{len(seq)}.")
            except ValueError:
                print(f"Please enter a number 1-{len(seq)}.")

    game = getattr(player, 'game', None)
    if game and hasattr(game, 'rng'):
        return game.rng.choice(seq, context=context)

    import random as _r
    return _r.choice(list(seq))


def random_sample(player, seq, k: int, context: str = ""):
    """通用随机采样（不重复选取 k 个元素）。

    推理模式下弹出提示让用户手动选择；训练模式使用 game.rng。
    """
    if not seq or k <= 0:
        return []
    k = min(k, len(seq))

    if _is_inference_mode(player):
        print(f"\n[Random Sample] {context} (需要选 {k} 个)" if context else f"\n[Random Sample] (需要选 {k} 个)")
        for i, item in enumerate(seq):
            tag = _owner_tag(item, player)
            print(f"  [{i+1}] {tag} {item}")
        selected = []
        for n in range(k):
            while True:
                try:
                    idx = int(input(f"Select item {n+1}/{k}:\n")) - 1
                    if 0 <= idx < len(seq) and seq[idx] not in selected:
                        selected.append(seq[idx])
                        break
                    print(f"Invalid or duplicate selection. Pick a unique item 1-{len(seq)}.")
                except ValueError:
                    print(f"Please enter a number 1-{len(seq)}.")
        return selected

    game = getattr(player, 'game', None)
    if game and hasattr(game, 'rng'):
        return game.rng.sample(seq, k)

    import random as _r
    return _r.sample(list(seq), k)
