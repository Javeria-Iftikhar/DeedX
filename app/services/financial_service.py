"""
services/financial_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INSTALLMENT ARCHITECTURE (CORRECT)
────────────────────────────────────
  • Installments are generated ONCE, on FIRST DISBURSEMENT, based on
    loan.no_of_installments and loan.loan_amount.
  • They are NEVER created during repayment processing.
  • Repayment ONLY:
      1. Records the payment (Repayment row)
      2. Allocates the payment against the existing installment schedule
      3. Creates a FinancialTransaction record
      4. Links via RepaymentTransaction
      5. Updates loan status
      6. Writes AuditLog

AUTOMATED FIELDS
────────────────
  disbursement_no     — auto-sequenced per loan
  repayment_no        — auto-sequenced per loan
  outstanding_balance — computed (loan_amount − cumulative paid)
  Loan.status         — "Pending" → "ACTIVE" → "CLOSED" (state machine)
  log_id              — auto-sequenced per user
  log_timestamp       — always datetime.utcnow()
  transaction_date    — always datetime.utcnow()
  reference           — always composed by service
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


# ─────────────────────────────────────────────
# SEQUENCE HELPERS
# ─────────────────────────────────────────────

def _next_log_id(db: Session, user_id: int) -> int:
    max_id = (
        db.query(func.max(models.AuditLog.log_id))
        .filter(models.AuditLog.user_id == user_id)
        .scalar()
    )
    return (max_id or 0) + 1


def _next_disbursement_no(db: Session, loan_id: int) -> int:
    max_no = (
        db.query(func.max(models.LoanDisbursement.disbursement_no))
        .filter(models.LoanDisbursement.loan_id == loan_id)
        .scalar()
    )
    return (max_no or 0) + 1


def _next_repayment_no(db: Session, loan_id: int) -> int:
    max_no = (
        db.query(func.max(models.Repayment.repayment_no))
        .filter(models.Repayment.loan_id == loan_id)
        .scalar()
    )
    return (max_no or 0) + 1


# ─────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────

def _write_audit_log(
    db: Session,
    *,
    actor_user_id: int,
    action: str,
    entity_affected: str,
    before_state: Optional[dict] = None,
    after_state: Optional[dict] = None,
) -> models.AuditLog:
    payload = {}
    if before_state:
        payload["before"] = before_state
    if after_state:
        payload["after"] = after_state

    log = models.AuditLog(
        user_id=actor_user_id,
        log_id=_next_log_id(db, actor_user_id),
        action=action,
        log_timestamp=datetime.utcnow(),
        entity_affected=entity_affected,
    )
    if payload:
        log.action = f"{action} | {json.dumps(payload)}"

    db.add(log)
    return log


# ─────────────────────────────────────────────
# FINANCIAL TRANSACTION
# ─────────────────────────────────────────────

def _create_financial_transaction(
    db: Session,
    *,
    user_id: int,
    imf_account_id: int,
    currency_code: str,
    amount: Decimal,
    transaction_type: str,
    reference: str,
) -> models.FinancialTransaction:
    txn = models.FinancialTransaction(
        user_id=user_id,
        imf_account_id=imf_account_id,
        currency_code=currency_code,
        amount=amount,
        transaction_type=transaction_type,
        transaction_date=datetime.utcnow(),
        reference=reference,
    )
    db.add(txn)
    db.flush()
    return txn


# ─────────────────────────────────────────────
# INSTALLMENT SCHEDULE — created ONCE at first disbursement
# ─────────────────────────────────────────────

def _create_installment_schedule(
    db: Session,
    loan: models.Loan,
) -> None:
    """
    Generate the fixed installment schedule for a loan.
    Called ONLY when the first disbursement is processed.
    Never called from repayment logic.

    Formula: amount_due = loan_amount / no_of_installments (equal instalments)
    All installments start as PENDING with amount_paid = 0.
    due_date is computed from loan.start_date and loan.end_date, spreading
    installments evenly over the loan period (monthly fallback if no end_date).
    """
    n = loan.no_of_installments
    if not n or n <= 0:
        raise HTTPException(400, f"Loan {loan.loan_id} has invalid no_of_installments ({n})")

    amount_due = (Decimal(str(loan.loan_amount)) / Decimal(str(n))).quantize(Decimal("0.01"))

    # Compute due_date by spreading installments evenly between start_date
    # and end_date. Falls back to 30-day monthly intervals if end_date absent.
    anchor = loan.start_date or date.today()
    if loan.end_date and loan.end_date > anchor:
        total_days = (loan.end_date - anchor).days
        interval_days = total_days / n
    else:
        interval_days = 30  # default: monthly

    for i in range(1, n + 1):
        due = anchor + timedelta(days=round(interval_days * i))
        inst = models.Installment(
            loan_id=loan.loan_id,
            installment_no=i,
            due_date=due,
            amount_due=float(amount_due),
            amount_paid=0,
            status="PENDING",
        )
        db.add(inst)

    db.flush()


# ─────────────────────────────────────────────
# INSTALLMENT ALLOCATION ENGINE
# Called by process_repayment ONLY — never creates installments
# ─────────────────────────────────────────────

def _apply_payment_to_installments(
    db: Session,
    loan_id: int,
    amount_paid: Decimal,
) -> None:
    """
    Allocate `amount_paid` against the existing installment schedule
    in installment_no order.

    Rules:
      • Skip already-PAID installments.
      • Fill partial installments first.
      • Set status to PAID when amount_paid >= amount_due.
      • Set status to PARTIAL when partially covered.
      • Leave PENDING installments untouched if no remaining budget.
    """
    remaining = Decimal(str(amount_paid))

    installments = (
        db.query(models.Installment)
        .filter(models.Installment.loan_id == loan_id)
        .filter(models.Installment.status.notin_(["PAID"]))
        .order_by(models.Installment.installment_no)
        .all()
    )

    for inst in installments:
        if remaining <= Decimal("0"):
            break

        due  = Decimal(str(inst.amount_due or 0))
        paid = Decimal(str(inst.amount_paid or 0))
        owed = due - paid

        if owed <= 0:
            inst.status = "PAID"
            continue

        if remaining >= owed:
            inst.amount_paid = float(paid + owed)
            inst.status = "PAID"
            remaining -= owed
        else:
            inst.amount_paid = float(paid + remaining)
            inst.status = "PARTIAL"
            remaining = Decimal("0")


# ─────────────────────────────────────────────
# LOAN STATUS STATE MACHINE
# ─────────────────────────────────────────────

def _sync_loan_status_after_repayment(
    db: Session,
    loan: models.Loan,
    new_total_paid: Decimal,
) -> str:
    loan_amount = Decimal(str(loan.loan_amount))

    if new_total_paid >= loan_amount:
        new_status = "CLOSED"
    elif new_total_paid > 0:
        new_status = "ACTIVE"
    else:
        new_status = loan.status  # no change

    loan.status = new_status
    return new_status


def _mark_loan_disbursements_completed(db: Session, loan_id: int) -> None:
    """When a loan is fully repaid, mark its disbursements as Completed."""
    disbursements = (
        db.query(models.LoanDisbursement)
        .filter(models.LoanDisbursement.loan_id == loan_id)
        .filter(models.LoanDisbursement.status.in_(["Pending", "Approved", "Disbursed"]))
        .all()
    )
    for dis in disbursements:
        dis.status = "Completed"


# ─────────────────────────────────────────────
# PUBLIC: PROCESS DISBURSEMENT
# ─────────────────────────────────────────────

def process_disbursement(
    db: Session,
    *,
    loan_id: int,
    imf_account_id: int,
    amount: Decimal,
    disbursement_date: Optional[date],
    actor_user_id: int,
) -> models.LoanDisbursement:
    """
    Full disbursement pipeline (atomic):
      1. Validate loan exists
      2. Validate IMF account exists and has sufficient balance
      3. Auto-sequence disbursement_no
      4. Create LoanDisbursement row (status = "Disbursed")
      5. DEDUCT disbursed amount from IMF account balance
      6. If this is the FIRST disbursement → generate installment schedule
      7. Transition loan status: Pending/Approved → ACTIVE
      8. Create FinancialTransaction (system-generated)
      9. Link via DisbursementTransaction
     10. Write AuditLog
     11. Commit
    """
    # 1. Validate loan
    loan = db.query(models.Loan).filter(models.Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, f"Loan {loan_id} not found")
    if loan.status == "CLOSED":
        raise HTTPException(400, "Cannot disburse to a CLOSED loan")
    if amount <= 0:
        raise HTTPException(400, "Disbursement amount must be positive")

    # 2. Validate IMF account and balance
    imf_account = db.query(models.IMFAccount).filter(
        models.IMFAccount.imf_account_id == imf_account_id
    ).first()
    if not imf_account:
        raise HTTPException(404, f"IMF account {imf_account_id} not found")
    current_balance = Decimal(str(imf_account.balance or 0))
    if current_balance < amount:
        raise HTTPException(
            400,
            f"Insufficient IMF account balance. "
            f"Available: {current_balance}, Requested: {amount}",
        )

    # 3. Auto-sequence
    dis_no = _next_disbursement_no(db, loan_id)

    # 4. Create disbursement row
    dis = models.LoanDisbursement(
        loan_id=loan_id,
        disbursement_no=dis_no,         # auto-sequenced
        imf_account_id=imf_account_id,
        amount=float(amount),
        disbursement_date=disbursement_date or date.today(),
        status="Disbursed",
    )
    db.add(dis)
    db.flush()

    # 5. DEDUCT from IMF account balance (money leaves the IMF)
    balance_before = current_balance
    imf_account.balance = float(current_balance - amount)
    db.flush()

    # 6. First disbursement → generate installment schedule ONCE
    existing_count = (
        db.query(func.count(models.Installment.installment_no))
        .filter(models.Installment.loan_id == loan_id)
        .scalar() or 0
    )
    if existing_count == 0:
        _create_installment_schedule(db, loan)

    # 7. Activate loan on first disbursement
    if loan.status in ("Pending", "PENDING", "Approved", "APPROVED"):
        loan.status = "ACTIVE"

    # 8. Financial transaction
    txn = _create_financial_transaction(
        db,
        user_id=actor_user_id,
        imf_account_id=imf_account_id,
        currency_code=loan.currency_code,
        amount=amount,
        transaction_type="DISBURSEMENT",
        reference=f"LOAN-{loan_id}/DISB-{dis_no}",
    )

    # 9. Link table
    link = models.DisbursementTransaction(
        transaction_id=txn.transaction_id,
        loan_id=loan_id,
        disbursement_no=dis_no,
    )
    db.add(link)
    db.flush()

    # 10. Audit log
    _write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="DISBURSEMENT",
        entity_affected=f"Loan:{loan_id}",
        before_state={
            "imf_account_balance": str(balance_before),
        },
        after_state={
            "disbursement_no": dis_no,
            "amount": str(amount),
            "imf_account_balance": str(imf_account.balance),
            "transaction_id": txn.transaction_id,
            "loan_status": loan.status,
        },
    )

    # 11. Commit
    db.commit()
    db.refresh(dis)
    return dis


# ─────────────────────────────────────────────
# PUBLIC: PROCESS REPAYMENT
# ─────────────────────────────────────────────

def process_repayment(
    db: Session,
    *,
    loan_id: int,
    amount_paid: Decimal,
    payment_date: Optional[date],
    actor_user_id: int,
) -> models.Repayment:
    """
    Full repayment pipeline (atomic):
      1. Validate loan and that installment schedule exists
      2. Auto-sequence repayment_no
      3. Compute outstanding_balance (never user-supplied)
      4. Create Repayment row
      5. Allocate payment against existing installment schedule (NEVER creates installments)
      6. Sync loan status
      7. CREDIT repaid amount back to IMF account balance
      8. Create FinancialTransaction (system-generated)
      9. Link via RepaymentTransaction
     10. Write AuditLog
     11. Commit
    """
    # 1. Validate
    loan = db.query(models.Loan).filter(models.Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, f"Loan {loan_id} not found")
    if loan.status == "CLOSED":
        raise HTTPException(400, "Loan is already CLOSED")
    if amount_paid <= 0:
        raise HTTPException(400, "amount_paid must be positive")

    inst_count = (
        db.query(func.count(models.Installment.installment_no))
        .filter(models.Installment.loan_id == loan_id)
        .scalar() or 0
    )
    if inst_count == 0:
        raise HTTPException(
            400,
            "No installment schedule found for this loan. "
            "Disburse the loan first to generate the installment schedule.",
        )

    # Validate IMF account exists
    imf_account = db.query(models.IMFAccount).filter(
        models.IMFAccount.imf_account_id == loan.imf_account_id
    ).first()
    if not imf_account:
        raise HTTPException(404, f"IMF account {loan.imf_account_id} not found")

    # 2. Auto-sequence
    repayment_no = _next_repayment_no(db, loan_id)

    # 3. Compute totals
    prev_paid = Decimal(str(
        db.query(func.sum(models.Repayment.amount_paid))
        .filter(models.Repayment.loan_id == loan_id)
        .scalar() or 0
    ))
    new_total   = prev_paid + Decimal(str(amount_paid))
    outstanding = Decimal(str(loan.loan_amount)) - new_total

    # 4. Repayment row
    repayment = models.Repayment(
        loan_id=loan_id,
        repayment_no=repayment_no,          # auto-sequenced
        amount_paid=float(amount_paid),
        payment_date=payment_date or date.today(),
        outstanding_balance=float(outstanding),  # computed
        # no_of_installments column removed from Repayment model
    )
    db.add(repayment)
    db.flush()

    # 5. Allocate against existing installment schedule (no creation)
    _apply_payment_to_installments(db, loan_id, Decimal(str(amount_paid)))

    # 6. Loan status
    new_loan_status = _sync_loan_status_after_repayment(db, loan, new_total)
    if new_loan_status == "CLOSED":
        _mark_loan_disbursements_completed(db, loan_id)

    # 7. CREDIT repaid amount back to IMF account balance (money returns to the IMF)
    balance_before = Decimal(str(imf_account.balance or 0))
    imf_account.balance = float(balance_before + Decimal(str(amount_paid)))
    db.flush()

    # 8. Financial transaction
    txn = _create_financial_transaction(
        db,
        user_id=actor_user_id,
        imf_account_id=loan.imf_account_id,
        currency_code=loan.currency_code,
        amount=Decimal(str(amount_paid)),
        transaction_type="REPAYMENT",
        reference=f"LOAN-{loan_id}/REP-{repayment_no}",
    )

    # 9. Link table
    link = models.RepaymentTransaction(
        transaction_id=txn.transaction_id,
        loan_id=loan_id,
        repayment_no=repayment_no,
    )
    db.add(link)
    db.flush()

    # 10. Audit log
    _write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="REPAYMENT",
        entity_affected=f"Loan:{loan_id}",
        before_state={
            "imf_account_balance": str(balance_before),
        },
        after_state={
            "repayment_no": repayment_no,
            "amount_paid": str(amount_paid),
            "outstanding_balance": str(outstanding),
            "total_paid": str(new_total),
            "loan_status": new_loan_status,
            "imf_account_balance": str(imf_account.balance),
            "transaction_id": txn.transaction_id,
        },
    )

    # 11. Commit
    db.commit()
    db.refresh(repayment)
    return repayment
