import os,sys,tempfile
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
_tmp=tempfile.mkdtemp(prefix='joint-test-')
os.environ['DATABASE_URL']=f'sqlite:///{_tmp}/test.db'
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET','test-secret')
os.environ['ARTIFACTS_DIR']=_tmp

import pytest
from src.config.database import Base,engine,Session
from src.models import user as user_model,study,observation,run,review,audit,joint

@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    with Session() as s:
        for t in reversed(Base.metadata.sorted_tables): s.execute(t.delete())
        s.commit()
        yield s

@pytest.fixture(autouse=True)
def pushed(monkeypatch):
    jobs=[]
    monkeypatch.setattr('src.services.queue.push',lambda q,i: jobs.append((q,i)))
    return jobs

@pytest.fixture()
def user(db):
    u=user_model.User(email='analyst@demo.local',role='analyst',password_hash='x')
    db.add(u);db.commit();return u
