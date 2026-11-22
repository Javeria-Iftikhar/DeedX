"""
routers/loans.py — Routes for:
  Currency, Country, LoanProgram, IMFAccount,
  Loan, LoanCondition, LoanConditionMapping,
  LoanDisbursement, Repayment, Installment (read-only)

RBAC:
  • Currency / Country / LoanProgram / IMFAccount CRUD — Admin only
  • Loan create/update/delete                          — Admin or Officer
  • Loan read                                          — Admin or Officer
  • LoanCondition / LoanConditionMapping               — Admin or Officer
  • Disbursements (POST/GET)                           — Admin or Officer
  • Repayments (POST/GET)                              — Admin or Officer
  • Installments (GET only, auto-generated)            — Admin or Officer
  • DELETE on disbursements/repayments                 — Admin only

Audit logging after every successful mutating operation.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.auth.dependencies import get_db, require_admin, require_officer, require_staff
from app.crud import loans as crud
from app.services import financial_service as svc

router = APIRouter(tags=["Loans"])


# ─── CURRENCY ───────────────────────────────────────────────────────────────

@router.post("/currencies/", response_model=schemas.CurrencyResponse, tags=["Currency"])
def create_currency(
    data: schemas.CurrencyCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Create a new currency."""
    obj = crud.create_currency(db, data)
    write_audit_log(db, current_user.user_id, f"Created Currency code={data.currency_code}", "Currency")
    return obj


@router.get("/currencies/", response_model=list[schemas.CurrencyResponse], tags=["Currency"])
def list_currencies(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all currencies."""
    return crud.get_currencies(db)


@router.get("/currencies/{currency_code}", response_model=schemas.CurrencyResponse, tags=["Currency"])
def get_currency(
    currency_code: str,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific currency."""
    obj = crud.get_currency(db, currency_code)
    if not obj:
        raise HTTPException(404, "Currency not found")
    return obj


@router.delete("/currencies/{currency_code}", tags=["Currency"])
def delete_currency(
    currency_code: str,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a currency."""
    obj = crud.delete_currency(db, currency_code)
    if not obj:
        raise HTTPException(404, "Currency not found")
    write_audit_log(db, current_user.user_id, f"Deleted Currency code={currency_code}", "Currency")
    return {"msg": "deleted"}


# ─── COUNTRY ────────────────────────────────────────────────────────────────

def _require_currency(db: Session, currency_code: str) -> None:
    if not crud.get_currency(db, currency_code):
        raise HTTPException(
            status_code=400,
            detail=f"Currency '{currency_code}' does not exist. Add it under Currencies first.",
        )


@router.post("/countries/", response_model=schemas.CountryResponse, tags=["Country"])
def create_country(
    data: schemas.CountryCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Create a new country."""
    _require_currency(db, data.currency_code)
    obj = crud.create_country(db, data)
    write_audit_log(db, current_user.user_id, f"Created Country id={obj.country_id} name={data.name}", "Country")
    return obj


@router.get("/countries/", response_model=list[schemas.CountryResponse], tags=["Country"])
def list_countries(
    _user: models.User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """**Admin, Officer, or Analyst.** List all countries (reference data for loans & economics)."""
    return crud.get_countries(db)


@router.get("/countries/{country_id}", response_model=schemas.CountryResponse, tags=["Country"])
def get_country(
    country_id: int,
    _user: models.User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """**Admin, Officer, or Analyst.** Get a specific country."""
    obj = crud.get_country(db, country_id)
    if not obj:
        raise HTTPException(404, "Country not found")
    return obj


@router.put("/countries/{country_id}", response_model=schemas.CountryResponse, tags=["Country"])
def update_country(
    country_id: int,
    data: schemas.CountryCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Update a country."""
    if not crud.get_country(db, country_id):
        raise HTTPException(404, "Country not found")
    _require_currency(db, data.currency_code)
    obj = crud.update_country(db, country_id, data)
    if not obj:
        raise HTTPException(404, "Country not found")
    write_audit_log(db, current_user.user_id, f"Updated Country id={country_id}", "Country")
    return obj


@router.delete("/countries/{country_id}", tags=["Country"])
def delete_country(
    country_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a country."""
    obj = crud.delete_country(db, country_id)
    if not obj:
        raise HTTPException(404, "Country not found")
    write_audit_log(db, current_user.user_id, f"Deleted Country id={country_id}", "Country")
    return {"msg": "deleted"}


# ─── LOAN PROGRAM ───────────────────────────────────────────────────────────

@router.post("/programs/", response_model=schemas.LoanProgramResponse, tags=["Loan Program"])
def create_program(
    data: schemas.LoanProgramCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Create a new loan program."""
    obj = crud.create_loan_program(db, data)
    write_audit_log(db, current_user.user_id, f"Created LoanProgram id={obj.program_id} name={data.program_name}", "LoanProgram")
    return obj


@router.get("/programs/", response_model=list[schemas.LoanProgramResponse], tags=["Loan Program"])
def list_programs(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all loan programs."""
    return crud.get_loan_programs(db)


@router.get("/programs/{program_id}", response_model=schemas.LoanProgramResponse, tags=["Loan Program"])
def get_program(
    program_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific loan program."""
    obj = crud.get_loan_program(db, program_id)
    if not obj:
        raise HTTPException(404, "Loan program not found")
    return obj


@router.delete("/programs/{program_id}", tags=["Loan Program"])
def delete_program(
    program_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a loan program."""
    obj = crud.delete_loan_program(db, program_id)
    if not obj:
        raise HTTPException(404, "Loan program not found")
    write_audit_log(db, current_user.user_id, f"Deleted LoanProgram id={program_id}", "LoanProgram")
    return {"msg": "deleted"}


# ─── IMF ACCOUNT ────────────────────────────────────────────────────────────

@router.post("/accounts/", response_model=schemas.IMFAccountResponse, tags=["IMF Account"])
def create_account(
    data: schemas.IMFAccountCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Create a new IMF account."""
    obj = crud.create_imf_account(db, data)
    write_audit_log(db, current_user.user_id, f"Created IMFAccount id={obj.imf_account_id} number={data.account_number}", "IMFAccount")
    return obj


@router.get("/accounts/", response_model=list[schemas.IMFAccountResponse], tags=["IMF Account"])
def list_accounts(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all IMF accounts."""
    return crud.get_imf_accounts(db)


@router.get("/accounts/{imf_account_id}", response_model=schemas.IMFAccountResponse, tags=["IMF Account"])
def get_account(
    imf_account_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific IMF account."""
    obj = crud.get_imf_account(db, imf_account_id)
    if not obj:
        raise HTTPException(404, "IMF account not found")
    return obj


@router.patch("/accounts/{imf_account_id}/adjust", response_model=schemas.IMFAccountResponse, tags=["IMF Account"])
def adjust_balance(
    imf_account_id: int,
    adjustment_amount: float = Query(..., description="Amount to add (positive) or subtract (negative)"),
    reason: str = Query("", description="Reason for adjustment"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Manually adjust an IMF account balance."""
    obj = crud.adjust_imf_account_balance(db, imf_account_id, adjustment_amount, reason)
    if not obj:
        raise HTTPException(404, "IMF account not found")
    write_audit_log(db, current_user.user_id, f"Adjusted IMFAccount id={imf_account_id} by {adjustment_amount}: {reason}", "IMFAccount")
    return obj


@router.delete("/accounts/{imf_account_id}", tags=["IMF Account"])
def delete_account(
    imf_account_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete an IMF account."""
    obj = crud.delete_imf_account(db, imf_account_id)
    if not obj:
        raise HTTPException(404, "IMF account not found")
    write_audit_log(db, current_user.user_id, f"Deleted IMFAccount id={imf_account_id}", "IMFAccount")
    return {"msg": "deleted"}


# ─── LOAN ───────────────────────────────────────────────────────────────────

@router.post("/loans/", response_model=schemas.LoanResponse, tags=["Loan"])
def create_loan(
    data: schemas.LoanCreate,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Create a new loan (status set to Pending automatically)."""
    obj = crud.create_loan(db, data)
    write_audit_log(db, current_user.user_id, f"Created Loan id={obj.loan_id} amount={data.loan_amount}", "Loan")
    return obj


@router.get("/loans/", response_model=list[schemas.LoanResponse], tags=["Loan"])
def list_loans(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all loans."""
    return crud.get_loans(db)


@router.get("/loans/{loan_id}", response_model=schemas.LoanResponse, tags=["Loan"])
def get_loan(
    loan_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific loan."""
    obj = crud.get_loan(db, loan_id)
    if not obj:
        raise HTTPException(404, "Loan not found")
    return obj


@router.patch("/loans/{loan_id}", response_model=schemas.LoanResponse, tags=["Loan"])
def update_loan(
    loan_id: int,
    data: schemas.LoanUpdate,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Update loan details."""
    obj = crud.update_loan(db, loan_id, data)
    if not obj:
        raise HTTPException(404, "Loan not found")
    write_audit_log(db, current_user.user_id, f"Updated Loan id={loan_id}", "Loan")
    return obj


@router.delete("/loans/{loan_id}", tags=["Loan"])
def delete_loan(
    loan_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a loan record."""
    obj = crud.delete_loan(db, loan_id)
    if not obj:
        raise HTTPException(404, "Loan not found")
    write_audit_log(db, current_user.user_id, f"Deleted Loan id={loan_id}", "Loan")
    return {"msg": "deleted"}


# ─── LOAN CONDITION ─────────────────────────────────────────────────────────

@router.post("/conditions/", response_model=schemas.LoanConditionResponse, tags=["Loan Condition"])
def create_condition(
    data: schemas.LoanConditionCreate,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Create a new loan condition."""
    obj = crud.create_loan_condition(db, data)
    write_audit_log(db, current_user.user_id, f"Created LoanCondition id={obj.condition_id}", "LoanCondition")
    return obj


@router.get("/conditions/", response_model=list[schemas.LoanConditionResponse], tags=["Loan Condition"])
def list_conditions(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all loan conditions."""
    return crud.get_loan_conditions(db)


@router.get("/conditions/{condition_id}", response_model=schemas.LoanConditionResponse, tags=["Loan Condition"])
def get_condition(
    condition_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific loan condition."""
    obj = crud.get_loan_condition(db, condition_id)
    if not obj:
        raise HTTPException(404, "Condition not found")
    return obj


@router.delete("/conditions/{condition_id}", tags=["Loan Condition"])
def delete_condition(
    condition_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a loan condition."""
    obj = crud.delete_loan_condition(db, condition_id)
    if not obj:
        raise HTTPException(404, "Condition not found")
    write_audit_log(db, current_user.user_id, f"Deleted LoanCondition id={condition_id}", "LoanCondition")
    return {"msg": "deleted"}


# ─── LOAN CONDITION MAPPING ─────────────────────────────────────────────────

@router.post("/mappings/", response_model=schemas.LoanConditionMappingResponse, tags=["Mapping"])
def create_mapping(
    data: schemas.LoanConditionMappingCreate,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Link a condition to a loan."""
    obj = crud.create_mapping(db, data)
    write_audit_log(db, current_user.user_id, f"Created LoanConditionMapping loan_id={data.loan_id} condition_id={data.condition_id}", "LoanConditionMapping")
    return obj


@router.get("/mappings/", response_model=list[schemas.LoanConditionMappingResponse], tags=["Mapping"])
def list_mappings(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all loan-condition mappings."""
    return crud.get_mappings(db)


@router.get("/mappings/{loan_id}", response_model=list[schemas.LoanConditionMappingResponse], tags=["Mapping"])
def get_mappings_for_loan(
    loan_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get all condition mappings for a loan."""
    return crud.get_mappings_for_loan(db, loan_id)


@router.delete("/mappings/{loan_id}/{condition_id}", tags=["Mapping"])
def delete_mapping(
    loan_id: int,
    condition_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Remove a condition mapping from a loan."""
    obj = crud.delete_mapping(db, loan_id, condition_id)
    if not obj:
        raise HTTPException(404, "Mapping not found")
    write_audit_log(db, current_user.user_id, f"Deleted LoanConditionMapping loan_id={loan_id} condition_id={condition_id}", "LoanConditionMapping")
    return {"msg": "deleted"}


# ─── LOAN DISBURSEMENT ──────────────────────────────────────────────────────

@router.post("/disbursements/", response_model=schemas.LoanDisbursementResponse, tags=["Disbursement"])
def create_disbursement(
    data: schemas.LoanDisbursementCreate,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """
    **Admin or Officer.** Process a loan disbursement.
    Automatically sequences disbursement_no, sets status, generates the installment
    schedule on first disbursement, creates a FinancialTransaction, and writes an audit log.
    """
    try:
        obj = svc.process_disbursement(
            db,
            loan_id=data.loan_id,
            imf_account_id=data.imf_account_id,
            amount=data.amount,
            disbursement_date=data.disbursement_date,
            actor_user_id=current_user.user_id,
        )
        write_audit_log(db, current_user.user_id, f"Processed disbursement for Loan id={data.loan_id} amount={data.amount}", "LoanDisbursement")
        return obj
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Disbursement failed (rolled back): {e}")


@router.get("/disbursements/all/", response_model=list[schemas.LoanDisbursementResponse], tags=["Disbursement"])
def list_all_disbursements(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List every loan disbursement in the database."""
    return crud.get_all_disbursements(db)


@router.get("/disbursements/{loan_id}", response_model=list[schemas.LoanDisbursementResponse], tags=["Disbursement"])
def list_disbursements(
    loan_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all disbursements for a loan."""
    return crud.get_disbursements(db, loan_id)


@router.get("/disbursements/{loan_id}/{disbursement_no}", response_model=schemas.LoanDisbursementResponse, tags=["Disbursement"])
def get_disbursement(
    loan_id: int,
    disbursement_no: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific disbursement."""
    obj = crud.get_disbursement(db, loan_id, disbursement_no)
    if not obj:
        raise HTTPException(404, "Disbursement not found")
    return obj


@router.patch("/disbursements/{loan_id}/{disbursement_no}/status", tags=["Disbursement"])
def update_disbursement_status(
    loan_id: int,
    disbursement_no: int,
    status: str,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Update the status of a disbursement."""
    allowed_statuses = {"Pending", "Approved", "Disbursed", "Completed", "Cancelled"}
    if status not in allowed_statuses:
        raise HTTPException(400, f"Invalid status '{status}'. Allowed values: {sorted(allowed_statuses)}")
    obj = crud.update_disbursement_status(db, loan_id, disbursement_no, status)
    if not obj:
        raise HTTPException(404, "Disbursement not found")
    write_audit_log(db, current_user.user_id, f"Updated disbursement status loan_id={loan_id} disbursement_no={disbursement_no} -> {status}", "LoanDisbursement")
    return obj


@router.delete("/disbursements/{loan_id}/{disbursement_no}", tags=["Disbursement"])
def delete_disbursement(
    loan_id: int,
    disbursement_no: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a disbursement record."""
    obj = crud.delete_disbursement(db, loan_id, disbursement_no)
    if not obj:
        raise HTTPException(404, "Disbursement not found")
    write_audit_log(db, current_user.user_id, f"Deleted LoanDisbursement loan_id={loan_id} disbursement_no={disbursement_no}", "LoanDisbursement")
    return {"msg": "deleted"}


# ─── REPAYMENT ──────────────────────────────────────────────────────────────

def _build_repayment_response(db: Session, rp: models.Repayment) -> schemas.RepaymentResponse:
    total_paid = db.query(sqlfunc.sum(models.Repayment.amount_paid)).filter(
        models.Repayment.loan_id == rp.loan_id,
        models.Repayment.repayment_no <= rp.repayment_no,
    ).scalar() or 0
    return schemas.RepaymentResponse(
        loan_id=rp.loan_id,
        repayment_no=rp.repayment_no,
        amount_paid=rp.amount_paid,
        payment_date=rp.payment_date,
        outstanding_balance=rp.outstanding_balance,
        total_paid=total_paid,
    )


@router.post("/repayments/", response_model=schemas.RepaymentResponse, tags=["Repayment"])
def create_repayment(
    data: schemas.RepaymentCreate,
    current_user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """
    **Admin or Officer.** Process a loan repayment.
    Automatically sequences repayment_no, computes outstanding_balance,
    updates installment schedule, transitions loan status, and writes audit log.
    """
    try:
        rp = svc.process_repayment(
            db,
            loan_id=data.loan_id,
            amount_paid=data.amount_paid,
            payment_date=data.payment_date,
            actor_user_id=current_user.user_id,
        )
        write_audit_log(db, current_user.user_id, f"Processed repayment for Loan id={data.loan_id} amount={data.amount_paid}", "Repayment")
        return _build_repayment_response(db, rp)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Repayment failed (rolled back): {e}")


@router.get("/repayments/all/", response_model=list[schemas.RepaymentResponse], tags=["Repayment"])
def list_all_repayments(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List every repayment in the database."""
    return [_build_repayment_response(db, rp) for rp in crud.get_all_repayments(db)]


@router.get("/repayments/{loan_id}", response_model=list[schemas.RepaymentResponse], tags=["Repayment"])
def list_repayments(
    loan_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List all repayments for a loan."""
    return [_build_repayment_response(db, rp) for rp in crud.get_repayments(db, loan_id)]


@router.get("/repayments/{loan_id}/{repayment_no}", response_model=schemas.RepaymentResponse, tags=["Repayment"])
def get_repayment(
    loan_id: int,
    repayment_no: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific repayment."""
    rp = crud.get_repayment(db, loan_id, repayment_no)
    if not rp:
        raise HTTPException(404, "Repayment not found")
    return _build_repayment_response(db, rp)


@router.delete("/repayments/{loan_id}/{repayment_no}", tags=["Repayment"])
def delete_repayment(
    loan_id: int,
    repayment_no: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a repayment record."""
    obj = crud.delete_repayment(db, loan_id, repayment_no)
    if not obj:
        raise HTTPException(404, "Repayment not found")
    write_audit_log(db, current_user.user_id, f"Deleted Repayment loan_id={loan_id} repayment_no={repayment_no}", "Repayment")
    return {"msg": "deleted"}


# ─── INSTALLMENT (read-only — auto-generated on first disbursement) ──────────

@router.get("/installments/all/", response_model=list[schemas.InstallmentResponse], tags=["Installment"])
def list_all_installments(
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** List every installment schedule row in the database."""
    return crud.get_all_installments(db)


@router.get("/installments/{loan_id}", response_model=list[schemas.InstallmentResponse], tags=["Installment"])
def list_installments(
    loan_id: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """
    **Admin or Officer.** Returns the fixed installment schedule for a loan.
    Auto-generated when the first disbursement is processed. Read-only.
    """
    return crud.get_installments_for_loan(db, loan_id)


@router.get("/installments/{loan_id}/{installment_no}", response_model=schemas.InstallmentResponse, tags=["Installment"])
def get_installment(
    loan_id: int,
    installment_no: int,
    _user: models.User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    """**Admin or Officer.** Get a specific installment."""
    obj = crud.get_installment(db, loan_id, installment_no)
    if not obj:
        raise HTTPException(404, "Installment not found")
    return obj
