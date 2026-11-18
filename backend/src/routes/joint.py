from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.middlewares.auth import current_user,writer
from src.schemas.joint import JointStudyInput,JointMemberInput,JointRunInput
from src.controllers import joint
router=APIRouter()
@router.get('/joints')
def list_joints(db=Depends(get_db),user=Depends(current_user)): return joint.list_studies(db)
@router.post('/joints')
def create_joint(data:JointStudyInput,db=Depends(get_db),user=Depends(writer)): return joint.create_study(db,data,user)
@router.get('/joints/{id}')
def joint_detail(id:int,db=Depends(get_db),user=Depends(current_user)): return joint.study_detail(db,id)
@router.post('/joints/{id}/members')
def add_member(id:int,data:JointMemberInput,db=Depends(get_db),user=Depends(writer)): return joint.save_member(db,id,data,user)
@router.put('/joints/{id}/members/{mid}')
def edit_member(id:int,mid:int,data:JointMemberInput,db=Depends(get_db),user=Depends(writer)): return joint.save_member(db,id,data,user,mid)
@router.post('/joints/{id}/members/{mid}/withdraw')
def withdraw_member(id:int,mid:int,db=Depends(get_db),user=Depends(writer)): return joint.withdraw_member(db,id,mid,user)
@router.post('/joints/{id}/runs')
def seal_run(id:int,data:JointRunInput,db=Depends(get_db),user=Depends(writer)): return joint.create_run(db,id,data,user)
@router.get('/joint-runs/{rid}')
def joint_run(rid:int,db=Depends(get_db),user=Depends(current_user)): return joint.get_run(db,rid)
