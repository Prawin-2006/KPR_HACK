from datetime import date, datetime, timezone
from app.risk import forecast_risk

def test_coverage_and_projected_shortage_are_explainable():
    result = forecast_risk(12, 3, 6, 0, 5, 5, 1)
    assert result['coverage_days'] == 4
    assert result['projected_stock_at_delivery'] == -6
    assert result['severity'] == 'critical'
    assert '12 usable' in result['explanation']

def test_zero_consumption_does_not_claim_depletion():
    result = forecast_risk(20, 0, 7, 0, 5, 5, 1)
    assert result['coverage_days'] is None
    assert result['depletion_date'] is None
    assert result['data_quality'] == 'insufficient'

def test_zero_usable_stock_is_critical_even_without_history():
    result = forecast_risk(0, None, None, 0, 5, 5, 0)
    assert result['severity'] == 'critical'
from datetime import date
from app.models import Base, engine, Session, Facility, Batch, Transaction, User
from app.security import hash_password
from app.risk import forecast_risk

def test_expired_and_unverified_stock_is_never_usable():
    assert usable_batch(10, date.today()-__import__('datetime').timedelta(days=1), 'usable', True) == 0
    assert usable_batch(10, date.today()+__import__('datetime').timedelta(days=10), 'quarantined', True) == 0
    assert usable_batch(10, date.today()+__import__('datetime').timedelta(days=10), 'usable', False) == 0

def usable_batch(qty, expiry, status, verified):
    return qty if expiry >= date.today() and status=='usable' and verified else 0

def test_risk_engine_shortage_before_delivery():
    result=forecast_risk(12,3,6,0,10,8,30)
    assert result['shortage_before_delivery'] is True
    assert result['severity']=='critical'
