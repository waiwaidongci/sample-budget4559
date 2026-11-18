import math
from decimal import Decimal
import numpy as np
from scipy import stats

MAX_IMPRESSIONS=10000000
MAX_AFFORDABLE=200000

def z_stat(x0,n0,x1,n1):
    pooled=(x0+x1)/(n0+n1);se=math.sqrt(pooled*(1-pooled)*(1/n0+1/n1))
    return 0.0 if se<=0 else (x1/n1-x0/n0)/se

def _z_vec(x0,n0,x1,n1):
    pooled=(x0+x1)/(n0+n1);se=np.sqrt(pooled*(1-pooled)*(1/n0+1/n1))
    return np.divide(x1/n1-x0/n0,se,out=np.zeros(len(x0),dtype=float),where=se>0)

def simulate_null_stats(n0,family_ns,p_null,B,seed):
    # Joint-null statistics. Every candidate reuses the SAME control draw
    # within each replication (shared control), which correlates the family.
    rng=np.random.default_rng(seed)
    x0=rng.binomial(n0,p_null,B)
    return np.column_stack([_z_vec(x0,n0,rng.binomial(nk,p_null,B),nk) for nk in family_ns])

def calibrate_maxstat(n0,family_ns,p_null,alpha,B,seed):
    maxz=np.abs(simulate_null_stats(n0,family_ns,p_null,B,seed)).max(axis=1)
    return float(np.quantile(maxz,1-alpha)),maxz

def budget_power(n0,p0,ns,p1s,c,B,seed):
    # Power per candidate at budget-limited impressions; control drawn once per rep.
    rng=np.random.default_rng(seed)
    x0=rng.binomial(n0,p0,B)
    out=[]
    for nk,p1 in zip(ns,p1s):
        if nk<=0: out.append((0.0,0.0));continue
        rejected=np.abs(_z_vec(x0,n0,rng.binomial(nk,p1,B),nk))>c
        prob=float(np.mean(rejected));out.append((prob,math.sqrt(prob*(1-prob)/B)))
    return out

def _check_member(m,need_budget):
    n=int(m['impressions']);x=int(m['clicks'])
    if not 1<=n<=MAX_IMPRESSIONS: raise ValueError('触达数必须位于1到10000000之间')
    if not 0<=x<=n: raise ValueError('点击数必须位于0与触达数之间')
    if need_budget:
        cost=float(m['cost_per_contact']);budget=float(m['budget'])
        if not(math.isfinite(cost) and cost>0) or not(math.isfinite(budget) and budget>0): raise ValueError('候选的成本与预算必须为正')
        return n,x,cost,budget
    return n,x,None,None

def joint_calculate(snapshot,params,seed):
    alpha=float(params.get('alpha',.05));B=int(params.get('simulations',10000))
    if not .001<=alpha<=.2: raise ValueError('alpha超出范围')
    if not 200<=B<=20000: raise ValueError('模拟次数超出范围')
    if not snapshot or 'control' not in snapshot: raise ValueError('联合研究缺少共同对照')
    control=snapshot['control'];candidates=snapshot.get('candidates') or []
    n0,x0,_,_= _check_member(control,False)
    active=[c for c in candidates if c.get('status')=='active']
    if not candidates: raise ValueError('检验族为空，无法校准')
    if not active: raise ValueError('至少需要一名活跃候选')
    family_ns=[int(c['impressions']) for c in candidates]  # 退出候选仍保留在检验族内
    checked={c['member_key']:_check_member(c,True) for c in active}
    p_null=(x0+sum(checked[k][1] for k in checked))/(n0+sum(checked[k][0] for k in checked))
    if not 0<p_null<1: raise ValueError('联合零假设共同率位于边界，无法校准')
    z_naive=float(stats.norm.ppf(1-alpha/2))
    affordables=[]
    for cand in active:
        _,_,cost,budget=checked[cand['member_key']]
        affordable=int(Decimal(str(budget))/Decimal(str(cost)))  # 十进制除法向下取整，避免浮点少算
        if affordable>MAX_AFFORDABLE: raise ValueError(f"候选{cand['member_key']}预算允许超过{MAX_AFFORDABLE}次触达，请缩小预算或提高成本口径")
        affordables.append(affordable)
    c,maxz=calibrate_maxstat(n0,family_ns,p_null,alpha,B,seed)
    powers=budget_power(n0,x0/n0,affordables,[checked[cand['member_key']][1]/checked[cand['member_key']][0] for cand in active],c,B,seed+1)
    members=[{'member_key':control['member_key'],'role':'control','status':'active','impressions':n0,'clicks':x0,'rate':x0/n0,'z':None,'p_raw':None,'p_adj':None,'verdict_raw':'共同对照','verdict_adj':'共同对照','affordable':None,'power_budget':None,'power_se':None}]
    adopted=[]
    for cand,(affordable,(pw,se)) in zip(active,zip(affordables,powers)):
        n,x,_,_=checked[cand['member_key']]
        z=z_stat(x0,n0,x,n);p_raw=float(2*stats.norm.sf(abs(z)));p_adj=float(np.mean(maxz>=abs(z)))
        verdict_adj='采用' if abs(z)>c else '不显著'
        if verdict_adj=='采用': adopted.append(cand['member_key'])
        members.append({'member_key':cand['member_key'],'role':'candidate','status':'active','impressions':n,'clicks':x,'rate':x/n,'z':z,'p_raw':p_raw,'p_adj':p_adj,'verdict_raw':'显著' if abs(z)>z_naive else '不显著','verdict_adj':verdict_adj,'affordable':affordable,'power_budget':pw,'power_se':se})
    for cand in candidates:
        if cand.get('status')!='active':
            members.append({'member_key':cand['member_key'],'role':'candidate','status':'withdrawn','impressions':int(cand['impressions']),'clicks':int(cand['clicks']),'rate':int(cand['clicks'])/int(cand['impressions']),'z':None,'p_raw':None,'p_adj':None,'verdict_raw':'—','verdict_adj':'退出','affordable':None,'power_budget':None,'power_se':None})
    metrics={'检验族规模':len(candidates),'活跃候选数':len(active),'共同对照触达':n0,'共同对照点击率':round(x0/n0,6),'联合零假设共同率':round(p_null,6),'未校正临界值':round(z_naive,4),'校正临界值c':round(c,4),'双侧显著性α':alpha,'模拟次数':B,'随机种子':seed,'数据版本':snapshot.get('version'),'采用成员数':len(adopted)}
    interpretation=f"共同对照{n0}次触达，检验族共{len(candidates)}名候选（活跃{len(active)}名，退出仍计入族）。联合零假设模拟校准的双侧最大统计量临界值c={c:.3f}，严于未校正的{z_naive:.3f}。校正后采用{len(adopted)}名候选"+(f"：{'、'.join(adopted)}。" if adopted else '。')
    return {'metrics':metrics,'members':members,'interpretation':interpretation,'caveat':'校正基于联合零假设下最大统计量模拟，控制整族误报率；各候选共用同次对照抽样。候选退出不缩减检验族。预算下功效按观测点击率与预算可负担触达模拟，属设计参考，不保证真实业务效应；低事件率时正态近似可能失真。'}
