"""
crud/economic.py  —  CRUD for:
  EconomicIndicator, EconomicRecord, ExchangeRate

EconomicRecord is a DERIVED table — auto-computed from EconomicIndicator.
  GDP       = 0.4 * industrial_output + 0.2 * agricultural_output + 0.4 * services_output
  Inflation = 0.6 * CPI + 0.3 * money_supply − 0.1 * interest_rate

sync_economic_record() is called automatically after every indicator
create / update / delete so records stay consistent.

FIX: Added missing create_record(), get_records_by_indicator(), delete_record()
that the economic router references.
"""

from sqlalchemy.orm import Session
from app import models, schemas


# ─────────────────────────────────────────────
# SYNC HELPER
# ─────────────────────────────────────────────

def sync_economic_record(db: Session) -> None:
    try:
        indicators = db.query(models.EconomicIndicator).all()
        for i in indicators:
            gdp = (
                0.4 * float(i.industrial_output or 0) +
                0.2 * float(i.agricultural_output or 0) +
                0.4 * float(i.services_output or 0)
            )
            inflation = (
                0.6 * float(i.CPI or 0) +
                0.3 * float(i.money_supply or 0) -
                0.1 * float(i.interest_rate or 0)
            )
            record = db.query(models.EconomicRecord).filter(
                models.EconomicRecord.indicator_id == i.indicator_id
            ).first()
            if not record:
                record = models.EconomicRecord(
                    indicator_id=i.indicator_id,
                    GDP=gdp,
                    inflation=inflation,
                )
                db.add(record)
            else:
                record.GDP = gdp
                record.inflation = inflation
        db.commit()
    except Exception as e:
        db.rollback()
        print("EconomicRecord sync failed:", repr(e))


# ─────────────────────────────────────────────
# ECONOMIC INDICATOR
# ─────────────────────────────────────────────

def create_indicator(db: Session, data: schemas.EconomicIndicatorCreate):
    obj = models.EconomicIndicator(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    sync_economic_record(db)
    return obj

def get_indicators(db: Session):
    return db.query(models.EconomicIndicator).all()

def get_indicators_by_country(db: Session, country_id: int):
    return db.query(models.EconomicIndicator).filter(
        models.EconomicIndicator.country_id == country_id
    ).all()

def get_indicator(db: Session, indicator_id: int):
    return db.query(models.EconomicIndicator).filter(
        models.EconomicIndicator.indicator_id == indicator_id
    ).first()

def update_indicator(db: Session, indicator_id: int, data: schemas.EconomicIndicatorCreate):
    obj = get_indicator(db, indicator_id)
    if not obj: return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    sync_economic_record(db)
    return obj

def delete_indicator(db: Session, indicator_id: int):
    obj = get_indicator(db, indicator_id)
    if not obj: return None
    db.delete(obj); db.commit()
    sync_economic_record(db)
    return obj


# ─────────────────────────────────────────────
# ECONOMIC RECORD  (derived — normally read-only)
# create_record and delete_record are available for admin overrides.
# In normal operation records are managed by sync_economic_record().
# ─────────────────────────────────────────────

def create_record(db: Session, data: schemas.EconomicRecordCreate):
    obj = models.EconomicRecord(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_records(db: Session):
    return db.query(models.EconomicRecord).all()

def get_record(db: Session, record_id: int):
    return db.query(models.EconomicRecord).filter(
        models.EconomicRecord.record_id == record_id
    ).first()

def get_records_by_indicator(db: Session, indicator_id: int):
    return db.query(models.EconomicRecord).filter(
        models.EconomicRecord.indicator_id == indicator_id
    ).all()

def update_record(db: Session, record_id: int, patch: dict):
    """Patch GDP / inflation on an economic record (admin NL overrides)."""
    obj = get_record(db, record_id)
    if not obj:
        return None
    for key in ("GDP", "inflation"):
        if key in patch and patch[key] is not None:
            setattr(obj, key, patch[key])
    db.commit()
    db.refresh(obj)
    return obj


def get_latest_record_for_country(db: Session, country_id: int):
    """Most recent economic record for a country (via latest indicator by record_date)."""
    indicator = (
        db.query(models.EconomicIndicator)
        .filter(models.EconomicIndicator.country_id == country_id)
        .order_by(models.EconomicIndicator.record_date.desc())
        .first()
    )
    if not indicator:
        return None, None
    record = (
        db.query(models.EconomicRecord)
        .filter(models.EconomicRecord.indicator_id == indicator.indicator_id)
        .first()
    )
    return indicator, record


def delete_record(db: Session, record_id: int):
    obj = get_record(db, record_id)
    if not obj: return None
    db.delete(obj); db.commit()
    return obj


# ─────────────────────────────────────────────
# EXCHANGE RATE
# ─────────────────────────────────────────────

def create_exchange_rate(db: Session, data: schemas.ExchangeRateCreate):
    obj = models.ExchangeRate(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_exchange_rates(db: Session):
    return db.query(models.ExchangeRate).all()

def get_exchange_rate(db: Session, exchange_rate_id: int):
    return db.query(models.ExchangeRate).filter(
        models.ExchangeRate.exchange_rate_id == exchange_rate_id
    ).first()

def get_exchange_rate_by_pair(db: Session, from_currency: str, to_currency: str):
    return (
        db.query(models.ExchangeRate)
        .filter(
            models.ExchangeRate.from_currency == from_currency,
            models.ExchangeRate.to_currency == to_currency,
        )
        .order_by(models.ExchangeRate.rate_date.desc())
        .first()
    )

def update_exchange_rate_patch(db: Session, exchange_rate_id: int, patch: dict):
    obj = get_exchange_rate(db, exchange_rate_id)
    if not obj:
        return None
    for key in ("from_currency", "to_currency", "rate", "rate_date"):
        if key in patch and patch[key] is not None:
            setattr(obj, key, patch[key])
    db.commit()
    db.refresh(obj)
    return obj


def delete_exchange_rate(db: Session, exchange_rate_id: int):
    obj = get_exchange_rate(db, exchange_rate_id)
    if not obj: return None
    db.delete(obj); db.commit()
    return obj
