from src.services import runs,studies
from src.schemas.study import StudyInput
from src.schemas.observation import ObservationInput
from src.schemas.run import RunInput
from src import worker

def test_independent_pipeline_unchanged(db,user,pushed):
    s=studies.create(db,StudyInput(name='独立批次',source_filename='indep.csv',description=''),user)
    studies.save_observation(db,s['id'],ObservationInput(source_key='R1',values={'p0':.08,'p1':.1,'cost_per_contact':.12,'budget':3000}),user)
    r=runs.create(db,RunInput(study_id=s['id'],name='独立核算',parameters={'simulations':500}),user)
    assert ('analysis-queue',r['id']) in pushed
    worker.process_run(db,r['id'])
    got=runs.get(db,r['id'])
    assert got['status']=='completed'
    assert got['result']['metrics']['情景数']==1
    assert got['result']['input_sha256']==got['checksum']
    assert ('joint-queue',r['id']) not in pushed
