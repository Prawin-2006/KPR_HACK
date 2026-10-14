from datetime import date, datetime, timedelta, timezone
from contextlib import asynccontextmanager
import json, math, csv, io
from fastapi import FastAPI, Depends, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .models import init_db, Facility, Batch, Transaction, Alert, Replenishment, Audit, User, ConsumptionSummary
from .security import get_db, current_user, issue_token, verify_password, require, can_access
from .risk import forecast_risk

@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield

app=FastAPI(title='VenoTrack API',version='1.0.0',description='Synthetic anti-venom logistics decision support demo. Not clinical guidance.',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def facility_json(db, f):
    batches=db.scalars(select(Batch).where(Batch.facility_id==f.id)).all()
    txs=db.scalars(select(Transaction).where(Transaction.facility_id==f.id)).all()
    quantities={b.id:0 for b in batches}
    for t in txs: quantities[t.batch_id]=quantities.get(t.batch_id,0)+(t.quantity if t.kind in ('receipt','adjustment_in','transfer_in') else -t.quantity)
    total=0; expiring=0; all_qty=0
    for b in batches:
        qty=max(0,quantities[b.id]); all_qty+=qty
        if b.expiry and b.expiry>=date.today() and b.storage_status=='usable' and b.verified: total+=qty
        if b.expiry and date.today()<=b.expiry<=date.today()+timedelta(days=60): expiring+=qty
    summaries=db.scalars(select(ConsumptionSummary).where(ConsumptionSummary.facility_id==f.id)).all()
    period_days=sum(s.period_days for s in summaries)
    consumption=sum(s.quantity for s in summaries)/period_days if period_days>0 else None
    risk=forecast_risk(total,consumption,f.lead_days,0,f.minimum_stock,f.safety_stock,period_days)
    risk['average_daily_consumption']=consumption; risk['facility_id']=f.id; risk['facility_code']=f.code; risk['facility_name']=f.name; risk['usable_stock']=total; risk['total_reported_stock']=all_qty; risk['expiring_60_days']=expiring; risk['last_verified']=f.last_verified.isoformat() if f.last_verified else None
    return {'id':f.id,'code':f.code,'name':f.name,'kind':f.kind,'district':f.district,'phone':f.phone,'latitude':f.latitude,'longitude':f.longitude,'usable_stock':total,'reported_stock':all_qty,'risk':risk,'last_verified':risk['last_verified'],'lead_days':f.lead_days,'expiry_60_days':expiring,'batches':[{'id':b.id,'batch_number':b.batch_number,'expiry':b.expiry.isoformat() if b.expiry else None,'storage_status':b.storage_status,'verified':b.verified,'quantity':max(0,quantities[b.id]),'usable_quantity':max(0,quantities[b.id]) if b.expiry and b.expiry>=date.today() and b.storage_status=='usable' and b.verified else 0} for b in batches]}

def assert_access(user, f):
    if not can_access(user,f): raise HTTPException(403,'Facility access denied')
def audit(db,user,action,entity,eid,details=''):
    db.add(Audit(actor_id=user.id,action=action,entity_type=entity,entity_id=str(eid),details=details))

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
        if point: point['issues' if t.kind=='issue' else 'receipts']+=t.quantity
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
class TxIn(BaseModel): batch_id:int; kind:str; quantity:int=Field(gt=0); reason:str=Field(min_length=3,max_length=200); idempotency_key:str|None=None
@app.post('/api/v1/facilities/{fid}/transactions')
def create_tx(fid:int,p:TxIn,db:Session=Depends(get_db),u=Depends(current_user)):
    if u.role not in ['worker','officer','admin']: raise HTTPException(403,'Read-only role')
    f=db.get(Facility,fid); b=db.get(Batch,p.batch_id)
    if not f or not b or b.facility_id!=fid: raise HTTPException(404,'Facility or batch not found')
    assert_access(u,f)
    if p.kind not in ['receipt','issue','adjustment_in','adjustment_out']: raise HTTPException(422,'Unsupported transaction type')
    balance=sum(t.quantity if t.kind in ['receipt','adjustment_in','transfer_in'] else -t.quantity for t in db.scalars(select(Transaction).where(Transaction.batch_id==b.id)).all())
    if p.kind in ['issue','adjustment_out'] and (balance<p.quantity or b.storage_status!='usable' or not b.verified or not b.expiry or b.expiry<date.today()): raise HTTPException(409,'Insufficient verified usable stock')
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
            inputs={k:risk.get(k) for k in ['usable_stock','coverage_days','projected_stock_at_delivery','expected_delivery_date','data_quality']}
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
    return [{'id':a.id,'facility':db.get(Facility,a.facility_id).code,'facility_id':a.facility_id,'severity':a.severity,'explanation':a.explanation,'recommendation':a.recommendation,'status':a.status,'created_at':a.created_at.isoformat() if a.created_at else None} for a in db.scalars(select(Alert).order_by(Alert.created_at.desc())).all() if can_access(u,db.get(Facility,a.facility_id))]
@app.post('/api/v1/alerts/{aid}/acknowledge')
def acknowledge(aid:int,db:Session=Depends(get_db),u=Depends(current_user)):
    a=db.get(Alert,aid)
    if not a: raise HTTPException(404,'Alert not found')
    assert_access(u,db.get(Facility,a.facility_id)); a.acknowledged_at=datetime.now(timezone.utc); audit(db,u,'acknowledge','alert',aid); db.commit(); return {'status':a.status,'acknowledged':True}
@app.get('/api/v1/inventory/transactions')
def transactions(db:Session=Depends(get_db),u=Depends(current_user),limit:int=Query(100,ge=1,le=500)):
    return [{'id':t.id,'facility':db.get(Facility,t.facility_id).code,'facility_id':t.facility_id,'batch':db.get(Batch,t.batch_id).batch_number,'batch_id':t.batch_id,'kind':t.kind,'quantity':t.quantity,'reason':t.reason,'created_at':t.created_at.isoformat() if t.created_at else None} for t in db.scalars(select(Transaction).order_by(Transaction.created_at.desc()).limit(limit)).all() if can_access(u,db.get(Facility,t.facility_id))]
class ReqIn(BaseModel): facility_id:int; quantity:int=Field(gt=0,le=1000); reason:str=Field(min_length=5,max_length=500); priority:str='routine'; expected_date:date|None=None
@app.get('/api/v1/replenishments')
def requests(db:Session=Depends(get_db),u=Depends(current_user)):
    return [req_json(r,db) for r in db.scalars(select(Replenishment).order_by(Replenishment.created_at.desc())).all() if can_access(u,db.get(Facility,r.facility_id))]
@app.post('/api/v1/replenishments')
def submit_request(p:ReqIn,db:Session=Depends(get_db),u=Depends(require('worker','officer','admin'))):
    f=db.get(Facility,p.facility_id)
    if not f: raise HTTPException(404,'Facility not found')
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
        r.received+=qty; r.status='received' if r.received==r.quantity else 'partially_received'
        db.add(Transaction(facility_id=f.id,batch_id=b.id,kind='receipt',quantity=qty,reason=f'Replenishment {r.request_code} delivery',actor_id=u.id));
    elif action=='verify':
        if r.status!='received': raise HTTPException(409,'Request must be fully received before verification')
        b=db.get(Batch,p.batch_id) if p.batch_id else None
        if not b or b.facility_id!=f.id: raise HTTPException(422,'Destination batch is required')
        b.verified=True; f.last_verified=datetime.now(timezone.utc); r.status='verified'; r.notes=(r.notes+'; ' if r.notes else '')+(p.reason or 'Physical stock verified')
    else: raise HTTPException(404,'Unknown action')
    audit(db,u,action,'replenishment',r.id,p.reason or ''); db.commit(); return req_json(r,db)
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
            available=max(0,s['usable_stock']-src.safety_stock)
            if available<=0: continue
            lat1,lon1,lat2,lon2=map(math.radians,[dest.latitude,dest.longitude,src.latitude,src.longitude]); a=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2; distance=6371*2*math.atan2(math.sqrt(a),math.sqrt(1-a))
            out.append({'source':src.code,'source_name':src.name,'destination':dest.code,'destination_name':dest.name,'distance_km':round(distance,1),'reported_usable_stock':s['usable_stock'],'potential_quantity':min(available,max(1,src.safety_stock)),'last_verified':src.last_verified.isoformat(),'status':'requires officer approval and stock verification','approval_status':'suggestion only'})
    return sorted(out,key=lambda x:x['distance_km'])
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
    verified_alerts=[a for a in alerts if a.status in ['verified_true','verified_false']]
    return {'synthetic':True,'labelled_alerts':len(verified_alerts),'sample_size':len(verified_alerts),'detection_metrics':{'precision':None,'recall':None,'f1':None,'specificity':None,'false_alert_rate':None,'note':'No independently verified evaluation labels are seeded; metrics are not calculable. Acknowledgement is not a correctness label.'},'service':{'facilities':len(fs),'facility_days_with_usable_stock':'Not measured: no daily observation series','fulfilment_rate':round(sum(r.received for r in reqs)/sum(r.quantity for r in reqs),3) if reqs and sum(r.quantity for r in reqs)>0 else None,'active_high_risks':sum(facility_json(db,f)['risk']['severity'] in ['critical','high'] for f in fs),'unresolved_high_risk_incidents':'Not tracked in MVP'},'method':'Metrics are computed from persisted synthetic demo records only. Undefined metrics require independently verified labels.'}
@app.get('/api/v1/audit')
def audit_records(db:Session=Depends(get_db),u=Depends(current_user)):
    return [{'id':a.id,'actor':db.get(User,a.actor_id).name,'action':a.action,'entity_type':a.entity_type,'entity_id':a.entity_id,'details':a.details,'created_at':a.created_at.isoformat() if a.created_at else None} for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all() if u.role in ['admin','auditor'] or a.actor_id==u.id]
