from fastapi.testclient import TestClient
from app.main import app
from app.models import Session,Facility,Batch
from sqlalchemy import select

def test_closed_loop_replenishment_with_partial_delivery():
    with TestClient(app) as c:
        worker=c.post('/api/v1/auth/login',data={'username':'worker@venotrack.demo','password':'VenoTrack2026!'}).json()['access_token']
        officer=c.post('/api/v1/auth/login',data={'username':'officer@venotrack.demo','password':'VenoTrack2026!'}).json()['access_token']
        wh={'Authorization':'Bearer '+worker}; oh={'Authorization':'Bearer '+officer}
        with Session() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            b=db.scalar(select(Batch).where(Batch.facility_id==f.id,Batch.verified.is_(True)))
            fid,bid=f.id,b.id
        request=c.post('/api/v1/replenishments',headers=wh,json={'facility_id':fid,'quantity':6,'reason':'Demonstration workflow request','priority':'urgent'})
        assert request.status_code==200,request.text
        rid=request.json()['id']
        assert c.post(f'/api/v1/replenishments/{rid}/approve',headers=oh,json={}).json()['status']=='approved'
        assert c.post(f'/api/v1/replenishments/{rid}/dispatch',headers=oh,json={}).json()['status']=='dispatched'
        partial=c.post(f'/api/v1/replenishments/{rid}/receive',headers=wh,json={'quantity':4,'batch_id':bid})
        assert partial.status_code==200 and partial.json()['outstanding']==2
        assert partial.json()['status']=='partially_received'
        final=c.post(f'/api/v1/replenishments/{rid}/receive',headers=wh,json={'quantity':2,'batch_id':bid})
        assert final.status_code==200 and final.json()['status']=='received'
        verified=c.post(f'/api/v1/replenishments/{rid}/verify',headers=wh,json={'batch_id':bid,'reason':'Physical count confirmed'})
        assert verified.status_code==200 and verified.json()['status']=='verified'
