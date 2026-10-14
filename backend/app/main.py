from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import json, math, csv, io
from fastapi import FastAPI, Depends, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .models import init_db, Facility, Batch, Transaction, Alert, Replenishment, Audit, User, ConsumptionSummary, Product, PhysicalCount, CountLine, Discrepancy, Transfer, AlertEvent, EvaluationLabel, ReorderDraft, BatchEvent, DailyObservation
from .security import get_db, current_user, issue_token, verify_password, require, can_access
from .risk import forecast_risk

@asynccontextmanager
async def lifespan(_app):
    from alembic import command
    from alembic.config import Config
    backend_dir=Path(__file__).resolve().parents[1]
    migration_config=Config(str(backend_dir/'alembic.ini'))
    migration_config.set_main_option('script_location',str(backend_dir/'migrations'))
    command.upgrade(migration_config,'head')
    init_db()
    yield

app=FastAPI(title='VenoTrack API',version='1.0.0',description='Synthetic anti-venom logistics decision support demo. Not clinical guidance.',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173','http://localhost:5174','http://127.0.0.1:5174'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def facility_json(db, f):
    batches=db.scalars(select(Batch).where(Batch.facility_id==f.id)).all()
    txs=db.scalars(select(Transaction).where(Transaction.facility_id==f.id)).all()
    quantities={b.id:0 for b in batches}
    for t in txs: quantities[t.batch_id]=quantities.get(t.batch_id,0)+(t.quantity if t.kind in ('receipt','adjustment_in','transfer_in') else -t.quantity)
    total=0; expiring=0; warning_expiring=0; all_qty=0
    for b in batches:
        qty=max(0,quantities[b.id]); all_qty+=qty
        if b.expiry and b.expiry>=date.today() and b.storage_status=='usable' and b.verified and b.quality_status=='verified': total+=qty
        if b.expiry and date.today()<=b.expiry<=date.today()+timedelta(days=60): expiring+=qty
        if b.expiry and date.today()<=b.expiry<=date.today()+timedelta(days=f.expiry_warning_days): warning_expiring+=qty
    summaries=db.scalars(select(ConsumptionSummary).where(ConsumptionSummary.facility_id==f.id)).all()
    period_days=sum(s.period_days for s in summaries)
    consumption=sum(s.quantity for s in summaries)/period_days if period_days>0 else None
    delivery_date=date.today()+timedelta(days=max(0,f.lead_days or 0))
    incoming=sum(max(0,r.quantity-r.received) for r in db.scalars(select(Replenishment).where(Replenishment.facility_id==f.id,Replenishment.status.in_(['approved','dispatched','partially_received']))).all() if r.expected_date and date.today()<=r.expected_date<=delivery_date)
    unresolved=db.scalar(select(func.count(Discrepancy.id)).join(Batch,Discrepancy.batch_id==Batch.id).where(Batch.facility_id==f.id,Discrepancy.status=='open')) or 0
    fresh=bool(f.last_verified and (datetime.now(timezone.utc)-f.last_verified.replace(tzinfo=timezone.utc)).days<=30 and not unresolved)
    risk=forecast_risk(total,consumption,f.lead_days,incoming,f.minimum_stock,f.safety_stock,period_days)
    if not fresh:
        risk['confidence']='low'; risk['inventory_freshness']='needs_reconciliation' if unresolved else ('stale' if f.last_verified else 'unverified'); risk['verification_recommended']=True
        reason='unresolved count discrepancies' if unresolved else 'physical inventory verification is stale or missing'
        risk['explanation'] += f'. Forecast confidence is reduced because {reason}.'
    else:
        risk['inventory_freshness']='current'; risk['verification_recommended']=False
    risk['average_daily_consumption']=consumption; risk['facility_id']=f.id; risk['facility_code']=f.code; risk['facility_name']=f.name; risk['usable_stock']=total; risk['total_reported_stock']=all_qty; risk['expiring_60_days']=expiring; risk['last_verified']=f.last_verified.isoformat() if f.last_verified else None
    risk['confirmed_incoming']=incoming
    risk['expiry_warning_quantity']=warning_expiring
    return {'id':f.id,'code':f.code,'name':f.name,'kind':f.kind,'district':f.district,'parent_id':f.parent_id,'phone':f.phone,'latitude':f.latitude,'longitude':f.longitude,'usable_stock':total,'reported_stock':all_qty,'risk':risk,'last_verified':risk['last_verified'],'lead_days':f.lead_days,'minimum_stock':f.minimum_stock,'maximum_stock':f.maximum_stock,'reorder_point':f.reorder_point,'safety_stock':f.safety_stock,'expiry_warning_days':f.expiry_warning_days,'expiry_60_days':expiring,'expiry_warning_quantity':warning_expiring,'batches':[{'id':b.id,'batch_number':b.batch_number,'product':b.product,'product_id':b.product_id,'expiry':b.expiry.isoformat() if b.expiry else None,'storage_status':b.storage_status,'quality_status':b.quality_status,'verified':b.verified,'quantity':max(0,quantities[b.id]),'usable_quantity':max(0,quantities[b.id]) if b.expiry and b.expiry>=date.today() and b.storage_status=='usable' and b.verified and b.quality_status=='verified' else 0} for b in batches]}

def assert_access(user, f):
    if not can_access(user,f): raise HTTPException(403,'Facility access denied')
def audit(db,user,action,entity,eid,details=''):
    db.add(Audit(actor_id=user.id,action=action,entity_type=entity,entity_id=str(eid),details=details))
def ledger_balance(db,batch_id):
    return sum(t.quantity if t.kind in ('receipt','adjustment_in','transfer_in') else -t.quantity for t in db.scalars(select(Transaction).where(Transaction.batch_id==batch_id)).all())
def eligible(batch):
    return bool(batch and batch.expiry and batch.expiry>=date.today() and batch.storage_status=='usable' and batch.verified and batch.quality_status=='verified')
def batch_json(db,b):
    q=max(0,ledger_balance(db,b.id)); f=db.get(Facility,b.facility_id); days=f.expiry_warning_days if f else 60
    return {'id':b.id,'facility_id':b.facility_id,'batch_number':b.batch_number,'product':b.product,'product_id':b.product_id,'expiry':b.expiry.isoformat() if b.expiry else None,'storage_status':b.storage_status,'quality_status':b.quality_status,'verified':b.verified,'quantity':q,'usable_quantity':q if eligible(b) else 0,'expiry_warning':bool(b.expiry and date.today()<=b.expiry<=date.today()+timedelta(days=days))}

@app.post('/api/v1/auth/login')
def login(form:OAuth2PasswordRequestForm=Depends(),db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==form.username))
    if not user or not verify_password(form.password,user.password_hash): raise HTTPException(401,'Incorrect email or password')
    return {'access_token':issue_token(user),'token_type':'bearer','user':{'id':user.id,'name':user.name,'email':user.email,'role':user.role,'district':user.district,'facility_id':user.facility_id}}
@app.get('/api/v1/auth/me')
def me(u=Depends(current_user)): return {'id':u.id,'name':u.name,'email':u.email,'role':u.role,'district':u.district,'facility_id':u.facility_id}
@app.get('/api/v1/dashboard')
def dashboard(db:Session=Depends(get_db),u=Depends(current_user)):
    fs=[f for f in db.scalars(select(Facility)).all() if can_access(u,f)]
    rows=[facility_json(db,f) for f in fs]
    alerts=db.scalars(select(Alert).where(Alert.status=='active').order_by(Alert.created_at.desc()).limit(8)).all()
    alerts=[a for a in alerts if can_access(u,db.get(Facility,a.facility_id))]
    reqs=db.scalars(select(Replenishment).order_by(Replenishment.created_at.desc())).all()
    reqs=[r for r in reqs if can_access(u,db.get(Facility,r.facility_id))]
    txs=db.scalars(select(Transaction).order_by(Transaction.created_at.desc()).limit(8)).all()
    txs=[t for t in txs if can_access(u,db.get(Facility,t.facility_id))]
    counts={'facilities':len(fs),'critical':sum(x['risk']['severity']=='critical' for x in rows),'low':sum(x['usable_stock']>0 and x['risk']['severity'] in ['high','critical'] for x in rows),'zero':sum(x['usable_stock']==0 for x in rows),'expiring_batches':sum(len([b for b in x['batches'] if b['expiry'] and date.fromisoformat(b['expiry'])<=date.today()+timedelta(days=60)]) for x in rows),'active_alerts':len(alerts),'pending_requests':sum(r.status in ['pending','approved','dispatched'] for r in reqs),'overdue_deliveries':sum(bool(r.expected_date and r.expected_date<date.today() and r.received<r.quantity) for r in reqs)}
    trend=[]
    for offset in range(5,-1,-1):
        month=(date.today().replace(day=1)-timedelta(days=offset*30)).replace(day=1)
        trend.append({'month':month.strftime('%b'),'receipts':0,'issues':0,'key':month.strftime('%Y-%m')})
    allowed_ids={f.id for f in fs}
    for t in db.scalars(select(Transaction)).all():
        if t.facility_id not in allowed_ids or not t.created_at: continue
        key=t.created_at.strftime('%Y-%m')
        point=next((m for m in trend if m['key']==key),None)
        if point:
            if t.kind in ('issue','adjustment_out','transfer_out'): point['issues']+=t.quantity
            elif t.kind in ('receipt','adjustment_in','transfer_in'): point['receipts']+=t.quantity
    for point in trend: point.pop('key',None)
    return {'synthetic':True,'counts':counts,'facilities':rows,'trend':trend,'alerts':[{'id':a.id,'facility_id':a.facility_id,'severity':a.severity,'explanation':a.explanation,'status':a.status,'created_at':a.created_at.isoformat() if a.created_at else None} for a in alerts],'requests':[req_json(r,db) for r in reqs[:8]],'transactions':[{'id':t.id,'facility':db.get(Facility,t.facility_id).code,'kind':t.kind,'quantity':t.quantity,'reason':t.reason,'created_at':t.created_at.isoformat() if t.created_at else None} for t in txs]}

def req_json(r,db):
    f=db.get(Facility,r.facility_id)
    return {'id':r.id,'request_code':r.request_code,'facility_id':r.facility_id,'facility':f.code if f else '','facility_name':f.name if f else '', 'quantity':r.quantity,'received':r.received,'outstanding':r.quantity-r.received,'reason':r.reason,'priority':r.priority,'status':r.status,'expected_date':r.expected_date.isoformat() if r.expected_date else None,'created_at':r.created_at.isoformat() if r.created_at else None,'notes':r.notes}
@app.get('/api/v1/facilities')
def facilities(db:Session=Depends(get_db),u=Depends(current_user),q:str|None=None):
    fs=db.scalars(select(Facility).order_by(Facility.code)).all(); fs=[f for f in fs if can_access(u,f)]
    if q: fs=[f for f in fs if q.lower() in f.name.lower() or q.lower() in f.code.lower() or q.lower() in f.district.lower()]
    return [facility_json(db,f) for f in fs]
@app.get('/api/v1/facilities/{fid}')
def facility_detail(fid:int,db:Session=Depends(get_db),u=Depends(current_user)):
    f=db.get(Facility,fid)
    if not f: raise HTTPException(404,'Facility not found')
    assert_access(u,f); data=facility_json(db,f)
    data['transactions']=[{'id':t.id,'kind':t.kind,'quantity':t.quantity,'reason':t.reason,'created_at':t.created_at.isoformat() if t.created_at else None} for t in db.scalars(select(Transaction).where(Transaction.facility_id==fid).order_by(Transaction.created_at.desc()).limit(50)).all()]
    return data
class ProductIn(BaseModel): identifier:str=Field(min_length=2,max_length=80); name:str=Field(min_length=2,max_length=160); category:str='Anti-snake venom'; unit:str='vial'
@app.get('/api/v1/products')
def products(db:Session=Depends(get_db),u=Depends(current_user)):
    return [{'id':p.id,'identifier':p.identifier,'name':p.name,'category':p.category,'unit':p.unit,'active':p.active} for p in db.scalars(select(Product).order_by(Product.name)).all()]
@app.post('/api/v1/products')
def add_product(p:ProductIn,db:Session=Depends(get_db),u=Depends(require('admin'))):
    if db.scalar(select(Product).where(Product.identifier==p.identifier)): raise HTTPException(409,'Product identifier already exists')
    row=Product(**p.model_dump()); db.add(row); db.flush(); audit(db,u,'create','product',row.id,p.identifier); db.commit(); return {'id':row.id,'identifier':row.identifier,'name':row.name}
class BatchIn(BaseModel): product_id:int; batch_number:str=Field(min_length=2,max_length=80); expiry:date; quality_status:str='awaiting_quality'
@app.post('/api/v1/facilities/{fid}/batches')
def add_batch(fid:int,p:BatchIn,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    f=db.get(Facility,fid); product=db.get(Product,p.product_id)
    if not f or not product: raise HTTPException(404,'Facility or product not found')
    assert_access(u,f)
    if p.expiry<date.today() or p.quality_status not in ('awaiting_quality','verified'): raise HTTPException(422,'Expiry must be in the future and quality state must be valid')
    if db.scalar(select(Batch).where(Batch.facility_id==fid,Batch.batch_number==p.batch_number)): raise HTTPException(409,'Batch identifier already exists at this facility')
    b=Batch(facility_id=fid,batch_number=p.batch_number,product=product.name,product_id=product.id,expiry=p.expiry,storage_status='usable',verified=False,quality_status='awaiting_quality')
    db.add(b); db.flush(); audit(db,u,'create','batch',b.id,f'Product {product.identifier}; awaiting quality verification'); db.commit(); return batch_json(db,b)
@app.get('/api/v1/facilities/{fid}/batches')
def facility_batches(fid:int,db:Session=Depends(get_db),u=Depends(current_user)):
    f=db.get(Facility,fid)
    if not f: raise HTTPException(404,'Facility not found')
    assert_access(u,f)
    return [batch_json(db,b) for b in db.scalars(select(Batch).where(Batch.facility_id==fid).order_by(Batch.expiry)).all()]
class QualityIn(BaseModel): status:str; reason:str=Field(min_length=3,max_length=300)
@app.post('/api/v1/batches/{bid}/quality')
def batch_quality(bid:int,p:QualityIn,db:Session=Depends(get_db),u=Depends(current_user)):
    b=db.get(Batch,bid)
    if not b: raise HTTPException(404,'Batch not found')
    assert_access(u,db.get(Facility,b.facility_id))
    if p.status not in ('verified','awaiting_quality','quarantined','damaged','rejected'): raise HTTPException(422,'Unsupported quality status')
    if p.status=='verified' and u.role not in ('officer','admin'): raise HTTPException(403,'Quality verification requires an officer')
    if p.status in ('quarantined','damaged','rejected') and u.role not in ('worker','officer','admin'): raise HTTPException(403,'Operational role required')
    if p.status=='verified' and (not b.expiry or b.expiry<date.today()): raise HTTPException(409,'Expired batches cannot be quality-verified')
    b.quality_status=p.status; b.verified=p.status=='verified'; b.storage_status='usable' if p.status in ('verified','awaiting_quality') else p.status
    b.version=(b.version or 0)+1; db.add(BatchEvent(batch_id=b.id,actor_id=u.id,event_type='quality_'+p.status,reason=p.reason)); audit(db,u,'quality_'+p.status,'batch',b.id,p.reason); db.commit(); return batch_json(db,b)
class BatchWarningIn(BaseModel): reason:str=Field(min_length=3,max_length=300)
@app.post('/api/v1/batches/{bid}/expiry-warning/acknowledge')
def expiry_ack(bid:int,p:BatchWarningIn,db:Session=Depends(get_db),u=Depends(current_user)):
    b=db.get(Batch,bid)
    if not b: raise HTTPException(404,'Batch not found')
    assert_access(u,db.get(Facility,b.facility_id)); f=db.get(Facility,b.facility_id)
    if not b.expiry or b.expiry>date.today()+timedelta(days=f.expiry_warning_days): raise HTTPException(409,'Batch is outside the configured expiry warning window')
    db.add(BatchEvent(batch_id=bid,actor_id=u.id,event_type='expiry_warning_acknowledged',reason=p.reason)); audit(db,u,'expiry_warning_acknowledged','batch',bid,p.reason); db.commit(); return {'acknowledged':True,'usable':eligible(b)}
@app.post('/api/v1/batches/{bid}/expiry-warning/override')
def expiry_override(bid:int,p:BatchWarningIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    b=db.get(Batch,bid)
    if not b: raise HTTPException(404,'Batch not found')
    assert_access(u,db.get(Facility,b.facility_id)); f=db.get(Facility,b.facility_id)
    if not b.expiry or b.expiry>date.today()+timedelta(days=f.expiry_warning_days): raise HTTPException(409,'Batch is outside the configured expiry warning window')
    db.add(BatchEvent(batch_id=bid,actor_id=u.id,event_type='expiry_warning_override',reason=p.reason)); audit(db,u,'expiry_warning_override','batch',bid,p.reason); db.commit()
    return {'recorded':True,'usable':eligible(b),'message':'The acknowledgement does not change expiry or quality eligibility.'}
@app.post('/api/v1/facilities/{fid}/counts')
def submit_count(fid:int,p:dict,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    f=db.get(Facility,fid)
    if not f: raise HTTPException(404,'Facility not found')
    assert_access(u,f); lines=p.get('lines')
    if not isinstance(lines,list) or not lines: raise HTTPException(422,'At least one batch count is required')
    ids=[x.get('batch_id') for x in lines if isinstance(x,dict)]
    if len(ids)!=len(lines) or len(ids)!=len(set(ids)): raise HTTPException(422,'Each batch must appear exactly once')
    count=PhysicalCount(facility_id=fid,counted_by=u.id,notes=str(p.get('notes',''))[:500]); db.add(count); db.flush(); discrepancies=[]
    for line in lines:
        b=db.get(Batch,line['batch_id']); qty=line.get('counted_quantity')
        if not b or b.facility_id!=fid or not isinstance(qty,int) or qty<0: db.rollback(); raise HTTPException(422,'Invalid batch count or quantity')
        ledger=ledger_balance(db,b.id); db.add(CountLine(count_id=count.id,batch_id=b.id,ledger_quantity=ledger,counted_quantity=qty))
        if ledger!=qty:
            d=Discrepancy(count_id=count.id,batch_id=b.id,ledger_quantity=ledger,counted_quantity=qty); db.add(d); db.flush(); discrepancies.append({'id':d.id,'batch_id':b.id,'ledger_quantity':ledger,'counted_quantity':qty,'delta':qty-ledger,'status':'open'})
    f.last_verified=datetime.now(timezone.utc); count.status='discrepancy' if discrepancies else 'verified'; audit(db,u,'submit_physical_count','physical_count',count.id,f'{len(lines)} batch(es); {len(discrepancies)} discrepancy(s)'); db.commit()
    return {'id':count.id,'facility_id':fid,'status':count.status,'discrepancies':discrepancies,'message':'Discrepancies do not change ledger stock until an officer resolves them.'}
class ResolveIn(BaseModel): resolution:str=Field(min_length=3,max_length=500)
@app.get('/api/v1/discrepancies')
def discrepancies(db:Session=Depends(get_db),u=Depends(current_user)):
    rows=[]
    for d in db.scalars(select(Discrepancy).order_by(Discrepancy.id.desc())).all():
        b=db.get(Batch,d.batch_id); f=db.get(Facility,b.facility_id)
        if can_access(u,f): rows.append({'id':d.id,'facility_id':f.id,'facility':f.code,'batch_id':b.id,'batch_number':b.batch_number,'ledger_quantity':d.ledger_quantity,'counted_quantity':d.counted_quantity,'delta':d.counted_quantity-d.ledger_quantity,'status':d.status,'resolution':d.resolution})
    return rows
@app.post('/api/v1/discrepancies/{did}/resolve')
def resolve_discrepancy(did:int,p:ResolveIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    d=db.scalar(select(Discrepancy).where(Discrepancy.id==did).with_for_update())
    if not d: raise HTTPException(404,'Discrepancy not found')
    if d.status!='open': raise HTTPException(409,'Discrepancy is already resolved')
    b=db.get(Batch,d.batch_id); f=db.get(Facility,b.facility_id); assert_access(u,f)
    if ledger_balance(db,b.id)!=d.ledger_quantity: raise HTTPException(409,'Ledger changed since this count; submit a fresh physical count')
    delta=d.counted_quantity-d.ledger_quantity
    if delta: db.add(Transaction(facility_id=f.id,batch_id=b.id,kind='adjustment_in' if delta>0 else 'adjustment_out',quantity=abs(delta),reason=f'Physical count discrepancy {did}: {p.resolution}',actor_id=u.id))
    d.status='resolved'; d.resolved_by=u.id; d.resolved_at=datetime.now(timezone.utc); d.resolution=p.resolution; audit(db,u,'resolve_discrepancy','discrepancy',did,p.resolution); db.commit()
    return {'id':did,'status':d.status,'ledger_delta':delta,'balance':ledger_balance(db,b.id)}
class TxIn(BaseModel): batch_id:int; kind:str; quantity:int=Field(gt=0); reason:str=Field(min_length=3,max_length=200); idempotency_key:str|None=None
@app.post('/api/v1/facilities/{fid}/transactions')
def create_tx(fid:int,p:TxIn,db:Session=Depends(get_db),u=Depends(current_user)):
    if u.role not in ['worker','officer','admin']: raise HTTPException(403,'Read-only role')
    f=db.get(Facility,fid); b=db.get(Batch,p.batch_id)
    if not f or not b or b.facility_id!=fid: raise HTTPException(404,'Facility or batch not found')
    assert_access(u,f)
    if p.kind not in ['receipt','issue','adjustment_in','adjustment_out']: raise HTTPException(422,'Unsupported transaction type')
    if p.kind in ('adjustment_in','adjustment_out') and u.role not in ('officer','admin'): raise HTTPException(403,'Stock adjustments require an authorized officer')
    if p.kind=='receipt' and (not b.expiry or b.expiry<date.today() or b.quality_status in ('damaged','quarantined','rejected')): raise HTTPException(409,'Cannot receive an expired, damaged, quarantined, or rejected batch')
    balance=sum(t.quantity if t.kind in ['receipt','adjustment_in','transfer_in'] else -t.quantity for t in db.scalars(select(Transaction).where(Transaction.batch_id==b.id)).all())
    if p.kind=='issue' and (balance<p.quantity or not eligible(b)): raise HTTPException(409,'Insufficient verified usable stock')
    if p.kind=='adjustment_out' and balance<p.quantity: raise HTTPException(409,'Adjustment would make batch balance negative')
    t=Transaction(facility_id=fid,batch_id=b.id,kind=p.kind,quantity=p.quantity,reason=p.reason,actor_id=u.id)
    db.add(t); audit(db,u,p.kind,'inventory_transaction','pending',p.reason); db.commit(); db.refresh(t)
    return {'id':t.id,'kind':t.kind,'quantity':t.quantity,'message':'Inventory ledger updated'}
@app.post('/api/v1/risk/run')
def run_risks(db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    results=[]
    for f in db.scalars(select(Facility)).all():
        if not can_access(u,f): continue
        row=facility_json(db,f); risk=row['risk']; key='stockout'
        existing=db.scalar(select(Alert).where(Alert.facility_id==f.id,Alert.risk_key==key,Alert.status=='active'))
        if risk['severity'] in ['critical','high']:
            inputs={k:risk.get(k) for k in ['usable_stock','coverage_days','projected_stock_at_delivery','expected_delivery_date','data_quality','inventory_freshness','confirmed_incoming']}
            if existing:
                existing.severity=risk['severity']; existing.explanation=risk['explanation']; existing.recommendation=risk['recommended_action']; existing.inputs=json.dumps(inputs)
            else:
                existing=Alert(facility_id=f.id,risk_key=key,severity=risk['severity'],explanation=risk['explanation'],recommendation=risk['recommended_action'],inputs=json.dumps(inputs),status='active'); db.add(existing)
            results.append({'facility':f.code,'severity':risk['severity'],'alert_id':existing.id,'explanation':risk['explanation']})
    audit(db,u,'run_risk_check','system','manual',f'{len(results)} actionable risks')
    db.commit(); return {'evaluated':len(results),'alerts':results}
@app.get('/api/v1/risks')
def risks(db:Session=Depends(get_db),u=Depends(current_user),severity:str|None=None):
    data=[]
    for f in db.scalars(select(Facility)).all():
        if can_access(u,f):
            row=facility_json(db,f)['risk']
            if severity is None or row['severity']==severity: data.append(row)
    rank={'critical':0,'high':1,'medium':2,'low':3}; return sorted(data,key=lambda x:rank[x['severity']])
@app.get('/api/v1/alerts')
def alerts(db:Session=Depends(get_db),u=Depends(current_user)):
    out=[]
    for a in db.scalars(select(Alert).order_by(Alert.created_at.desc())).all():
        f=db.get(Facility,a.facility_id)
        if not can_access(u,f): continue
        label=db.scalar(select(EvaluationLabel).where(EvaluationLabel.alert_id==a.id))
        events=db.scalars(select(AlertEvent).where(AlertEvent.alert_id==a.id)).all()
        out.append({'id':a.id,'facility':f.code,'facility_id':a.facility_id,'severity':a.severity,'explanation':a.explanation,'recommendation':a.recommendation,'status':a.status,'created_at':a.created_at.isoformat() if a.created_at else None,'acknowledged_at':a.acknowledged_at.isoformat() if a.acknowledged_at else None,'escalated':any(e.event_type=='escalated' for e in events),'evaluation_outcome':label.outcome if label else None})
    return out
@app.post('/api/v1/alerts/{aid}/acknowledge')
def acknowledge(aid:int,p:dict|None=None,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    a=db.get(Alert,aid)
    if not a: raise HTTPException(404,'Alert not found')
    assert_access(u,db.get(Facility,a.facility_id)); now=datetime.now(timezone.utc); a.acknowledged_at=a.acknowledged_at or now
    note=(p or {}).get('note','') if p else ''
    if not db.scalar(select(AlertEvent.id).where(AlertEvent.alert_id==aid,AlertEvent.event_type=='acknowledged')): db.add(AlertEvent(alert_id=aid,actor_id=u.id,event_type='acknowledged',note=note))
    audit(db,u,'acknowledge','alert',aid,note); db.commit(); return {'status':a.status,'acknowledged':True,'acknowledged_at':a.acknowledged_at.isoformat()}
class EscalationIn(BaseModel): target_role:str=Field(min_length=3,max_length=40); note:str=Field(min_length=3,max_length=500)
@app.post('/api/v1/alerts/{aid}/escalate')
def escalate_alert(aid:int,p:EscalationIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    a=db.get(Alert,aid)
    if not a: raise HTTPException(404,'Alert not found')
    assert_access(u,db.get(Facility,a.facility_id))
    existing=db.scalar(select(AlertEvent).where(AlertEvent.alert_id==aid,AlertEvent.event_type=='escalated',AlertEvent.target_role==p.target_role))
    if existing: return {'id':existing.id,'status':'escalated','created_at':existing.created_at.isoformat() if existing.created_at else None}
    event=AlertEvent(alert_id=aid,actor_id=u.id,event_type='escalated',target_role=p.target_role,note=p.note); db.add(event); db.flush(); audit(db,u,'escalate','alert',aid,p.note); db.commit(); return {'id':event.id,'status':'escalated','created_at':event.created_at.isoformat() if event.created_at else None}
class LabelIn(BaseModel): outcome:str; evidence:str=Field(min_length=10,max_length=2000); period_start:date; period_end:date
@app.post('/api/v1/alerts/{aid}/evaluation-label')
def label_alert(aid:int,p:LabelIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    a=db.get(Alert,aid)
    if not a: raise HTTPException(404,'Alert not found')
    assert_access(u,db.get(Facility,a.facility_id))
    if p.outcome not in ('true_positive','false_positive') or p.period_end<p.period_start: raise HTTPException(422,'Alerts can be labeled only true-positive or false-positive; the review period must be valid')
    if a.created_at and not p.period_start<=a.created_at.date()<=p.period_end: raise HTTPException(422,'Review period must include the alert detection date')
    if db.scalar(select(EvaluationLabel.id).where(EvaluationLabel.alert_id==aid)): raise HTTPException(409,'This alert already has an independent evaluation label')
    row=EvaluationLabel(alert_id=aid,facility_id=a.facility_id,outcome=p.outcome,risk_key=a.risk_key,evidence=p.evidence,reviewer_id=u.id,period_start=p.period_start,period_end=p.period_end); db.add(row); audit(db,u,'label_evaluation','alert',aid,p.evidence); db.commit(); return {'id':row.id,'outcome':row.outcome,'risk_key':row.risk_key,'reviewer_id':u.id}
class IndependentLabelIn(BaseModel): facility_id:int; outcome:str; risk_key:str=Field(min_length=2,max_length=60); evidence:str=Field(min_length=10,max_length=2000); period_start:date; period_end:date
@app.post('/api/v1/evaluation/labels')
def label_independent_event(p:IndependentLabelIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    f=db.get(Facility,p.facility_id)
    if not f: raise HTTPException(404,'Facility not found')
    assert_access(u,f)
    if p.outcome not in ('true_negative','false_negative') or p.period_end<p.period_start or p.period_end>date.today(): raise HTTPException(422,'Independent no-alert labels require a valid completed review period')
    if p.outcome=='true_negative':
        start=datetime.combine(p.period_start,datetime.min.time(),tzinfo=timezone.utc); end=datetime.combine(p.period_end+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)
        if db.scalar(select(Alert.id).where(Alert.facility_id==f.id,Alert.risk_key==p.risk_key,Alert.created_at>=start,Alert.created_at<end)): raise HTTPException(409,'A detection exists for this facility, risk type, and review period')
    row=EvaluationLabel(alert_id=None,facility_id=f.id,outcome=p.outcome,risk_key=p.risk_key,evidence=p.evidence,reviewer_id=u.id,period_start=p.period_start,period_end=p.period_end); db.add(row); db.flush(); audit(db,u,'label_evaluation_observation','facility',f.id,f'{p.risk_key}: {p.outcome}; {p.evidence}'); db.commit(); return {'id':row.id,'outcome':row.outcome,'risk_key':row.risk_key,'reviewer_id':u.id}
@app.get('/api/v1/inventory/transactions')
def transactions(db:Session=Depends(get_db),u=Depends(current_user),limit:int=Query(100,ge=1,le=500)):
    return [{'id':t.id,'facility':db.get(Facility,t.facility_id).code,'facility_id':t.facility_id,'batch':db.get(Batch,t.batch_id).batch_number,'batch_id':t.batch_id,'kind':t.kind,'quantity':t.quantity,'reason':t.reason,'created_at':t.created_at.isoformat() if t.created_at else None} for t in db.scalars(select(Transaction).order_by(Transaction.created_at.desc()).limit(limit)).all() if can_access(u,db.get(Facility,t.facility_id))]
class ReqIn(BaseModel): facility_id:int; quantity:int=Field(gt=0,le=1000); reason:str=Field(min_length=5,max_length=500); priority:str='routine'; expected_date:date|None=None
@app.get('/api/v1/replenishments')
def requests(db:Session=Depends(get_db),u=Depends(current_user)):
    return [req_json(r,db) for r in db.scalars(select(Replenishment).order_by(Replenishment.created_at.desc())).all() if can_access(u,db.get(Facility,r.facility_id))]
@app.post('/api/v1/replenishments')
def submit_request(p:ReqIn,db:Session=Depends(get_db),u=Depends(require('worker'))):
    f=db.get(Facility,p.facility_id)
    if not f: raise HTTPException(404,'Facility not found')
    if p.expected_date and p.expected_date<date.today(): raise HTTPException(422,'Expected delivery date cannot be in the past')
    if p.priority not in ('routine','high','urgent'): raise HTTPException(422,'Unsupported request priority')
    assert_access(u,f); code=f"VR-{date.today().year}-{int(datetime.now().timestamp())%100000:05d}"
    r=Replenishment(request_code=code,facility_id=f.id,quantity=p.quantity,reason=p.reason,priority=p.priority,status='pending',expected_date=p.expected_date,created_by=u.id)
    db.add(r); db.flush(); audit(db,u,'submit','replenishment',r.id,p.reason); db.commit(); db.refresh(r); return req_json(r,db)
class ActionIn(BaseModel): reason:str|None=None; quantity:int|None=None; batch_id:int|None=None
@app.post('/api/v1/replenishments/{rid}/{action}')
def action_request(rid:int,action:str,p:ActionIn,db:Session=Depends(get_db),u=Depends(current_user)):
    r=db.get(Replenishment,rid)
    if not r: raise HTTPException(404,'Request not found')
    f=db.get(Facility,r.facility_id); assert_access(u,f)
    officer=u.role in ['officer','admin']
    if action in ['receive','verify'] and u.role not in ['worker','officer','admin']: raise HTTPException(403,'Operational role required')
    if action in ['approve','reject','dispatch'] and not officer: raise HTTPException(403,'Officer role required')
    if action in ['approve','reject'] and r.status!='pending': raise HTTPException(409,'Request is no longer pending')
    if action=='approve': r.status='approved'; r.approved_at=datetime.now(timezone.utc)
    elif action=='reject':
        if not p.reason or len(p.reason)<3: raise HTTPException(422,'Rejection reason is required')
        r.status='rejected'; r.notes=p.reason
    elif action=='dispatch':
        if r.status!='approved': raise HTTPException(409,'Only approved requests can be dispatched')
        r.status='dispatched'; r.dispatched_at=datetime.now(timezone.utc)
    elif action=='receive':
        if r.status not in ['dispatched','partially_received']: raise HTTPException(409,'Only dispatched requests can be received')
        qty=p.quantity or 0; b=db.get(Batch,p.batch_id) if p.batch_id else None
        if qty<=0 or qty>r.quantity-r.received: raise HTTPException(422,'Received quantity exceeds outstanding amount')
        if not b or b.facility_id!=f.id or b.storage_status!='usable' or not b.expiry or b.expiry<date.today(): raise HTTPException(422,'Select a suitable batch at destination')
        if r.product_id and b.product_id!=r.product_id: raise HTTPException(422,'Delivery batch does not match the requested product')
        r.received+=qty; r.status='received' if r.received==r.quantity else 'partially_received'
        db.add(Transaction(facility_id=f.id,batch_id=b.id,kind='receipt',quantity=qty,reason=f'Replenishment {r.request_code} delivery',actor_id=u.id));
    elif action=='verify':
        if r.status!='received': raise HTTPException(409,'Request must be fully received before verification')
        b=db.get(Batch,p.batch_id) if p.batch_id else None
        if not b or b.facility_id!=f.id: raise HTTPException(422,'Destination batch is required')
        b.verified=True; f.last_verified=datetime.now(timezone.utc); r.status='verified'; r.notes=(r.notes+'; ' if r.notes else '')+(p.reason or 'Physical stock verified')
    else: raise HTTPException(404,'Unknown action')
    audit(db,u,action,'replenishment',r.id,p.reason or ''); db.commit(); return req_json(r,db)
class PolicyIn(BaseModel): minimum_stock:int=Field(ge=0); maximum_stock:int|None=Field(default=None,ge=1); reorder_point:int|None=Field(default=None,ge=0); safety_stock:int=Field(ge=0); lead_days:int=Field(ge=0,le=365); expiry_warning_days:int=Field(ge=1,le=365)
@app.put('/api/v1/facilities/{fid}/policy')
def facility_policy(fid:int,p:PolicyIn,db:Session=Depends(get_db),u=Depends(require('admin'))):
    f=db.get(Facility,fid)
    if not f: raise HTTPException(404,'Facility not found')
    if p.maximum_stock is not None and (p.maximum_stock<p.minimum_stock or p.maximum_stock<p.safety_stock): raise HTTPException(422,'Maximum stock must cover minimum and safety stock')
    for k,v in p.model_dump().items(): setattr(f,k,v)
    audit(db,u,'update_stock_policy','facility',fid,str(p.model_dump())); db.commit(); return {'facility_id':fid,'policy':p.model_dump()}
class HierarchyIn(BaseModel): parent_id:int|None
@app.put('/api/v1/facilities/{fid}/hierarchy')
def facility_hierarchy(fid:int,p:HierarchyIn,db:Session=Depends(get_db),u=Depends(require('admin'))):
    f=db.get(Facility,fid)
    if not f: raise HTTPException(404,'Facility not found')
    parent=db.get(Facility,p.parent_id) if p.parent_id else None
    if p.parent_id and not parent: raise HTTPException(404,'Parent facility not found')
    if parent and parent.district!=f.district: raise HTTPException(422,'Parent and child must be in the same district')
    cursor=parent; seen={fid}
    while cursor:
        if cursor.id in seen: raise HTTPException(422,'Facility hierarchy cannot contain a cycle')
        seen.add(cursor.id); cursor=db.get(Facility,cursor.parent_id) if cursor.parent_id else None
    f.parent_id=p.parent_id; audit(db,u,'change_hierarchy','facility',fid,f'parent_id={p.parent_id}'); db.commit(); return {'facility_id':fid,'parent_id':f.parent_id}
def reorder_calculation(db,f,pid):
    batches=db.scalars(select(Batch).where(Batch.facility_id==f.id,Batch.product_id==pid)).all()
    usable=sum(max(0,ledger_balance(db,b.id)) for b in batches if eligible(b))
    expected=date.today()+timedelta(days=f.lead_days)
    incoming=sum(max(0,r.quantity-r.received) for r in db.scalars(select(Replenishment).where(Replenishment.facility_id==f.id,Replenishment.status.in_(['approved','dispatched','partially_received']))).all() if r.product_id in (None,pid) and r.expected_date and date.today()<=r.expected_date<=expected)
    summaries=db.scalars(select(ConsumptionSummary).where(ConsumptionSummary.facility_id==f.id)).all(); days=sum(x.period_days for x in summaries); daily=sum(x.quantity for x in summaries)/days if days else 0
    demand=daily*f.lead_days; target=f.maximum_stock if f.maximum_stock is not None else max(f.minimum_stock,f.reorder_point or 0,f.safety_stock)
    uncapped=max(0,math.ceil(target+ demand-usable-incoming)); qty=min(uncapped,max(0,(f.maximum_stock-usable-incoming))) if f.maximum_stock is not None else uncapped
    explanation=f"Target {target} vials − {usable} usable stock − {incoming} confirmed incoming due by {expected.isoformat()} + {demand:g} estimated lead-time demand = {qty} vials recommended."
    flags=[]
    if not days: flags.append('Demand history is unavailable; zero demand was assumed for this draft.')
    if f.maximum_stock is None: flags.append('Maximum stock is not configured; minimum/safety target used.')
    elif qty<uncapped: flags.append('Recommendation capped at the configured maximum stock.')
    pending=db.scalars(select(Replenishment).where(Replenishment.facility_id==f.id,Replenishment.status.in_(['approved','dispatched','partially_received']))).all()
    if any(r.product_id in (None,pid) and (not r.expected_date or r.expected_date<date.today()) for r in pending): flags.append('Undated or overdue incoming quantities were excluded.')
    unresolved=db.scalar(select(func.count(Discrepancy.id)).join(Batch,Discrepancy.batch_id==Batch.id).where(Batch.facility_id==f.id,Discrepancy.status=='open')) or 0
    fresh=bool(f.last_verified and (datetime.now(timezone.utc)-f.last_verified.replace(tzinfo=timezone.utc)).days<=30 and not unresolved)
    freshness='current' if fresh else 'needs_reconciliation' if unresolved else 'stale' if f.last_verified else 'unverified'
    if not fresh: flags.append(f'Inventory confidence is low: verification is {freshness}.')
    return {'facility_id':f.id,'facility':f.code,'product_id':pid,'product':db.get(Product,pid).name,'usable_stock':usable,'confirmed_incoming':incoming,'estimated_daily_demand':daily,'estimated_lead_demand':demand,'expected_date':expected.isoformat(),'target_stock':target,'recommended_quantity':qty,'explanation':explanation,'inventory_freshness':freshness,'data_flags':flags}
@app.get('/api/v1/reorder/recommendations')
def reorder_recommendations(db:Session=Depends(get_db),u=Depends(current_user)):
    out=[]
    products=db.scalars(select(Product).where(Product.active==True)).all()
    for f in db.scalars(select(Facility)).all():
        if can_access(u,f): out.extend([reorder_calculation(db,f,p.id) for p in products])
    return out
class DraftIn(BaseModel): facility_id:int; product_id:int
@app.post('/api/v1/reorder/drafts')
def create_reorder_draft(p:DraftIn,db:Session=Depends(get_db),u=Depends(require('worker'))):
    f=db.get(Facility,p.facility_id); product=db.get(Product,p.product_id)
    if not f or not product: raise HTTPException(404,'Facility or product not found')
    assert_access(u,f); calc=reorder_calculation(db,f,p.product_id)
    row=ReorderDraft(facility_id=f.id,product_id=product.id,usable_stock=calc['usable_stock'],confirmed_incoming=calc['confirmed_incoming'],estimated_demand=calc['estimated_lead_demand'],recommended_quantity=calc['recommended_quantity'],expected_date=date.fromisoformat(calc['expected_date']),explanation=calc['explanation'],created_by=u.id)
    db.add(row); db.flush(); audit(db,u,'create_reorder_draft','reorder_draft',row.id,row.explanation); db.commit(); return {'id':row.id,**calc,'status':row.status}
@app.post('/api/v1/reorder/drafts/{draft_id}/submit')
def submit_reorder_draft(draft_id:int,db:Session=Depends(get_db),u=Depends(require('worker'))):
    row=db.get(ReorderDraft,draft_id)
    if not row: raise HTTPException(404,'Draft not found')
    f=db.get(Facility,row.facility_id); assert_access(u,f)
    if row.status!='draft': raise HTTPException(409,'Draft already submitted')
    if row.recommended_quantity<=0: raise HTTPException(409,'No replenishment quantity is recommended by this draft')
    row.status='submitted'; r=Replenishment(request_code=f"VI-{datetime.now().strftime('%y%m%d%H%M%S')}-{row.id}",facility_id=f.id,product_id=row.product_id,quantity=max(1,row.recommended_quantity),received=0,reason=row.explanation,priority='high' if row.recommended_quantity>f.minimum_stock else 'routine',status='pending',expected_date=row.expected_date,created_by=u.id); db.add(r); audit(db,u,'submit_indent','reorder_draft',row.id,r.reason); db.commit(); return req_json(r,db)
@app.get('/api/v1/transfers/suggestions')
def transfers(db:Session=Depends(get_db),u=Depends(current_user)):
    facilities=[f for f in db.scalars(select(Facility)).all() if can_access(u,f) and f.latitude is not None and f.longitude is not None]
    out=[]
    for dest in facilities:
        d=facility_json(db,dest)['risk']
        if d['severity'] not in ['critical','high']: continue
        for src in facilities:
            if src.id==dest.id: continue
            s=facility_json(db,src)
            if not src.last_verified or (datetime.now(timezone.utc)-src.last_verified.replace(tzinfo=timezone.utc)).days>30: continue
            pending=db.scalars(select(Transfer).where(Transfer.source_facility_id==src.id,Transfer.status.in_(['proposed','verified','approved']))).all()
            reserved=sum(t.quantity for t in pending)
            if db.scalar(select(func.count(Discrepancy.id)).join(Batch,Discrepancy.batch_id==Batch.id).where(Batch.facility_id==src.id,Discrepancy.status=='open')): continue
            available=max(0,s['usable_stock']-src.safety_stock-reserved)
            if available<=0: continue
            lat1,lon1,lat2,lon2=map(math.radians,[dest.latitude,dest.longitude,src.latitude,src.longitude]); a=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2; distance=6371*2*math.atan2(math.sqrt(a),math.sqrt(1-a))
            out.append({'source':src.code,'source_name':src.name,'destination':dest.code,'destination_name':dest.name,'distance_km':round(distance,1),'reported_usable_stock':s['usable_stock'],'potential_quantity':min(available,max(1,src.safety_stock)),'last_verified':src.last_verified.isoformat(),'status':'requires officer approval and stock verification','approval_status':'suggestion only'})
    return sorted(out,key=lambda x:x['distance_km'])
class TransferIn(BaseModel): source_facility_id:int; destination_facility_id:int; batch_id:int; quantity:int=Field(gt=0); note:str=Field(min_length=3,max_length=300)
def transfer_json(t,db):
    src=db.get(Facility,t.source_facility_id); dst=db.get(Facility,t.destination_facility_id); b=db.get(Batch,t.batch_id)
    return {'id':t.id,'code':t.transfer_code,'source_facility_id':t.source_facility_id,'source':src.code,'destination_facility_id':t.destination_facility_id,'destination':dst.code,'batch_id':t.batch_id,'batch_number':b.batch_number,'quantity':t.quantity,'received_quantity':t.received_quantity,'outstanding':max(0,t.quantity-t.received_quantity),'status':t.status,'verified_by':t.verified_by,'verified_at':t.verified_at.isoformat() if t.verified_at else None,'source_approved':bool(t.source_approved_by),'source_approved_by':t.source_approved_by,'destination_approved':bool(t.destination_approved_by),'destination_approved_by':t.destination_approved_by,'storage_suitable':t.storage_suitable,'transport_suitable':t.transport_suitable}
@app.get('/api/v1/transfers')
def transfer_list(db:Session=Depends(get_db),u=Depends(current_user)):
    return [transfer_json(t,db) for t in db.scalars(select(Transfer).order_by(Transfer.id.desc())).all() if can_access(u,db.get(Facility,t.source_facility_id)) or can_access(u,db.get(Facility,t.destination_facility_id))]
@app.post('/api/v1/transfers')
def propose_transfer(p:TransferIn,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    src=db.get(Facility,p.source_facility_id); dst=db.get(Facility,p.destination_facility_id); b=db.get(Batch,p.batch_id)
    if not src or not dst or not b or b.facility_id!=p.source_facility_id: raise HTTPException(404,'Source, destination, or batch not found')
    assert_access(u,src); assert_access(u,dst)
    if src.id==dst.id: raise HTTPException(422,'Source and destination must differ')
    # Lock the facility and batch while reserving to serialize competing proposals.
    src=db.scalar(select(Facility).where(Facility.id==src.id).with_for_update())
    b=db.scalar(select(Batch).where(Batch.id==b.id).with_for_update())
    if not src.last_verified or (datetime.now(timezone.utc)-src.last_verified.replace(tzinfo=timezone.utc)).days>30: raise HTTPException(409,'Source requires a recent physical verification')
    if db.scalar(select(func.count(Discrepancy.id)).join(Batch,Discrepancy.batch_id==Batch.id).where(Batch.facility_id==src.id,Discrepancy.status=='open')): raise HTTPException(409,'Open stock discrepancies require resolution before a transfer proposal')
    if not eligible(b): raise HTTPException(409,'Transfer source batch is not verified, in date, and usable')
    pending=db.scalars(select(Transfer).where(Transfer.source_facility_id==src.id,Transfer.status.in_(['proposed','verified','approved']))).all()
    reserved_batch=sum(t.quantity for t in pending if t.batch_id==b.id); reserved_facility=sum(t.quantity for t in pending)
    available=min(max(0,ledger_balance(db,b.id)-reserved_batch),max(0,facility_json(db,src)['usable_stock']-src.safety_stock-reserved_facility))
    if p.quantity>available: raise HTTPException(409,'Quantity exceeds verified transferable stock after safety stock and reservations')
    code=f"VT-{datetime.now().strftime('%y%m%d%H%M%S')}-{(b.id%1000):03d}"
    t=Transfer(transfer_code=code,source_facility_id=src.id,destination_facility_id=dst.id,batch_id=b.id,quantity=p.quantity,status='proposed')
    db.add(t); db.flush(); audit(db,u,'propose_transfer','transfer',t.id,p.note); db.commit(); return transfer_json(t,db)
class VerifyTransferIn(BaseModel): counted_quantity:int=Field(ge=0); storage_suitable:bool; transport_suitable:bool; note:str=Field(min_length=3,max_length=500)
@app.post('/api/v1/transfers/{tid}/verify')
def verify_transfer(tid:int,p:VerifyTransferIn,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    t=db.scalar(select(Transfer).where(Transfer.id==tid).with_for_update())
    if not t: raise HTTPException(404,'Transfer not found')
    src=db.get(Facility,t.source_facility_id); assert_access(u,src)
    if t.status!='proposed': raise HTTPException(409,'Transfer is not awaiting verification')
    src=db.scalar(select(Facility).where(Facility.id==src.id).with_for_update())
    b=db.scalar(select(Batch).where(Batch.id==t.batch_id).with_for_update())
    if p.counted_quantity!=ledger_balance(db,b.id) or not eligible(b): raise HTTPException(409,'Physical count does not match an eligible source batch')
    pending=db.scalars(select(Transfer).where(Transfer.source_facility_id==src.id,Transfer.status.in_(['proposed','verified','approved']))).all()
    reserved_batch=sum(x.quantity for x in pending if x.batch_id==b.id); reserved_facility=sum(x.quantity for x in pending)
    if ledger_balance(db,b.id)-reserved_batch<0 or facility_json(db,src)['usable_stock']-src.safety_stock<reserved_facility: raise HTTPException(409,'Other reservations have used the transferable balance')
    if db.scalar(select(func.count(Discrepancy.id)).join(Batch,Discrepancy.batch_id==Batch.id).where(Batch.facility_id==src.id,Discrepancy.status=='open')): raise HTTPException(409,'Open stock discrepancies require resolution before transfer verification')
    if not src.last_verified or (datetime.now(timezone.utc)-src.last_verified.replace(tzinfo=timezone.utc)).days>30: raise HTTPException(409,'Source verification is stale')
    t.verified_by=u.id; t.verified_at=datetime.now(timezone.utc); t.storage_suitable=p.storage_suitable; t.transport_suitable=p.transport_suitable; t.status='verified'; audit(db,u,'verify_transfer_source','transfer',tid,p.note); db.commit(); return transfer_json(t,db)
class TransferApprovalIn(BaseModel): side:str; approved:bool; storage_suitable:bool=False; transport_suitable:bool=False; note:str=Field(min_length=3,max_length=500)
@app.post('/api/v1/transfers/{tid}/authorize')
def authorize_transfer(tid:int,p:TransferApprovalIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    t=db.scalar(select(Transfer).where(Transfer.id==tid).with_for_update())
    if not t: raise HTTPException(404,'Transfer not found')
    if t.status not in ('verified','approved'): raise HTTPException(409,'Physical source verification is required first')
    if not t.verified_at or (datetime.now(timezone.utc)-t.verified_at.replace(tzinfo=timezone.utc)).days>30: raise HTTPException(409,'Source physical verification is stale; recount before approval')
    if p.side not in ('source','destination'): raise HTTPException(422,'Side must be source or destination')
    facility=db.get(Facility,t.source_facility_id if p.side=='source' else t.destination_facility_id); assert_access(u,facility)
    if not p.approved: t.status='rejected'; audit(db,u,'reject_transfer','transfer',tid,p.note); db.commit(); return transfer_json(t,db)
    if not p.storage_suitable or not p.transport_suitable or not t.storage_suitable or not t.transport_suitable: raise HTTPException(422,'Suitable storage and transport must be confirmed by verifier and approver')
    if p.side=='source':
        if t.destination_approved_by==u.id: raise HTTPException(409,'A separate authorized officer must approve the source side')
        t.source_approved_by=u.id
    else:
        if t.source_approved_by==u.id: raise HTTPException(409,'A separate authorized officer must approve the destination side')
        t.destination_approved_by=u.id
    if t.source_approved_by and t.destination_approved_by: t.status='approved'
    audit(db,u,'approve_transfer_'+p.side,'transfer',tid,p.note); db.commit(); return transfer_json(t,db)
@app.post('/api/v1/transfers/{tid}/dispatch')
def dispatch_transfer(tid:int,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    t=db.scalar(select(Transfer).where(Transfer.id==tid).with_for_update())
    if not t: raise HTTPException(404,'Transfer not found')
    src=db.get(Facility,t.source_facility_id); assert_access(u,src)
    if t.status!='approved' or not t.verified_at or not t.source_approved_by or not t.destination_approved_by: raise HTTPException(409,'Both facility approvals and physical verification are required')
    if (datetime.now(timezone.utc)-t.verified_at.replace(tzinfo=timezone.utc)).days>30: raise HTTPException(409,'Source physical verification is stale; recount and reapprove before dispatch')
    src=db.scalar(select(Facility).where(Facility.id==src.id).with_for_update())
    b=db.scalar(select(Batch).where(Batch.id==t.batch_id).with_for_update())
    reserved=db.scalars(select(Transfer).where(Transfer.source_facility_id==src.id,Transfer.status.in_(['proposed','verified','approved']))).all()
    reserved_batch=sum(x.quantity for x in reserved if x.batch_id==b.id); reserved_facility=sum(x.quantity for x in reserved)
    has_discrepancy=db.scalar(select(func.count(Discrepancy.id)).join(Batch,Discrepancy.batch_id==Batch.id).where(Batch.facility_id==src.id,Discrepancy.status=='open'))
    if not eligible(b) or ledger_balance(db,b.id)-reserved_batch<0 or facility_json(db,src)['usable_stock']-src.safety_stock<reserved_facility or has_discrepancy: raise HTTPException(409,'Transferable stock changed or has unresolved discrepancies; verification and approval must be repeated')
    t.status='dispatched'; t.dispatched_at=datetime.now(timezone.utc); db.add(Transaction(facility_id=src.id,batch_id=b.id,kind='transfer_out',quantity=t.quantity,reason=f'Transfer {t.transfer_code} dispatched',actor_id=u.id,transfer_id=t.id)); audit(db,u,'dispatch_transfer','transfer',tid,t.transfer_code); db.commit(); return transfer_json(t,db)
class ReceiveTransferIn(BaseModel): quantity:int=Field(gt=0); note:str=Field(min_length=3,max_length=500)
@app.post('/api/v1/transfers/{tid}/receive')
def receive_transfer(tid:int,p:ReceiveTransferIn,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    t=db.scalar(select(Transfer).where(Transfer.id==tid).with_for_update())
    if not t: raise HTTPException(404,'Transfer not found')
    dst=db.get(Facility,t.destination_facility_id); assert_access(u,dst)
    if t.status not in ('dispatched','partially_received') or p.quantity>t.quantity-t.received_quantity: raise HTTPException(409,'Quantity exceeds dispatched outstanding amount')
    source=db.get(Batch,t.batch_id)
    dest_batch=db.scalar(select(Batch).where(Batch.facility_id==dst.id,Batch.batch_number==source.batch_number))
    if not dest_batch:
        dest_batch=Batch(facility_id=dst.id,batch_number=source.batch_number,product=source.product,product_id=source.product_id,expiry=source.expiry,storage_status='usable',verified=True,quality_status='verified'); db.add(dest_batch); db.flush()
    elif dest_batch.expiry!=source.expiry or dest_batch.product_id!=source.product_id: raise HTTPException(409,'Destination batch identifier conflicts with product or expiry')
    t.received_quantity+=p.quantity; now=datetime.now(timezone.utc); t.received_at=now
    db.add(Transaction(facility_id=dst.id,batch_id=dest_batch.id,kind='transfer_in',quantity=p.quantity,reason=f'Transfer {t.transfer_code} received',actor_id=u.id,transfer_id=t.id))
    if t.received_quantity==t.quantity: t.status='received'; dst.last_verified=now
    else: t.status='partially_received'
    audit(db,u,'receive_transfer','transfer',tid,p.note); db.commit(); return transfer_json(t,db)
class TransferReconcileIn(BaseModel): resolution:str=Field(min_length=5,max_length=500)
@app.post('/api/v1/transfers/{tid}/reconcile')
def reconcile_transfer(tid:int,p:TransferReconcileIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    t=db.get(Transfer,tid)
    if not t: raise HTTPException(404,'Transfer not found')
    assert_access(u,db.get(Facility,t.destination_facility_id))
    if t.status!='partially_received': raise HTTPException(409,'Only partial deliveries require reconciliation')
    t.status='reconciled_partial'; audit(db,u,'reconcile_partial_transfer','transfer',tid,p.resolution); db.commit(); return transfer_json(t,db)
class ObservationIn(BaseModel): facility_id:int; observed_date:date; usable_quantity:int=Field(ge=0); evidence:str=Field(min_length=10,max_length=1000)
@app.post('/api/v1/evaluation/observations')
def record_observation(p:ObservationIn,db:Session=Depends(get_db),u=Depends(require('officer','admin'))):
    f=db.get(Facility,p.facility_id)
    if not f: raise HTTPException(404,'Facility not found')
    assert_access(u,f)
    if p.observed_date>date.today(): raise HTTPException(422,'Observation date cannot be in the future')
    if db.scalar(select(DailyObservation.id).where(DailyObservation.facility_id==f.id,DailyObservation.observed_date==p.observed_date)): raise HTTPException(409,'A verified observation already exists for this facility and date')
    row=DailyObservation(facility_id=f.id,observed_date=p.observed_date,usable_quantity=p.usable_quantity,observed_by=u.id,evidence=p.evidence); db.add(row); audit(db,u,'record_stock_observation','facility',f.id,f'{p.observed_date}: {p.usable_quantity} usable units'); db.commit(); return {'id':row.id,'facility_id':f.id,'observed_date':p.observed_date.isoformat(),'usable_quantity':p.usable_quantity}
@app.get('/api/v1/reports/stock.csv')
def stock_csv(db:Session=Depends(get_db),u=Depends(current_user)):
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(['synthetic','facility_code','facility_name','district','usable_stock','reported_stock','risk','days_coverage','last_verified'])
    for f in db.scalars(select(Facility)).all():
        if can_access(u,f):
            row=facility_json(db,f); r=row['risk']; w.writerow(['YES',f.code,f.name,f.district,row['usable_stock'],row['reported_stock'],r['severity'],r['coverage_days'],row['last_verified'] or 'unverified'])
    return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=venotrack-stock-report.csv'})
@app.get('/api/v1/evaluation')
def evaluation(db:Session=Depends(get_db),u=Depends(current_user)):
    fs=[f for f in db.scalars(select(Facility)).all() if can_access(u,f)]; reqs=[r for r in db.scalars(select(Replenishment)).all() if can_access(u,db.get(Facility,r.facility_id))]
    alerts=db.scalars(select(Alert)).all(); alerts=[a for a in alerts if can_access(u,db.get(Facility,a.facility_id))]
    labels=[x for x in db.scalars(select(EvaluationLabel)).all() if can_access(u,db.get(Facility,x.facility_id))]
    counts={k:sum(1 for x in labels if x.outcome==k) for k in ('true_positive','false_positive','true_negative','false_negative')}
    def metric(num,den,name): return {'value':round(num/den,4) if den else None,'undefined_reason':None if den else f'{name} denominator is zero for the verified sample'}
    precision=metric(counts['true_positive'],counts['true_positive']+counts['false_positive'],'Precision')
    recall=metric(counts['true_positive'],counts['true_positive']+counts['false_negative'],'Recall')
    specificity=metric(counts['true_negative'],counts['true_negative']+counts['false_positive'],'Specificity')
    far=metric(counts['false_positive'],counts['false_positive']+counts['true_negative'],'False-alert rate')
    f1den=2*counts['true_positive']+counts['false_positive']+counts['false_negative']; f1={'value':round(2*counts['true_positive']/f1den,4) if f1den else None,'undefined_reason':None if f1den else 'F1 denominator is zero for the verified sample'}
    allowed={f.id for f in fs}; observations=[o for o in db.scalars(select(DailyObservation)).all() if o.facility_id in allowed]
    usable_days=sum(o.usable_quantity>0 for o in observations); stockout_days=sum(o.usable_quantity==0 for o in observations)
    ack_minutes=[]; escalation_minutes=[]
    for a in alerts:
        for e in db.scalars(select(AlertEvent).where(AlertEvent.alert_id==a.id)).all():
            start=a.created_at.replace(tzinfo=timezone.utc) if a.created_at and a.created_at.tzinfo is None else a.created_at
            end=e.created_at.replace(tzinfo=timezone.utc) if e.created_at and e.created_at.tzinfo is None else e.created_at
            if start and end and e.event_type=='acknowledged': ack_minutes.append(max(0,(end-start).total_seconds()/60))
            if start and end and e.event_type=='escalated': escalation_minutes.append(max(0,(end-start).total_seconds()/60))
    response={'detection_to_acknowledgement_minutes':{'average':round(sum(ack_minutes)/len(ack_minutes),2) if ack_minutes else None,'sample_size':len(ack_minutes),'undefined_reason':None if ack_minutes else 'No alert acknowledgement events'},'detection_to_escalation_minutes':{'average':round(sum(escalation_minutes)/len(escalation_minutes),2) if escalation_minutes else None,'sample_size':len(escalation_minutes),'undefined_reason':None if escalation_minutes else 'No escalation events'}}
    fulfil=sum(r.received for r in reqs)/sum(r.quantity for r in reqs) if reqs and sum(r.quantity for r in reqs)>0 else None
    return {'synthetic':True,'labelled_alerts':len(labels),'sample_size':len(labels),'confusion_counts':counts,'detection_metrics':{'precision':precision,'recall':recall,'f1':f1,'specificity':specificity,'false_alert_rate':far,'note':'Only independently reviewed evidence labels count. Acknowledgement is not a correctness label.'},'response_time':response,'service':{'facilities':len(fs),'observation_sample_size':len(observations),'facility_days_with_usable_stock':usable_days,'stockout_days':stockout_days,'availability':{'value':round(usable_days/len(observations),4) if observations else None,'undefined_reason':None if observations else 'No verified daily stock observations'},'fulfilment_rate':round(fulfil,3) if fulfil is not None else None,'active_high_risks':sum(facility_json(db,f)['risk']['severity'] in ['critical','high'] for f in fs),'unresolved_high_risk_incidents':'Not tracked in this release'},'method':'Metrics use persisted synthetic demo observations and independently reviewed evidence labels only. Missing samples and zero denominators remain undefined.'}
@app.get('/api/v1/audit')
def audit_records(db:Session=Depends(get_db),u=Depends(current_user)):
    return [{'id':a.id,'actor':db.get(User,a.actor_id).name,'action':a.action,'entity_type':a.entity_type,'entity_id':a.entity_id,'details':a.details,'created_at':a.created_at.isoformat() if a.created_at else None} for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all() if u.role in ['admin','auditor'] or a.actor_id==u.id]
