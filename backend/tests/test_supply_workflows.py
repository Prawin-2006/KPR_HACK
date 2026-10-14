from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import Session, Batch, Facility, Transaction, Discrepancy, Alert, Product, User, ReorderDraft, Transfer
from test_api import token

def test_count_discrepancy_waits_for_officer_resolution():
    with TestClient(app) as c:
        worker=token(c); officer=token(c,'officer@venotrack.demo')
        with Session() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            b=db.scalar(select(Batch).where(Batch.facility_id==f.id))
            fid,bid=f.id,b.id
            before=sum(t.quantity if t.kind in ('receipt','adjustment_in','transfer_in') else -t.quantity for t in db.scalars(select(Transaction).where(Transaction.batch_id==bid)))
        result=c.post(f'/api/v1/facilities/{fid}/counts',headers=worker,json={'lines':[{'batch_id':bid,'counted_quantity':before+2}]})
        assert result.status_code==200,result.text
        discrepancy=result.json()['discrepancies'][0]['id']
        assert c.post(f'/api/v1/discrepancies/{discrepancy}/resolve',headers=worker,json={'resolution':'recount confirmed'}).status_code==403
        with Session() as db:
            after=sum(t.quantity if t.kind in ('receipt','adjustment_in','transfer_in') else -t.quantity for t in db.scalars(select(Transaction).where(Transaction.batch_id==bid)))
        assert after==before
        assert c.post(f'/api/v1/discrepancies/{discrepancy}/resolve',headers=officer,json={'resolution':'recount confirmed'}).status_code==200
        assert c.post(f'/api/v1/discrepancies/{discrepancy}/resolve',headers=officer,json={'resolution':'duplicate'}).status_code==409

def test_quality_pending_batch_is_not_issueable():
    with TestClient(app) as c:
        h=token(c)
        with Session.begin() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            b=db.scalar(select(Batch).where(Batch.facility_id==f.id)); fid,bid=f.id,b.id
            b.quality_status='awaiting_quality'; b.verified=True
        result=c.post(f'/api/v1/facilities/{fid}/transactions',headers=h,json={'batch_id':bid,'kind':'issue','quantity':1,'reason':'quality hold test'})
        assert result.status_code==409

def test_reorder_draft_explains_usable_stock_and_due_supply():
    with TestClient(app) as c:
        h=token(c,'officer@venotrack.demo')
        result=c.get('/api/v1/reorder/recommendations',headers=h)
        assert result.status_code==200,result.text
        row=next(x for x in result.json() if x['facility']=='RH-014')
        assert row['recommended_quantity']>=0
        assert 'usable stock' in row['explanation'].lower()

def test_reorder_quantity_is_capped_at_maximum_stock_position():
    with TestClient(app) as c:
        h=token(c,'officer@venotrack.demo')
        with Session.begin() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014')); f.maximum_stock=25
        row=next(x for x in c.get('/api/v1/reorder/recommendations',headers=h).json() if x['facility']=='RH-014')
        assert row['usable_stock']==21
        assert row['recommended_quantity']<=25-row['usable_stock']
        assert any('capped' in flag.lower() for flag in row['data_flags'])

def test_alert_acknowledgement_and_escalation_are_events():
    with TestClient(app) as c:
        h=token(c,'officer@venotrack.demo')
        c.post('/api/v1/risk/run',headers=h)
        alert=next(a for a in c.get('/api/v1/alerts',headers=h).json() if a['status']=='active')
        ack=c.post(f"/api/v1/alerts/{alert['id']}/acknowledge",headers=h,json={'note':'review started'})
        assert ack.status_code==200
        escalation=c.post(f"/api/v1/alerts/{alert['id']}/escalate",headers=h,json={'target_role':'admin','note':'urgent review'})
        assert escalation.status_code==200
        assert c.get('/api/v1/alerts',headers=h).json()[0]['status']=='active'

def test_transfer_requires_verification_both_approvals_and_reconciles_partial_delivery():
    with TestClient(app) as c:
        h=token(c,'officer@venotrack.demo'); admin=token(c,'admin@venotrack.demo')
        with Session() as db:
            src=db.scalar(select(Facility).where(Facility.code=='RH-021'))
            dst=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            b=db.scalar(select(Batch).where(Batch.facility_id==src.id))
            src_id,dst_id,bid=src.id,dst.id,b.id
        rejected=c.post('/api/v1/transfers',headers=h,json={'source_facility_id':src_id,'destination_facility_id':dst_id,'batch_id':bid,'quantity':100,'note':'over-reserve test'})
        assert rejected.status_code==409
        proposed=c.post('/api/v1/transfers',headers=h,json={'source_facility_id':src_id,'destination_facility_id':dst_id,'batch_id':bid,'quantity':2,'note':'verified transfer test'})
        assert proposed.status_code==200,proposed.text
        tid=proposed.json()['id']
        assert c.post(f'/api/v1/transfers/{tid}/dispatch',headers=h).status_code==409
        verified=c.post(f'/api/v1/transfers/{tid}/verify',headers=h,json={'counted_quantity':36,'storage_suitable':True,'transport_suitable':True,'note':'physical source check'})
        assert verified.status_code==200,verified.text
        approved=c.post(f'/api/v1/transfers/{tid}/authorize',headers=h,json={'side':'source','approved':True,'storage_suitable':True,'transport_suitable':True,'note':'source facility review'})
        assert approved.status_code==200,approved.text
        same_officer=c.post(f'/api/v1/transfers/{tid}/authorize',headers=h,json={'side':'destination','approved':True,'storage_suitable':True,'transport_suitable':True,'note':'must be independently approved'})
        assert same_officer.status_code==409
        destination=c.post(f'/api/v1/transfers/{tid}/authorize',headers=admin,json={'side':'destination','approved':True,'storage_suitable':True,'transport_suitable':True,'note':'destination facility review'})
        assert destination.status_code==200,destination.text
        assert c.post(f'/api/v1/transfers/{tid}/dispatch',headers=h).status_code==200
        partial=c.post(f'/api/v1/transfers/{tid}/receive',headers=h,json={'quantity':1,'note':'partial receipt'})
        assert partial.status_code==200 and partial.json()['status']=='partially_received'
        assert c.post(f'/api/v1/transfers/{tid}/reconcile',headers=h,json={'resolution':'Remaining unit documented as a transport discrepancy.'}).json()['status']=='reconciled_partial'
        with Session() as db:
            movements=db.scalars(select(Transaction).where(Transaction.transfer_id==tid)).all()
            assert sorted(t.kind for t in movements)==['transfer_in','transfer_out']

def test_hierarchy_rejects_cycles_and_evaluation_uses_evidence_labels_only():
    with TestClient(app) as c:
        admin=token(c,'admin@venotrack.demo'); officer=token(c,'officer@venotrack.demo')
        with Session() as db:
            warehouse=db.scalar(select(Facility).where(Facility.code=='WH-001'))
            child=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            wid,cid=warehouse.id,child.id
        assert c.put(f'/api/v1/facilities/{wid}/hierarchy',headers=admin,json={'parent_id':cid}).status_code==422
        data=c.get('/api/v1/evaluation',headers=officer).json()
        assert data['sample_size']==2
        assert data['confusion_counts']['true_positive']==1 and data['confusion_counts']['false_positive']==1
        assert data['detection_metrics']['precision']['value']==0.5

def test_expiry_warning_override_never_restores_usability_and_stale_count_lowers_confidence():
    with TestClient(app) as c:
        worker=token(c); officer=token(c,'officer@venotrack.demo')
        with Session() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            expired=db.scalar(select(Batch).where(Batch.batch_number=='ASV-OLD-21'))
            fid,bid=f.id,expired.id
        with Session.begin() as db: db.get(Batch,bid).expiry=date.today()-timedelta(days=1)
        ack=c.post(f'/api/v1/batches/{bid}/expiry-warning/acknowledge',headers=officer,json={'reason':'warning reviewed'})
        assert ack.status_code==200 and ack.json()['usable'] is False
        override=c.post(f'/api/v1/batches/{bid}/expiry-warning/override',headers=officer,json={'reason':'documented officer override'})
        assert override.status_code==200 and override.json()['usable'] is False
        risk=next(x for x in c.get('/api/v1/risks',headers=worker).json() if x['facility_code']=='RH-014')
        assert risk['confidence']=='low' and risk['inventory_freshness']=='needs_reconciliation'
        assert risk['data_quality']=='limited'

def test_evaluation_labels_match_review_window_and_no_alert_true_negative():
    with TestClient(app) as c:
        officer=token(c,'officer@venotrack.demo'); auditor=token(c,'auditor@venotrack.demo')
        with Session.begin() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            product=db.scalar(select(Product).where(Product.identifier=='ASV-POLY-001'))
            row=Alert(facility_id=f.id,product_id=product.id,risk_key='label-window-test',severity='medium',explanation='Synthetic test event',recommendation='review',inputs='{}',status='active')
            db.add(row); db.flush(); aid,fid=row.id,f.id
        bad=c.post(f'/api/v1/alerts/{aid}/evaluation-label',headers=officer,json={'outcome':'true_positive','evidence':'Independent physical review confirms this synthetic test event.','period_start':(date.today()-timedelta(days=10)).isoformat(),'period_end':(date.today()-timedelta(days=9)).isoformat()})
        assert bad.status_code==422
        period={'period_start':(date.today()-timedelta(days=1)).isoformat(),'period_end':date.today().isoformat()}
        good=c.post(f'/api/v1/alerts/{aid}/evaluation-label',headers=officer,json={'outcome':'true_positive','evidence':'Independent physical review confirms this synthetic test event.','period_start':period['period_start'],'period_end':period['period_end']})
        assert good.status_code==200
        assert c.post(f'/api/v1/alerts/{aid}/evaluation-label',headers=officer,json={'outcome':'true_positive','evidence':'Second label should be rejected as duplicate.','period_start':period['period_start'],'period_end':period['period_end']}).status_code==409
        tn=c.post('/api/v1/evaluation/labels',headers=officer,json={'facility_id':fid,'outcome':'true_negative','risk_key':'no-detection-test','evidence':'Independent daily physical verification recorded no shortage.','period_start':period['period_start'],'period_end':period['period_end']})
        assert tn.status_code==200,tn.text
        assert c.post('/api/v1/evaluation/labels',headers=auditor,json={'facility_id':fid,'outcome':'false_negative','risk_key':'no-detection-test','evidence':'Auditor cannot create outcomes.','period_start':period['period_start'],'period_end':period['period_end']}).status_code==403

def test_reorder_and_transfer_cannot_reference_non_asv_inventory():
    with TestClient(app) as c:
        worker=token(c)
        officer=token(c,'officer@venotrack.demo')
        with Session.begin() as db:
            src=db.scalar(select(Facility).where(Facility.code=='RH-021'))
            dst=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            worker_facility=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            user=db.scalar(select(User).where(User.email=='worker@venotrack.demo'))
            product=Product(identifier='LEGACY-ANTIBIOTIC',name='Amoxicillin',category='Anti-snake venom',unit='tablet',active=True)
            db.add(product); db.flush()
            batch=Batch(facility_id=src.id,batch_number='LEGACY-TRANSFER-001',product=product.name,product_id=product.id,expiry=date.today()+timedelta(days=100),storage_status='usable',verified=True,quality_status='verified')
            db.add(batch); db.flush()
            db.add(Transaction(facility_id=src.id,batch_id=batch.id,kind='receipt',quantity=7,reason='legacy stock',actor_id=user.id))
            source_id,destination_id,worker_facility_id,product_id,batch_id=src.id,dst.id,worker_facility.id,product.id,batch.id
            src.last_verified=datetime.now(timezone.utc)

        draft=c.post('/api/v1/reorder/drafts',headers=worker,json={'facility_id':worker_facility_id,'product_id':product_id})
        assert draft.status_code==422
        transfer=c.post('/api/v1/transfers',headers=officer,json={'source_facility_id':source_id,'destination_facility_id':destination_id,'batch_id':batch_id,'quantity':1,'note':'legacy batch transfer'})
        assert transfer.status_code==422
        with Session() as db:
            assert db.scalar(select(ReorderDraft).where(ReorderDraft.product_id==product_id)) is None
            assert db.scalar(select(Transfer).where(Transfer.batch_id==batch_id)) is None

