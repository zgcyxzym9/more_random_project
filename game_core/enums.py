from enum import IntEnum

class CardAttributes(IntEnum):
    INSTANT = 1
    NO_FIRE_CONSUMPTION = 2
    CAN_PLAY_WHEN_DEAD = 3

class HeroAttributes(IntEnum):
    AGILE = 1

class PlayerState(IntEnum):
    INITIAL_PICK = 1
    PLAYING = 2
    WAITING = 3
    SELECTING_TARGET = 4
    LOST = 5
    WON = 6