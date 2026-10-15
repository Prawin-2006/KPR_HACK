from datetime import date, timedelta, datetime
from pathlib import Path
import os
from sqlalchemy import create_engine, String, Integer, Float, Date, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.sql import func

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100))
    email: Mapped[str]=mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(40), index=True)
    district: Mapped[str|None]=mapped_column(String(100), nullable=True)
    facility_id: Mapped[int|None]=mapped_column(ForeignKey('facilities.id'), nullable=True)
    active: Mapped[bool]=mapped_column(Boolean, default=True)
class Facility(Base):
    __tablename__='facilities'
    id: Mapped[int]=mapped_column(primary_key=True)
    code: Mapped[str]=mapped_column(String(24), unique=True, index=True)
    name: Mapped[str]=mapped_column(String(160))
    kind: Mapped[str]=mapped_column(String(50))
    district: Mapped[str]=mapped_column(String(100), index=True)
    latitude: Mapped[float|None]=mapped_column(Float, nullable=True)
    longitude: Mapped[float|None]=mapped_column(Float, nullable=True)
    phone: Mapped[str]=mapped_column(String(40), default='')
    lead_days: Mapped[int]=mapped_column(Integer, default=5)
    minimum_stock: Mapped[int]=mapped_column(Integer, default=10)
    safety_stock: Mapped[int]=mapped_column(Integer, default=8)
    last_verified: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    parent_id: Mapped[int|None]=mapped_column(ForeignKey('facilities.id'), nullable=True, index=True)
    maximum_stock: Mapped[int|None]=mapped_column(Integer, nullable=True)
    reorder_point: Mapped[int|None]=mapped_column(Integer, nullable=True)
    expiry_warning_days: Mapped[int]=mapped_column(Integer, default=60)
class Product(Base):
    __tablename__='products'
    id: Mapped[int]=mapped_column(primary_key=True)
    identifier: Mapped[str]=mapped_column(String(80), unique=True, index=True)
    name: Mapped[str]=mapped_column(String(160))
    category: Mapped[str]=mapped_column(String(100), default='Anti-snake venom')
    unit: Mapped[str]=mapped_column(String(40), default='vial')
    active: Mapped[bool]=mapped_column(Boolean, default=True)
class Batch(Base):
    __tablename__='batches'
    __table_args__=(UniqueConstraint('facility_id','batch_number',name='uq_fac_batch'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    batch_number: Mapped[str]=mapped_column(String(80))
    product: Mapped[str]=mapped_column(String(120), default='Polyvalent Anti-Snake Venom')
    expiry: Mapped[date|None]=mapped_column(Date, nullable=True)
    storage_status: Mapped[str]=mapped_column(String(30), default='usable')
    verified: Mapped[bool]=mapped_column(Boolean, default=False)
    product_id: Mapped[int|None]=mapped_column(ForeignKey('products.id'), nullable=True, index=True)
    quality_status: Mapped[str]=mapped_column(String(30), default='awaiting_quality')
    version: Mapped[int]=mapped_column(Integer, default=1)
class Transaction(Base):
    __tablename__='inventory_transactions'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    batch_id: Mapped[int]=mapped_column(ForeignKey('batches.id'), index=True)
    kind: Mapped[str]=mapped_column(String(30))
    quantity: Mapped[int]=mapped_column(Integer)
    reason: Mapped[str]=mapped_column(String(200))
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    transfer_id: Mapped[int|None]=mapped_column(ForeignKey('stock_transfers.id'), nullable=True, index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
class ConsumptionSummary(Base):
    __tablename__='consumption_summaries'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    product_id: Mapped[int|None]=mapped_column(ForeignKey('products.id'), nullable=True, index=True)
    quantity: Mapped[float]=mapped_column(Float)
    period_days: Mapped[int]=mapped_column(Integer)
    source: Mapped[str]=mapped_column(String(40), default='reported')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
class Alert(Base):
    __tablename__='alerts'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    product_id: Mapped[int|None]=mapped_column(ForeignKey('products.id'), nullable=True, index=True)
    risk_key: Mapped[str]=mapped_column(String(60))
    severity: Mapped[str]=mapped_column(String(20), index=True)
    explanation: Mapped[str]=mapped_column(Text)
    recommendation: Mapped[str]=mapped_column(Text)
    inputs: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30), default='active', index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
class Replenishment(Base):
    __tablename__='replenishments'
    id: Mapped[int]=mapped_column(primary_key=True)
    request_code: Mapped[str]=mapped_column(String(30), unique=True, index=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    product_id: Mapped[int|None]=mapped_column(ForeignKey('products.id'), nullable=True)
    quantity: Mapped[int]=mapped_column(Integer)
    received: Mapped[int]=mapped_column(Integer, default=0)
    reason: Mapped[str]=mapped_column(Text)
    priority: Mapped[str]=mapped_column(String(20), default='routine')
    status: Mapped[str]=mapped_column(String(30), default='pending')
    expected_date: Mapped[date|None]=mapped_column(Date, nullable=True)
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str]=mapped_column(Text, default='')
class Audit(Base):
    __tablename__='audit_logs'
    id: Mapped[int]=mapped_column(primary_key=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    action: Mapped[str]=mapped_column(String(80))
    entity_type: Mapped[str]=mapped_column(String(80))
    entity_id: Mapped[str]=mapped_column(String(80))
    details: Mapped[str]=mapped_column(Text, default='')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())

class PhysicalCount(Base):
    __tablename__='physical_counts'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    counted_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    counted_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str]=mapped_column(Text, default='')
    status: Mapped[str]=mapped_column(String(20), default='submitted')
class CountLine(Base):
    __tablename__='count_lines'
    id: Mapped[int]=mapped_column(primary_key=True)
    count_id: Mapped[int]=mapped_column(ForeignKey('physical_counts.id'), index=True)
    batch_id: Mapped[int]=mapped_column(ForeignKey('batches.id'), index=True)
    ledger_quantity: Mapped[int]=mapped_column(Integer)
    counted_quantity: Mapped[int]=mapped_column(Integer)
class Discrepancy(Base):
    __tablename__='discrepancies'
    id: Mapped[int]=mapped_column(primary_key=True)
    count_id: Mapped[int]=mapped_column(ForeignKey('physical_counts.id'), index=True)
    batch_id: Mapped[int]=mapped_column(ForeignKey('batches.id'), index=True)
    ledger_quantity: Mapped[int]=mapped_column(Integer)
    counted_quantity: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(20), default='open', index=True)
    resolved_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    resolved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str]=mapped_column(Text, default='')
class Transfer(Base):
    __tablename__='stock_transfers'
    id: Mapped[int]=mapped_column(primary_key=True)
    transfer_code: Mapped[str]=mapped_column(String(32), unique=True, index=True)
    source_facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    destination_facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    batch_id: Mapped[int]=mapped_column(ForeignKey('batches.id'))
    quantity: Mapped[int]=mapped_column(Integer)
    received_quantity: Mapped[int]=mapped_column(Integer, default=0)
    status: Mapped[str]=mapped_column(String(30), default='proposed', index=True)
    verified_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    verified_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    source_approved_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    destination_approved_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    storage_suitable: Mapped[bool]=mapped_column(Boolean, default=False)
    transport_suitable: Mapped[bool]=mapped_column(Boolean, default=False)
    dispatched_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
class AlertEvent(Base):
    __tablename__='alert_events'
    id: Mapped[int]=mapped_column(primary_key=True)
    alert_id: Mapped[int]=mapped_column(ForeignKey('alerts.id'), index=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    event_type: Mapped[str]=mapped_column(String(30))
    note: Mapped[str]=mapped_column(Text, default='')
    target_role: Mapped[str|None]=mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
class EvaluationLabel(Base):
    __tablename__='evaluation_labels'
    __table_args__=(UniqueConstraint('alert_id',name='uq_evaluation_alert_label'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    alert_id: Mapped[int|None]=mapped_column(ForeignKey('alerts.id'), nullable=True, index=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    product_id: Mapped[int|None]=mapped_column(ForeignKey('products.id'), nullable=True, index=True)
    outcome: Mapped[str]=mapped_column(String(20))
    risk_key: Mapped[str]=mapped_column(String(60),default='stockout')
    evidence: Mapped[str]=mapped_column(Text)
    reviewer_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    period_start: Mapped[date]=mapped_column(Date)
    period_end: Mapped[date]=mapped_column(Date)
class ReorderDraft(Base):
    __tablename__='reorder_drafts'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    product_id: Mapped[int]=mapped_column(ForeignKey('products.id'))
    usable_stock: Mapped[int]=mapped_column(Integer)
    confirmed_incoming: Mapped[int]=mapped_column(Integer)
    estimated_demand: Mapped[float]=mapped_column(Float)
    recommended_quantity: Mapped[int]=mapped_column(Integer)
    expected_date: Mapped[date]=mapped_column(Date)
    explanation: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(20), default='draft')
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
class BatchEvent(Base):
    __tablename__='batch_events'
    id: Mapped[int]=mapped_column(primary_key=True)
    batch_id: Mapped[int]=mapped_column(ForeignKey('batches.id'), index=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    event_type: Mapped[str]=mapped_column(String(40))
    reason: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
class DailyObservation(Base):
    __tablename__='daily_stock_observations'
    __table_args__=(UniqueConstraint('facility_id','observed_date',name='uq_daily_facility_observation'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    product_id: Mapped[int|None]=mapped_column(ForeignKey('products.id'), nullable=True, index=True)
    observed_date: Mapped[date]=mapped_column(Date)
    usable_quantity: Mapped[int]=mapped_column(Integer)
    observed_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())

url=os.getenv('DATABASE_URL','sqlite:///./venotrack.db')
connect_args={'check_same_thread':False} if url.startswith('sqlite') else {}
engine=create_engine(url, connect_args=connect_args, pool_pre_ping=True)
Session=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
def init_db(): Base.metadata.create_all(engine)
