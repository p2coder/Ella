import sys
name=['Helm','Gloves','Boots','Sword']
reinforce_avaliable=[1,1,1,1]
reinforce_coin_cost=[[30],[40],[10],[50]]
reinforce_strength_get=[[20],[30],[10],[50]]
coins=100
def get_max(name,reinforce_avaliable,reinforce_coin_cost,reinforce_strength_get,coins):
    # name[i]:第i件装备名称
    # reinforce_avaliable[i]:装备i剩余可强化次数
    # reinforce_coin_cost[i][j]:装备i第j+1次强化消耗的金币
    # reinforce_strength_get[i][j]:装备i第j+1次强化获得的战力
    # coins:金币数量


    # 记录强化结果
    reinforce=[0]*len(reinforce_avaliable)
    final_strength=0
    reinforce_total=reinforce_avaliable.copy()
    n=len(name)

    def backtrace(strength,current_coin,n):
        # 回溯，每次尝试强化一次装备，记录当次战力，如果钱不够或者所有装备强化完成，那么返回
        # 利用一个available_reinforce列表来记录强化次数，availabl_reinforce[i]表示装备i剩余可强化次数
        if current_coin<0 or sum(reinforce_avaliable)<1e-6:
            nonlocal final_strength,reinforce
            if strength>final_strength:
                final_strength=strength
                for i in range(len(reinforce)):
                    reinforce[i]=reinforce_total[i]-reinforce_avaliable[i]
            return
        for i in range(n):
            # 对第i件装备操作
            if reinforce_avaliable[i]==0:
                # 当前装备不可强化了
                continue
            # 强化一次当前装备
            times=reinforce_total[i]-reinforce_avaliable[i]
            reinforce_avaliable[i]-=1
            strength+=reinforce_strength_get[i][times]
            current_coin-=reinforce_coin_cost[i][times]

            backtrace(strength,current_coin,n)

            current_coin+=reinforce_coin_cost[i][times]
            strength-=reinforce_strength_get[i][times]
            reinforce_avaliable[i]+=1
        return
    backtrace(0,coins,n)



    return reinforce,final_strength
a,b=get_max(name,reinforce_avaliable,reinforce_coin_cost,reinforce_strength_get,coins)
print(a,b)
# for line in sys.stdin:
#     a = line.split()
#     print(int(a[0]) + int(a[1]))
