from datetime import date, timedelta, datetime, timezone
from sqlalchemy import select
from .models import Base, engine, Session, User, Facility, Batch, Transaction, Replenishment, Alert, Audit, ConsumptionSummary, Product, PhysicalCount, CountLine, Discrepancy, Transfer, AlertEvent, EvaluationLabel
from .security import hash_password

def ensure_synthetic_evaluation_labels(db):
    product=db.scalar(select(Product).where(Product.identifier=='ASV-POLY-001'))
    reviewer=db.scalar(select(User).where(User.email=='officer@venotrack.demo'))
    facilities=db.scalars(select(Facility).order_by(Facility.id)).all()
    if not product or not reviewer or not facilities: return
    labels=db.scalars(select(EvaluationLabel).where(EvaluationLabel.product_id==product.id)).all()
    if not any(label.evidence.startswith(('Synthetic training label:','Synthetic evaluation label:')) for label in labels): return
    counts={outcome:sum(label.outcome==outcome for label in labels) for outcome in ('true_positive','false_positive','true_negative','false_negative')}
    targets={'true_positive':4,'false_positive':1,'true_negative':4,'false_negative':1}
    start=date.today()-timedelta(days=2); end=date.today()
    for outcome,target in targets.items():
        for index in range(target-counts[outcome]):
            facility=facilities[(counts[outcome]+index)%len(facilities)]
            evidence=f'Synthetic evaluation label: fictional independent review recorded a {outcome.replace("_"," ")} for demonstration.'
            alert_id=None
            if outcome in ('true_positive','false_positive'):
                alert=Alert(facility_id=facility.id,product_id=product.id,risk_key=f'demo-evaluation-{outcome}-{counts[outcome]+index+1}',severity='high',explanation='Synthetic evaluation example; not a live operational alert.',recommendation='Demonstration record only.',inputs='{}',status='closed')
                db.add(alert); db.flush(); alert_id=alert.id
            db.add(EvaluationLabel(alert_id=alert_id,facility_id=facility.id,product_id=product.id,outcome=outcome,risk_key=f'demo-evaluation-{outcome}',evidence=evidence,reviewer_id=reviewer.id,period_start=start,period_end=end))

def seed():
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        if db.scalar(select(User.id).limit(1)):
            ensure_synthetic_evaluation_labels(db)
            return
        facilities=[
          Facility(code='RH-014',name='Kothapalli Rural Health Sub-centre',kind='Sub-centre',district='Coimbatore Rural',latitude=11.0168,longitude=76.9558,lead_days=6,minimum_stock=10,safety_stock=8),
          Facility(code='RH-021',name='Mettupalayam Health Sub-centre',kind='Sub-centre',district='Coimbatore Rural',latitude=11.3000,longitude=76.9400,lead_days=4,minimum_stock=10,safety_stock=8,last_verified=datetime.now(timezone.utc)-timedelta(days=1)),
          Facility(code='RH-033',name='Annur Rural Health Sub-centre',kind='Sub-centre',district='Coimbatore Rural',latitude=11.2300,longitude=77.1050,lead_days=5,minimum_stock=10,safety_stock=8),
          Facility(code='WH-001',name='Coimbatore District Medical Store',kind='Warehouse',district='Coimbatore Rural',latitude=11.0350,longitude=77.0200,lead_days=1,minimum_stock=25,safety_stock=20)]
        db.add_all(facilities); db.flush()
        for f in facilities[:3]: f.parent_id=facilities[3].id
        product=Product(identifier='ASV-POLY-001',name='Polyvalent Anti-Snake Venom',category='Anti-snake venom',unit='vial')
        db.add(product); db.flush()
        users=[User(name='Kavitha Nair',email='worker@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='worker',district='Coimbatore Rural',facility_id=facilities[0].id),User(name='Arun Kumar',email='officer@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='officer',district='Coimbatore Rural'),User(name='System Admin',email='admin@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='admin'),User(name='Audit Analyst',email='auditor@venotrack.demo',password_hash=hash_password('VenoTrack2026!'),role='auditor',district='Coimbatore Rural')]
        db.add_all(users); db.flush()
        specs=[('ASV-KP-2401',0,4,'usable',True,20),('ASV-KP-2402',0,180,'usable',True,9),('ASV-MT-2404',1,240,'usable',True,36),('ASV-AN-2402',2,150,'usable',True,22),('ASV-WH-2403',3,300,'usable',True,120),('ASV-OLD-21',2,10,'usable',True,0)]
        for number,fi,days,status,verified,qty in specs:
            batch=Batch(facility_id=facilities[fi].id,batch_number=number,product=product.name,product_id=product.id,expiry=date.today()+timedelta(days=days),storage_status=status,verified=verified,quality_status='verified' if verified else 'awaiting_quality')
            db.add(batch); db.flush()
            if qty: db.add(Transaction(facility_id=facilities[fi].id,batch_id=batch.id,kind='receipt',quantity=qty,reason='Synthetic demonstration opening balance',actor_id=users[0].id))
        # Additional fictional records demonstrate pending QC and damage exclusions.
        pending=Batch(facility_id=facilities[0].id,batch_number='ASV-QC-2601',product=product.name,product_id=product.id,expiry=date.today()+timedelta(days=210),storage_status='usable',verified=False,quality_status='awaiting_quality')
        damaged=Batch(facility_id=facilities[2].id,batch_number='ASV-DMG-2601',product=product.name,product_id=product.id,expiry=date.today()+timedelta(days=180),storage_status='damaged',verified=False,quality_status='damaged')
        db.add_all([pending,damaged]); db.flush()
        db.add_all([Transaction(facility_id=facilities[0].id,batch_id=pending.id,kind='receipt',quantity=6,reason='Synthetic QC-pending example',actor_id=users[0].id),Transaction(facility_id=facilities[2].id,batch_id=damaged.id,kind='receipt',quantity=3,reason='Synthetic damaged-stock example',actor_id=users[0].id)])
        # consume opening stock at RH-014 to create explainable 12-vial risk
        db.add(Transaction(facility_id=facilities[0].id,batch_id=1,kind='issue',quantity=8,reason='Synthetic demonstration usage history',actor_id=users[0].id))
        db.add(ConsumptionSummary(facility_id=facilities[0].id,product_id=product.id,quantity=8,period_days=2,source='synthetic demo'))
        # Add a replenishment example with overdue/delayed status
        db.add(Replenishment(request_code='VR-2026-0042',facility_id=facilities[2].id,product_id=product.id,quantity=24,received=0,reason='Synthetic delayed shipment example',priority='high',status='dispatched',expected_date=date.today()-timedelta(days=2),created_by=users[1].id,dispatched_at=datetime.now(timezone.utc),notes='Fictional demonstration record'))
        count=PhysicalCount(facility_id=facilities[0].id,counted_by=users[0].id,counted_at=datetime.now(timezone.utc)-timedelta(days=45),notes='Synthetic stale-count discrepancy example',status='discrepancy')
        db.add(count); db.flush(); db.add(CountLine(count_id=count.id,batch_id=1,ledger_quantity=12,counted_quantity=11))
        db.add(Discrepancy(count_id=count.id,batch_id=1,ledger_quantity=12,counted_quantity=11,status='open'))
        facilities[0].last_verified=datetime.now(timezone.utc)-timedelta(days=45)
        alert=Alert(facility_id=facilities[0].id,product_id=product.id,risk_key='stockout',severity='critical',explanation='Synthetic critical stockout warning for demonstration.',recommendation='Review physical stock and replenishment options.',inputs='{}',status='active')
        alert_fp=Alert(facility_id=facilities[2].id,product_id=product.id,risk_key='stockout-review',severity='high',explanation='Synthetic alert used for independent evaluation training.',recommendation='Review recorded demand and current stock.',inputs='{}',status='active')
        db.add_all([alert,alert_fp]); db.flush()
        db.add_all([AlertEvent(alert_id=alert.id,actor_id=users[1].id,event_type='acknowledged',note='Synthetic acknowledgement example'),AlertEvent(alert_id=alert.id,actor_id=users[1].id,event_type='escalated',target_role='admin',note='Synthetic escalation example'),EvaluationLabel(alert_id=alert.id,facility_id=facilities[0].id,product_id=product.id,outcome='true_positive',evidence='Synthetic evaluation label: a separately recorded physical review confirmed the risk condition.',reviewer_id=users[1].id,period_start=date.today()-timedelta(days=2),period_end=date.today()),EvaluationLabel(alert_id=alert_fp.id,facility_id=facilities[2].id,product_id=product.id,outcome='false_positive',evidence='Synthetic evaluation label: independent review found the forecast condition was not present.',reviewer_id=users[1].id,period_start=date.today()-timedelta(days=2),period_end=date.today())])
        ensure_synthetic_evaluation_labels(db)
        db.add(Transfer(transfer_code='VT-DEMO-0001',source_facility_id=facilities[1].id,destination_facility_id=facilities[0].id,batch_id=3,quantity=2,received_quantity=0,status='proposed'))

def reset():
    Base.metadata.drop_all(engine); seed()
if __name__=='__main__': seed(); print('Seeded fictional VenoTrack demo records.')
