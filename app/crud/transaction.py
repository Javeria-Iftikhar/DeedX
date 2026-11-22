"""
crud/transaction.py  —  CRUD for FinancialTransaction,
                         DisbursementTransaction, RepaymentTransaction, AuditLog
"""

from sqlalchemy.orm import Session
from app import models, schemas


# ─── FINANCIAL TRANSACTION ──────────────────────────────────────────────────

def create_transaction(db: Session, data: schemas.FinancialTransactionCreate):
    obj = models.FinancialTransaction(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_transactions(db: Session):
    return db.query(models.FinancialTransaction).all()

def get_transaction(db: Session, transaction_id: int):
    return db.query(models.FinancialTransaction).filter(
        models.FinancialTransaction.transaction_id == transaction_id
    ).first()

def get_transactions_by_user(db: Session, user_id: int):
    return db.query(models.FinancialTransaction).filter(
        models.FinancialTransaction.user_id == user_id
    ).all()

def delete_transaction(db: Session, transaction_id: int):
    obj = get_transaction(db, transaction_id)
    if not obj:
        return None
    db.delete(obj); db.commit()
    return obj


# ─── DISBURSEMENT TRANSACTION (linking table) ───────────────────────────────

def create_disbursement_transaction(db: Session, data: schemas.DisbursementTransactionCreate):
    obj = models.DisbursementTransaction(**data.model_dump())
    db.add(obj); db.commit()
    return obj

def get_disbursement_transactions(db: Session):
    return db.query(models.DisbursementTransaction).all()

def get_disbursement_transaction(db: Session, transaction_id: int):
    return db.query(models.DisbursementTransaction).filter(
        models.DisbursementTransaction.transaction_id == transaction_id
    ).first()


# ─── REPAYMENT TRANSACTION (linking table) ──────────────────────────────────

def create_repayment_transaction(db: Session, data: schemas.RepaymentTransactionCreate):
    obj = models.RepaymentTransaction(**data.model_dump())
    db.add(obj); db.commit()
    return obj

def get_repayment_transactions(db: Session):
    return db.query(models.RepaymentTransaction).all()

def get_repayment_transaction(db: Session, transaction_id: int):
    return db.query(models.RepaymentTransaction).filter(
        models.RepaymentTransaction.transaction_id == transaction_id
    ).first()


# ─── AUDIT LOG ──────────────────────────────────────────────────────────────

def create_audit_log(db: Session, data: schemas.AuditLogCreate):
    obj = models.AuditLog(**data.model_dump())
    db.add(obj); db.commit()
    return obj

def get_audit_logs(db: Session):
    return db.query(models.AuditLog).all()

def get_audit_logs_by_user(db: Session, user_id: int):
    return db.query(models.AuditLog).filter(
        models.AuditLog.user_id == user_id
    ).all()
