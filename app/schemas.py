"""
schemas.py  —  Pydantic request/response models for all 21 tables.

AUTOMATED FIELD POLICY
───────────────────────
The following fields are managed exclusively by the backend / financial_service
and must NEVER appear in *Create or *Update schemas (Swagger UI input):

  • Loan.status                   — set by financial_service state machine
  • Loan.no_of_installments       — user-supplied at creation; drives schedule generation
  • LoanDisbursement.status       — set by financial_service
  • LoanDisbursement.disbursement_no — auto-sequenced server-side
  • Repayment.repayment_no        — auto-sequenced server-side
  • Repayment.outstanding_balance — computed (loan_amount − cumulative paid)
  • Repayment.total_paid          — derived SUM; response-only
  • Installment.*                 — entire table is generated on first disbursement;
                                    no user POST route. installment_no, amount_due,
                                    amount_paid, status all set by backend.
  • IMFAccount.balance            — starts at opening_balance on creation;
                                    modified only via PATCH /accounts/{id}/adjust
  • IMFAccount.created_at         — server timestamp on creation
  • Admin.last_login              — set by auth layer on login
  • AuditLog.*                    — entirely system-generated; no POST route
  • FinancialTransaction.*        — entirely system-generated; no POST route
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────
# CURRENCY
# ─────────────────────────────────────────────

class CurrencyCreate(BaseModel):
    currency_code: str
    currency_name: Optional[str] = None
    symbol: Optional[str] = None
    exchange_regime: Optional[str] = None

class CurrencyResponse(BaseModel):
    currency_code: str
    currency_name: Optional[str] = None
    symbol: Optional[str] = None
    exchange_regime: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# COUNTRY
# ─────────────────────────────────────────────

class CountryCreate(BaseModel):
    currency_code: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=100)
    region: Optional[str] = None
    population: Optional[int] = None

    @field_validator("currency_code", "name", mode="before")
    @classmethod
    def strip_required_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, v: str) -> str:
        return v.upper()

class CountryResponse(BaseModel):
    country_id: int
    currency_code: str
    name: str
    region: Optional[str] = None
    population: Optional[int] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LOAN PROGRAM
# ─────────────────────────────────────────────

class LoanProgramCreate(BaseModel):
    program_name: str
    description: Optional[str] = None
    max_amount: Optional[Decimal] = None
    interest_policy: Optional[str] = None

class LoanProgramResponse(BaseModel):
    program_id: int
    program_name: str
    description: Optional[str] = None
    max_amount: Optional[Decimal] = None
    interest_policy: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# IMF ACCOUNT
# ─────────────────────────────────────────────
# opening_balance  — accepted on creation so accounts can be pre-funded.
#                    Stored as balance in the DB. Separate from PATCH /adjust.
# balance          — response only (reflects current live balance)
# created_at       — server-generated; never accepted from user

class IMFAccountCreate(BaseModel):
    account_number: str
    account_type: str
    opening_balance: float = 0      # user may fund the account on creation

    @field_validator("account_type", mode="before")
    @classmethod
    def strip_account_type(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("account_type")
    @classmethod
    def require_account_type(cls, v: str) -> str:
        if not v:
            raise ValueError("account_type is required")
        return v

class IMFAccountResponse(BaseModel):
    imf_account_id: int
    account_number: str
    account_type: Optional[str] = None
    balance: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class UserResponse(BaseModel):
    user_id: int
    name: str
    email: str
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────
# last_login — set by auth layer on login; never accepted from user

class AdminCreate(BaseModel):
    user_id: int
    admin_type: Optional[str] = None
    access_scope: Optional[str] = None

class AdminResponse(BaseModel):
    user_id: int
    admin_type: Optional[str] = None
    access_scope: Optional[str] = None
    last_login: Optional[datetime] = None   # response only
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# OFFICER
# ─────────────────────────────────────────────

class OfficerCreate(BaseModel):
    user_id: int
    department: Optional[str] = None
    designation: Optional[str] = None
    approval_limit: Optional[Decimal] = None
    approval_role: Optional[str] = None
    approval_scope: Optional[str] = None

class OfficerResponse(BaseModel):
    user_id: int
    department: Optional[str] = None
    designation: Optional[str] = None
    approval_limit: Optional[Decimal] = None
    approval_role: Optional[str] = None
    approval_scope: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ECONOMIC ANALYST
# ─────────────────────────────────────────────

class EconomicAnalystCreate(BaseModel):
    user_id: int
    specialization: Optional[str] = None
    organization: Optional[str] = None
    report_access_level: Optional[str] = None

class EconomicAnalystResponse(BaseModel):
    user_id: int
    specialization: Optional[str] = None
    organization: Optional[str] = None
    report_access_level: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LOAN
# ─────────────────────────────────────────────
# status             — backend sets "Pending" on creation; never user input
# no_of_installments — user supplies this; drives the installment schedule
#                      that is auto-generated on first disbursement

class LoanCreate(BaseModel):
    country_id: int
    program_id: int
    imf_account_id: int
    currency_code: str
    loan_amount: Decimal
    interest_rate: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    no_of_installments: int             # required; used by installment schedule engine

class LoanUpdate(BaseModel):
    loan_amount: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    no_of_installments: Optional[int] = None
    # status intentionally omitted — managed by financial_service

class LoanResponse(BaseModel):
    loan_id: int
    country_id: int
    program_id: int
    imf_account_id: int
    currency_code: str
    loan_amount: Decimal
    interest_rate: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    no_of_installments: Optional[int] = None
    status: Optional[str] = None        # response only
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LOAN CONDITION
# ─────────────────────────────────────────────

class LoanConditionCreate(BaseModel):
    program_id: int
    condition_type: Optional[str] = None
    description: Optional[str] = None
    threshold_value: Optional[Decimal] = None
    eligibility_criteria: Optional[str] = None

class LoanConditionResponse(BaseModel):
    condition_id: int
    program_id: int
    condition_type: Optional[str] = None
    description: Optional[str] = None
    threshold_value: Optional[Decimal] = None
    eligibility_criteria: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LOAN CONDITION MAPPING
# ─────────────────────────────────────────────

class LoanConditionMappingCreate(BaseModel):
    loan_id: int
    condition_id: int

class LoanConditionMappingResponse(BaseModel):
    loan_id: int
    condition_id: int
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ECONOMIC INDICATOR
# ─────────────────────────────────────────────

class EconomicIndicatorCreate(BaseModel):
    country_id: int
    record_date: date
    CPI: Optional[Decimal] = None
    industrial_output: Optional[Decimal] = None
    agricultural_output: Optional[Decimal] = None
    services_output: Optional[Decimal] = None
    money_supply: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None

class EconomicIndicatorResponse(BaseModel):
    indicator_id: int
    country_id: int
    record_date: date
    CPI: Optional[Decimal] = None
    industrial_output: Optional[Decimal] = None
    agricultural_output: Optional[Decimal] = None
    services_output: Optional[Decimal] = None
    money_supply: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ECONOMIC RECORD  (derived — auto-computed from indicator)
# ─────────────────────────────────────────────

class EconomicRecordCreate(BaseModel):
    indicator_id: int
    GDP: Optional[Decimal] = None
    inflation: Optional[Decimal] = None

class EconomicRecordResponse(BaseModel):
    record_id: int
    indicator_id: int
    GDP: Optional[Decimal] = None
    inflation: Optional[Decimal] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# EXCHANGE RATE
# ─────────────────────────────────────────────

class ExchangeRateCreate(BaseModel):
    from_currency: str
    to_currency: str
    rate: Decimal
    rate_date: date

class ExchangeRateResponse(BaseModel):
    exchange_rate_id: int
    from_currency: str
    to_currency: str
    rate: Decimal
    rate_date: date
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# FINANCIAL TRANSACTION  (system-generated — no POST route)
# ─────────────────────────────────────────────

class FinancialTransactionCreate(BaseModel):
    """INTERNAL USE ONLY — never expose via POST route."""
    user_id: int
    imf_account_id: int
    currency_code: str
    amount: Decimal
    transaction_type: str

class FinancialTransactionResponse(BaseModel):
    transaction_id: int
    user_id: int
    imf_account_id: int
    currency_code: str
    amount: Decimal
    transaction_type: str
    transaction_date: Optional[datetime] = None  # response only
    reference: Optional[str] = None             # response only
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LOAN DISBURSEMENT
# ─────────────────────────────────────────────
# disbursement_no — auto-sequenced server-side
# status          — always "Pending" on creation; set by financial_service

class LoanDisbursementCreate(BaseModel):
    loan_id: int
    imf_account_id: int
    amount: Decimal
    disbursement_date: Optional[date] = None
    # disbursement_no intentionally omitted — auto-sequenced
    # status          intentionally omitted — set by financial_service

class LoanDisbursementResponse(BaseModel):
    loan_id: int
    disbursement_no: int            # response only
    imf_account_id: int
    amount: Decimal
    disbursement_date: Optional[date] = None
    status: Optional[str] = None   # response only
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# REPAYMENT
# ─────────────────────────────────────────────
# repayment_no        — auto-sequenced server-side
# outstanding_balance — computed by financial_service
# total_paid          — derived SUM; response-only
# no_of_installments  — REMOVED: installments are now a fixed schedule on the
#                        loan, not driven per-repayment

class RepaymentCreate(BaseModel):
    loan_id: int
    amount_paid: Decimal
    payment_date: Optional[date] = None
    # repayment_no        intentionally omitted — auto-sequenced
    # outstanding_balance intentionally omitted — computed
    # no_of_installments  intentionally omitted — schedule is per-loan, not per-repayment

class RepaymentResponse(BaseModel):
    loan_id: int
    repayment_no: int               # response only
    amount_paid: Decimal
    payment_date: date
    outstanding_balance: Decimal    # response only
    total_paid: Decimal             # response only
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# INSTALLMENT  (auto-generated on first disbursement — no POST route)
# ─────────────────────────────────────────────
# The entire installment schedule is created automatically when the first
# disbursement is processed. Users never create, update, or delete installments.
# All fields are system-managed:
#   installment_no — sequential (1..N)
#   amount_due     — loan_amount / no_of_installments
#   amount_paid    — updated by _apply_payment_to_installments()
#   status         — PENDING / PARTIAL / PAID; set by _apply_payment_to_installments()

class InstallmentResponse(BaseModel):
    loan_id: int
    installment_no: int
    due_date: Optional[date] = None
    amount_due: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None
    status: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# DISBURSEMENT TRANSACTION  (linking table — system-generated)
# ─────────────────────────────────────────────

class DisbursementTransactionCreate(BaseModel):
    """INTERNAL USE ONLY."""
    transaction_id: int
    loan_id: int
    disbursement_no: int

class DisbursementTransactionResponse(BaseModel):
    transaction_id: int
    loan_id: int
    disbursement_no: int
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# REPAYMENT TRANSACTION  (linking table — system-generated)
# ─────────────────────────────────────────────

class RepaymentTransactionCreate(BaseModel):
    """INTERNAL USE ONLY."""
    transaction_id: int
    loan_id: int
    repayment_no: int

class RepaymentTransactionResponse(BaseModel):
    transaction_id: int
    loan_id: int
    repayment_no: int
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# AUDIT LOG  (system-generated — no POST route)
# ─────────────────────────────────────────────

class AuditLogCreate(BaseModel):
    """INTERNAL USE ONLY."""
    user_id: int
    action: str
    entity_affected: Optional[str] = None

class AuditLogResponse(BaseModel):
    user_id: int
    log_id: int
    action: str
    log_timestamp: Optional[datetime] = None
    entity_affected: Optional[str] = None
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# FINANCIAL AUTOMATION REQUEST SCHEMAS
# Used by POST /process-disbursement/ and POST /process-repayment/
# These are the ONLY public entry points for financial actions.
# ─────────────────────────────────────────────

class ProcessDisbursementRequest(BaseModel):
    loan_id: int
    imf_account_id: int
    amount: Decimal
    disbursement_date: Optional[date] = None
    # actor_user_id intentionally omitted — always sourced from the authenticated JWT

class ProcessRepaymentRequest(BaseModel):
    loan_id: int
    amount_paid: Decimal
    payment_date: Optional[date] = None
    # actor_user_id intentionally omitted — always sourced from the authenticated JWT
