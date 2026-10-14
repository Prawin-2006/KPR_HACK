from datetime import date, timedelta

def forecast_risk(usable_stock, avg_daily_consumption, lead_days, confirmed_incoming, minimum_stock, safety_stock, history_days):
    """Transparent logistics forecast. No clinical guidance."""
    usable = max(0, int(usable_stock))
    consumption = float(avg_daily_consumption or 0)
    coverage = round(usable / consumption, 1) if consumption > 0 else None
    depletion = date.today() + timedelta(days=int(coverage)) if coverage is not None else None
    expected = date.today() + timedelta(days=max(0, int(lead_days or 0))) if lead_days is not None else None
    projected = round(usable + max(0, int(confirmed_incoming or 0)) - consumption * max(0, int(lead_days or 0)), 1)
    quality = "sufficient" if history_days >= 28 and consumption > 0 else "limited" if history_days and consumption > 0 else "insufficient"
    if usable <= 0:
        severity = "critical"
    elif consumption > 0 and coverage is not None and lead_days is not None and coverage < lead_days:
        severity = "critical"
    elif usable < minimum_stock or (consumption > 0 and projected < safety_stock):
        severity = "high"
    elif quality != "sufficient":
        severity = "medium"
    else:
        severity = "low"
    risk = severity in {"critical", "high"}
    explanation = f"{usable} usable vials" + (f", estimated consumption {consumption:g} vials/day, about {coverage:g} days of coverage" if coverage is not None else "; insufficient consumption history for a depletion estimate")
    if expected:
        explanation += f". Expected replenishment in {int(lead_days)} days; projected stock at delivery is {projected:g} vials"
    if risk:
        explanation += ". Verify physical stock and review replenishment logistics."
    return {"coverage_days": coverage, "depletion_date": depletion.isoformat() if depletion else None, "expected_delivery_date": expected.isoformat() if expected else None, "projected_stock_at_delivery": projected if lead_days is not None else None, "safety_stock": safety_stock, "shortage_before_delivery": bool(consumption > 0 and lead_days is not None and coverage is not None and coverage < lead_days), "severity": severity, "confidence": "high" if quality == "sufficient" else "low", "data_quality": quality, "explanation": explanation, "recommended_action": "Verify physical count and initiate urgent replenishment review" if risk else "Continue routine monitoring"}
