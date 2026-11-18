import os,json,logging
from pathlib import Path
from redis import Redis
from sqlalchemy import select,update
from src.config.database import Session
from src.models.run import Run
from src.models.joint import JointRun,JointStudy
from src.models import user,study,observation,review,audit,joint
from src.services.algorithm import calculate
from src.services.joint_algorithm import joint_calculate
from src.utils.serializers import checksum,now
QUEUES=('analysis-queue','joint-queue')
def artifacts_dir():
    path=Path(os.environ.get('ARTIFACTS_DIR','/app/artifacts'));path.mkdir(parents=True,exist_ok=True);return path
def recover_jobs(db):
    # Jobs interrupted after dequeue are re-queued. A project runs exactly one worker.
    jobs=[('analysis-queue',x) for x in db.scalars(select(Run.id).where(Run.status.in_(['queued','running'])))]
    jobs+=[('joint-queue',x) for x in db.scalars(select(JointRun.id).where(JointRun.status.in_(['queued','running'])))]
    return jobs
def process_run(db,id):
    run=db.get(Run,id)
    if not run or run.status in ('completed','failed'): return
    run.status='running';db.commit()
    try:
        if checksum(run.snapshot)!=run.checksum: raise ValueError('输入快照校验失败')
        result=calculate(run.snapshot,run.parameters)
        result['input_sha256']=run.checksum
        run.result=result;run.status='completed'
        artifacts_dir().joinpath(f'run-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except Exception as e:
        logging.exception('analysis failed');run.status='failed';run.error=str(e)
    db.commit()
def publish_joint(db,id,result):
    # 整族齐备才生效、重试不重复发布、旧计算迟归不覆盖新结论：单行条件更新原子生效。
    run=db.get(JointRun,id)
    if not run: return False
    db.scalar(select(JointStudy).where(JointStudy.id==run.joint_id).with_for_update())
    newer=db.scalar(select(JointRun.id).where(JointRun.joint_id==run.joint_id,JointRun.id>id,JointRun.published==True).limit(1))
    if newer is not None:
        db.execute(update(JointRun).where(JointRun.id==id,JointRun.status.in_(['queued','running'])).values(status='invalidated',invalidation_reason=f'已有更新结论（运行#{newer}），迟归计算不覆盖'))
        db.commit();return False
    res=db.execute(update(JointRun).where(JointRun.id==id,JointRun.status.in_(['queued','running']),JointRun.published==False).values(result=result,status='completed',published=True,finished_at=now()))
    db.commit()
    if res.rowcount==0: return False
    artifacts_dir().joinpath(f'joint-run-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return True
def process_joint_run(db,id):
    run=db.get(JointRun,id)
    if not run or run.status in ('completed','failed','invalidated'): return
    study=db.get(JointStudy,run.joint_id)
    if study and run.data_version!=study.data_version:
        run.status='invalidated';run.invalidation_reason=f'源数据已更新至版本{study.data_version}（本计算基于版本{run.data_version}），未发布计算失效';db.commit();return
    run.status='running';db.commit()
    try:
        if checksum(run.snapshot)!=run.checksum: raise ValueError('输入快照校验失败')
        result=joint_calculate(run.snapshot,run.parameters,run.seed)  # 中断恢复沿用整族随机依据
        result['input_sha256']=run.checksum
        expected={c['member_key'] for c in run.snapshot['candidates']}
        got={m['member_key'] for m in result['members'] if m['role']=='candidate'}
        if expected!=got: raise ValueError('整族未齐备，结论不生效')
        publish_joint(db,id,result)
    except Exception as e:
        logging.exception('joint analysis failed');db.rollback()
        db.execute(update(JointRun).where(JointRun.id==id,JointRun.status.in_(['queued','running'])).values(status='failed',error=str(e)[:2000]))
        db.commit()
def main():
    redis=Redis.from_url(os.environ['REDIS_URL'])
    artifacts_dir()
    with Session() as db:
        for queue_name,job_id in recover_jobs(db): redis.rpush(queue_name,job_id)
    while True:
        Path('/tmp/worker-heartbeat').touch()
        job=redis.blpop(list(QUEUES),timeout=2)
        if not job: continue
        queue_name=job[0].decode() if isinstance(job[0],bytes) else job[0]
        id=int(job[1])
        with Session() as db:
            if queue_name=='joint-queue': process_joint_run(db,id)
            else: process_run(db,id)
if __name__=='__main__': main()
