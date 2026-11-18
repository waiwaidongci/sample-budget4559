import fakeredis
from fastapi.testclient import TestClient
from src.models.user import User
from src.utils.security import hash_password

def client(db,monkeypatch):
    monkeypatch.setattr('src.middlewares.rate_limit.redis',fakeredis.FakeRedis())
    from src.main import app
    for role in ('admin','viewer'):
        db.add(User(email=f'{role}@demo.local',role=role,password_hash=hash_password('Research2026!')))
    db.commit()
    return TestClient(app)

def login(c,email):
    r=c.post('/auth/login',json={'email':email,'password':'Research2026!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}

def test_joint_api_flow(db,monkeypatch,pushed):
    with client(db,monkeypatch) as c:
        admin=login(c,'admin@demo.local')
        viewer=login(c,'viewer@demo.local')
        s=c.post('/joints',json={'name':'API联合','description':'冒烟'},headers=admin)
        assert s.status_code==200,s.text
        sid=s.json()['id']
        assert c.post('/joints',json={'name':'API联合','description':''},headers=admin).status_code==409
        assert c.post('/joints',json={'name':'越权','description':''},headers=viewer).status_code==403
        ok=c.post(f'/joints/{sid}/members',json={'member_key':'CTRL','role':'control','impressions':5000,'clicks':400},headers=admin)
        assert ok.status_code==200,ok.text
        assert c.post(f'/joints/{sid}/members',json={'member_key':'CTRL2','role':'control','impressions':5000,'clicks':400},headers=admin).status_code==409
        assert c.post(f'/joints/{sid}/members',json={'member_key':'C1','role':'candidate','impressions':3000,'clicks':290,'cost_per_contact':.1,'budget':500},headers=admin).status_code==200
        assert c.post(f'/joints/{sid}/members',json={'member_key':'C2','role':'candidate','impressions':3000,'clicks':3001,'cost_per_contact':.1,'budget':500},headers=admin).status_code==422
        r=c.post(f'/joints/{sid}/runs',json={'name':'核算','parameters':{'simulations':500}},headers=admin)
        assert r.status_code==200,r.text
        rid=r.json()['id']
        assert ('joint-queue',rid) in pushed
        detail=c.get(f'/joints/{sid}',headers=viewer)
        assert detail.status_code==200 and detail.json()['runs'][0]['id']==rid
        run=c.get(f'/joint-runs/{rid}',headers=viewer)
        assert run.status_code==200 and run.json()['status']=='queued'
        mid=[m for m in detail.json()['members'] if m['member_key']=='C1'][0]['id']
        w=c.post(f'/joints/{sid}/members/{mid}/withdraw',headers=admin)
        assert w.status_code==200 and w.json()['status']=='withdrawn'
        run=c.get(f'/joint-runs/{rid}',headers=viewer).json()
        assert run['status']=='invalidated' and '失效' in run['invalidation_reason']
        assert c.get('/joints',headers=viewer).status_code==200
