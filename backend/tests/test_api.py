from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models import Session, User, Facility, Batch, Transaction, Product, PhysicalCount, ConsumptionSummary, Alert, EvaluationLabel, DailyObservation
from sqlalchemy import select, func, text

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

def test_unlinked_legacy_consumption_does_not_change_asv_forecast():
    with TestClient(app) as c:
        h=token(c,'admin@venotrack.demo')
        before=c.get('/api/v1/facilities',headers=h).json()
        facility=next(f for f in before if f['code']=='RH-014')
        original=facility['risk']['average_daily_consumption']
        with Session.begin() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            db.add(ConsumptionSummary(facility_id=f.id,quantity=500,period_days=1,source='unlinked historical demand'))
        after=c.get('/api/v1/facilities',headers=h).json()
        facility=next(f for f in after if f['code']=='RH-014')
        assert facility['risk']['average_daily_consumption']==original

def test_asv_scope_migration_report_is_admin_only_and_stock_csv_names_vials():
    with TestClient(app) as c:
        admin=token(c,'admin@venotrack.demo'); worker=token(c)
        with Session.begin() as db:
            db.execute(text("INSERT INTO asv_scope_migration_reports (product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, preserved_workflow_count, scope_action, original_state) VALUES ('UNLINKED-CONSUMPTION','Legacy summaries','[]',0,0,1,'unscoped_excluded','{}')"))
        response=c.get('/api/v1/admin/asv-scope-migration-report',headers=admin)
        assert response.status_code==200
        assert response.json()['reports'][0]['product_identifier']=='UNLINKED-CONSUMPTION'
        assert c.get('/api/v1/admin/asv-scope-migration-report',headers=worker).status_code==403
        csv=c.get('/api/v1/reports/stock.csv',headers=admin).text
        assert 'product_identifier,quantity_unit' in csv
        assert 'ASV-POLY-001,vial' in csv

def test_unlinked_alerts_labels_and_observations_are_excluded_from_asv_evaluation():
    with TestClient(app) as c:
        admin=token(c,'admin@venotrack.demo')
        baseline_alerts=c.get('/api/v1/alerts',headers=admin).json()
        baseline=c.get('/api/v1/evaluation',headers=admin).json()
        with Session.begin() as db:
            f=db.scalar(select(Facility).where(Facility.code=='RH-014'))
            user=db.scalar(select(User).where(User.email=='officer@venotrack.demo'))
            alert=Alert(facility_id=f.id,risk_key='unlinked-legacy',severity='critical',explanation='Legacy unlinked alert',recommendation='',inputs='{}',status='active')
            db.add(alert); db.flush()
            db.add(EvaluationLabel(alert_id=alert.id,facility_id=f.id,outcome='true_positive',risk_key=alert.risk_key,evidence='Legacy unlinked evaluation label',reviewer_id=user.id,period_start=date.today(),period_end=date.today()))
            db.add(DailyObservation(facility_id=f.id,observed_date=date.today()-timedelta(days=3),usable_quantity=0,observed_by=user.id,evidence='Legacy unlinked stock observation'))
        assert len(c.get('/api/v1/alerts',headers=admin).json())==len(baseline_alerts)
        after=c.get('/api/v1/evaluation',headers=admin).json()
        assert after['sample_size']==baseline['sample_size']
        assert after['service']['observation_sample_size']==baseline['service']['observation_sample_size']

def test_new_stock_observations_are_linked_to_asv_vials():
    with TestClient(app) as c:
        officer=token(c,'officer@venotrack.demo')
        response=c.post('/api/v1/evaluation/observations',headers=officer,json={'facility_id':1,'observed_date':(date.today()-timedelta(days=1)).isoformat(),'usable_quantity':8,'evidence':'Synthetic ASV shelf count checked against the vial batch ledger.'})
        assert response.status_code==200,response.text
        assert response.json()['unit']=='vial'
        with Session() as db:
            row=db.scalar(select(DailyObservation).where(DailyObservation.observed_date==date.today()-timedelta(days=1)))
            assert row.product_id==db.scalar(select(Product.id).where(Product.identifier=='ASV-POLY-001'))

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

def _add_legacy_inventory():
    with Session.begin() as db:
        facility=db.scalar(select(Facility).where(Facility.code=='RH-014'))
        worker=db.scalar(select(User).where(User.email=='worker@venotrack.demo'))
        product=Product(identifier='LEGACY-AMOXICILLIN',name='Amoxicillin',category='Anti-snake venom',unit='tablet',active=True)
        db.add(product); db.flush()
        batch=Batch(facility_id=facility.id,batch_number='LEGACY-LOT-001',product=product.name,product_id=product.id,expiry=date.today()+timedelta(days=100),storage_status='usable',verified=True,quality_status='verified')
        db.add(batch); db.flush()
        tx=Transaction(facility_id=facility.id,batch_id=batch.id,kind='receipt',quantity=7,reason='preserved legacy receipt',actor_id=worker.id)
        db.add(tx)
        return facility.id,product.id,batch.id,tx.id

def test_product_catalog_rejects_unrelated_medicine_and_hides_inactive_legacy_product():
    with TestClient(app) as c:
        admin=token(c,'admin@venotrack.demo')
        rejected=c.post('/api/v1/products',headers=admin,json={'identifier':'AMOX-001','name':'Amoxicillin','category':'Antibiotic','unit':'tablet'})
        assert rejected.status_code==422
        facility_id,product_id,batch_id,_=_add_legacy_inventory()
        with Session.begin() as db:
            db.get(Product,product_id).active=False
            batch=db.get(Batch,batch_id); batch.storage_status='quarantined'; batch.quality_status='quarantined'; batch.verified=False
        catalog=c.get('/api/v1/products',headers=admin)
        assert catalog.status_code==200
        assert [p['identifier'] for p in catalog.json()]==['ASV-POLY-001']
        facility=c.get(f'/api/v1/facilities/{facility_id}',headers=admin).json()
        assert all(b['batch_number']!='LEGACY-LOT-001' for b in facility['batches'])
        assert facility['reported_stock']==27
        assert all(t['batch']!='LEGACY-LOT-001' for t in c.get('/api/v1/inventory/transactions',headers=admin).json())

def test_inventory_writes_reject_legacy_product_batches_without_side_effects():
    with TestClient(app) as c:
        h=token(c); facility_id,product_id,batch_id,_=_add_legacy_inventory()
        with Session() as db: before_counts=db.scalar(select(func.count(PhysicalCount.id)))
        tx=c.post(f'/api/v1/facilities/{facility_id}/transactions',headers=h,json={'batch_id':batch_id,'kind':'issue','quantity':1,'reason':'legacy batch issue'})
        assert tx.status_code==422
        count=c.post(f'/api/v1/facilities/{facility_id}/counts',headers=h,json={'lines':[{'batch_id':batch_id,'counted_quantity':7}]})
        assert count.status_code==422
        with Session() as db:
            assert db.scalar(select(Transaction).where(Transaction.batch_id==batch_id,Transaction.kind=='issue')) is None
            assert db.scalar(select(func.count(PhysicalCount.id)))==before_counts
from fastapi.testclient import TestClient
from app.main import app

def test_auditor_cannot_write_inventory():
    with TestClient(app) as c:
        login=c.post('/api/v1/auth/login',data={'username':'auditor@venotrack.demo','password':'VenoTrack2026!'})
        h={'Authorization':'Bearer '+login.json()['access_token']}
        result=c.post('/api/v1/facilities/1/transactions',headers=h,json={'batch_id':1,'kind':'issue','quantity':1,'reason':'unauthorized audit write'})
        assert result.status_code==403
