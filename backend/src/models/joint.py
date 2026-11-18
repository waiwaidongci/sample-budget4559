from sqlalchemy import Column,Integer,String,Text,JSON,Boolean,Float,ForeignKey,UniqueConstraint
from src.config.database import Base
class JointStudy(Base):
    __tablename__='joint_studies'
    id=Column(Integer,primary_key=True)
    name=Column(String(120),unique=True,nullable=False)
    description=Column(Text,default='')
    data_version=Column(Integer,nullable=False,default=1)
    seed_base=Column(Integer,nullable=False)
    created_at=Column(String(40),nullable=False)
class JointMember(Base):
    __tablename__='joint_members'
    __table_args__=(UniqueConstraint('joint_id','member_key'),)
    id=Column(Integer,primary_key=True)
    joint_id=Column(Integer,ForeignKey('joint_studies.id'),nullable=False)
    member_key=Column(String(100),nullable=False)
    role=Column(String(20),nullable=False)
    status=Column(String(20),nullable=False,default='active')
    impressions=Column(Integer,nullable=False)
    clicks=Column(Integer,nullable=False)
    cost_per_contact=Column(Float,nullable=True)
    budget=Column(Float,nullable=True)
    updated_at=Column(String(40),nullable=False)
class JointRun(Base):
    __tablename__='joint_runs'
    id=Column(Integer,primary_key=True)
    joint_id=Column(Integer,ForeignKey('joint_studies.id'),nullable=False)
    name=Column(String(120),nullable=False)
    status=Column(String(20),default='queued')
    data_version=Column(Integer,nullable=False)
    seed=Column(Integer,nullable=False)
    parameters=Column(JSON,nullable=False)
    snapshot=Column(JSON,nullable=False)
    checksum=Column(String(64),nullable=False)
    result=Column(JSON,nullable=True)
    error=Column(Text,default='')
    invalidation_reason=Column(Text,default='')
    published=Column(Boolean,nullable=False,default=False)
    created_at=Column(String(40),nullable=False)
    finished_at=Column(String(40),default='')
