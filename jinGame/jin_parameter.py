test_flg = True
if test_flg:
    print('test')
    EPOCHS = 2 # 1セットあたりの学習回数
    NUMBER_OF_SETS = 2 # ( 学習 + self play ) を何セット行うか
    NUMBER_OF_SELFPLAY = 1
else:
    print('learn')
    EPOCHS = 100
    NUMBER_OF_SETS  = 100
    NUMBER_OF_SELFPLAY = 20

LOG_IN_LEARNING = True

ON_EPSILON_ZERO = False