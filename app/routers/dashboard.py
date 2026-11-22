"""
routers/dashboard.py — Dashboard statistics and report endpoints.

GET /dashboard/stats          — high-level KPIs (all authenticated users)
GET /reports/loan-summary     — loan breakdown (officer + admin)
GET /reports/economic-summary — economic indicators summary (analyst + admin)
GET /reports/pdf-data         — full structured payload for PDF generation (admin)
"""

from decimal import Decimal
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    get_db,
    require_admin,
    require_analyst,
    require_officer,
)
from app import models

router = APIRouter(tags=["Dashboard & Reports"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _decimal_to_float(val) -> float:
    if val is None:
        return 0.0
    return float(val)


def _gather_core_stats(db: Session) -> Dict[str, Any]:
    """Aggregate KPIs from the live database (same source as dashboard)."""
    total_loans = db.query(func.count(models.Loan.loan_id)).scalar() or 0
    total_disbursed = db.query(func.sum(models.LoanDisbursement.amount)).scalar()
    total_repaid = db.query(func.sum(models.Repayment.amount_paid)).scalar()
    portfolio_total = db.query(func.sum(models.Loan.loan_amount)).scalar()
    active_loans = (
        db.query(func.count(models.Loan.loan_id))
        .filter(func.upper(models.Loan.status).in_(["ACTIVE"]))
        .scalar()
        or 0
    )
    total_countries = db.query(func.count(models.Country.country_id)).scalar() or 0
    total_users = db.query(func.count(models.User.user_id)).scalar() or 0
    total_transactions = (
        db.query(func.count(models.FinancialTransaction.transaction_id)).scalar() or 0
    )
    audit_logs = db.query(models.AuditLog).count()

    disbursed_f = _decimal_to_float(total_disbursed)
    repaid_f = _decimal_to_float(total_repaid)
    repayment_rate = round((repaid_f / disbursed_f) * 100, 1) if disbursed_f > 0 else 0.0

    # All member countries; loan_amount is 0 when no sovereign loan on file
    country_rows = (
        db.query(
            models.Country.name,
            func.coalesce(func.sum(models.Loan.loan_amount), 0),
        )
        .outerjoin(models.Loan, models.Loan.country_id == models.Country.country_id)
        .group_by(models.Country.country_id, models.Country.name)
        .order_by(func.coalesce(func.sum(models.Loan.loan_amount), 0).desc())
        .all()
    )
    portfolio_by_country = [
        {"label": name, "amount": _decimal_to_float(amount)}
        for name, amount in country_rows
    ]

    return {
        "total_loans": total_loans,
        "active_loans": active_loans,
        "total_portfolio_usd": _decimal_to_float(portfolio_total),
        "total_disbursed_usd": disbursed_f,
        "total_repaid_usd": repaid_f,
        "repayment_rate_pct": repayment_rate,
        "outstanding_balance_usd": disbursed_f - repaid_f,
        "total_countries": total_countries,
        "total_users": total_users,
        "total_transactions": total_transactions,
        "audit_log_count": audit_logs,
        "portfolio_by_country": portfolio_by_country,
    }


# ── Public landing stats (no auth) ───────────────────────────────────────────

@router.get("/public/stats")
def public_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """KPIs for the marketing landing page — reads the same seeded database."""
    return _gather_core_stats(db)


# ── Dashboard stats ───────────────────────────────────────────────────────────

@router.get("/dashboard/stats")
def dashboard_stats(
    _current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    High-level KPIs visible to all authenticated users.
    """
    stats = _gather_core_stats(db)
    return {
        "total_loans": stats["total_loans"],
        "active_loans": stats["active_loans"],
        "total_disbursed_usd": stats["total_disbursed_usd"],
        "total_repaid_usd": stats["total_repaid_usd"],
        "outstanding_balance_usd": stats["outstanding_balance_usd"],
        "total_countries": stats["total_countries"],
        "total_users": stats["total_users"],
        "total_transactions": stats["total_transactions"],
    }


# ── Loan summary ──────────────────────────────────────────────────────────────

@router.get("/reports/loan-summary")
def loan_summary(
    _current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Loan breakdown by status and program. Accessible by officer and admin.
    """
    # By status
    status_rows = (
        db.query(models.Loan.status, func.count(models.Loan.loan_id), func.sum(models.Loan.loan_amount))
        .group_by(models.Loan.status)
        .all()
    )
    by_status = [
        {"status": r[0], "count": r[1], "total_amount": _decimal_to_float(r[2])}
        for r in status_rows
    ]

    # By program
    program_rows = (
        db.query(
            models.LoanProgram.program_name,
            func.count(models.Loan.loan_id),
            func.sum(models.Loan.loan_amount),
        )
        .join(models.Loan, models.Loan.program_id == models.LoanProgram.program_id, isouter=True)
        .group_by(models.LoanProgram.program_name)
        .all()
    )
    by_program = [
        {"program": r[0], "count": r[1] or 0, "total_amount": _decimal_to_float(r[2])}
        for r in program_rows
    ]

    # Recent disbursements (last 10)
    recent_disb = (
        db.query(models.LoanDisbursement)
        .order_by(models.LoanDisbursement.disbursement_date.desc())
        .limit(10)
        .all()
    )
    disbursements = [
        {
            "loan_id": d.loan_id,
            "disbursement_no": d.disbursement_no,
            "amount": _decimal_to_float(d.amount),
            "date": str(d.disbursement_date),
            "status": d.status,
        }
        for d in recent_disb
    ]

    # Overdue installments
    from datetime import date
    overdue = (
        db.query(func.count(models.Installment.loan_id))
        .filter(
            models.Installment.due_date < date.today(),
            func.lower(models.Installment.status) != "paid",
        )
        .scalar()
        or 0
    )

    return {
        "by_status": by_status,
        "by_program": by_program,
        "recent_disbursements": disbursements,
        "overdue_installments": overdue,
    }


# ── Economic summary ──────────────────────────────────────────────────────────

@router.get("/reports/economic-summary")
def economic_summary(
    _current_user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Economic indicator aggregates. Accessible by analyst and admin.
    """
    avg_cpi = db.query(func.avg(models.EconomicIndicator.CPI)).scalar()
    avg_inflation = db.query(func.avg(models.EconomicRecord.inflation)).scalar()
    avg_gdp = db.query(func.avg(models.EconomicRecord.GDP)).scalar()
    avg_exchange = db.query(func.avg(models.EconomicIndicator.exchange_rate)).scalar()

    # Latest record per country (top 10 by most recent date)
    latest_rows = (
        db.query(
            models.Country.name,
            models.EconomicIndicator.record_date,
            models.EconomicIndicator.CPI,
            models.EconomicIndicator.interest_rate,
            models.EconomicIndicator.exchange_rate,
        )
        .join(models.EconomicIndicator, models.EconomicIndicator.country_id == models.Country.country_id)
        .order_by(models.EconomicIndicator.record_date.desc())
        .limit(10)
        .all()
    )
    latest = [
        {
            "country": r[0],
            "record_date": str(r[1]),
            "CPI": _decimal_to_float(r[2]),
            "interest_rate": _decimal_to_float(r[3]),
            "exchange_rate": _decimal_to_float(r[4]),
        }
        for r in latest_rows
    ]

    # Exchange rate snapshot (latest 5)
    exchange_rows = (
        db.query(models.ExchangeRate)
        .order_by(models.ExchangeRate.rate_date.desc())
        .limit(5)
        .all()
    )
    exchange_rates = [
        {
            "from": e.from_currency,
            "to": e.to_currency,
            "rate": _decimal_to_float(e.rate),
            "date": str(e.rate_date),
        }
        for e in exchange_rows
    ]

    return {
        "averages": {
            "avg_CPI": _decimal_to_float(avg_cpi),
            "avg_inflation": _decimal_to_float(avg_inflation),
            "avg_GDP": _decimal_to_float(avg_gdp),
            "avg_exchange_rate": _decimal_to_float(avg_exchange),
        },
        "latest_indicators": latest,
        "exchange_rates": exchange_rates,
    }


# ── PDF data payload ──────────────────────────────────────────────────────────

@router.get("/reports/pdf-data")
def pdf_data(
    _current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Full structured payload for admin PDF generation.
    Combines loan summary + economic summary + audit log tail.
    """
    # All loans
    loans = db.query(models.Loan).all()
    loan_list = [
        {
            "loan_id": l.loan_id,
            "country_id": l.country_id,
            "program_id": l.program_id,
            "amount": _decimal_to_float(l.loan_amount),
            "interest_rate": _decimal_to_float(l.interest_rate),
            "status": l.status,
            "start_date": str(l.start_date),
            "end_date": str(l.end_date),
        }
        for l in loans
    ]

    # Audit log tail (last 50)
    audit_rows = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.log_timestamp.desc())
        .limit(50)
        .all()
    )
    audit_list = [
        {
            "log_id": a.log_id,
            "user_id": a.user_id,
            "action": a.action,
            "timestamp": str(a.log_timestamp),
            "entity": a.entity_affected,
        }
        for a in audit_rows
    ]

    # Users overview
    users = db.query(models.User).all()
    user_list = [{"user_id": u.user_id, "name": u.name, "email": u.email} for u in users]

    return {
        "report_generated_at": str(__import__("datetime").datetime.utcnow()),
        "loans": loan_list,
        "users": user_list,
        "recent_audit_logs": audit_list,
    }
