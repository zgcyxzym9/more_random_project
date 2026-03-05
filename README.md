# more_random_project
**Note: the actor-critic method in `rl` is deprecated, please use the DQN model in `rl_dqn`**

## Repo structure

`game_core` This is where all the game simulation files are.

`env` This folder contains the environment used for RL training.

`rl` This folder contains all the code for the actor-critic method. **Currently this method and this folder is not maintained.**

`rl_dqn` This folder contains all the code for the DQN method.

## How to use the model for inference

In the `rl_dqn` folder you can find `inference_full_game.py`. Change the card list of `player1` to your starting deck, and the card list of `player2` to the opponent's starting deck (if available) for a more accurate simulation. Then run the code. Note that changing the agent's decision is currently not supported.

This work currently only considered a small range of cards and heroes. Check `game_core\cards\card_names.txt` and `game_core\hero_names.txt` for a complete list of supported cards and heroes.