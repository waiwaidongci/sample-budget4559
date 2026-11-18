import math
import numpy as np
import pytest
from scipy import stats
from src.services.joint_algorithm import joint_calculate,calibrate_maxstat,simulate_null_stats,budget_power,z_stat

def snap(cands,control=(20000,1640),version=1):
    return {'version':version,'control':{'member_key':'CTRL','impressions':control[0],'clicks':control[1]},
            'candidates':[{'member_key':k,'status':s,'impressions':n,'clicks':x,'cost_per_contact':c,'budget':b} for k,s,n,x,c,b in cands]}

def test_calibration_stricter_than_naive_and_grows_with_family():
    z_naive=float(stats.norm.ppf(.975))
    c2,_=calibrate_maxstat(20000,[10000,10000],.08,.05,5000,7)
    c6,_=calibrate_maxstat(20000,[10000]*6,.08,.05,5000,7)
    assert c2>z_naive,'联合校正临界值应严于逐项未校正检验'
    assert c6>c2,'检验族越大校正越严'

def test_shared_control_draw_induces_correlation():
    Z=simulate_null_stats(20000,[10000,10000],.08,8000,11)
    assert Z.shape==(8000,2)
    corr=float(np.corrcoef(Z[:,0],Z[:,1])[0,1])
    assert corr>.2,'各候选共用同次对照抽样，族内统计量应正相关'

def test_fwer_under_all_null_controlled():
    # 全零效应：全部候选与对照同率。联合校正的整族误报应受 α 控制，逐项检验则放大误报。
    rng=np.random.default_rng(2026)
    R,B=250,1500
    joint_hits=naive_hits=0
    for _ in range(R):
        cands=[{'member_key':f'C{k}','status':'active','impressions':2500,'clicks':int(rng.binomial(2500,.08)),'cost_per_contact':.1,'budget':250} for k in range(4)]
        res=joint_calculate({'version':1,'control':{'member_key':'CTRL','impressions':4000,'clicks':int(rng.binomial(4000,.08))},'candidates':cands},{'alpha':.05,'simulations':B},99)
        active=[m for m in res['members'] if m['role']=='candidate']
        joint_hits+=any(m['verdict_adj']=='采用' for m in active)
        naive_hits+=any(m['p_raw']<.05 for m in active)
    fwer=joint_hits/R
    assert fwer<=.05+3*math.sqrt(.05*.95/R),f'整族误报率{fwer:.3f}超出α容差'
    assert naive_hits>joint_hits,'逐项未校正检验应比联合校正产生更多整族误报'

def test_budget_power_increases_with_affordable_n():
    c,_=calibrate_maxstat(20000,[10000],.08,.05,5000,5)
    low,_=budget_power(20000,.08,[2000],[.10],c,5000,6)[0]
    high,_=budget_power(20000,.08,[20000],[.10],c,5000,6)[0]
    assert high>low,'预算可负担触达越多，预算下功效越高'

def test_withdrawn_member_stays_in_family():
    res=joint_calculate(snap([('C1','active',10000,880,.1,1500),('C2','withdrawn',10000,860,.1,1500),('C3','active',10000,820,.1,1500)]),{'alpha':.05,'simulations':3000},42)
    assert res['metrics']['检验族规模']==3 and res['metrics']['活跃候选数']==2
    c_expected,_=calibrate_maxstat(20000,[10000,10000,10000],(1640+880+820)/40000,.05,3000,42)
    assert res['metrics']['校正临界值c']==round(c_expected,4),'退出候选不缩减检验族，临界值不变'
    c2=[m for m in res['members'] if m['member_key']=='C2'][0]
    assert c2['status']=='withdrawn' and c2['verdict_adj']=='退出' and c2['z'] is None

def test_adjusted_p_not_below_raw():
    res=joint_calculate(snap([('C1','active',10000,900,.1,1500),('C2','active',10000,870,.1,1500)]),{'alpha':.05,'simulations':5000},3)
    for m in res['members']:
        if m['role']=='candidate': assert m['p_adj']>=m['p_raw']-.01

def test_joint_calculate_deterministic_with_seed():
    s=snap([('C1','active',10000,900,.1,1500),('C2','active',10000,870,.1,1500)])
    a=joint_calculate(s,{'alpha':.05,'simulations':2000},123)
    b=joint_calculate(s,{'alpha':.05,'simulations':2000},123)
    assert a['metrics']==b['metrics'] and a['members']==b['members']

def test_z_stat_zero_when_no_variance():
    assert z_stat(0,1000,0,1000)==0.0

def test_validation_errors():
    with pytest.raises(ValueError): joint_calculate(snap([('C1','active',10000,10001,.1,1500)]),{},1)
    with pytest.raises(ValueError): joint_calculate(snap([('C1','withdrawn',10000,800,.1,1500)]),{},1)
    with pytest.raises(ValueError): joint_calculate(snap([('C1','active',10000,900,.1,1500)]),{'simulations':50},1)
    with pytest.raises(ValueError): joint_calculate(snap([('C1','active',10000,900,.1,1500)]),{'alpha':.5},1)
    with pytest.raises(ValueError): joint_calculate(snap([('C1','active',10000,900,.0001,1000)]),{'simulations':500},1)
    with pytest.raises(ValueError): joint_calculate({'version':1,'control':{'member_key':'CTRL','impressions':1000,'clicks':0},'candidates':[{'member_key':'C1','status':'active','impressions':1000,'clicks':0,'cost_per_contact':.1,'budget':100}]},{'simulations':500},1)
