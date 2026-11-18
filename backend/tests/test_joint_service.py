import pytest
from sqlalchemy import select,func
from src.schemas.joint import JointStudyInput,JointMemberInput,JointRunInput
from src.services import joints
from src.services.joint_algorithm import joint_calculate,calibrate_maxstat
from src.models.joint import JointStudy,JointMember,JointRun
from src.utils.serializers import checksum
from src import worker

def add(db,user,sid,key,role,im,cl,cost=None,budget=None,mid=None):
    return joints.save_member(db,sid,JointMemberInput(member_key=key,role=role,impressions=im,clicks=cl,cost_per_contact=cost,budget=budget),user,mid)

def family(db,user,name='联合测试'):
    s=joints.create_study(db,JointStudyInput(name=name,description=''),user)
    sid=s['id']
    add(db,user,sid,'CTRL','control',20000,1640)
    add(db,user,sid,'C1','candidate',10000,880,.1,1500)
    add(db,user,sid,'C2','candidate',10000,860,.1,1500)
    add(db,user,sid,'C3','candidate',10000,820,.1,1500)
    return sid

def seal(db,user,sid,name='核算',simulations=500):
    return joints.create_run(db,sid,JointRunInput(name=name,parameters={'alpha':.05,'simulations':simulations}),user)

def test_seal_uses_complete_same_version_data(db,user,pushed):
    sid=family(db,user)
    study=joints.require(db,sid)
    r=seal(db,user,sid)
    assert r['data_version']==study.data_version and r['snapshot']['version']==study.data_version
    assert r['seed']==study.seed_base,'封存沿用整族随机依据'
    assert r['snapshot']['control']['member_key']=='CTRL' and len(r['snapshot']['candidates'])==3
    assert r['checksum']==checksum(r['snapshot'])
    assert ('joint-queue',r['id']) in pushed

def test_seal_requires_control_and_active_candidate(db,user):
    s=joints.create_study(db,JointStudyInput(name='空族',description=''),user)
    with pytest.raises(Exception): seal(db,user,s['id'])
    add(db,user,s['id'],'CTRL','control',20000,1640)
    with pytest.raises(Exception): seal(db,user,s['id'])

def test_source_update_invalidates_unpublished_and_recomputes(db,user,pushed):
    sid=family(db,user)
    a=seal(db,user,sid)
    add(db,user,sid,'C4','candidate',9000,800,.1,1500)
    study=joints.require(db,sid)
    assert study.data_version==a['data_version']+1
    old=db.get(JointRun,a['id'])
    assert old.status=='invalidated' and '失效' in old.invalidation_reason
    assert len(old.snapshot['candidates'])==3,'旧计算快照保留原检验族'
    runs=list(db.scalars(select(JointRun).where(JointRun.joint_id==sid).order_by(JointRun.id)))
    assert len(runs)==2,'失效后自动重算一次'
    new=runs[1]
    assert new.status=='queued' and new.data_version==study.data_version and new.name==old.name
    assert len(new.snapshot['candidates'])==4
    assert ('joint-queue',new.id) in pushed

def test_interleaved_corrections_keep_single_live_run(db,user):
    sid=family(db,user)
    a=seal(db,user,sid)
    add(db,user,sid,'C4','candidate',9000,800,.1,1500)
    m=db.scalar(select(JointMember).where(JointMember.joint_id==sid,JointMember.member_key=='C4'))
    add(db,user,sid,'C4','candidate',9500,810,.1,1500,mid=m.id)
    runs=list(db.scalars(select(JointRun).where(JointRun.joint_id==sid).order_by(JointRun.id)))
    assert [r.status for r in runs]==['invalidated','invalidated','queued'],'交错更正只保留最新一次未发布计算'
    assert runs[0].data_version<runs[1].data_version<runs[2].data_version
    assert runs[0].snapshot['candidates'][-1]['member_key']=='C3','首版快照不含后加候选'
    assert runs[2].snapshot['candidates'][-1]['impressions']==9500,'最新快照采用更正后同版数据'

def test_withdraw_keeps_original_family(db,user):
    sid=family(db,user)
    a=seal(db,user,sid,simulations=2000)
    member=db.scalar(select(JointMember).where(JointMember.joint_id==sid,JointMember.member_key=='C2'))
    joints.withdraw_member(db,sid,member.id,user)
    old=db.get(JointRun,a['id'])
    assert old.status=='invalidated'
    assert len(old.snapshot['candidates'])==3 and all(c['status']=='active' for c in old.snapshot['candidates'])
    new=db.scalar(select(JointRun).where(JointRun.joint_id==sid,JointRun.status=='queued'))
    assert len(new.snapshot['candidates'])==3,'删减候选后检验族仍保留'
    assert {c['member_key']:c['status'] for c in new.snapshot['candidates']}['C2']=='withdrawn'
    worker.process_joint_run(db,new.id)
    run=db.get(JointRun,new.id)
    assert run.status=='completed' and run.published
    res=run.result
    assert res['metrics']['检验族规模']==3 and res['metrics']['活跃候选数']==2
    c2=[m for m in res['members'] if m['member_key']=='C2'][0]
    assert c2['status']=='withdrawn' and c2['verdict_adj']=='退出' and c2['z'] is None
    c_expected,_=calibrate_maxstat(20000,[10000,10000,10000],(1640+880+820)/40000,.05,2000,run.seed)
    assert res['metrics']['校正临界值c']==round(c_expected,4),'退出候选不缩减检验族'

def test_withdraw_control_rejected(db,user):
    sid=family(db,user)
    ctrl=db.scalar(select(JointMember).where(JointMember.joint_id==sid,JointMember.role=='control'))
    with pytest.raises(Exception): joints.withdraw_member(db,sid,ctrl.id,user)

def test_late_old_run_never_overwrites_newer_conclusion(db,user):
    sid=family(db,user)
    a=seal(db,user,sid)
    run=db.get(JointRun,a['id']);run.status='running';db.commit()  # 旧计算已被取走
    add(db,user,sid,'C4','candidate',9000,800,.1,1500)  # 更正使其失效并重算
    b=db.scalar(select(JointRun).where(JointRun.joint_id==sid,JointRun.status=='queued'))
    worker.process_joint_run(db,b.id)
    b=db.get(JointRun,b.id)
    assert b.status=='completed' and b.published
    conclusion=b.result
    assert worker.publish_joint(db,a['id'],{'metrics':{'迟归':1}}) is False,'迟归旧计算不得发布'
    old=db.get(JointRun,a['id'])
    assert old.status=='invalidated' and not old.published
    assert db.get(JointRun,b.id).result==conclusion,'新结论不被覆盖'
    worker.process_joint_run(db,a['id'])  # 迟归任务再投递也是空转
    assert db.get(JointRun,b.id).result==conclusion

def test_retry_does_not_double_publish(db,user):
    sid=family(db,user)
    a=seal(db,user,sid)
    worker.process_joint_run(db,a['id'])
    worker.process_joint_run(db,a['id'])
    run=db.get(JointRun,a['id'])
    assert run.status=='completed' and run.published
    assert worker.publish_joint(db,a['id'],run.result) is False,'重复发布被拒绝'
    assert db.scalar(select(func.count()).select_from(JointRun).where(JointRun.joint_id==sid,JointRun.published==True))==1

def test_recovery_reuses_family_random_basis(db,user):
    sid=family(db,user)
    a=seal(db,user,sid,simulations=2000)
    expected=joint_calculate(a['snapshot'],a['parameters'],a['seed'])
    run=db.get(JointRun,a['id']);run.status='running';db.commit()  # 模拟中断
    assert ('joint-queue',a['id']) in worker.recover_jobs(db)
    worker.process_joint_run(db,a['id'])
    run=db.get(JointRun,a['id'])
    assert run.status=='completed'
    assert run.result['metrics']==expected['metrics'],'中断恢复沿用整族随机依据，结论可复现'

def test_family_must_be_complete_before_effect(db,user,monkeypatch):
    sid=family(db,user)
    a=seal(db,user,sid)
    original=worker.joint_calculate
    def incomplete(snapshot,params,seed):
        res=original(snapshot,params,seed)
        res['members']=[m for m in res['members'] if m['member_key']!='C3']
        return res
    monkeypatch.setattr(worker,'joint_calculate',incomplete)
    worker.process_joint_run(db,a['id'])
    run=db.get(JointRun,a['id'])
    assert run.status=='failed' and '整族未齐备' in run.error and not run.published

def test_stale_version_run_invalidated_at_pickup(db,user):
    sid=family(db,user)
    a=seal(db,user,sid)
    add(db,user,sid,'C4','candidate',9000,800,.1,1500)  # A失效，B重算
    b=db.scalar(select(JointRun).where(JointRun.joint_id==sid,JointRun.status=='queued'))
    run=db.get(JointRun,b.id)
    db.execute(run.__table__.update().where(run.__table__.c.id==b.id).values(data_version=1))  # 人为制造版本滞后
    db.commit()
    db.expire_all()
    worker.process_joint_run(db,b.id)
    run=db.get(JointRun,b.id)
    assert run.status=='invalidated' and '失效' in run.invalidation_reason and not run.published
