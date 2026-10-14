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
class Transaction(Base):
    __tablename__='inventory_transactions'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    batch_id: Mapped[int]=mapped_column(ForeignKey('batches.id'), index=True)
    kind: Mapped[str]=mapped_column(String(30))
    quantity: Mapped[int]=mapped_column(Integer)
    reason: Mapped[str]=mapped_column(String(200))
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
class ConsumptionSummary(Base):
    __tablename__='consumption_summaries'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
    quantity: Mapped[float]=mapped_column(Float)
    period_days: Mapped[int]=mapped_column(Integer)
    source: Mapped[str]=mapped_column(String(40), default='reported')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
class Alert(Base):
    __tablename__='alerts'
    id: Mapped[int]=mapped_column(primary_key=True)
    facility_id: Mapped[int]=mapped_column(ForeignKey('facilities.id'), index=True)
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

url=os.getenv('DATABASE_URL','sqlite:///./venotrack.db')
connect_args={'check_same_thread':False} if url.startswith('sqlite') else {}
engine=create_engine(url, connect_args=connect_args, pool_pre_ping=True)
Session=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
def init_db(): Base.metadata.create_all(engine)
