from datetime import date, timedelta, datetime, timezone
from sqlalchemy import select
from .models import Base, engine, Session, User, Facility, Batch, Transaction, Replenishment, Alert, Audit, ConsumptionSummary
from .security import hash_password

def seed():
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        if db.scalar(select(User.id).limit(1)): return
        facilities=[
          Facility(code='RH-014',name='Kothapalli Rural Health Sub-centre',kind='Sub-centre',district='Coimbatore Rural',latitude=11.0168,longitude=76.9558,phone='+91 422 555 0140',lead_days=6,minimum_stock=10,safety_stock=8),
          Facility(code='RH-021',name='Mettupalayam Health Sub-centre',kind='Sub-centre',district='Coimbatore Rural',latitude=11.3000,longitude=76.9400,phone='+91 422 555 0210',lead_days=4,minimum_stock=10,safety_stock=8,last_verified=datetime.now(timezone.utc)-timedelta(days=1)),
          Facility(code='RH-033',name='Annur Rural Health Sub-centre',kind='Sub-centre',district='Coimbatore Rural',latitude=11.2300,longitude=77.1050,phone='+91 422 555 0330',lead_days=5,minimum_stock=10,safety_stock=8),
          Facility(code='WH-001',name='Coimbatore District Medical Store',kind='Warehouse',district='Coimbatore Rural',latitude=11.0350,longitude=77.0200,phone='+91 422 555 0001',lead_days=1,minimum_stock=25,safety_stock=20)]
        db.add_all(facilities); db.flush()
        users=[User(name='Kavitha Nair',email='worker@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='worker',district='Coimbatore Rural',facility_id=facilities[0].id),User(name='Arun Kumar',email='officer@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='officer',district='Coimbatore Rural'),User(name='System Admin',email='admin@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='admin'),User(name='Audit Analyst',email='auditor@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='auditor',district='Coimbatore Rural')]
        db.add_all(users); db.flush()
        specs=[('ASV-KP-2401',0,4,'usable',True,20),('ASV-KP-2402',0,180,'usable',True,9),('ASV-MT-2404',1,240,'usable',True,36),('ASV-AN-2402',2,150,'usable',True,22),('ASV-WH-2403',3,300,'usable',True,120),('ASV-OLD-21',2,10,'usable',True,0)]
        for number,fi,days,status,verified,qty in specs:
            batch=Batch(facility_id=facilities[fi].id,batch_number=number,expiry=date.today()+timedelta(days=days),storage_status=status,verified=verified)
            db.add(batch); db.flush()
            if qty: db.add(Transaction(facility_id=facilities[fi].id,batch_id=batch.id,kind='receipt',quantity=qty,reason='Synthetic demonstration opening balance',actor_id=users[0].id))
        # consume opening stock at RH-014 to create explainable 12-vial risk
        db.add(Transaction(facility_id=facilities[0].id,batch_id=1,kind='issue',quantity=8,reason='Synthetic demonstration usage history',actor_id=users[0].id))
        db.add(ConsumptionSummary(facility_id=facilities[0].id,quantity=8,period_days=2,source='synthetic demo'))
        # Add a replenishment example with overdue/delayed status
        db.add(Replenishment(request_code='VR-2026-0042',facility_id=facilities[2].id,quantity=24,received=0,reason='Synthetic delayed shipment example',priority='high',status='dispatched',expected_date=date.today()-timedelta(days=2),created_by=users[1].id,dispatched_at=datetime.now(timezone.utc),notes='Fictional demonstration record'))

def reset():
    Base.metadata.drop_all(engine); seed()
if __name__=='__main__': seed(); print('Seeded fictional VenoTrack demo records.')
