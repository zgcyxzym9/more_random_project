from game import Game
from player import Player
from agent import IOAgent

player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "WuShiZhiLi", "WuShiZhiLi"], ["ZhiRenWuShi", "TianXieGuiTuanHuo"])
player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "WuShiZhiLi", "WuShiZhiLi"], ["ZhiRenWuShi", "TianXieGuiTuanHuo"])
game_instance = Game([player1, player2])
player1.agent = IOAgent(game_instance, player1)
player2.agent = IOAgent(game_instance, player2)
game_instance.play()