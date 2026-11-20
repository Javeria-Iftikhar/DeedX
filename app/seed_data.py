"""
seed_data.py  —  Populates all 21 tables with realistic IMF sample data.

Run once after tables exist:
    python -m app.seed_data

Or via bootstrap_dev.py / reseed_dev.py.
"""

from datetime import date, datetime
from decimal import Decimal

from app.database import SessionLocal
from app import models
from app.auth.hashing import hash_password


def seed_data(*, force: bool = False) -> None:
    """Insert canonical IMF sample data (same records as the original schema seed)."""
    db = SessionLocal()
    try:
        if db.query(models.Currency).first() and not force:
            print("Database already seeded — skipping.")
            return

        if force:
            _clear_all(db)

        print("Seeding canonical IMF dataset…")

        # 1. Currency
        db.add_all([
            models.Currency(currency_code="USD", currency_name="US Dollar", symbol="$", exchange_regime="Floating"),
            models.Currency(currency_code="PKR", currency_name="Pakistani Rupee", symbol="Rs", exchange_regime="Managed Float"),
            models.Currency(currency_code="ARS", currency_name="Argentine Peso", symbol="$", exchange_regime="Floating"),
            models.Currency(currency_code="EUR", currency_name="Euro", symbol="€", exchange_regime="Floating"),
            models.Currency(currency_code="EGP", currency_name="Egyptian Pound", symbol="£", exchange_regime="Managed Float"),
        ])
        db.flush()

        # 2. Country
        db.add_all([
            models.Country(currency_code="PKR", name="Pakistan", region="Asia", population=240_000_000),
            models.Country(currency_code="ARS", name="Argentina", region="South America", population=45_000_000),
            models.Country(currency_code="EGP", name="Egypt", region="Africa", population=104_000_000),
            models.Country(currency_code="EUR", name="Greece", region="Europe", population=10_600_000),
        ])
        db.flush()

        pakistan = db.query(models.Country).filter_by(name="Pakistan").one()
        argentina = db.query(models.Country).filter_by(name="Argentina").one()
        egypt = db.query(models.Country).filter_by(name="Egypt").one()
        greece = db.query(models.Country).filter_by(name="Greece").one()

        # 3. LoanProgram
        db.add_all([
            models.LoanProgram(
                program_name="EFF", description="Extended Fund Facility — long-term balance of payments support",
                max_amount=Decimal("50000000000"), interest_policy="Variable",
            ),
            models.LoanProgram(
                program_name="SBA", description="Stand-By Arrangement — short-term crisis relief",
                max_amount=Decimal("20000000000"), interest_policy="Fixed",
            ),
            models.LoanProgram(
                program_name="RFI", description="Rapid Financing Instrument — emergency disbursement",
                max_amount=Decimal("5000000000"), interest_policy="Concessional",
            ),
            models.LoanProgram(
                program_name="ECF", description="Extended Credit Facility — low-income country support",
                max_amount=Decimal("10000000000"), interest_policy="Concessional",
            ),
        ])
        db.flush()

        eff = db.query(models.LoanProgram).filter_by(program_name="EFF").one()
        sba = db.query(models.LoanProgram).filter_by(program_name="SBA").one()
        ecf = db.query(models.LoanProgram).filter_by(program_name="ECF").one()

        # 4. IMF Account
        db.add_all([
            models.IMFAccount(account_number="IMF-001", account_type="General Fund", balance=Decimal("80000000000"), created_at=datetime(2020, 1, 1)),
            models.IMFAccount(account_number="IMF-002", account_type="Special Drawing", balance=Decimal("30000000000"), created_at=datetime(2021, 3, 15)),
            models.IMFAccount(account_number="IMF-003", account_type="Concessional", balance=Decimal("15000000000"), created_at=datetime(2021, 6, 1)),
        ])
        db.flush()

        acct1 = db.query(models.IMFAccount).filter_by(account_number="IMF-001").one()
        acct2 = db.query(models.IMFAccount).filter_by(account_number="IMF-002").one()
        acct3 = db.query(models.IMFAccount).filter_by(account_number="IMF-003").one()

        # 5. Users (IMF staff — referenced by transactions / audit)
        db.add_all([
            models.User(name="Ali Khan", email="ali@imf.org", password=hash_password("ali123")),
            models.User(name="Sara Ahmed", email="sara@imf.org", password="hashed_pass_2"),
            models.User(name="John Miller", email="john@imf.org", password=hash_password("john123")),
            models.User(name="Fatima Malik", email="fatima@imf.org", password="hashed_pass_4"),
            models.User(name="Carlos Ruiz", email="carlos@imf.org", password="hashed_pass_5"),
        ])
        db.flush()

        ali = db.query(models.User).filter_by(email="ali@imf.org").one()
        sara = db.query(models.User).filter_by(email="sara@imf.org").one()
        john = db.query(models.User).filter_by(email="john@imf.org").one()
        fatima = db.query(models.User).filter_by(email="fatima@imf.org").one()
        carlos = db.query(models.User).filter_by(email="carlos@imf.org").one()

        # 6. Admin
        db.add_all([
            models.Admin(user_id=ali.user_id, admin_type="Super Admin", access_scope="Global", last_login=datetime(2026, 4, 10)),
            models.Admin(user_id=john.user_id, admin_type="Regional", access_scope="Asia", last_login=datetime(2026, 4, 12)),
        ])

        # 7. Officer
        db.add_all([
            models.Officer(user_id=sara.user_id, department="Loans", designation="Senior Officer", approval_limit=Decimal("5000000000")),
            models.Officer(user_id=carlos.user_id, department="Latin America", designation="Loan Officer", approval_limit=Decimal("3000000000")),
        ])

        # 8. EconomicAnalyst
        db.add_all([
            models.EconomicAnalyst(user_id=fatima.user_id, specialization="Macroeconomics", organization="IMF Research", report_access_level="Full"),
        ])
        db.flush()

        # 9. Loan
        db.add_all([
            models.Loan(
                country_id=pakistan.country_id, program_id=eff.program_id, imf_account_id=acct1.imf_account_id,
                currency_code="USD", loan_amount=Decimal("3000000000"), interest_rate=Decimal("6.0"),
                start_date=date(2023, 7, 1), end_date=date(2026, 7, 1), no_of_installments=12, status="Active",
            ),
            models.Loan(
                country_id=argentina.country_id, program_id=sba.program_id, imf_account_id=acct2.imf_account_id,
                currency_code="USD", loan_amount=Decimal("4400000000"), interest_rate=Decimal("5.5"),
                start_date=date(2022, 3, 1), end_date=date(2025, 3, 1), no_of_installments=10, status="Active",
            ),
            models.Loan(
                country_id=egypt.country_id, program_id=ecf.program_id, imf_account_id=acct3.imf_account_id,
                currency_code="USD", loan_amount=Decimal("3000000000"), interest_rate=Decimal("2.0"),
                start_date=date(2023, 1, 1), end_date=date(2026, 12, 31), no_of_installments=8, status="Active",
            ),
            models.Loan(
                country_id=greece.country_id, program_id=eff.program_id, imf_account_id=acct1.imf_account_id,
                currency_code="EUR", loan_amount=Decimal("8500000000"), interest_rate=Decimal("4.0"),
                start_date=date(2010, 5, 1), end_date=date(2014, 5, 1), no_of_installments=16, status="Completed",
            ),
        ])
        db.flush()

        pak_loan = db.query(models.Loan).filter_by(country_id=pakistan.country_id).one()
        arg_loan = db.query(models.Loan).filter_by(country_id=argentina.country_id).one()
        egy_loan = db.query(models.Loan).filter_by(country_id=egypt.country_id).one()

        # 10. LoanCondition
        db.add_all([
            models.LoanCondition(program_id=eff.program_id, condition_type="Fiscal", description="Reduce budget deficit below 5% of GDP", threshold_value=Decimal("5"), eligibility_criteria="Deficit < 5% GDP"),
            models.LoanCondition(program_id=eff.program_id, condition_type="Monetary", description="Maintain inflation below 10%", threshold_value=Decimal("10"), eligibility_criteria="Inflation < 10%"),
            models.LoanCondition(program_id=sba.program_id, condition_type="Structural", description="Implement pension reform within 18 months", threshold_value=Decimal("18"), eligibility_criteria="Reform enacted"),
            models.LoanCondition(program_id=ecf.program_id, condition_type="Social", description="Protect social spending floor at 4% of GDP", threshold_value=Decimal("4"), eligibility_criteria="Social spend ≥ 4% GDP"),
        ])
        db.flush()

        cond_fiscal = db.query(models.LoanCondition).filter_by(program_id=eff.program_id, condition_type="Fiscal").one()
        cond_monetary = db.query(models.LoanCondition).filter_by(program_id=eff.program_id, condition_type="Monetary").one()
        cond_struct = db.query(models.LoanCondition).filter_by(program_id=sba.program_id, condition_type="Structural").one()
        cond_social = db.query(models.LoanCondition).filter_by(program_id=ecf.program_id, condition_type="Social").one()

        # 11. LoanConditionMapping
        db.add_all([
            models.LoanConditionMapping(loan_id=pak_loan.loan_id, condition_id=cond_fiscal.condition_id),
            models.LoanConditionMapping(loan_id=pak_loan.loan_id, condition_id=cond_monetary.condition_id),
            models.LoanConditionMapping(loan_id=arg_loan.loan_id, condition_id=cond_struct.condition_id),
            models.LoanConditionMapping(loan_id=egy_loan.loan_id, condition_id=cond_social.condition_id),
        ])

        # 12. EconomicIndicator
        db.add_all([
            models.EconomicIndicator(country_id=pakistan.country_id, record_date=date(2023, 1, 1), CPI=Decimal("148.0"), industrial_output=Decimal("58.0"), agricultural_output=Decimal("39.0"), services_output=Decimal("68.0"), money_supply=Decimal("2450.0"), interest_rate=Decimal("11.8"), exchange_rate=Decimal("276.0")),
            models.EconomicIndicator(country_id=argentina.country_id, record_date=date(2023, 1, 1), CPI=Decimal("211.4"), industrial_output=Decimal("74.0"), agricultural_output=Decimal("62.0"), services_output=Decimal("91.0"), money_supply=Decimal("8500.0"), interest_rate=Decimal("97.0"), exchange_rate=Decimal("350.0")),
            models.EconomicIndicator(country_id=egypt.country_id, record_date=date(2023, 1, 1), CPI=Decimal("126.0"), industrial_output=Decimal("81.0"), agricultural_output=Decimal("55.0"), services_output=Decimal("77.0"), money_supply=Decimal("4200.0"), interest_rate=Decimal("16.25"), exchange_rate=Decimal("30.9")),
            models.EconomicIndicator(country_id=greece.country_id, record_date=date(2023, 1, 1), CPI=Decimal("119.0"), industrial_output=Decimal("91.0"), agricultural_output=Decimal("44.0"), services_output=Decimal("102.0"), money_supply=Decimal("1800.0"), interest_rate=Decimal("4.0"), exchange_rate=Decimal("1.09")),
        ])
        db.flush()

        pak_ind = db.query(models.EconomicIndicator).filter_by(country_id=pakistan.country_id).one()
        arg_ind = db.query(models.EconomicIndicator).filter_by(country_id=argentina.country_id).one()
        egy_ind = db.query(models.EconomicIndicator).filter_by(country_id=egypt.country_id).one()
        grc_ind = db.query(models.EconomicIndicator).filter_by(country_id=greece.country_id).one()

        # 13. EconomicRecord
        db.add_all([
            models.EconomicRecord(indicator_id=pak_ind.indicator_id, GDP=Decimal("372"), inflation=Decimal("29.2")),
            models.EconomicRecord(indicator_id=arg_ind.indicator_id, GDP=Decimal("633"), inflation=Decimal("94.8")),
            models.EconomicRecord(indicator_id=egy_ind.indicator_id, GDP=Decimal("476"), inflation=Decimal("31.5")),
            models.EconomicRecord(indicator_id=grc_ind.indicator_id, GDP=Decimal("219"), inflation=Decimal("4.2")),
        ])

        # 14. ExchangeRate
        db.add_all([
            models.ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("276.0"), rate_date=date(2023, 1, 1)),
            models.ExchangeRate(from_currency="USD", to_currency="ARS", rate=Decimal("350.0"), rate_date=date(2023, 1, 1)),
            models.ExchangeRate(from_currency="USD", to_currency="EGP", rate=Decimal("30.9"), rate_date=date(2023, 1, 1)),
            models.ExchangeRate(from_currency="USD", to_currency="EUR", rate=Decimal("0.92"), rate_date=date(2023, 1, 1)),
            models.ExchangeRate(from_currency="EUR", to_currency="USD", rate=Decimal("1.09"), rate_date=date(2023, 1, 1)),
            models.ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("285.0"), rate_date=date(2024, 1, 1)),
        ])

        # 15. LoanDisbursement
        db.add_all([
            models.LoanDisbursement(loan_id=pak_loan.loan_id, disbursement_no=1, imf_account_id=acct1.imf_account_id, amount=Decimal("1000000000"), disbursement_date=date(2023, 7, 18), status="Completed"),
            models.LoanDisbursement(loan_id=pak_loan.loan_id, disbursement_no=2, imf_account_id=acct1.imf_account_id, amount=Decimal("1000000000"), disbursement_date=date(2024, 1, 15), status="Completed"),
            models.LoanDisbursement(loan_id=pak_loan.loan_id, disbursement_no=3, imf_account_id=acct1.imf_account_id, amount=Decimal("1000000000"), disbursement_date=date(2024, 7, 10), status="Pending"),
            models.LoanDisbursement(loan_id=arg_loan.loan_id, disbursement_no=1, imf_account_id=acct2.imf_account_id, amount=Decimal("2200000000"), disbursement_date=date(2022, 3, 20), status="Completed"),
            models.LoanDisbursement(loan_id=arg_loan.loan_id, disbursement_no=2, imf_account_id=acct2.imf_account_id, amount=Decimal("2200000000"), disbursement_date=date(2023, 3, 20), status="Completed"),
            models.LoanDisbursement(loan_id=egy_loan.loan_id, disbursement_no=1, imf_account_id=acct3.imf_account_id, amount=Decimal("1500000000"), disbursement_date=date(2023, 2, 1), status="Completed"),
        ])

        # 16. Repayment
        db.add_all([
            models.Repayment(loan_id=pak_loan.loan_id, repayment_no=1, amount_paid=Decimal("300000000"), payment_date=date(2024, 7, 1), outstanding_balance=Decimal("2700000000")),
            models.Repayment(loan_id=arg_loan.loan_id, repayment_no=1, amount_paid=Decimal("500000000"), payment_date=date(2023, 9, 1), outstanding_balance=Decimal("3900000000")),
            models.Repayment(loan_id=egy_loan.loan_id, repayment_no=1, amount_paid=Decimal("200000000"), payment_date=date(2024, 2, 1), outstanding_balance=Decimal("2800000000")),
        ])

        # 17. Installment
        db.add_all([
            models.Installment(loan_id=pak_loan.loan_id, installment_no=1, due_date=date(2024, 7, 1), amount_due=Decimal("75000000"), amount_paid=Decimal("75000000"), status="Paid"),
            models.Installment(loan_id=pak_loan.loan_id, installment_no=2, due_date=date(2024, 10, 1), amount_due=Decimal("75000000"), amount_paid=Decimal("75000000"), status="Paid"),
            models.Installment(loan_id=pak_loan.loan_id, installment_no=3, due_date=date(2025, 1, 1), amount_due=Decimal("75000000"), amount_paid=Decimal("75000000"), status="Paid"),
            models.Installment(loan_id=pak_loan.loan_id, installment_no=4, due_date=date(2025, 4, 1), amount_due=Decimal("75000000"), amount_paid=Decimal("0"), status="Pending"),
            models.Installment(loan_id=arg_loan.loan_id, installment_no=1, due_date=date(2023, 9, 1), amount_due=Decimal("166666667"), amount_paid=Decimal("166666667"), status="Paid"),
            models.Installment(loan_id=arg_loan.loan_id, installment_no=2, due_date=date(2023, 12, 1), amount_due=Decimal("166666667"), amount_paid=Decimal("166666667"), status="Paid"),
            models.Installment(loan_id=arg_loan.loan_id, installment_no=3, due_date=date(2024, 3, 1), amount_due=Decimal("166666666"), amount_paid=Decimal("0"), status="Overdue"),
            models.Installment(loan_id=egy_loan.loan_id, installment_no=1, due_date=date(2024, 2, 1), amount_due=Decimal("100000000"), amount_paid=Decimal("100000000"), status="Paid"),
            models.Installment(loan_id=egy_loan.loan_id, installment_no=2, due_date=date(2024, 8, 1), amount_due=Decimal("100000000"), amount_paid=Decimal("0"), status="Pending"),
        ])

        # 18. FinancialTransaction
        txns = [
            models.FinancialTransaction(user_id=sara.user_id, imf_account_id=acct1.imf_account_id, currency_code="USD", amount=Decimal("1000000000"), transaction_type="Disbursement", transaction_date=datetime(2023, 7, 18), reference="PAK-DISB-001"),
            models.FinancialTransaction(user_id=sara.user_id, imf_account_id=acct1.imf_account_id, currency_code="USD", amount=Decimal("1000000000"), transaction_type="Disbursement", transaction_date=datetime(2024, 1, 15), reference="PAK-DISB-002"),
            models.FinancialTransaction(user_id=carlos.user_id, imf_account_id=acct2.imf_account_id, currency_code="USD", amount=Decimal("2200000000"), transaction_type="Disbursement", transaction_date=datetime(2022, 3, 20), reference="ARG-DISB-001"),
            models.FinancialTransaction(user_id=carlos.user_id, imf_account_id=acct3.imf_account_id, currency_code="USD", amount=Decimal("1500000000"), transaction_type="Disbursement", transaction_date=datetime(2023, 2, 1), reference="EGY-DISB-001"),
            models.FinancialTransaction(user_id=sara.user_id, imf_account_id=acct1.imf_account_id, currency_code="USD", amount=Decimal("300000000"), transaction_type="Repayment", transaction_date=datetime(2024, 7, 1), reference="PAK-REP-001"),
            models.FinancialTransaction(user_id=carlos.user_id, imf_account_id=acct2.imf_account_id, currency_code="USD", amount=Decimal("500000000"), transaction_type="Repayment", transaction_date=datetime(2023, 9, 1), reference="ARG-REP-001"),
            models.FinancialTransaction(user_id=sara.user_id, imf_account_id=acct3.imf_account_id, currency_code="USD", amount=Decimal("200000000"), transaction_type="Repayment", transaction_date=datetime(2024, 2, 1), reference="EGY-REP-001"),
        ]
        db.add_all(txns)
        db.flush()

        def txn_by_ref(ref: str) -> models.FinancialTransaction:
            return db.query(models.FinancialTransaction).filter_by(reference=ref).one()

        # 19. DisbursementTransaction
        db.add_all([
            models.DisbursementTransaction(transaction_id=txn_by_ref("PAK-DISB-001").transaction_id, loan_id=pak_loan.loan_id, disbursement_no=1),
            models.DisbursementTransaction(transaction_id=txn_by_ref("PAK-DISB-002").transaction_id, loan_id=pak_loan.loan_id, disbursement_no=2),
            models.DisbursementTransaction(transaction_id=txn_by_ref("ARG-DISB-001").transaction_id, loan_id=arg_loan.loan_id, disbursement_no=1),
            models.DisbursementTransaction(transaction_id=txn_by_ref("EGY-DISB-001").transaction_id, loan_id=egy_loan.loan_id, disbursement_no=1),
        ])

        # 20. RepaymentTransaction
        db.add_all([
            models.RepaymentTransaction(transaction_id=txn_by_ref("PAK-REP-001").transaction_id, loan_id=pak_loan.loan_id, repayment_no=1),
            models.RepaymentTransaction(transaction_id=txn_by_ref("ARG-REP-001").transaction_id, loan_id=arg_loan.loan_id, repayment_no=1),
            models.RepaymentTransaction(transaction_id=txn_by_ref("EGY-REP-001").transaction_id, loan_id=egy_loan.loan_id, repayment_no=1),
        ])

        # 21. AuditLog
        db.add_all([
            models.AuditLog(user_id=ali.user_id, log_id=1, action="INSERT", log_timestamp=datetime(2023, 7, 18, 9, 0), entity_affected="Loan"),
            models.AuditLog(user_id=sara.user_id, log_id=1, action="INSERT", log_timestamp=datetime(2023, 7, 18, 10, 0), entity_affected="LoanDisbursement"),
            models.AuditLog(user_id=sara.user_id, log_id=2, action="UPDATE", log_timestamp=datetime(2024, 7, 1, 11, 0), entity_affected="Repayment"),
            models.AuditLog(user_id=carlos.user_id, log_id=1, action="INSERT", log_timestamp=datetime(2022, 3, 20, 8, 30), entity_affected="LoanDisbursement"),
            models.AuditLog(user_id=fatima.user_id, log_id=1, action="INSERT", log_timestamp=datetime(2023, 2, 1, 9, 15), entity_affected="EconomicRecord"),
            models.AuditLog(user_id=john.user_id, log_id=1, action="SELECT", log_timestamp=datetime(2026, 4, 12, 14, 0), entity_affected="Country"),
        ])

        db.commit()
        print("All 21 tables seeded successfully (canonical IMF dataset).")
    finally:
        db.close()


def _clear_all(db) -> None:
    """Delete seeded rows in reverse FK order (keeps schema intact)."""
    for model in (
        models.AuditLog, models.RepaymentTransaction, models.DisbursementTransaction,
        models.FinancialTransaction, models.Installment, models.Repayment,
        models.LoanDisbursement, models.ExchangeRate, models.EconomicRecord,
        models.EconomicIndicator, models.LoanConditionMapping, models.LoanCondition,
        models.Loan, models.EconomicAnalyst, models.Officer, models.Admin,
        models.User, models.IMFAccount, models.LoanProgram, models.Country, models.Currency,
    ):
        db.query(model).delete()
    db.commit()


if __name__ == "__main__":
    seed_data()
