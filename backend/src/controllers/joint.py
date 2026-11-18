from src.services import joints
# Controllers keep endpoint contracts separate from persistence and calculation.
def create_study(db,data,user): return joints.create_study(db,data,user)
def list_studies(db): return joints.list_studies(db)
def study_detail(db,id): return joints.detail(db,id)
def save_member(db,id,data,user,member_id=None): return joints.save_member(db,id,data,user,member_id)
def withdraw_member(db,id,member_id,user): return joints.withdraw_member(db,id,member_id,user)
def create_run(db,id,data,user): return joints.create_run(db,id,data,user)
def get_run(db,id): return joints.get_run(db,id)
