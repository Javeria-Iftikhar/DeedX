"""
routers/transactions.py — Financial transaction endpoints.

SECURITY RULE
─────────────
Users NEVER directly insert FinancialTransaction, DisbursementTransaction,
RepaymentTransaction, or AuditLog. Those rows are ONLY created automatically
by financial_service.py.

RBAC:
  • process-disbursement / process-repayment — Admin or Officer
  • Read financial transactions              — Admin or Officer
  • Delete financial transactions            — Admin only
  • Read transaction links (disbursement/repayment) — Admin or Officer

Audit logging after every successful action.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.auth.dependencies import get_db, require_admin, require_officer
from app.crud import transaction as crud
from app.services.financial_service import process_disbursement, process_repayment

router = APIRouter(tags=["Transactions"])


# ─────────────────────────────────────────────
# FINANCIAL AUTOMATION — public entry points
# ─────────────────────────────────────────────

@router.post(
    "/process-disbursement/",
    response_model=schemas.LoanDisbursementResponse,
    tags=["Financial Automation"],
)
def api_process_disbursement(
    data: schemas.ProcessDisbursementRequest,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """
    **Admin or Officer.** Disburse a loan amount. Automatically:
    - Sequences disbursement_no
    - Sets status
    - Generates installment schedule on first disbursement
    - Activates the loan
    - Creates FinancialTransaction + DisbursementTransaction link
    - Writes AuditLog
    """
    try:
        obj = process_disbursement(
            db,
            loan_id=data.loan_id,
            imf_account_id=data.imf_account_id,
            amount=Decimal(str(data.amount)),
            disbursement_date=data.disbursement_date,
            actor_user_id=current_user.user_id,
        )
        # NOTE: audit log is written inside process_disbursement (financial_service).
        # Do NOT call write_audit_log here — the service already committed it.
        return obj
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Disbursement failed: {e}")


@router.post(
    "/process-repayment/",
    response_model=schemas.RepaymentResponse,
    tags=["Financial Automation"],
)
def api_process_repayment(
    data: schemas.ProcessRepaymentRequest,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """
    **Admin or Officer.** Process a repayment. Automatically:
    - Sequences repayment_no
    - Computes outstanding_balance
    - Allocates payment against installment schedule
    - Updates loan status (ACTIVE → CLOSED when fully paid)
    - Creates FinancialTransaction + RepaymentTransaction link
    - Writes AuditLog
    """
    try:
        rp = process_repayment(
            db,
            loan_id=data.loan_id,
            amount_paid=Decimal(str(data.amount_paid)),
            payment_date=data.payment_date,
            actor_user_id=current_user.user_id,
        )
        total_paid = db.query(sqlfunc.sum(models.Repayment.amount_paid)).filter(
            models.Repayment.loan_id == rp.loan_id
        ).scalar() or 0
        # NOTE: audit log is written inside process_repayment (financial_service).
        # Do NOT call write_audit_log here — the service already committed it.
        return schemas.RepaymentResponse(
            loan_id=rp.loan_id,
            repayment_no=rp.repayment_no,
            amount_paid=rp.amount_paid,
            payment_date=rp.payment_date,
            outstanding_balance=rp.outstanding_balance,
            total_paid=total_paid,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Repayment failed: {e}")


# ─────────────────────────────────────────────
# FINANCIAL TRANSACTION  (READ + DELETE only)
# ─────────────────────────────────────────────

@router.get("/transactions/", response_model=list[schemas.FinancialTransactionResponse], tags=["Financial Transaction"])
def list_transactions(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all financial transactions."""
    return crud.get_transactions(db)


@router.get("/transactions/{transaction_id}", response_model=schemas.FinancialTransactionResponse, tags=["Financial Transaction"])
def get_transaction(
    transaction_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific financial transaction."""
    obj = crud.get_transaction(db, transaction_id)
    if not obj:
        raise HTTPException(404, "Transaction not found")
    return obj


@router.get("/transactions/user/{user_id}", response_model=list[schemas.FinancialTransactionResponse], tags=["Financial Transaction"])
def get_user_transactions(
    user_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get all financial transactions for a specific user."""
    return crud.get_transactions_by_user(db, user_id)


@router.delete("/transactions/{transaction_id}", tags=["Financial Transaction"])
def delete_transaction(
    transaction_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a financial transaction record."""
    obj = crud.delete_transaction(db, transaction_id)
    if not obj:
        raise HTTPException(404, "Transaction not found")
    write_audit_log(db, current_user.user_id, f"Deleted FinancialTransaction id={transaction_id}", "FinancialTransaction")
    return {"msg": "deleted"}


# ─────────────────────────────────────────────
# DISBURSEMENT TRANSACTION LINKS  (READ only)
# ─────────────────────────────────────────────

@router.get("/transactions/disbursement-link/", response_model=list[schemas.DisbursementTransactionResponse], tags=["Transaction Links"])
def list_disbursement_links(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all disbursement-transaction links."""
    return crud.get_disbursement_transactions(db)


@router.get("/transactions/disbursement-link/{transaction_id}", response_model=schemas.DisbursementTransactionResponse, tags=["Transaction Links"])
def get_disbursement_link(
    transaction_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific disbursement-transaction link."""
    obj = crud.get_disbursement_transaction(db, transaction_id)
    if not obj:
        raise HTTPException(404, "Disbursement link not found")
    return obj


# ─────────────────────────────────────────────
# REPAYMENT TRANSACTION LINKS  (READ only)
# ─────────────────────────────────────────────

@router.get("/transactions/repayment-link/", response_model=list[schemas.RepaymentTransactionResponse], tags=["Transaction Links"])
def list_repayment_links(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all repayment-transaction links."""
    return crud.get_repayment_transactions(db)


@router.get("/transactions/repayment-link/{transaction_id}", response_model=schemas.RepaymentTransactionResponse, tags=["Transaction Links"])
def get_repayment_link(
    transaction_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific repayment-transaction link."""
    obj = crud.get_repayment_transaction(db, transaction_id)
    if not obj:
        raise HTTPException(404, "Repayment link not found")
    return obj
