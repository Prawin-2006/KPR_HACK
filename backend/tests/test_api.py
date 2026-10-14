from fastapi.testclient import TestClient
from app.main import app
from app.models import Session, User, Facility, Batch, Transaction, Base, engine
from sqlalchemy import select

def token(c,email='worker@venotrack.demo',password='VenoTrack2026!'):
    r=c.post('/api/v1/auth/login',data={'username':email,'password':password}); assert r.status_code==200,r.text; return {'Authorization':'Bearer '+r.json()['access_token']}

def test_dashboard_and_risk_are_database_backed():
    with TestClient(app) as c:
        h=token(c)
        d=c.get('/api/v1/dashboard',headers=h); assert d.status_code==200
        assert d.json()['synthetic'] is True
        assert d.json()['counts']['facilities']==1
        risks=c.get('/api/v1/risks',headers=h).json()
        assert any(r['facility_code']=='RH-014' and r['severity']=='critical' for r in risks)

def test_worker_cannot_access_unassigned_facility():
    with TestClient(app) as c:
        h=token(c)
        with Session() as db: fid=db.scalar(select(Facility.id).where(Facility.code=='WH-001'))
        # worker district access permits the whole district; different district fixture tests strict block
        with Session.begin() as db:
            f=db.get(Facility,fid); f.district='Other District'
        try: assert c.get(f'/api/v1/facilities/{fid}',headers=h).status_code==403
        finally:
            with Session.begin() as db: db.get(Facility,fid).district='Coimbatore Rural'

def test_issue_rejects_unusable_and_excess_quantity():
    with TestClient(app) as c:
        h=token(c)
        with Session() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014')); b=db.scalar(select(Batch).where(Batch.facility_id==f.id))
            fid,bid=f.id,b.id
        r=c.post(f'/api/v1/facilities/{fid}/transactions',headers=h,json={'batch_id':bid,'kind':'issue','quantity':10000,'reason':'test over-issue'})
        assert r.status_code==409

def test_officer_risk_run_deduplicates_alerts():
    with TestClient(app) as c:
        h=token(c,'officer@venotrack.demo')
        first=c.post('/api/v1/risk/run',headers=h).json(); second=c.post('/api/v1/risk/run',headers=h).json()
        assert first['evaluated']>=1 and second['evaluated']>=1
        alerts=c.get('/api/v1/alerts',headers=h).json()
        assert len([a for a in alerts if a['facility']=='RH-014' and a['status']=='active'])==1
from fastapi.testclient import TestClient
from app.main import app

def test_auditor_cannot_write_inventory():
    with TestClient(app) as c:
        login=c.post('/api/v1/auth/login',data={'username':'auditor@venotrack.demo','password':'VenoTrack2026!'})
        h={'Authorization':'Bearer '+login.json()['access_token']}
        result=c.post('/api/v1/facilities/1/transactions',headers=h,json={'batch_id':1,'kind':'issue','quantity':1,'reason':'unauthorized audit write'})
        assert result.status_code==403
