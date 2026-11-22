"""
routers/economic.py — Routes for EconomicIndicator, EconomicRecord, ExchangeRate.

RBAC:
  • Create / Update indicators & records    — Admin or Analyst
  • Delete indicators / records             — Admin only
  • Read (list/get) all economic data       — Admin or Analyst
  • Exchange rate create/update             — Admin only
  • Exchange rate read                      — Admin or Analyst
  • Exchange rate delete                    — Admin only

Audit logging after every successful mutating operation.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_db,
    require_admin,
    require_analyst,
)
from app.audit import write_audit_log
from app.crud import economic as crud
from app import models, schemas

router = APIRouter(tags=["Economic Data"])


# ─── ECONOMIC INDICATOR ─────────────────────────────────────────────────────

@router.post("/indicators/", response_model=schemas.EconomicIndicatorResponse, tags=["Economic Indicator"])
def create_indicator(
    data: schemas.EconomicIndicatorCreate,
    current_user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Create a new economic indicator record."""
    obj = crud.create_indicator(db, data)
    write_audit_log(db, current_user.user_id, f"Created EconomicIndicator id={obj.indicator_id}", "EconomicIndicator")
    return obj


@router.get("/indicators/", response_model=list[schemas.EconomicIndicatorResponse], tags=["Economic Indicator"])
def list_indicators(
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** List all economic indicators."""
    return crud.get_indicators(db)


@router.get("/indicators/country/{country_id}", response_model=list[schemas.EconomicIndicatorResponse], tags=["Economic Indicator"])
def list_by_country(
    country_id: int,
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** List economic indicators for a specific country."""
    return crud.get_indicators_by_country(db, country_id)


@router.get("/indicators/{indicator_id}", response_model=schemas.EconomicIndicatorResponse, tags=["Economic Indicator"])
def get_indicator(
    indicator_id: int,
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Get a specific economic indicator."""
    obj = crud.get_indicator(db, indicator_id)
    if not obj:
        raise HTTPException(404, "Indicator not found")
    return obj


@router.put("/indicators/{indicator_id}", response_model=schemas.EconomicIndicatorResponse, tags=["Economic Indicator"])
def update_indicator(
    indicator_id: int,
    data: schemas.EconomicIndicatorCreate,
    current_user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Update an economic indicator."""
    obj = crud.update_indicator(db, indicator_id, data)
    if not obj:
        raise HTTPException(404, "Indicator not found")
    write_audit_log(db, current_user.user_id, f"Updated EconomicIndicator id={indicator_id}", "EconomicIndicator")
    return obj


@router.delete("/indicators/{indicator_id}", tags=["Economic Indicator"])
def delete_indicator(
    indicator_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete an economic indicator."""
    obj = crud.delete_indicator(db, indicator_id)
    if not obj:
        raise HTTPException(404, "Indicator not found")
    write_audit_log(db, current_user.user_id, f"Deleted EconomicIndicator id={indicator_id}", "EconomicIndicator")
    return {"msg": "deleted"}


# ─── ECONOMIC RECORD ────────────────────────────────────────────────────────

@router.post("/records/", response_model=schemas.EconomicRecordResponse, tags=["Economic Record"])
def create_record(
    data: schemas.EconomicRecordCreate,
    current_user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Create a new economic record (GDP/inflation)."""
    obj = crud.create_record(db, data)
    write_audit_log(db, current_user.user_id, f"Created EconomicRecord id={obj.record_id}", "EconomicRecord")
    return obj


@router.get("/records/", response_model=list[schemas.EconomicRecordResponse], tags=["Economic Record"])
def list_records(
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** List all economic records."""
    return crud.get_records(db)


@router.get("/records/indicator/{indicator_id}", response_model=list[schemas.EconomicRecordResponse], tags=["Economic Record"])
def list_by_indicator(
    indicator_id: int,
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** List economic records for a specific indicator."""
    return crud.get_records_by_indicator(db, indicator_id)


@router.get("/records/{record_id}", response_model=schemas.EconomicRecordResponse, tags=["Economic Record"])
def get_record(
    record_id: int,
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Get a specific economic record."""
    obj = crud.get_record(db, record_id)
    if not obj:
        raise HTTPException(404, "Record not found")
    return obj


@router.delete("/records/{record_id}", tags=["Economic Record"])
def delete_record(
    record_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete an economic record."""
    obj = crud.delete_record(db, record_id)
    if not obj:
        raise HTTPException(404, "Record not found")
    write_audit_log(db, current_user.user_id, f"Deleted EconomicRecord id={record_id}", "EconomicRecord")
    return {"msg": "deleted"}


# ─── EXCHANGE RATE ──────────────────────────────────────────────────────────

@router.post("/exchange-rates/", response_model=schemas.ExchangeRateResponse, tags=["Exchange Rate"])
def create_exchange_rate(
    data: schemas.ExchangeRateCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Create a new exchange rate entry."""
    obj = crud.create_exchange_rate(db, data)
    write_audit_log(db, current_user.user_id, f"Created ExchangeRate id={obj.exchange_rate_id} {data.from_currency}->{data.to_currency}", "ExchangeRate")
    return obj


@router.get("/exchange-rates/", response_model=list[schemas.ExchangeRateResponse], tags=["Exchange Rate"])
def list_exchange_rates(
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** List all exchange rates."""
    return crud.get_exchange_rates(db)


@router.get("/exchange-rates/{exchange_rate_id}", response_model=schemas.ExchangeRateResponse, tags=["Exchange Rate"])
def get_exchange_rate(
    exchange_rate_id: int,
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Get a specific exchange rate by ID."""
    obj = crud.get_exchange_rate(db, exchange_rate_id)
    if not obj:
        raise HTTPException(404, "Exchange rate not found")
    return obj


@router.get("/exchange-rates/pair/{from_currency}/{to_currency}", response_model=schemas.ExchangeRateResponse, tags=["Exchange Rate"])
def get_pair_rate(
    from_currency: str,
    to_currency: str,
    _user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """**Admin or Analyst.** Look up the latest rate for a currency pair."""
    obj = crud.get_exchange_rate_by_pair(db, from_currency, to_currency)
    if not obj:
        raise HTTPException(404, "Exchange rate pair not found")
    return obj


@router.delete("/exchange-rates/{exchange_rate_id}", tags=["Exchange Rate"])
def delete_exchange_rate(
    exchange_rate_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete an exchange rate entry."""
    obj = crud.delete_exchange_rate(db, exchange_rate_id)
    if not obj:
        raise HTTPException(404, "Exchange rate not found")
    write_audit_log(db, current_user.user_id, f"Deleted ExchangeRate id={exchange_rate_id}", "ExchangeRate")
    return {"msg": "deleted"}
