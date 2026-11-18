from typing import Optional
from pydantic import BaseModel,Field
class JointStudyInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    description:str=Field(default='',max_length=2000)
class JointMemberInput(BaseModel):
    member_key:str=Field(min_length=2,max_length=100)
    role:str=Field(pattern='^(control|candidate)$')
    impressions:int=Field(ge=1,le=10000000)
    clicks:int=Field(ge=0)
    cost_per_contact:Optional[float]=None
    budget:Optional[float]=None
class JointRunInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    parameters:dict=Field(default_factory=dict)
