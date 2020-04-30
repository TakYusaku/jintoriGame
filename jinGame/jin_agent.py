import datetime
import math
import sys
import pandas as pd
import pickle
import random
import numpy as np
import mimetypes
import json
import copy
import os
from collections import deque
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

import jin_jinGame
from jin_consts import *
from jin_init_parameter_optim import *
from jin_parameter import *
from jin_replayMemory import *
from jin_replayMemory import *
from jin_util import *
from jin_consts import *
from jin_NN import *

def get_dim_list(li): # 2次元配列(list)のshapeを取得
    return [len(li),len([len(v) for v in li])]

class jinGame_DQNAgent():
    # 何か初期化がいるなら追加する
    def __init__(self,k_division=17, states_number=27, eps_start=0.99, eps_end=0.1, eps_decay=100,gamma=0.9, target_update=10):#target_update=7):
        self.k_division = k_division
        self.states_number = states_number
        self.actions_number = k_division
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay = eps_decay
        self.gamma = gamma
        self.target_update = target_update
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        #以下の変数はrun agentのタイミングで初期化する。これらは商品の数によって決まる。
        self.numberOfProducts = 0
        self.batch_size = 0
        self.memory_length = 0
        self.samplingCount = 0
        self.averageLoss = -1
        self.eps_threshold = 0

        self.on_epsilon_zero = ON_EPSILON_ZERO

        self.action_history = deque() # 行った行動を保存しておく
        self.agent_history = [[],[],[]] # [[#loss_median], [# target_name], [# policy_name]]
        self.feature_for_reward = [[],[],[],[],[]] #[[before_point],[now_point],[code],[do_direction]]

        self.EXPORT_REPLAYMEMORY_FILE_NAME_1 = ''
        self.EXPORT_REPLAYMEMORY_FILE_NAME_2 = ''
        self.IMPORT_REPLAYMEMORY_FILE_NAME_1 = ''
        self.IMPORT_REPLAYMEMORY_FILE_NAME_2 = ''

        self.IMPORT_TARGET_FILE_NAME = IMPORT_TARGET_FILE_NAME
        self.IMPORT_POLICY_FILE_NAME = IMPORT_POLICY_FILE_NAME
        self.EXPORT_POLICY_FILE_NAME = EXPORT_POLICY_FILE_NAME
        self.EXPORT_TARGET_FILE_NAME = EXPORT_TARGET_FILE_NAME

    #初期化
    def _init_agent(self, flg=False):
        if self.on_epsilon_zero: # epsilon-zero起動時
            print('is epsZero')
            if not flg: # 学習のとき
                #print('_init_agent: not flg')
                self.policy_net = DQN_epsZero(self.states_number, self.actions_number).to(self.device)
                self.target_net = DQN_epsZero(self.states_number, self.actions_number).to(self.device)
                self.target_net.eval()
                self.optimizer = optim.RMSprop(self.policy_net.parameters(),lr=1e-4)
                self.replay_memory = ReplayMemory(self.memory_length)
            else: # evaluationのとき
                #print('_init_agent: flg')
                self.policy_net_a = DQN_epsZero(self.states_number, self.actions_number).to(self.device)
                self.target_net_a = DQN_epsZero(self.states_number, self.actions_number).to(self.device)
                self.target_net_a.eval()
                self.policy_net_e = DQN_epsZero(self.states_number, self.actions_number).to(self.device)
                self.target_net_e = DQN_epsZero(self.states_number, self.actions_number).to(self.device)
                self.target_net_e.eval()
        else: # dqnのとき
            print('is dqn')
            if not flg: # 学習のとき
                self.policy_net = DQN(self.states_number, self.actions_number).to(self.device)
                self.target_net = DQN(self.states_number, self.actions_number).to(self.device)
                self.target_net.eval()
                self.optimizer = optim.RMSprop(self.policy_net.parameters(),lr=1e-4)
                self.replay_memory = ReplayMemory(self.memory_length)
            else: # evaluationのとき
                self.policy_net_a = DQN(self.states_number, self.actions_number).to(self.device)
                self.target_net_a = DQN(self.states_number, self.actions_number).to(self.device)
                self.target_net_a.eval()
                self.policy_net_e = DQN(self.states_number, self.actions_number).to(self.device)
                self.target_net_e = DQN(self.states_number, self.actions_number).to(self.device)
                self.target_net_e.eval()

    def _load_agent(self,file_name=None,flg=False): # fn_agent = {"policy": [name], "target": [name] }
        if not flg: # 学習の際
            if file_name is None:
                self.policy_net.load_state_dict(torch.load(self.IMPORT_POLICY_FILE_NAME))
                self.target_net.load_state_dict(torch.load(self.IMPORT_TARGET_FILE_NAME))
            else:
                self.policy_net.load_state_dict(torch.load(file_name['policy']))
                self.target_net.load_state_dict(torch.load(file_name['target']))            
        else: # evaluationのとき
                self.policy_net_a.load_state_dict(torch.load(file_name[0]['policy']))
                self.target_net_a.load_state_dict(torch.load(file_name[0]['target']))   
                self.policy_net_e.load_state_dict(torch.load(file_name[1]['oppo_policy']))
                self.target_net_e.load_state_dict(torch.load(file_name[1]['oppo_target']))   

    #replay_memoryにはmemory_lengthだけ格納することができる。その中から一回だけ、batch_size分だけ取得して学習する。
    def _optimize_model(self):
        #replay_memoryにbatch_size分だけ入っていない時は中止する
        if len(self.replay_memory) < self.batch_size:
            return
        sampled_data = self.replay_memory.sample(self.batch_size)
        sampled_state = torch.FloatTensor([])
        sampled_action = []
        sampled_reward = []
        sampled_next_state = torch.FloatTensor([])
        for data in sampled_data:
            #catはtorch.Tensorをリスト入れて渡すことで、それらを連結したTensorを返してくれる。0で行を追加となる
            #print('type(data)',type(data))
            #print(data)
            sampled_state = torch.cat((sampled_state, data.state.view(1,-1)), 0)
            sampled_next_state = torch.cat((sampled_next_state, data.next_state.view(1,-1)), 0)
            sampled_action.append(data.action)
            sampled_reward.append(data.reward)
        

        #print('sampled_state: ',sampled_state)
        #print('sampled_next_state: ',sampled_next_state)
        #print('sampled_action: ',sampled_action)
        #print('sampled_reward: ',sampled_reward)

        sampled_action = torch.FloatTensor(sampled_action)
        sampled_reward = torch.FloatTensor(sampled_reward)
        

        #to GPU
        sampled_state = sampled_state.to(self.device)
        sampled_next_state = sampled_next_state.to(self.device)
        sampled_action = sampled_action.to(self.device)
        sampled_reward = sampled_reward.to(self.device)

        #dimで指定された軸(dim=1(列))に沿って、選択した行動を基にQ(s_t, a)を収集。
        #print('sampled_action',sampled_action)
        #print('sampled_action.unsqueeze(1).long()',sampled_action.unsqueeze(1).long())
        #print('self.policy_net(sampled_state)',self.policy_net(sampled_state))
        state_action_values = self.policy_net(sampled_state).gather(1, sampled_action.unsqueeze(1).long())
        #target_netでは次の状態でのQ値を出す。ここではmaxを取る
        next_state_values = self.target_net(sampled_next_state).max(1)[0].detach()
        expected_state_action_values = (next_state_values * self.gamma) + sampled_reward
        # expected_state_action_valuesは
        # sizeが[batch_size]になっているから、unsqueezeで[batch_size x 1]へ
        criterion = nn.MSELoss()
        sampleLoss = criterion(state_action_values, expected_state_action_values.unsqueeze(1))
        self.optimizer.zero_grad()
        # 勾配の計算
        sampleLoss.backward()
        # error clipping
        for param in self.policy_net.parameters():
            #勾配の値を直接変更する
            #https://pytorch.org/docs/master/torch.html#torch.clamp
            param.grad.data.clamp_(-1, 1)
        # パラメータの更新
        self.optimizer.step()
        #lossから実数値を取り出す。
        sampleLoss = sampleLoss.item()
        #第一引数に元の数値、第二引数に桁数（何桁に丸めるか）を指定する。
        return round(float(sampleLoss), 3)

    def _reward(self,usr):
        #return 2*sigmoid(reward_r/100)-1
        print('usr',usr)
        print('self.feature_for_reward',self.feature_for_reward)
        rewards = (self.feature_for_reward[1][usr] - self.feature_for_reward[0][usr])/6 + (self.feature_for_reward[2][usr]-5)/5
        print('reward',rewards)
        return rewards/2

    def _reward_ver2(self,usr):
        #print('usr',usr)
        #print('self.feature_for_reward',self.feature_for_reward)
        if self.feature_for_reward[2][usr]==5 or (self.feature_for_reward[2][usr]==4 and self.feature_for_reward[3][usr] > 8): # codeが5,4(remove)なら1, それ以外なら-1
            fac1 = 1
        else:
            fac1 = -1

        if self.feature_for_reward[3][usr]==-1: 
            fac2 = 0
        elif self.feature_for_reward[3][usr]==4: # 他のますに対する行動をしなかったら-1, したら1
            fac2 = -1
        else:
            fac2 = 1

        if usr==1:
            idx = 1
        else:
            idx = 4

        if (self.feature_for_reward[0][idx] != 0 and self.feature_for_reward[1][idx] != 0) or (self.feature_for_reward[0][idx] == 0 and self.feature_for_reward[1][idx] != 0): # areapoint!=0が維持 or areapoint が入れば1
            fac3 = 1
        elif self.feature_for_reward[0][idx] != 0 and self.feature_for_reward[1][idx] == 0: # areapointが0になれば-1,
            fac3 = -1
        else:
            fac3 = -1

        #print('fac1,fac2,fac3',fac1,fac2,fac3)
        reward = (fac1+fac2+fac3)/3
        #print('reward',reward)
        return reward

    def _reward_ver3(self,env, usr):
        #print('usr',usr)
        #print('self.feature_for_reward',self.feature_for_reward)
        if usr==1:
            idx = 1
            pnl = 5
        else:
            idx = 4
            pnl = 6

        pf, uf = env._getField()
        uf = np.array(uf)
        uf_shape = uf.shape
        #print('uf_shape',uf_shape)
        uf = np.ravel(uf)
        if self.feature_for_reward[2][usr]==5 or (self.feature_for_reward[2][usr]==4 and self.feature_for_reward[3][usr] > 8): # codeが5,4(remove)なら1, それ以外なら-1
            fac1 = 1
            pos = self.feature_for_reward[4][usr]
            #print('pos',pos)
            #print('n_pos',pos[0] + pos[1]*uf_shape[1])
            if uf[pos[0] + pos[1]*uf_shape[1]] != pnl:
                fac4 = 1
            else:
                fac4 = -1
        else:
            fac1 = -1
            fac4 = -1

        if self.feature_for_reward[3][usr]==-1: 
            fac2 = 0
        elif self.feature_for_reward[3][usr]==4: # 他のますに対する行動をしなかったら-1, したら1
            fac2 = -1
        else:
            fac2 = 1

        if (self.feature_for_reward[0][idx] != 0 and self.feature_for_reward[1][idx] != 0) or (self.feature_for_reward[0][idx] == 0 and self.feature_for_reward[1][idx] != 0): # areapoint!=0が維持 or areapoint が入れば1
            fac3 = 1
        elif self.feature_for_reward[0][idx] != 0 and self.feature_for_reward[1][idx] == 0: # areapointが0になれば-1,
            fac3 = -1
        else:
            fac3 = -1

        #print('fac1,fac2,fac3,fac4',fac1,fac2,fac3,fac4)
        reward = (fac1+fac2+fac3+fac4)/4
        #print('reward',reward)
        return reward

    def _insert_agent(self, user_id):
        japantime_now = get_japantime_now()
        japantime_now_str = date_to_date(japantime_now)
        #最初の保存でのデータは使えないので、pickled_replay_memory_itemID_valueListに[]を格納する
        pickled_replay_memory_userID_valueList = pickle.dumps([])
        #insert_dictはdynamo_insert_itemメソッドで変数Itemに格納されている。
        insert_dict = {
            'user_id': int(user_id),
            'steps_done': int(self.steps_done),
            'replay_memory_memory': pickled_replay_memory_userID_valueList,
            'create': japantime_now_str
        }
        #print(insert_dict)

        #print('steps_done: ', self.steps_done)
        #print('create: ', japantime_now_str)
        if user_id == 1:
            self.EXPORT_REPLAYMEMORY_FILE_NAME_1 = REPLAYMEMORY_DIRECTORY_NAME + japantime_now_str + '_usr' + str(user_id)
            self.IMPORT_REPLAYMEMORY_FILE_NAME_1 = self.EXPORT_REPLAYMEMORY_FILE_NAME_1
        else:
            self.EXPORT_REPLAYMEMORY_FILE_NAME_2 = REPLAYMEMORY_DIRECTORY_NAME + japantime_now_str + '_usr' + str(user_id)
            self.IMPORT_REPLAYMEMORY_FILE_NAME_2 = self.EXPORT_REPLAYMEMORY_FILE_NAME_2
        self._save_data_pickle(insert_dict,user_id)
        #print('insert agent: done')
        return True

    def _save_agent(self, userID, replay_memory_userID_valueList):
        japantime_now = get_japantime_now()
        japantime_now_str = date_to_date(japantime_now)
    
        pickled_replay_memory_userID_valueList = pickle.dumps(replay_memory_userID_valueList)
        
        update_dict = {
            'user_id': int(userID),
            'steps_done': int(self.steps_done),
            'replay_memory_memory': pickled_replay_memory_userID_valueList,
            'updated': japantime_now_str
        }
        self._save_data_pickle(update_dict,userID)
        #print('saved agent: done')
        return True

    def _save_data_pickle(self,data,userID):
        if userID == 1:    
            file_name = self.EXPORT_REPLAYMEMORY_FILE_NAME_1
        else:
            file_name = self.EXPORT_REPLAYMEMORY_FILE_NAME_2
        #print(file_name)
        with open(file_name,'wb') as f:
            f.write(pickle.dumps(data))
        return True

    def _read_data_pickle(self, userID):
        if userID == 1:
            file_name = self.IMPORT_REPLAYMEMORY_FILE_NAME_1
        else:
            file_name = self.IMPORT_REPLAYMEMORY_FILE_NAME_2
        try:
            with open(file_name, 'rb') as f:
                data = pickle.loads(f.read())
            return data
        except:
           return None

    def _report_agent(self):
        return
        #print('#######################')
        ##print(get_japantime_now())
        #print('k division: ', self.k_division)
        #print('states number: ', self.states_number)
        #print('epsilon start: ', self.eps_start)
        #print('epsilon end: ', self.eps_end)
        #print('eplison decay: ', self.eps_decay)
        #print('gamma:', self.gamma)
        #print('target update: ', self.target_update)
        #print('memory length: ', self.memory_length)
        #print('device: ', self.device)

    def get_network_fn(self, idx, flag):
        date_now = get_japantime_now() # util.py
        date_now_str = date_to_date(date_now)
        #print(date_now_str)
        #print(type(date_now_str))
        idx_str = str(idx)
        if flag:
            flag_str = 'T'
        else:
            flag_str = 'F'
        #dir_name = PARAMETER_DIRECTORY_NAME + TODAYS_DATE_DIRECTORY_NAME
        dir_name = PARAMETER_DIRECTORY_NAME
        tmp = date_now_str + '_' + idx_str + '_' + flag_str + '.pt'
        fn = {"policy":dir_name + 'policy_' + tmp, "target": dir_name + 'target_' + tmp}
        return fn

    def _save_network(self, idx, flag):
        fn = self.get_network_fn(idx, flag)
        self.EXPORT_POLICY_FILE_NAME = fn["policy"]
        self.EXPORT_TARGET_FILE_NAME = fn["target"]
        torch.save(self.policy_net.state_dict(),self.EXPORT_POLICY_FILE_NAME)
        torch.save(self.target_net.state_dict(),self.EXPORT_TARGET_FILE_NAME)
        return fn

    def _select_action(self, state, evaluation=False, ez_flg=False): # ez_flg は epsilon-zero 用フラグ
        state = state.to(self.device)
        if evaluation or ez_flg: # self play中
            #print('ez_flg')
            #print("######### policy net ###")
            #print(self.policy_net)
            #print(self.policy_net(state))
            with torch.no_grad():
                #(1)で列　[1]でmaxになっているindexを取得
                return self.policy_net(state).max(1)[1]
        else: # 学習中
            sample = random.random()
            #これはPyTorchのDQNチュートリアルから
            eps_threshold = self.eps_end + (self.eps_start - self.eps_end) *  math.exp(-1. * self.steps_done / self.eps_decay)
            self.eps_threshold = eps_threshold
            #print("######### policy net ###")
            #print('self.policy_net',self.policy_net)
            #print('(state)',self.policy_net(state))
            if sample > eps_threshold:
            #if sample < eps_threshold:
                with torch.no_grad():
                    return self.policy_net(state).max(1)[1]
            else:
                #ランダムセレクト
                return torch.tensor(random.randrange(self.actions_number), device=self.device, dtype=torch.long)
                #return torch.tensor([random.randrange(self.actions_number) for i in range(len(state))], device=self.device, dtype=torch.long)

    def _run_agent(self, env, df_division, model_state_dict, epc, turn,i_flg=False): # 学習させてloss, nextActionを取得, i_flgは各インターバル1回目の学習
        dim = df_division.shape
        #モデルに渡すagentの数
        self.numberOfProducts = dim[0]#len(df_division)
        self.batch_size = min(64,int(self.numberOfProducts/2))
        #batch_sizeが２未満だと、標準化するときにエラーとなってしまうため、self.batch_sizeを2以上にする。
        if self.batch_size < 2:
            self.batch_size = 2
        
        self.memory_length = 14*self.numberOfProducts
        #_optimize_modelを呼び出す回数 ＝ 勾配を求める回数
        #samplingCountは徐々に減らすようにした方がいいかもしれない
        self.samplingCount = int(self.numberOfProducts / self.batch_size) * 20

        #print('numberOfProducts: ', self.numberOfProducts)
        #print('batch_size: ', self.batch_size)
        #print('memory_length: ', self.memory_length)
        #print('samplingCount: ',self.samplingCount)

        #userId取得
        userIDList = [1,2]
        
        if i_flg: # epoch = 1 かつ turn =1 のとき , ここでのepochは各インターバルでのepoch =1
            #print('i_flg')
            self._init_agent()
            #初回はpytorchのパラメータ保存ファイルがないので、loadしない。初回はsteps_done=0となる。
            if self.steps_done==0:
                if self.IMPORT_POLICY_FILE_NAME != '' and self.IMPORT_TARGET_FILE_NAME != '': # importfile名が空でない, つまり一番最初から指定したパラメータで学習を行う
                    self._load_agent()
                else: # 完全にまっさらな状態から学習を始める
                    #ここで楽観的初期化を行う
                    self.policy_net.load_state_dict(model_state_dict)
                    self.target_net.load_state_dict(model_state_dict)
            # if self.steps_done != 0:
            elif self.steps_done != 0:
                self._load_agent()

        replay_memory_dic = {}
        #rowがない場合(dynamo_select_row_by_itemIDでNoneとなる)とreplay_memory_memoryの内容が古い場合、このリストにitemIDを追加する
        none_user_id_list = [0,0]

        #replay_memoryをdynamoDBから読み込んで作成。
        #条件によって、not_max_steps_done_item_id_listとnone_item_id_listにitemIDを追加する
        #itemID毎に要素を取り出して、連結していく。
        # setps_doneが常にmaxであると願って...
        for userID in enumerate(userIDList):
            row = self._read_data_pickle(userID[1])
            if row is None:
                #print('row is none')
                none_user_id_list[userID[1]-1] = userID[1]
                replay_memory_dic[str(userID[1])] = None
            else:
                #print('row is existed')            
                replay_memory_dic[str(userID[1])] = pickle.loads(row['replay_memory_memory'])
        #print('epc',epc)
        #print('turn',turn)
        #print('replay_memory_dic',replay_memory_dic)

        #print(replay_memory_dic)
        #replay_memory_itemID_valueListに要素の数が最大で何個入っているか求める。最大サイズをmaxLengthに格納する
        maxLength = 0
        for replay_memory_userID_valueList in replay_memory_dic.values():
            if replay_memory_userID_valueList is not None:
                length = len(replay_memory_userID_valueList)
                if maxLength < length:
                    maxLength = length

        #print('maxLength',maxLength)
        #valueを取り出して、replay_memoryに格納していく
        #古いものから新しいものを入れていく
        for i in range(maxLength):
            for replay_memory_userID_valueList in replay_memory_dic.values():
                if replay_memory_userID_valueList is not None:
                    if len(replay_memory_userID_valueList) -1 >= i:
                        dayValue = replay_memory_userID_valueList[i]
                        #replay_memoryは_init_agentメソッドで初期化される。
                        #state, action, next_state, reward, userIDの順番
                        self.replay_memory.push(dayValue[0],dayValue[1],dayValue[2],dayValue[3],dayValue[4])

        #stateはbefore_(１日前)から取得
        state = torch.FloatTensor(df_division[:,:int(dim[1]/2)])
        #print('state(before_features)',state)

        actionList = torch.from_numpy(np.array(self.action_history.pop()))
        #print('actionList(state to next_state):',actionList)
        
        #next_stateはfeatures(当日)から取得
        next_state = torch.FloatTensor(df_division[:,int(dim[1]/2):])
        #print('next_state:',next_state)
        
        #before_features_listの内容を追加する。辞書の更新とreplay_memoryの更新
        replay_memory_count = 0
        reward = []
        for i in range(len(state)):
            #ここで取り出される順番はitemIDListと対応している。
            #辞書からvalueListを取得。
            #初回の時と一旦ストップした商品はreplay_memoryには入れない。

            # reward
            #reward.append(self._reward(i))
            #reward.append(self._reward_ver2(i))
            reward.append(self._reward_ver3(env, i))
            #print('reward:',reward)

            if replay_memory_dic[str(userIDList[i])] is None:
                #print('replay_memory_dic is None')
                continue
            #print(replay_memory_dic[str(userIDList[i])])
            replay_memory_userID_valueList = replay_memory_dic[str(userIDList[i])]
            #print('replay_memory_userID_valueList',replay_memory_userID_valueList)
            #print(replay_memory_userID_valueList)
            #追加するvalue
            #addValue = [state[i], actionList[i], next_state[i], reward[i],itemIDList[i]]
            addValue = [state[i], actionList[i], next_state[i], reward[i], userIDList[i]]
            #print('addValue=[state[i], actionList[i], next_state[i], reward[i],itemIDList[i]]:',addValue)
            #continueでない時、２回目以降などにくる。
            #valueListにappendする
            replay_memory_userID_valueList.append(addValue)
            #更新したvalueListを格納する。
            #replay_memory_dic[itemIDList[i]] = replay_memory_itemID_valueList
            replay_memory_dic[str(userIDList[i])] = replay_memory_userID_valueList
            replay_memory_count += 1
            #overWriteFlagがTrueの場合、上書きが発生した。辞書に対しても、先頭のValueに対して削除を行う必要がある。
            overWriteFlag,deleteItemID = self.replay_memory.push(state[i], actionList[i], next_state[i], reward[i],userIDList[i])
            if overWriteFlag:
                replay_memory_dic[str(deleteItemID)].pop(0)
        #print('replay_memory_dic',replay_memory_dic)
        #print("replay_memory_count: ",replay_memory_count)
        #print("replay_memory_size: ",len(self.replay_memory))
        #print("#############")
        #print("replay_memory_memory")
        #print(self.replay_memory.memory)
        #optimize_modelメソッドをsamplingCountだけ走らせる。samplingCountだけlossが求まり、パラメータが更新される。
        returnLoss = -1
        sumLoss = 0

        #self.samplingCountだけ勾配を求める
        for count in range(self.samplingCount):
            #学習
            sampleLoss = self._optimize_model()
            #if len(self.replay_memory) < self.batch_size: の時、return None
            if sampleLoss is None:
                break
            #print('count',count)
            #print('sampleLoss',sampleLoss)
            sumLoss += sampleLoss
        if sumLoss != 0:
            returnLoss = sumLoss / self.samplingCount
            self.averageLoss = returnLoss
        #print('loss',returnLoss)
        if epc == 0 and turn ==0 and self.steps_done % self.target_update == 0:
            #print('update target net')
            self.target_net.load_state_dict(self.policy_net.state_dict())

        # map to price
        new_action = np.array([0,0])
        #next_stateからnew_actionが求まる　このnew_actionからnew_priceが求まり、これがreturnされる。
        for i in range(len(df_division)):
            new_action[i] = self._select_action(next_state[i],ez_flg=self.on_epsilon_zero)
        
        #self.steps_done += 1
        #print('new_action by [next_state](next_state to next_next state):',new_action)
        #print('none_user_id_list',none_user_id_list)

        for userID in enumerate(userIDList):
            if none_user_id_list[userID[1]-1] == 0: # row is not None. no plobrem
                replay_memory_userID_valueList = replay_memory_dic[str(userID[1])]
                self._save_agent(userID[1],replay_memory_userID_valueList)
            else: # row is none
                self._insert_agent(userID[1])
                #print('_insert_agent_')

        self._report_agent()
        return new_action, returnLoss, np.array(reward)

    def agent_learning(self, env, idx, evaluation=False): # 一定期間試合を行わせて学習をさせる
        epochs_done = 0 # 正しく実行された回数をカウント
        loss_per_epoch = [] # 試合ごとのloss (最終ターンでのlossを収集)

        #try:
            # epochs の数だけ学習を行う
            # 流れ
            # 1.環境のリセット
            # 2.turnの数だけ各エージェントが行動とoptimizeを行う
            #  2.1 各エージェントの次の行動決定とoptimize
            #   2.1.1 ネットワークに突っ込むdata(特徴量)をまとめる
            #   2.1.2 楽観的初期化
            #   2.1.3 特徴量から行動を取得
            #  2.2 エージェントの移動先が重なっていないか判定し，行動を決定する
            #   2.2.1 重なっていなければデータを整理(行動を行う準備する)
            #   2.2.2 重なっていれば，両エージェントの行動をstayとする
            #  2.3 行動前に得点を取得
            #  2.4 行動させる
        epochs = EPOCHS
        for epc in range(epochs):
            print('now_epc:',epc+1)
            # game start
            # self.agent_history()の初期化
            usr1_data = {'motion':"move", "lists": [1,4]}
            usr2_data = {'motion':"move", "lists": [2,4]}
            m_data = [usr1_data,usr2_data]
            n_data = [4,4]
            self.action_history.append(n_data)
            #print('self.action_history',self.action_history)

            turn, length, width = env._start()
            before_features = []
            # turn の数だけ，行動を行う
            for t in range(turn+1):
                #print('############################# now_turn %d #############################' % (t+1))
                if t == 0: # before_feature の初期化
                    before_features = torch.cat(
                        (env.get_features(t,1),env.get_features(t,2)),
                        dim = 0
                    )
                else: # フィールドの得点を変える
                    env._changeField()
                # 2エージェント分の特徴量をまとめる
                now_features = torch.cat(
                    (env.get_features(t+1,1),env.get_features(t+1,2)),
                    dim=0 # 横長の配列を縦に並べる
                )#前ターンの行動後(つまり現ターンの行動前)の特徴量
                data = torch.cat(
                    (before_features, now_features),
                    dim = 0 # 配列を縦にくっつける
                )
                df_division = torch.cat(
                    (before_features, now_features),
                    dim = 1 # 配列を縦にくっつける
                )
                #print('df_division:',df_division)
                #print('before_features',before_features)
                #print('now_features',now_features)
                before_features = now_features # 次ターンのbefore_featuresに，現ターン行動前の特徴量を設定する
                # for 楽観的初期化
                #k_division = 17 # 行動数
                #states_num = 18 #len(data) 特徴量の大きさ(skalar)
                model = param_init_model(data, self.k_division, self.states_number, self.on_epsilon_zero, ite = 20, epoch = 5)
                
                # 移動前に得点を取得
                point_before_moving = env._calcPoint()

                if t==0:
                    self.feature_for_reward[0] = [0,0,0,0,0,0] # before_point
                    #self.feature_for_reward[1] = [point_before_moving[2],point_before_moving[5]] # now_point
                    self.feature_for_reward[1] = point_before_moving # now_point
                    self.feature_for_reward[2] = [5,5] # code
                    self.feature_for_reward[3] = [-1,-1]
                    self.feature_for_reward[4] = [env._getPosition(1),env._getPosition(2)]
                else:
                    self.feature_for_reward[0] = self.feature_for_reward[1] # before_point
                    #self.feature_for_reward[1] = [point_before_moving[2],point_before_moving[5]] # now_point
                    self.feature_for_reward[1] = point_before_moving # now_point
                #print('self.features_for_reward',self.feature_for_reward)
                #print('[[before_point],[now_point],[code],[do_direction]]')
                # 特徴量をもとにネットワークから行動を取得
                    # run_agent() で次の行動を決める(実際に行動はしない)
                #agent = DQNAgent(self.k_division)
                #if not evaluation: # 学習中
                # db_agent, df_division
                if epc == 0 and t==0:
                    new_action, loss, reward = self._run_agent(env, df_division, model.state_dict(), epc, t, i_flg=True) # new_action は数字を返す
                else:
                    new_action, loss, reward = self._run_agent(env, df_division, model.state_dict(), epc, t) # new_action は数字を返す
                # item_id_division:usrID(のリスト), new_price_division: usrの次の行動("n_position": 座標,"motion": move or remove,"direction": 方向,"is_possible": s_judjedirection()のコード)
                usr_id_division = np.array([1,2])
                if t==turn:
                    new_action = np.array([None]*2)
                df_dic = {'usrID': usr_id_division, 'now_eval': np.array([idx+1]*2), 'num_epoch': np.array([epochs]*2),'now_epoch_n': np.array([epc+1]*2), 'num_turn': np.array([turn]*2),'now_turn': np.array([t+1]*2), 'calcAction': new_action, 'Loss': np.array([loss]*2), 'reward': reward}#* len(item_id_division))}
                #df_dic = {'calcAction': new_action, 'Loss': np.array([loss]*2), 'reward': reward}#* len(item_id_division))}

                # action = {"n_position": 座標,"motion": move or remove,"direction": 方向,"is_possible": s_judjedirection()のコード}
                df_action = {}
                df_action["do_motion"] = []
                df_action["do_direction"] = []
                df_action["is_possible"] = []
                df_action['now_position'] = []
                df_action["next_position"] = []

                for usrID in enumerate(usr_id_division):
                    if t==turn:
                        df_action["do_motion"].append([None]*2)
                        df_action["do_direction"].append([None]*2)
                        df_action["is_possible"].append([None]*2)
                        df_action['now_position'].append([None]*2)
                        df_action["next_position"].append([None]*2)
                    else:
                        code, data, next_pos = env._judgeDirection(usrID[1],new_action[usrID[1]-1])
                        df_action["do_motion"].append(data['motion'])
                        df_action["do_direction"].append(data['d'])
                        df_action["is_possible"].append(code)
                        self.feature_for_reward[2][usrID[1]-1] = int(code)
                        df_action['now_position'].append(env._getPosition(usrID[1]))
                        df_action["next_position"].append(next_pos)
                        self.feature_for_reward[4][usrID[1]-1] = next_pos

            
                if t < turn:
                    # エージェントの移動先が重なってるか，いないかを判定し行動を決定
                    #print(df_action)
                    cnf, m_data, n_data = env.check_action(df_action)
                    self.feature_for_reward[3] = n_data
                    #print('after_feature_for_reward:',self.feature_for_reward)
                    #print('m_data, n_data',m_data, n_data)

                    #df_action["is_possible"] = np.array([int(i) for i in enumerate(df_action["is_possible"][1])])
                    df_dic.update(df_action)
                    df_dic["is_confliction"] = np.array([cnf]*2)
                    #print(df_dic)

                    #print(m_data)
                    # 判定後に実際に移動させる
                    env.do_action(m_data[0])
                    env.do_action(m_data[1])
                    # 行動を保存しておく
                    self.action_history.append(new_action)
                    #print('self.action_history_after',self.action_history)
                    # 移動後の得点を取得
                    point_after_moving = env._calcPoint()

                df_dic['on_eps_zero'] = np.array([self.on_epsilon_zero]*2)
                df_dic['eps_threshold'] = np.array([self.eps_threshold]*2)
                # logを保存
                if LOG_IN_LEARNING:
                    df = pd.DataFrame(df_dic)
                    if epc == 0 and t == 0:
                        #self.EXPORT_LEARN_HISTORY_FILE_NAME = 'learn_history_' + str(idx) + '_' + str(epc) + '_' + TODAYS_DATE + '.csv'
                        self.EXPORT_LEARN_HISTORY_FILE_NAME = 'learn_history_' + str(idx) + '_' + TODAYS_DATE + '.csv'
                        df.to_csv(LEARN_HISTORY_DIRECTORY_NAME + self.EXPORT_LEARN_HISTORY_FILE_NAME, encoding='shift_jis')
                    else:
                        df.to_csv(LEARN_HISTORY_DIRECTORY_NAME + self.EXPORT_LEARN_HISTORY_FILE_NAME, mode='a', header=False, encoding='shift_jis')
                
                if t+1 == turn:
                    loss_per_epoch.append(loss)
            epochs_done += 1
            self.action_history.clear()

        fn = self._save_network(idx, True)
        np_loss = np.array(loss_per_epoch)
        logs = {"num_sets": str(idx),"num_epoch": str(epochs),"epochs_done": str(epochs_done), "loss_max":  np.max(np_loss), "loss_max_idx": np.argmax(np_loss), "loss_median": np.median(np_loss),"loss_min": np.min(np_loss),"loss_min_idx":np.argmin(np_loss),"loss_average":np.average(np_loss),"policy":fn["policy"], "target":fn["target"]}
        # logの保存
        return True, logs
        '''
        except:
            fn = self._save_network(idx, False)
            logs = {"num_sets": str(idx),"num_epoch": str(epochs),"epochs_done": str(epochs_done), "loss_max":  np.max(np_loss), "loss_max_idx": np.argmax(np_loss), "loss_median": np.median(np_loss),"loss_min": np.min(np_loss),"loss_min_idx":np.argmin(np_loss),"loss_average":np.average(np_loss),"policy":fn["policy"], "target":fn["target"]}
            # logの保存
            return False, logs
        '''

    def judgeWorL(self,df_dic):
        if df_dic['after_totalpoint'][0] > df_dic['after_totalpoint'][1]: # agentの勝利
            return True
        elif df_dic['after_totalpoint'][0] < df_dic['after_totalpoint'][1]:
            return False
        elif df_dic['after_totalpoint'][0] == df_dic['after_totalpoint'][1]:
            if df_dic['after_areapoint'][0] > df_dic['after_areapoint'][1]:
                return True
            else:
                return False

    def agent_evaluation(self, env, agent, opponent, idx):  # self playを行う
        e_log = {'agent_won':0, 'opponent_won':0, 'num_game': NUMBER_OF_SELFPLAY}
#        try:
        self._init_agent(flg=True)
        self._load_agent(file_name=[agent, opponent],flg=True)
        games_done = 0
        games_num = NUMBER_OF_SELFPLAY

        for g_num in range(games_num):
            print('now_selfplay:',g_num+1)
            before_features = []
            turn, length, width = env._start()
            # self.agent_history()の初期化
            usr1_data = {'motion':"move", "lists": [1,4]}
            usr2_data = {'motion':"move", "lists": [2,4]}
            m_data = [usr1_data,usr2_data]
            n_data = [4,4]
            self.action_history.append(n_data)
            # turn の数だけ，行動を行う
            for t in range(turn):
                if t == 0: # before_feature の初期化
                    before_features = torch.cat(
                        (env.get_features(t,1),env.get_features(t,2)),
                        dim = 0
                    )
                else: # フィールドの得点を変える
                    env._changeField()

                # 2エージェント分の特徴量をまとめる
                now_features = torch.cat(
                    (env.get_features(t+1,1),env.get_features(t+1,2)),
                    dim=0 # 横長の配列を縦に並べる
                )#前ターンの行動後(つまり現ターンの行動前)の特徴量

                data = torch.cat(
                    (before_features, now_features),
                    dim = 0 # 配列を縦にくっつける
                )
                df_division = torch.cat(
                    (before_features, now_features),
                    dim = 1 # 配列を縦にくっつける
                )

                before_features = now_features # 次ターンのbefore_featuresに，現ターン行動前の特徴量を設定する
                dim = df_division.shape
                next_state = torch.FloatTensor(df_division[:,int(dim[1]/2):])
                new_action = np.array([0,0])
                next_state[0] = next_state[0].to(self.device)
                next_state[1] = next_state[1].to(self.device)
                with torch.no_grad():
                    new_action[0] = self.policy_net_a(next_state[0]).max(1)[1]
                    new_action[1] = self.policy_net_a(next_state[1]).max(1)[1]
                
                # item_id_division:usrID(のリスト), new_price_division: usrの次の行動("n_position": 座標,"motion": move or remove,"direction": 方向,"is_possible": s_judjedirection()のコード)
                usr_id_division = np.array([1,2])
                df_dic = {'usrID': usr_id_division, 'now_eval': np.array([idx+1]*2), 'num_game': np.array([games_num]*2),'now_game': np.array([g_num+1]*2), 'num_turn': np.array([turn]*2),'now_turn': np.array([t+1]*2), 'calcAction': new_action}#* len(item_id_division))} # num_ : 総数(総ターンなど), now_: 現在(現在は5ターン目など)
                #df_dic = {'calcAction': new_action, 'Loss': np.array([loss]*2), 'reward': reward}#* len(item_id_division))}

                #df_dic = pd.DataFrame(data=df_dic)

                # action = {"n_position": 座標,"motion": move or remove,"direction": 方向,"is_possible": s_judjedirection()のコード}
                df_action = {}
                df_action["do_motion"] = []
                df_action["do_direction"] = []
                df_action["is_possible"] = []
                df_action['now_position'] = []
                df_action["next_position"] = []

                for usrID in enumerate(usr_id_division):
                    code, data, next_pos = env._judgeDirection(usrID[1],new_action[usrID[1]-1])
                    df_action["do_motion"].append(data['motion'])
                    df_action["do_direction"].append(data['d'])
                    df_action["is_possible"].append(code)
                    df_action['now_position'].append(env._getPosition(usrID[1]))
                    df_action["next_position"].append(next_pos)
            
                # エージェントの移動先が重なってるか，いないかを判定し行動を決定
                cnf, m_data, n_data = env.check_action(df_action)

                #df_action["is_possible"] = np.array([int(i) for i in enumerate(df_action["is_possible"])])
                df_dic.update(df_action)
                df_dic["is_confliction"] = np.array([cnf]*2)
                
                
                # 移動前に得点を取得
                point_before_moving = env._calcPoint()
                # 判定後に実際に移動させる
                env.do_action(m_data[0])
                env.do_action(m_data[1])
                # 行動を保存しておく
                self.action_history.append(n_data)     
                # 移動後の得点を取得
                point_after_moving = env._calcPoint()

                df_dic['before_tilepoint'] = np.array([point_before_moving[0],point_before_moving[3]])
                df_dic['before_areapoint'] = np.array([point_before_moving[1],point_before_moving[4]])
                df_dic['before_totalpoint'] = np.array([point_before_moving[2],point_before_moving[5]])
                df_dic['after_tilepoint'] = np.array([point_after_moving[0],point_after_moving[3]])
                df_dic['after_areapoint'] = np.array([point_after_moving[1],point_after_moving[4]])
                df_dic['after_totalpoint'] = np.array([point_after_moving[2],point_after_moving[5]])
                df_dic['on_eps_zero'] = np.array([self.on_epsilon_zero]*2)
                # logを保存
                df = pd.DataFrame(df_dic)
                if g_num==0 and t==0:
                    self.EXPORT_EVAL_HISTORY_FILE_NAME = 'eval_history_' + str(idx) + '_' + TODAYS_DATE + '.csv'
                    #EXPORT_EVAL_HISTORY_FILE_NAME = 'eval_history_' + str(idx) + '_' + str(g_num) + '_' + TODAYS_DATE + '.csv'
                    df.to_csv(EVAL_HISTORY_DIRECTORY_NAME + self.EXPORT_EVAL_HISTORY_FILE_NAME, encoding='shift_jis')
                else:
                    df.to_csv(EVAL_HISTORY_DIRECTORY_NAME + self.EXPORT_EVAL_HISTORY_FILE_NAME, mode='a', header=False, encoding='shift_jis')
            
            self.action_history.clear()
            if self.judgeWorL(df_dic):
                e_log['agent_won'] += 1
            else:
                e_log['opponent_won'] += 1
            games_done += 1

        return True, e_log
#        except:
#            return False

    def select_model(self, a_logs, first=False, e_logs=None):
        if e_logs is not None: # 2回目(self play終了後)に呼ばれるとき
            return {"policy":a_logs["policy"], "target":a_logs["target"]}
            '''
            if float(int(e_logs['agent_won']) / int(e_logs['num_game'])) >= 0.5: # agentの勝率が5割以上
                return {"policy":a_logs["policy"], "target":a_logs["target"]}
            else:
                return {"policy":e_logs["oppo_policy"], "target":e_logs["oppo_target"]}
            '''
        else: # 1回目(self play前)に呼ばれるとき
            if first: # 初回のself play
                self.agent_history[0].append(a_logs['loss_median'])
                self.agent_history[1].append(a_logs['target'])
                self.agent_history[2].append(a_logs['policy'])
                return {'oppo_target': a_logs["target"], 'oppo_policy': a_logs["policy"]}
            else:
                oppo_target_name = self.agent_history[1][0]
                oppo_policy_name = self.agent_history[2][0]
                if a_logs['loss_median'] < self.agent_history[0][0]:
                    self.agent_history[0][0] = a_logs['loss_median']
                    self.agent_history[1][0] = a_logs['target']
                    self.agent_history[2][0] = a_logs['policy']
                return {'oppo_target': oppo_target_name, 'oppo_policy': oppo_policy_name}

    # e_logs = {'interval': str(num_selfPlay), 'n_times': str(n_times), 'num_agent_won': int(won)}
    # opponent = {'oppo_target':, 'oppo_policy'}
    def process(self, env, oppo=None): # 学習開始からself playを経て学習終了まで
        now_exec = np.array([])
        num_agent_won = np.array([])
        num_opponent_won = np.array([])
        agent_won = np.array([])
        agent_policy_network = np.array([])
        agent_target_network = np.array([])
        opponent_policy_network = np.array([])
        opponent_target_network = np.array([])
        won_network_filename_target = np.array([])
        won_network_filename_policy = np.array([])
        self.steps_done = 0

        #raise ValueError("error!")

        try:
            for idx in range(NUMBER_OF_SETS):
                print('self.steps_done',self.steps_done)
                now_exec = np.append(now_exec, idx+1)
                print('############################# now_exec: %d #############################' % (idx+1))
                japantime_now = get_japantime_now()
                print('learning start:',japantime_now)
                result, a_logs = self.agent_learning(env, idx) # 学習
                if not result:
                    return False
                # 対戦相手の選択    
                if oppo is not None: # 指定したagentと戦わせたい場合
                    opponent = oppo # {"policy":a_logs["policy"], "target":fn["target"]} の形式
                elif idx == 0: # 初回のself play
                    opponent = self.select_model(a_logs=a_logs,first=True)
                else: # 対戦相手を過去の中から選ぶ
                    opponent = self.select_model(a_logs)

                agent = {"policy":a_logs["policy"], "target":a_logs["target"]}
                agent_policy_network = np.append(agent_policy_network, agent['policy'])
                agent_target_network = np.append(agent_target_network, agent['target'])
                opponent_policy_network = np.append(opponent_policy_network, opponent['oppo_policy'])
                opponent_target_network = np.append(opponent_target_network, opponent['oppo_target'])
                #print(agent)
                #print(opponent)
                japantime_now = get_japantime_now()
                print('self play start:',japantime_now)
                result, e_logs = self.agent_evaluation(env, agent, opponent, idx) # self play
                if not result:
                    return False

                num_agent_won = np.append(num_agent_won, e_logs['agent_won'])
                num_opponent_won = np.append(num_opponent_won, e_logs['opponent_won'])
                
                if e_logs['agent_won'] > e_logs['opponent_won']:
                    agent_won = np.append(agent_won, 1)
                else:
                    agent_won = np.append(agent_won, 0)  
                
                if oppo is not None: # 指定したagentと戦わせる場合は，最初に生成したagentをずっと成長させる
                    self.IMPORT_POLICY_FILE_NAME = a_logs['target']
                    self.IMPORT_TARGET_FILE_NAME = a_logs['policy']
                    won_network_filename_target = np.append(won_network_filename_target, None)
                    won_network_filename_policy = np.append(won_network_filename_policy, None)
                else:
                    e_logs.update(opponent)
                    #print(e_logs)
                    next_agent = self.select_model(a_logs=a_logs, e_logs=e_logs)
                    won_network_filename_target = np.append(won_network_filename_target, next_agent['target'])
                    won_network_filename_policy = np.append(won_network_filename_policy, next_agent['policy'])
                    self.IMPORT_POLICY_FILE_NAME = next_agent['policy']
                    self.IMPORT_TARGET_FILE_NAME = next_agent['target']                


                self.steps_done += 1

            df_Logs = {'num_sets':np.array([NUMBER_OF_SETS]*NUMBER_OF_SETS), 'num_epochs': np.array([EPOCHS]*NUMBER_OF_SETS), 'num_games_per_selfplay': np.array([NUMBER_OF_SELFPLAY]*NUMBER_OF_SETS)}
            df_Logs['now_exec'] = now_exec
            df_Logs['num_agent_won'] = num_agent_won
            df_Logs['num_opponent_won'] = num_opponent_won
            df_Logs['agent_won'] = agent_won
            df_Logs['agent_target_network'] = agent_target_network
            df_Logs['agent_policy_network'] = agent_policy_network
            df_Logs['opponent_target_network'] = opponent_target_network
            df_Logs['opponent_policy_network'] = opponent_policy_network
            df_Logs['won_target_network'] = won_network_filename_target
            df_Logs['won_policy_network'] = won_network_filename_policy
            df_Logs['on_eps_zero'] = np.array([self.on_epsilon_zero]*NUMBER_OF_SETS)

            df = pd.DataFrame(df_Logs)
            EXPORT_NAME = EVAL_HISTORY_DIRECTORY_NAME + 'WoL_history_' + TODAYS_DATE + '.csv'
            df.to_csv(EXPORT_NAME, encoding='shift_jis')

            return True

        except:
            #num_done = min(len(now_exec),len(num_agent_won),len(num_opponent_won),len(agent_won))
            df_Logs = {'num_sets':np.array([NUMBER_OF_SETS]*self.steps_done), 'num_epochs': np.array([EPOCHS]*self.steps_done), 'num_games_per_selfplay': np.array([NUMBER_OF_SELFPLAY]*self.steps_done)}
            df_Logs['now_exec'] = now_exec#np.delete(now_exec,len(now_exec)-1)
            df_Logs['num_agent_won'] = num_agent_won
            df_Logs['num_opponent_won'] = num_opponent_won
            df_Logs['agent_won'] = agent_won

            #print(df_Logs)
            df = pd.DataFrame(df_Logs)
            EXPORT_NAME = EVAL_HISTORY_DIRECTORY_NAME + 'WoL_history_' + TODAYS_DATE + '.csv'
            df.to_csv(EXPORT_NAME, encoding='shift_jis')    

            return False

def main():
    env = jin_jinGame.jinGAME()
    agent = jinGame_DQNAgent()
    print('lets start')
    res = agent.process(env)
    if not res:
        print('see log file')
    else:
        print('done')
