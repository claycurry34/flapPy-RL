from math import exp, pi
from operator import index
from os import preadv
from random import random, randrange
from statistics import median
from turtle import update
import numpy as np
from typing import List
import pygame
import time
import config
import torch
import sys

# Actions
NO_FLAP = False
FLAP = True

# States
NUM_Y_STATES = 20                   # encodes height of player (this should be odd for keeping in center)
NUM_V_STATES = 10                   # encodes player velocity
NUM_DX_STATES = 1                   # encodes distance from pipe to player
NUM_PIPE_STATES = 8                 # encodes center position between pipes
NUM_ACTIONS = 2

# Training Parameters
J = 5           # overridden by command line arguments; determines which parameter index to use
EPSILON        = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
DISCOUNT       = [0.9, 0.9, 0.9, 0.9, 0.9, 0.9]
STEP_SIZE      = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1]

# Values + Uncertainty

# Learns on policy
class Agent:
    def __init__(self, FPS):
        self.FPS = FPS
        self.t = 0        # used to discretize time
        self.score_hist = [0]  
        self.sequence_count = 0
        self.hist_size = 300
        self.Q = makeQ()

        if len(sys.argv) > 1 and sys.argv[1].isnumeric:
            cmd_arg = sys.argv[1]
            self.EPSILON = EPSILON[int(cmd_arg)]
            self.DISCOUNT = DISCOUNT[int(cmd_arg)]
            self.STEP_SIZE = STEP_SIZE[int(cmd_arg)]
        else:
            self.EPSILON = EPSILON[int(J)]
            self.DISCOUNT = DISCOUNT[int(J)]
            self.STEP_SIZE = STEP_SIZE[int(J)]

        self.prev_SAR = []
        print("Created Q Learning Agent")
                                      
    def move(self, y_pos, y_vel, x_pipe, y_pipe,score):        
        move = NO_FLAP

        self.t = (1 + self.t)       
        if self.t % int(self.FPS * config.T_BETWEEN_STATES) == 0:
            # compute current state, reward action
            state = self.compute_state(y_pos, y_vel, x_pipe, y_pipe)
            reward = self.compute_reward(y_pos, y_pipe)
            action = self.compute_action(state, epsilon=self.EPSILON)
            self.prev_SAR.append((state, action, reward))
            if config.LOG:
                self.log_flappy(state=state, reward=reward, next_move=action)
            
            # self.update(reward_now=reward, state_now=state, action_now=action)
            
            move = FLAP if action == 1 else NO_FLAP

        return move
        
    def compute_state(self, y_pos, y_vel, x_pipe, y_pipe):
        try:
            Y_POS = map_bin(
                x=y_pos,
                minimum=config.Y_MIN_AGENT-50,
                maximum=config.Y_MAX_AGENT,
                n_bins=NUM_Y_STATES,
                enforce_bounds=True
            )

            Y_VEL = map_bin(
                x=y_vel,
                minimum=config.Y_MIN_VELOCITY,
                maximum=config.Y_MAX_VELOCITY,
                n_bins=NUM_V_STATES
            )

            DX = map_bin(
                x=x_pipe-config.X_POS_AGENT,
                minimum=0,
                maximum=config.X_MAX_PIPE,
                n_bins=NUM_DX_STATES,
                enforce_bounds=False
            )

            C_PIPE = map_bin(
                x= y_pipe,
                minimum=config.Y_MIN_LPIPE,
                maximum=config.Y_MAX_LPIPE,
                n_bins=NUM_PIPE_STATES,
                enforce_bounds=True)

        except ValueError as e:
            print(e)
            raise ValueError

        return (Y_POS, Y_VEL, DX, C_PIPE)

    def compute_reward(self, y_pos, y_pipe):
        return 1
        
    def compute_action(self, state, epsilon):
        "returns the esilon-greedy action over the possible actions"
        # Sanity check
        if epsilon < 0 or 1 < epsilon:
            raise ValueError(f"epsilon = {epsilon} which is not in [0,1]")

        greedy_index = 0        # no flap by default
        if self.Q[state][1] > self.Q[state][0]:
            greedy_index = 1    # flap if greedy

        if np.random.uniform(0, 1) >= epsilon: # true (1-epsilon)% of the time
            return greedy_index
        else:
            return 1 - greedy_index

    def update(self, reward_now, state_now, action_now):
        self.prev_SAR.append((state_now, action_now, reward_now))
        
        if len(self.prev_SAR) > self.hist_size:
            s,a,_ = self.prev_SAR.pop(0)
            state_now, action_now, reward_now = self.prev_SAR[0]
            max_action = max(self.Q[state_now])
            expected_update = self.STEP_SIZE * (reward_now + self.DISCOUNT * max_action - self.Q[s][a])
            self.Q[s][a] += expected_update
            self.Q[s][a]=self.Q[s][a]             
            

    def update_gameover(self):
        s = self.prev_SAR.pop()[0]
        pipe_height = config.Y_MIN_LPIPE + s[3] / (NUM_PIPE_STATES - 1) * (config.Y_MAX_LPIPE - config.Y_MIN_LPIPE)
        agent_height = config.BASEY * s[0] / (NUM_Y_STATES-1)
        low_death = False
        low_update = 0
        if agent_height > pipe_height:
            print('low')
            low_death = True           
        
        Gt = 0
        self.prev_SAR.reverse()
        while len(self.prev_SAR) > 0:
            s, a, r = self.prev_SAR.pop(0)
            if low_death and self.Q[s][0] >= self.Q[s][1]:
                self.Q[s][1]  = self.Q[s][0] + 0.1
                low_update += 1
                if low_update == 2:
                    low_death = False
            else:
                self.Q[s][a] += self.STEP_SIZE * (Gt - self.Q[s][a])
                Gt = r + self.DISCOUNT * Gt



    def gameover(self, y_pos, y_vel, x_pipe, y_pipe, score,update):
        self.t = 0
        self.EPSILON /= 1.00138640

        if update:
            self.update_gameover()

        self.score_hist.append(score)
        print(f'GAMEOVER(Q Learning): score = {score} max = {max(self.score_hist)}')
        print(f'Number Episodes = {len(self.score_hist)}')
        
        if len(self.score_hist) >= config.EPISODES_PER_SEQUENCE:
            self.save()
            from datetime import datetime
            # make file
            self.Q = makeQ()
            self.score_hist = []
            
            self.sequence_count += 1
            if self.sequence_count >= config.SEQUENCE_PER_PARAMETER:
                exit(0)
                
    def save(self):
        if config.SAVE == False:
            return
        from datetime import datetime
        dt = datetime.now().strftime("%m-%d-%Y-%H.%M.%S")
        saved = False
        while saved == False:
            try:
                open(f"data/scores/qlearning-rate-{self.STEP_SIZE}-{dt}.txt", 'x') 
                with open(f"data/scores/qlearning-rate-{self.STEP_SIZE}-{dt}.txt", 'w') as f:
                    f.write(str(self.score_hist))

                torch.save(self.Q, f"data/weights/qlearning-rate-{self.STEP_SIZE}-{dt}.pt")
                saved = True
            except Exception as e:
                print(e)
                dt = datetime.now().strftime("%m-%d-%Y %H.%M.%S")

    def log_flappy(self, state, reward, next_move) -> None:
        print(f'State = {state}')
        print(f'Reward = {reward}')
        print(f'Action = ' + ("Flap" if next_move == 1 else "No Flap"))
        print(f'V(NO_FLAP): {self.Q[state][0]}')
        print(f'V(FLAP): {self.Q[state][1]}')
        
        print()

def map_bin(x: float, minimum: float, maximum: float, n_bins: int,
            f=lambda x: x, one_indexed=False, enforce_bounds=True):
    # Sanity check
    if minimum > maximum:
        raise ValueError("minimum was not less than maximum")
    elif n_bins <= 0:
        raise ValueError("number of bins in positive")
    elif x < minimum:
        if enforce_bounds:
            raise ValueError("x was less than minimim")
        else:
            x = minimum
    elif x > maximum:
        if enforce_bounds:
            raise ValueError("x was greater than maximum")
        else:
            x = maximum

    # map to bin
    from math import floor
    _hash = (x - minimum) / (maximum - minimum)
    _hash = _hash if _hash < 0.0000001 else _hash - 0.0000001
    _hash = f(_hash) * n_bins
    _hash = floor(_hash)
    if one_indexed:
        return _hash + 1
    else:
        return _hash

def makeQ():
    if config.LOAD:
        return torch.load(f'data/weights/{config.LOAD_FILE}')
    else:
        Q = torch.ones((NUM_Y_STATES, NUM_V_STATES, NUM_DX_STATES, NUM_PIPE_STATES, NUM_ACTIONS)) * 3
        return Q