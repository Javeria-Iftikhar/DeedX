"""
models.py  —  SQLAlchemy ORM models aligned exactly with schema.sql.
Table names are all lowercase to match PostgreSQL's default behaviour.

INSTALLMENT MODEL NOTE
───────────────────────
Installment has NO repayment_no column. It is a fixed schedule keyed on
(loan_id, installment_no) only.  Installments are generated once at
first disbursement and then allocated against progressively via repayments.
The Repayment table tracks money received; the Installment table tracks
the fixed schedule and its fulfillment status.
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, BigInteger,
    Date, DateTime, Text, ForeignKey, UniqueConstraint,
    ForeignKeyConstraint,
)
from app.database import Base


# ─────────────────────────────────────────────
# CORE TABLES
# ─────────────────────────────────────────────

class Currency(Base):
    __tablename__ = "currency"

    currency_code   = Column(String(10), primary_key=True)
    currency_name   = Column(String(100))
    symbol          = Column(String(10))
    exchange_regime = Column(String(50))


class Country(Base):
    __tablename__ = "country"

    country_id    = Column(Integer, primary_key=True, index=True)
    currency_code = Column(String(10), ForeignKey("currency.currency_code", ondelete="RESTRICT"))
    name          = Column(String(100))
    region        = Column(String(100))
    population    = Column(BigInteger)


class LoanProgram(Base):
    __tablename__ = "loanprogram"

    program_id      = Column(Integer, primary_key=True, index=True)
    program_name    = Column(String(100))
    description     = Column(Text)
    max_amount      = Column(Numeric)
    interest_policy = Column(Text)


class IMFAccount(Base):
    __tablename__ = "imf_account"

    imf_account_id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String(50), unique=True)
    account_type   = Column(String(50))
    balance        = Column(Numeric)
    created_at     = Column(DateTime)


# ─────────────────────────────────────────────
# USERS & ROLES
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    user_id  = Column(Integer, primary_key=True, index=True)
    name     = Column(String(100))
    email    = Column(String(100), unique=True)
    password = Column(String(100))


class Admin(Base):
    __tablename__ = "admin"

    user_id      = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    admin_type   = Column(String(50))
    access_scope = Column(String(100))
    last_login   = Column(DateTime)


class Officer(Base):
    __tablename__ = "officer"

    user_id        = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    department     = Column(String(100))
    designation    = Column(String(100))
    approval_limit = Column(Numeric)
    approval_role  = Column(String(50))
    approval_scope = Column(String(100))


class EconomicAnalyst(Base):
    __tablename__ = "economicanalyst"

    user_id             = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    specialization      = Column(String(100))
    organization        = Column(String(100))
    report_access_level = Column(String(50))


# ─────────────────────────────────────────────
# LOANS
# ─────────────────────────────────────────────

class Loan(Base):
    __tablename__ = "loan"

    loan_id            = Column(Integer, primary_key=True, index=True)
    country_id         = Column(Integer, ForeignKey("country.country_id", ondelete="RESTRICT"))
    program_id         = Column(Integer, ForeignKey("loanprogram.program_id", ondelete="RESTRICT"))
    imf_account_id     = Column(Integer, ForeignKey("imf_account.imf_account_id", ondelete="RESTRICT"))
    currency_code      = Column(String(10), ForeignKey("currency.currency_code", ondelete="RESTRICT"))
    loan_amount        = Column(Numeric)
    interest_rate      = Column(Numeric)
    start_date         = Column(Date)
    end_date           = Column(Date)
    status             = Column(String(50))
    no_of_installments = Column(Integer)   # drives automatic installment schedule


class LoanCondition(Base):
    __tablename__ = "loancondition"

    condition_id         = Column(Integer, primary_key=True, index=True)
    program_id           = Column(Integer, ForeignKey("loanprogram.program_id", ondelete="CASCADE"))
    condition_type       = Column(String(100))
    description          = Column(Text)
    threshold_value      = Column(Numeric)
    eligibility_criteria = Column(Text)


class LoanConditionMapping(Base):
    __tablename__ = "loanconditionmapping"

    loan_id      = Column(Integer, ForeignKey("loan.loan_id", ondelete="CASCADE"), primary_key=True)
    condition_id = Column(Integer, ForeignKey("loancondition.condition_id", ondelete="CASCADE"), primary_key=True)


# ─────────────────────────────────────────────
# ECONOMIC DATA
# ─────────────────────────────────────────────

class EconomicIndicator(Base):
    __tablename__ = "economicindicator"

    indicator_id        = Column(Integer, primary_key=True, index=True)
    country_id          = Column(Integer, ForeignKey("country.country_id", ondelete="CASCADE"))
    record_date         = Column(Date)
    CPI                 = Column(Numeric)
    industrial_output   = Column(Numeric)
    agricultural_output = Column(Numeric)
    services_output     = Column(Numeric)
    money_supply        = Column(Numeric)
    interest_rate       = Column(Numeric)
    exchange_rate       = Column(Numeric)

    __table_args__ = (UniqueConstraint("country_id", "record_date"),)


class EconomicRecord(Base):
    __tablename__ = "economicrecord"

    record_id    = Column(Integer, primary_key=True, index=True)
    indicator_id = Column(Integer, ForeignKey("economicindicator.indicator_id", ondelete="CASCADE"))
    GDP          = Column(Numeric)
    inflation    = Column(Numeric)


class ExchangeRate(Base):
    __tablename__ = "exchangerate"

    exchange_rate_id = Column(Integer, primary_key=True, index=True)
    from_currency    = Column(String(10), ForeignKey("currency.currency_code", ondelete="RESTRICT"))
    to_currency      = Column(String(10), ForeignKey("currency.currency_code", ondelete="RESTRICT"))
    rate             = Column(Numeric)
    rate_date        = Column(Date)


# ─────────────────────────────────────────────
# FINANCIAL TRANSACTIONS
# ─────────────────────────────────────────────

class FinancialTransaction(Base):
    __tablename__ = "financialtransaction"

    transaction_id   = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    imf_account_id   = Column(Integer, ForeignKey("imf_account.imf_account_id", ondelete="RESTRICT"))
    currency_code    = Column(String(10), ForeignKey("currency.currency_code", ondelete="RESTRICT"))
    amount           = Column(Numeric)
    transaction_type = Column(String(50))
    transaction_date = Column(DateTime)
    reference        = Column(Text)


# ─────────────────────────────────────────────
# DISBURSEMENT / REPAYMENT
# ─────────────────────────────────────────────

class LoanDisbursement(Base):
    __tablename__ = "loandisbursement"

    loan_id           = Column(Integer, ForeignKey("loan.loan_id", ondelete="CASCADE"), primary_key=True)
    disbursement_no   = Column(Integer, primary_key=True)
    imf_account_id    = Column(Integer, ForeignKey("imf_account.imf_account_id", ondelete="RESTRICT"))
    amount            = Column(Numeric)
    disbursement_date = Column(Date)
    status            = Column(String(50))


class Repayment(Base):
    __tablename__ = "repayment"

    loan_id             = Column(Integer, ForeignKey("loan.loan_id", ondelete="CASCADE"), primary_key=True)
    repayment_no        = Column(Integer, primary_key=True)
    amount_paid         = Column(Numeric)
    payment_date        = Column(Date)
    outstanding_balance = Column(Numeric)
    # no_of_installments column REMOVED from repayment — installments are
    # a fixed per-loan schedule, not a per-repayment concept.


# ─────────────────────────────────────────────
# INSTALLMENT  (fixed schedule — auto-generated on first disbursement)
# ─────────────────────────────────────────────
# PK: (loan_id, installment_no)
# NO repayment_no column — this is a loan-level schedule, not repayment-linked.

class Installment(Base):
    __tablename__ = "installment"

    loan_id        = Column(Integer, ForeignKey("loan.loan_id", ondelete="CASCADE"), primary_key=True)
    installment_no = Column(Integer, primary_key=True)
    due_date       = Column(Date)
    amount_due     = Column(Numeric)
    amount_paid    = Column(Numeric)
    status         = Column(String(50))


# ─────────────────────────────────────────────
# TRANSACTION LINKING TABLES
# ─────────────────────────────────────────────

class DisbursementTransaction(Base):
    __tablename__ = "disbursementtransaction"

    transaction_id  = Column(Integer, ForeignKey("financialtransaction.transaction_id", ondelete="CASCADE"), primary_key=True)
    loan_id         = Column(Integer)
    disbursement_no = Column(Integer)

    __table_args__ = (
        ForeignKeyConstraint(
            ["loan_id", "disbursement_no"],
            ["loandisbursement.loan_id", "loandisbursement.disbursement_no"],
            ondelete="CASCADE",
        ),
    )


class RepaymentTransaction(Base):
    __tablename__ = "repaymenttransaction"

    transaction_id = Column(Integer, ForeignKey("financialtransaction.transaction_id", ondelete="CASCADE"), primary_key=True)
    loan_id        = Column(Integer)
    repayment_no   = Column(Integer)

    __table_args__ = (
        ForeignKeyConstraint(
            ["loan_id", "repayment_no"],
            ["repayment.loan_id", "repayment.repayment_no"],
            ondelete="CASCADE",
        ),
    )


# ─────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "auditlog"

    user_id         = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    log_id          = Column(Integer, primary_key=True)
    action          = Column(Text)
    log_timestamp   = Column(DateTime)
    entity_affected = Column(String(100))
