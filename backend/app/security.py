from datetime import datetime, timedelta, timezone
import os, jwt, secrets
from pwdlib import PasswordHash
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .models import Session as SessionFactory, User, Facility
from sqlalchemy import select
passwords=PasswordHash.recommended()
oauth=OAuth2PasswordBearer(tokenUrl='/api/v1/auth/login')
SECRET=os.getenv('JWT_SECRET') or secrets.token_urlsafe(32)
ALGORITHM='HS256'
def hash_password(value): return passwords.hash(value)
def verify_password(value, hashed): return passwords.verify(value,hashed)
def issue_token(user): return jwt.encode({'sub':str(user.id),'exp':datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm=ALGORITHM)
def get_db():
    db=SessionFactory()
    try: yield db
    finally: db.close()
def current_user(token=Depends(oauth), db=Depends(get_db)):
    try: uid=int(jwt.decode(token,SECRET,algorithms=[ALGORITHM])['sub'])
    except Exception: raise HTTPException(401,'Invalid or expired session')
    user=db.get(User,uid)
    if not user or not user.active: raise HTTPException(401,'Inactive account')
    return user
def require(*roles):
    def check(user=Depends(current_user)):
        if user.role not in roles: raise HTTPException(403,'This action is not permitted for your role')
        return user
    return check
def can_access(user, facility):
    if user.role=='admin': return True
    if user.role=='worker': return user.facility_id==facility.id
    if user.district==facility.district or user.facility_id==facility.id: return True
    if user.role=='officer' and user.facility_id:
        db=SessionFactory()
        try:
            ancestors={user.facility_id}; frontier={user.facility_id}
            while frontier:
                children=set(db.scalars(select(Facility.id).where(Facility.parent_id.in_(frontier))).all())-ancestors
                ancestors.update(children); frontier=children
            return facility.id in ancestors
        finally: db.close()
    return False
