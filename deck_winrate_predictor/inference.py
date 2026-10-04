"""推理示例：加载训练好的卡组胜率模型，对若干卡组打印预测胜率。

用法：
  .venv/Scripts/python.exe deck_winrate_predictor/inference.py [checkpoint]
不给 checkpoint 时自动用 logs/deck_winrate 下最新的 winrate_model.pt。
"""
import sys

sys.path.insert(0, "E:/more_random_project_vibe")

import glob
import os

from deck_winrate_predictor.predictor import DeckWinratePredictor
from deck_winrate_predictor.selfplay import DeckEnv


def latest_checkpoint():
    paths = glob.glob(os.path.join("logs", "deck_winrate", "*", "winrate_model.pt"))
    if not paths:
        raise FileNotFoundError("logs/deck_winrate 下没有 winrate_model.pt，请先训练")
    return max(paths, key=os.path.getmtime)


def evaluate(model_path=None):
    model_path = model_path or latest_checkpoint()
    print(f"checkpoint = {model_path}")
    predictor = DeckWinratePredictor.from_checkpoint(model_path)

    # 固定卡组（来自 experiments/deck_strength/decks.py）
    from experiments.deck_strength.decks import DECKS
    for name, (deck, heroes) in DECKS.items():
        print(f"  deck{name} {heroes} -> 预测胜率 {predictor.predict(heroes, deck):.3f}")

    # 随机卡组：预测值应当有分化，而不是全挤在 0.5 附近
    env = DeckEnv()
    random_decks = [env.random_deck() for _ in range(8)]
    preds = predictor.predict_batch(random_decks)
    print("  随机卡组预测:", " ".join(f"{p:.3f}" for p in preds))

    # 演示按胜率采样一套卡组
    heroes, deck = predictor.sample_deck()
    print(f"  sample_deck() -> {heroes} 预测胜率 {predictor.predict(heroes, deck):.3f}")


if __name__ == "__main__":
    evaluate(sys.argv[1] if len(sys.argv) > 1 else None)
