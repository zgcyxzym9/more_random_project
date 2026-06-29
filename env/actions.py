END_TURN = 0
UPGRADE_HERO_START = 1
HERO_ATTACK_START = 5
PLAY_CARD_START = 9
SELECT_TARGET_START = 21
REJECT_INITIAL_PICK_START = 31

HAND_LIMIT = 12
NUM_CARD_TYPES = 23      # 可用卡牌种类数（ID 1~23；ID 24 不可用）
OBS_DIM = 251             # 总观测维度（原240，手牌从12槽扩展为23槽，+11）

class ObsIdx:
    PLAYER_STATE      = 0
    PLAYER_HP         = 3
    OPPONENT_HP       = 4
    OPPONENT_DECK     = 102
    PLAYER_HAND_START = 103          # 103~125，共 NUM_CARD_TYPES 个槽
    FIRE_REMAINING    = 159
    TURN_COUNT        = 2
    OPP_HERO_HP  = [53 + i * 12 + 3 for i in range(4)]
    OPP_HERO_DEF = [53 + i * 12 + 6 for i in range(4)]