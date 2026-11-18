import math,hashlib
from sqlalchemy import select,func
from fastapi import HTTPException
from src.models.joint import JointStudy,JointMember,JointRun
from src.services import queue
from src.services.audits import log
from src.utils.serializers import record,now,checksum

JOINT_QUEUE='joint-queue'
MAX_CANDIDATES=50

def seed_base(name): return int(hashlib.sha256(name.encode()).hexdigest()[:8],16)%2**31

def create_study(db,data,user):
    if db.scalar(select(JointStudy).where(JointStudy.name==data.name)): raise HTTPException(409,'联合研究名称已存在')
    s=JointStudy(name=data.name,description=data.description,data_version=1,seed_base=seed_base(data.name),created_at=now())
    db.add(s);log(db,user,'joint.create',data.name);db.commit();return record(s)

def list_studies(db):
    out=[]
    for s in db.scalars(select(JointStudy).order_by(JointStudy.id)):
        x=record(s)
        x['member_count']=db.scalar(select(func.count()).select_from(JointMember).where(JointMember.joint_id==s.id))
        x['active_candidates']=db.scalar(select(func.count()).select_from(JointMember).where(JointMember.joint_id==s.id,JointMember.role=='candidate',JointMember.status=='active'))
        x['latest_run_id']=db.scalar(select(JointRun.id).where(JointRun.joint_id==s.id,JointRun.published==True).order_by(JointRun.id.desc()).limit(1))
        out.append(x)
    return out

def require(db,id):
    s=db.get(JointStudy,id)
    if not s: raise HTTPException(404,'联合研究不存在')
    return s

def _lock(db,id):
    # Sealing and correction both take the study row lock, so a sealed run
    # always captures one complete, same-version family.
    s=db.scalar(select(JointStudy).where(JointStudy.id==id).with_for_update())
    if not s: raise HTTPException(404,'联合研究不存在')
    return s

def detail(db,id):
    s=require(db,id);x=record(s)
    x['members']=[record(m) for m in db.scalars(select(JointMember).where(JointMember.joint_id==id).order_by(JointMember.id))]
    runs=[]
    for r in db.scalars(select(JointRun).where(JointRun.joint_id==id).order_by(JointRun.id.desc())):
        y=record(r);y.pop('result',None);y.pop('snapshot',None);runs.append(y)
    x['runs']=runs
    x['latest_published_id']=next((r['id'] for r in runs if r['published']),None)
    return x

def get_run(db,id):
    run=db.get(JointRun,id)
    if not run: raise HTTPException(404,'联合计算不存在')
    return record(run)

def validate_member(role,impressions,clicks,cost,budget):
    if role not in ('control','candidate'): raise ValueError('成员角色必须为control或candidate')
    try:
        if isinstance(impressions,bool) or isinstance(clicks,bool): raise ValueError
        im,cl=int(impressions),int(clicks)
        if float(impressions)!=im or float(clicks)!=cl: raise ValueError
    except (TypeError,ValueError): raise ValueError('触达与点击必须为整数')
    if not 1<=im<=10000000: raise ValueError('触达数必须是1到10000000的整数')
    if not 0<=cl<=im: raise ValueError('点击数必须是0到触达数之间的整数')
    if role=='control': return im,cl,None,None
    try: cost,budget=float(cost),float(budget)
    except (TypeError,ValueError): raise ValueError('候选须登记单次触达成本与预算')
    if not(math.isfinite(cost) and 0<cost<=1e9): raise ValueError('单次触达成本必须为正且有限')
    if not(math.isfinite(budget) and 0<budget<=1e12): raise ValueError('预算必须为正且有限')
    return im,cl,cost,budget

def validate_parameters(params):
    defaults={'alpha':.05,'simulations':10000}
    if not isinstance(params,dict) or set(params)-set(defaults): raise ValueError('存在未知分析参数')
    p=defaults|params
    try: p['alpha']=float(p['alpha'])
    except (TypeError,ValueError): raise ValueError('显著性必须为数值')
    if not math.isfinite(p['alpha']) or not .001<=p['alpha']<=.2: raise ValueError('显著性超出范围')
    b=p['simulations']
    if isinstance(b,bool) or not isinstance(b,(int,float)) or int(b)!=b or not 200<=b<=20000: raise ValueError('模拟次数必须是200到20000的整数')
    p['simulations']=int(b)
    return p

def save_member(db,joint_id,data,user,member_id=None):
    study=_lock(db,joint_id)
    try: im,cl,cost,budget=validate_member(data.role,data.impressions,data.clicks,data.cost_per_contact,data.budget)
    except (ValueError,TypeError) as e: raise HTTPException(422,str(e))
    other=db.scalar(select(JointMember).where(JointMember.joint_id==joint_id,JointMember.member_key==data.member_key))
    if other and other.id!=member_id: raise HTTPException(409,'成员编号重复')
    if data.role=='control':
        existing=db.scalar(select(JointMember.id).where(JointMember.joint_id==joint_id,JointMember.role=='control',JointMember.id!=(member_id or 0)))
        if existing: raise HTTPException(409,'共同对照只能有一名，请更正现有对照')
    if member_id:
        row=db.get(JointMember,member_id)
        if not row or row.joint_id!=joint_id: raise HTTPException(404,'成员不存在')
        if row.status=='withdrawn': raise HTTPException(409,'已退出成员不可编辑')
        if row.role!=data.role: raise HTTPException(409,'成员角色不可变更')
        row.member_key=data.member_key;row.impressions=im;row.clicks=cl;row.cost_per_contact=cost;row.budget=budget;row.updated_at=now()
    else:
        if data.role=='candidate':
            count=db.scalar(select(func.count()).select_from(JointMember).where(JointMember.joint_id==joint_id,JointMember.role=='candidate'))
            if count>=MAX_CANDIDATES: raise HTTPException(422,f'联合研究最多{MAX_CANDIDATES}名候选')
        row=JointMember(joint_id=joint_id,member_key=data.member_key,role=data.role,status='active',impressions=im,clicks=cl,cost_per_contact=cost,budget=budget,updated_at=now())
        db.add(row)
    log(db,user,'joint.member.save',f'{joint_id}/{data.member_key}')
    rerun=_after_source_update(db,study,user)
    db.commit()
    if rerun: queue.push(JOINT_QUEUE,rerun.id)
    return record(row)

def withdraw_member(db,joint_id,member_id,user):
    study=_lock(db,joint_id)
    row=db.get(JointMember,member_id)
    if not row or row.joint_id!=joint_id: raise HTTPException(404,'成员不存在')
    if row.role=='control': raise HTTPException(409,'共同对照不可退出，只能更正数据')
    if row.status=='withdrawn': raise HTTPException(409,'候选已退出，检验族仍保留该成员')
    row.status='withdrawn';row.updated_at=now()
    log(db,user,'joint.member.withdraw',f'{joint_id}/{row.member_key}')
    rerun=_after_source_update(db,study,user)
    db.commit()
    if rerun: queue.push(JOINT_QUEUE,rerun.id)
    return record(row)

def _after_source_update(db,study,user):
    # Source data moved: unpublished computations are invalidated and recomputed.
    study.data_version+=1
    log(db,user,'joint.source.update',f'研究{study.id}进入版本{study.data_version}')
    invalidated=list(db.scalars(select(JointRun).where(JointRun.joint_id==study.id,JointRun.status.in_(['queued','running']),JointRun.published==False).order_by(JointRun.id)))
    for r in invalidated:
        r.status='invalidated'
        r.invalidation_reason=f'源数据更新至版本{study.data_version}（本计算基于版本{r.data_version}），未发布计算失效'
        log(db,user,'joint.run.invalidate',f'运行{r.id}: {r.invalidation_reason}')
    if not invalidated: return None
    src=invalidated[-1]
    try: return _seal(db,study,src.name,src.parameters)
    except ValueError as e:
        log(db,user,'joint.run.recompute.skip',f'研究{study.id}: {e}')
        return None

def _snapshot(rows,version):
    control=None;cands=[]
    for m in rows:
        if m.role=='control': control={'member_key':m.member_key,'impressions':m.impressions,'clicks':m.clicks}
        else: cands.append({'member_key':m.member_key,'status':m.status,'impressions':m.impressions,'clicks':m.clicks,'cost_per_contact':m.cost_per_contact,'budget':m.budget})
    return {'version':version,'control':control,'candidates':cands}

def _seal(db,study,name,params):
    rows=list(db.scalars(select(JointMember).where(JointMember.joint_id==study.id).order_by(JointMember.id)))
    if not any(m.role=='control' for m in rows): raise ValueError('先登记共同对照的触达与点击')
    if not any(m.role=='candidate' for m in rows): raise ValueError('先登记至少一名候选')
    if not any(m.role=='candidate' and m.status=='active' for m in rows): raise ValueError('至少需要一名活跃候选才能封存计算')
    snap=_snapshot(rows,study.data_version)
    run=JointRun(joint_id=study.id,name=name,status='queued',data_version=study.data_version,seed=study.seed_base,parameters=params,snapshot=snap,checksum=checksum(snap),created_at=now())
    db.add(run);db.flush();return run

def create_run(db,joint_id,data,user):
    study=_lock(db,joint_id)
    try:
        params=validate_parameters(data.parameters)
        run=_seal(db,study,data.name,params)
    except (ValueError,TypeError) as e: raise HTTPException(422,str(e))
    log(db,user,'joint.run.seal',f'运行{run.id} 版本{run.data_version} 种子{run.seed}')
    db.commit()
    queue.push(JOINT_QUEUE,run.id)
    return record(run)
