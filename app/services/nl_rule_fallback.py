"""
Offline rule-based NL planner (regex / keyword routing).

Used before Groq when NL_RULE_FALLBACK=true (default) to save API quota.
Groq is only called when no rule pattern matches.

Design notes:
- No hardcoded country names or region member lists anywhere in this file.
- Geography filters are always expressed as field/operator/value triples;
  the execution layer resolves them against the live DB.
- Multi-turn conversation is NOT supported here — this is a last-resort fallback.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException

from app.analytics_schemas.analytics import AnalyticsSpec, FilterSpec, MetricSpec, SortSpec
from app.analytics_schemas.nl_plan import NLQueryPlan
from app.services.query_parser_service import parse_natural_language_query


def try_rule_nl_plan(query: str, role: str) -> Optional[NLQueryPlan]:  # noqa: C901
    t = query.lower()

    from app.services.nl_mutate_service import try_rule_mutate_plan

    mutate_plan = try_rule_mutate_plan(query)
    if mutate_plan is not None:
        return mutate_plan

    if re.search(r"\bcpi\b", t) and re.search(r"\b(country|countries|member)\b", t):
        spec = parse_natural_language_query(query)
        return NLQueryPlan(
            kind="aggregate",
            aggregate=spec.model_copy(
                update={
                    "module": "economic",
                    "group_by": ["country_name"],
                    "metrics": [MetricSpec(field="CPI", aggregation="avg")],
                    "chart_type": "bar",
                }
            ),
        )

    if re.search(r"\binflation\b", t) and re.search(r"\bcountr", t):
        m_top = re.search(r"\btop\s+(\d+)\b", t)
        limit = int(m_top.group(1)) if m_top else 5
        return NLQueryPlan(
            kind="aggregate",
            aggregate=AnalyticsSpec(
                module="economic",
                group_by=["country_name"],
                metrics=[MetricSpec(field="inflation", aggregation="avg")],
                sort=SortSpec(field="inflation", direction="desc"),
                limit=limit,
                chart_type="bar",
            ),
        )

    # ── Loan rollups: by status / by country (before flat "show all loans") ─
    if re.search(r"\bby\s+status\b", t) and re.search(r"\b(loans?|sovereign|lending)\b", t):
        return NLQueryPlan(kind="aggregate", aggregate=parse_natural_language_query(query))

    # ── Loans: outstanding balance by country + currency ───────────────────
    if re.search(r"\bloans?\b", t) and "outstanding" in t:
        if re.search(r"(country\s*name|\bcountries\b|\bcountry\b)", t) and "currency" in t:
            return NLQueryPlan(
                kind="browse",
                browse_entity="loan",
                browse_template="loan_country_currency_os",
                browse_limit=400,
            )

    # ── Financial transactions ─────────────────────────────────────────────
    if re.search(r"\bfinancial\s+transactions?\b|\btransactions?\b", t):
        if "january" in t and "march" in t:
            return NLQueryPlan(
                kind="browse",
                browse_entity="financial_transaction",
                browse_template="txn_jan_through_march",
                browse_projection=["transaction_date", "transaction_type", "amount", "reference"],
                browse_limit=400,
            )
        if "debit" in t:
            return NLQueryPlan(
                kind="browse",
                browse_entity="financial_transaction",
                browse_template="txn_debits_outflows",
                browse_projection=["transaction_date", "transaction_type", "amount", "reference"],
                browse_limit=400,
            )

    # ── Loan condition mappings ────────────────────────────────────────────
    if ("missing" in t or "without" in t) and "mapping" in t and "loan" in t:
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loans_missing_condition_mappings",
            browse_projection=["loan_id", "country_name", "currency_code"],
            browse_limit=200,
        )

    if "loan" in t and ("all installments paid" in t or ("installments paid" in t and "every" in t)):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loans_all_installments_paid",
            browse_projection=["loan_id", "country_name", "currency_code"],
            browse_limit=200,
        )

    if re.search(r"\bcountr(?:y|ies)\b", t) and "overdue" in t and "installment" in t:
        return NLQueryPlan(
            kind="browse",
            browse_entity="country",
            browse_template="countries_overdue_balances",
            browse_projection=["country_name", "loan_id", "outstanding_balance"],
            browse_limit=200,
        )

    if re.search(
        r"\bcountr(?:y|ies)\b.*(?:no|without|don't\s+have|do\s+not\s+have).*(?:imf\s+)?loan",
        t,
    ) or re.search(r"(?:no|without)\s+(?:imf\s+)?loan.*\bcountr", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="country",
            browse_template="countries_without_loans",
            browse_projection=["country_name", "region", "currency_code"],
            browse_limit=200,
        )

    if re.search(r"\bcompare\b", t) and "gdp" in t and re.search(r"\bloan\b", t):
        return NLQueryPlan(
            kind="aggregate",
            aggregate=parse_natural_language_query(query),
        )

    if "loan" in t and "overdue" in t and ("repayment" in t or "installment" in t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loans_installments_overdue",
            browse_projection=["loan_id", "country_name"],
            browse_limit=200,
        )

    if "installment" in t and ("partially paid" in t or ("partial" in t and "paid" in t)):
        return NLQueryPlan(
            kind="browse",
            browse_entity="installment",
            browse_template="installments_partial_only",
            browse_projection=[
                "loan_id", "installment_no", "due_date",
                "amount_due", "amount_paid", "status",
            ],
            browse_limit=400,
        )

    # ── Scalar: total repaid for a loan ───────────────────────────────────
    m_tot_ln = re.search(r"(?:loan|for\s+loan)\s*#?\s*(\d+)\b", t)
    if m_tot_ln and ("total paid" in t or "total amount paid" in t or "calculate" in t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="repayment",
            browse_template="scalar_sum_repaid_by_loan",
            browse_context={"loan_id": int(m_tot_ln.group(1))},
            browse_projection=["loan_id", "total_amount_paid"],
            browse_limit=10,
        )

    # ── FX rate: USD → EUR (or any two 3-letter codes near each other) ────
    fx_m = re.search(r"\b([A-Za-z]{3})\b.{0,30}?\b([A-Za-z]{3})\b", query)
    if fx_m and re.search(r"\b(exchange\s+rate|fx|rate|convert|latest|current)\b", t):
        from_c = fx_m.group(1).upper()
        to_c = fx_m.group(2).upper()
        # crude sanity: both must look like currency codes (all alpha, 3 chars)
        if from_c.isalpha() and to_c.isalpha() and from_c != to_c:
            return NLQueryPlan(
                kind="browse",
                browse_entity="exchange_rate",
                browse_template="fx_latest_pair",
                browse_context={"from_currency": from_c, "to_currency": to_c},
                browse_projection=["rate_date", "from_currency", "to_currency", "rate"],
                browse_limit=10,
            )

    # ── Economic records: GDP above threshold ─────────────────────────────
    if "economic records" in t and "gdp" in t and re.search(r"above|over|greater|>", t):
        gm = re.search(
            r"(?:above|over|greater|>)\s*(?:than\s*)?([\d\s,]+(?:\.\d+)?)\s*(billion)?", t
        )
        raw = gm.group(1).replace(",", "").strip() if gm else "500"
        thresh = Decimal(raw)
        return NLQueryPlan(
            kind="browse",
            browse_entity="economic_record",
            browse_template="econ_records_high_gdp",
            browse_context={"gdp_above": float(thresh)},
            browse_projection=["country_name", "record_date", "GDP", "inflation"],
            browse_limit=200,
        )

    # ── Countries with inflation above threshold ───────────────────────────
    if ("country" in t or "countries" in t) and "inflation" in t and re.search(r"above|over|greater|>", t):
        gm = re.search(r"(?:above|over|greater|>)\s*(?:than\s*)?(\d+(?:\.\d+)?)\s*%?", t)
        thresh = Decimal(gm.group(1) if gm else "10")
        return NLQueryPlan(
            kind="browse",
            browse_entity="economic_record",
            browse_template="econ_inflation_above_threshold",
            browse_context={"inflation_above": float(thresh)},
            browse_projection=["country_name", "record_date", "GDP", "inflation"],
            browse_limit=200,
        )

    # ── Single-country economic snapshot ──────────────────────────────────
    # Only triggers when user names a specific country AND asks for its indicators.
    # We do NOT hardcode which countries are valid — regex extracts the name.
    country_snapshot_m = re.search(
        r"(?:latest|current|show|get)\s+(?:economic\s+)?(?:indicators?|macro|gdp|inflation)\s+"
        r"(?:for|of)\s+([a-z][a-z\s]{2,40}?)(?:\s*$|\s+(?:in|as|from))",
        t,
    )
    if country_snapshot_m:
        cname = country_snapshot_m.group(1).strip().title()
        return NLQueryPlan(
            kind="browse",
            browse_entity="economic_indicator",
            browse_template="econ_snapshot_country",
            browse_context={"country": cname},
            browse_projection=["country_name", "record_date", "CPI", "GDP", "inflation",
                               "exchange_rate", "interest_rate"],
            browse_limit=20,
        )

    # ── European inflation comparison ──────────────────────────────────────
    # The execution layer resolves "European" from DB — we just flag the template.
    if re.search(r"\beurope(?:an)?\b", t) and "inflation" in t:
        cross_country = bool(
            re.search(r"\b(compare|versus|comparison|among|each|rank|all\s+countries|chart|graph|plot)\b", t)
            or re.search(r"\bcountries\s+.*europe\b|europe.*countries", t)
        )
        if cross_country:
            return NLQueryPlan(
                kind="browse",
                browse_entity="economic_indicator",
                browse_template="inflation_compare_europe_region",
                browse_projection=["country_name", "avg_inflation", "record_date"],
                browse_limit=100,
            )

    # ── Loans: conditions for a specific loan ─────────────────────────────
    r_loan = re.search(r"\bloan\s*#?\s*(\d+)\b", t)
    if r_loan and ("condition" in t or "conditions" in t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan_condition_mapping",
            browse_template="loan_mapped_conditions_sheet",
            browse_context={"loan_id": int(r_loan.group(1))},
            browse_limit=200,
        )

    # ── Loans: repayment / installment history for a specific loan ────────
    if r_loan and re.search(r"\b(repayments?|repayment\s+history)\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="repayment",
            browse_filters=[FilterSpec(field="loan_id", operator="=", value=int(r_loan.group(1)))],
            browse_projection=["loan_id", "repayment_no", "amount_paid", "payment_date", "outstanding_balance"],
            browse_limit=500,
        )
    if r_loan and re.search(r"\b(installments?|schedule)\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="installment",
            browse_filters=[FilterSpec(field="loan_id", operator="=", value=int(r_loan.group(1)))],
            browse_projection=["loan_id", "installment_no", "due_date", "amount_due", "amount_paid", "status"],
            browse_limit=500,
        )

    # ── Loans: join with country / program ────────────────────────────────
    loan_join_rx = (
        r"loan.*(?:country.*name|currency|program)|"
        r"(?:country|currency|program).*(?:loan|outstanding)"
    )
    if re.search(loan_join_rx, t, re.I):
        narrows_os = (
            "outstanding" in t
            and re.search(r"(country\s*name|\bcountry\b)", t)
            and "currency" in t
        )
        if not narrows_os:
            return NLQueryPlan(
                kind="browse",
                browse_entity="loan",
                browse_template="loan_extended",
                browse_limit=300,
            )

    # ── Loan detail by ID ─────────────────────────────────────────────────
    lid_m = re.search(r"\bloan(?:\s+id|\s+#)?\s*[#:]?\s*(\d+)\b", t)
    if lid_m and re.search(r"\b(details?|show|get)\b", t):
        lid = int(lid_m.group(1))
        if not re.search(r"\b(repayment|installment|condition|disburse)\b", t):
            return NLQueryPlan(
                kind="browse",
                browse_entity="loan",
                browse_template="loan_extended",
                browse_filters=[FilterSpec(field="loan_id", operator="=", value=lid)],
                browse_projection=["loan_id", "country_name", "currency_code", "loan_amount", "status"],
                browse_limit=20,
            )

    # ── Loans: status filters ─────────────────────────────────────────────
    if re.search(r"\bloans?\b", t) and "completed" in t and re.search(r"\b(show|list|all|find)\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loan_extended",
            browse_filters=[FilterSpec(field="status", operator="=", value="Completed")],
            browse_projection=["loan_id", "country_name", "program_name", "loan_amount", "status"],
            browse_limit=400,
        )

    if re.search(r"\b(imf\s+)?loans?\b", t) and re.search(
        r"\b(country|program)\b", t
    ) and re.search(r"\b(list|show|display|all)\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loan_extended",
            browse_projection=[
                "loan_id", "country_name", "program_name", "loan_amount", "currency_code", "status",
            ],
            browse_limit=400,
        )

    if re.search(r"\beconomic\s+indicators?\b", t) and re.search(r"\bcountry\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="economic_indicator",
            browse_template="economic_indicator_extended",
            browse_projection=[
                "indicator_id", "country_name", "record_date", "CPI", "GDP", "inflation",
            ],
            browse_limit=500,
        )

    if re.search(r"\b(program|programs)\b", t) and re.search(
        r"\b(number|count|how\s+many|issued)\b", t
    ) and "loan" in t:
        spec = parse_natural_language_query(query)
        spec = spec.model_copy(
            update={
                "module": "loan",
                "group_by": ["program_name"],
                "metrics": [MetricSpec(field="loan_id", aggregation="count")],
            }
        )
        return NLQueryPlan(kind="aggregate", aggregate=spec)

    if re.search(r"\bloans?\b", t) and "active" in t and re.search(r"\b(show|list|all|find)\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_filters=[FilterSpec(field="status", operator="=", value="Active")],
            browse_limit=400,
        )
    if re.search(r"\bloans?\b", t) and "pending" in t and re.search(r"\b(show|list|all|find)\b", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_filters=[FilterSpec(field="status", operator="ilike", value="%pending%")],
            browse_limit=400,
        )

    # ── Loans: filter by country name (extracted from query) ──────────────
    m_cn = re.search(r"\bloans?\s+(?:for|in)\s+([a-z][a-z\s]+)", t)
    if m_cn and re.search(r"\b(show|list|all|find)\b", t):
        phrase = m_cn.group(1).strip()
        slug = phrase.split()[0]
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loan_extended",
            browse_filters=[FilterSpec(field="country_name", operator="ilike", value=f"%{slug}%")],
            browse_projection=["loan_id", "country_name", "currency_code", "loan_amount", "status"],
            browse_limit=400,
        )

    # ── Loans: interest rate threshold ────────────────────────────────────
    ir_m = re.search(
        r"interest\s+rate.*(?:>|above|over|greater|higher\s+than)\s*(?:than\s*)?(\d+(?:\.\d+)?)\s*%?",
        t,
    )
    if re.search(r"\bloans?\b", t) and ir_m:
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_filters=[FilterSpec(field="interest_rate", operator=">", value=Decimal(ir_m.group(1)))],
            browse_limit=400,
        )

    # ── Loans: sort by amount ─────────────────────────────────────────────
    if re.search(r"\bloans?\b", t) and re.search(r"(highest\s+amount|sort(?:ed)?\s+by.*amount|largest\s+loan)", t):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_order_field="loan_amount",
            browse_order_dir="desc",
            browse_limit=400,
        )

    # ── Currencies ────────────────────────────────────────────────────────
    if (
        re.search(r"\bcurrencies\b|\bcurrency\b", t)
        and not re.search(r"\bexchange\b|\bfx\b|\brate\b", t)
        and re.search(r"\b(show|list|all)\b", t)
        and not re.search(r"create|add|delete|update", t)
    ):
        return NLQueryPlan(kind="browse", browse_entity="currency", browse_limit=400)

    cur_m = re.search(r"\b(?:code|currency)\s*([A-Za-z]{3})\b", query, re.I)
    if cur_m and "currency" in t:
        code = cur_m.group(1).upper()
        return NLQueryPlan(
            kind="browse",
            browse_entity="currency",
            browse_filters=[FilterSpec(field="currency_code", operator="=", value=code)],
        )

    # ── Countries: region filter (generic — works for any region word) ────
    region_m = re.search(
        r"\bcountri(?:es|y)\b.{0,40}?\b(asia|europe|africa|americas?|oceania|middle\s+east|latin)\b"
        r"|\b(asia|europe|africa|americas?|oceania|middle\s+east|latin)\b.{0,40}?\bcountri(?:es|y)\b",
        t,
    )
    if region_m:
        region_word = (region_m.group(1) or region_m.group(2) or "").strip()
        return NLQueryPlan(
            kind="browse",
            browse_entity="country",
            browse_filters=[FilterSpec(field="region", operator="ilike", value=f"%{region_word}%")],
            browse_limit=200,
        )

    # ── Countries: population threshold ───────────────────────────────────
    pop_m = re.search(r"population.*(?:greater|>|above)\s*(?:than\s*)?([\d\s,]+)", t)
    if pop_m:
        pval = int(re.sub(r"[,\s]", "", pop_m.group(1)))
        return NLQueryPlan(
            kind="browse",
            browse_entity="country",
            browse_filters=[FilterSpec(field="population", operator=">", value=pval)],
        )

    # ── Country by ID ─────────────────────────────────────────────────────
    cid_m = re.search(
        r"(?:country\s+(?:details?|info)|details?\s+(?:for|of)\s+a?\s*country).*?(?:\bid\s+|#)(\d+)\b"
        r"|\bcountry\s+(?:id|#)\s*(\d+)\b",
        t,
        re.I,
    )
    if cid_m and re.search(r"\b(details?|show|get)\b|\bcountry\s+id\b", t):
        cid = next(int(g) for g in cid_m.groups() if g)
        return NLQueryPlan(
            kind="browse",
            browse_entity="country",
            browse_filters=[FilterSpec(field="country_id", operator="=", value=cid)],
        )

    # ── Officers: approval limit ──────────────────────────────────────────
    if re.search(r"\bofficers?\b", t):
        lim_m = re.search(
            r"(?:approval\s*limit.*?|.*?)(?:greater|above|over|>)\s*(?:than\s*)?(?:\$)?([\d,]+(?:\.\d+)?)\s*million\b",
            t,
            re.I,
        )
        if lim_m:
            val_m = Decimal(lim_m.group(1).replace(",", "")) * Decimal(1_000_000)
            return NLQueryPlan(
                kind="browse",
                browse_entity="officer",
                browse_filters=[FilterSpec(field="approval_limit", operator=">", value=val_m)],
                browse_limit=200,
            )

    # ── Economic analysts: specialization filter ───────────────────────────
    if re.search(r"\banalyst", t) and "inflation" in t:
        return NLQueryPlan(
            kind="browse",
            browse_entity="economicanalyst",
            browse_filters=[FilterSpec(field="specialization", operator="ilike", value="%inflation%")],
            browse_limit=200,
        )

    # ── Loan programs: max amount threshold ───────────────────────────────
    if ("program" in t or "programs" in t) and re.search(r"max\s+amount|(above|>|greater).*billion", t):
        bm = re.search(r"([\d,.]+)\s*billion", t, re.I)
        floor = (
            Decimal(bm.group(1).replace(",", "")) * Decimal("1000000000")
            if bm
            else Decimal("1000000000")
        )
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan_program",
            browse_filters=[FilterSpec(field="max_amount", operator=">", value=floor)],
            browse_limit=400,
        )

    if re.search(r"\bloan\s+programs?\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="loan_program", browse_limit=400)

    # ── IMF accounts ──────────────────────────────────────────────────────
    im_bal = re.search(r"\bimf\s+account\s+#?(\d+)\b", t)
    if im_bal and "balance" in t:
        return NLQueryPlan(
            kind="browse",
            browse_entity="imf_account",
            browse_filters=[FilterSpec(field="imf_account_id", operator="=", value=int(im_bal.group(1)))],
            browse_limit=20,
        )
    if re.search(r"\b(imf\s+accounts?|reserve\s+accounts?)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="imf_account", browse_limit=400)

    # ── Generic list fallbacks ────────────────────────────────────────────
    if re.search(r"\busers?\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="users", browse_limit=500)

    if (
        re.search(r"\bloans?\b", t)
        and re.search(r"\b(show|list|all)\b", t)
        and "repayment" not in t
        and not re.search(r"\bby\s+(status|country|program)\b", t)
    ):
        return NLQueryPlan(
            kind="browse",
            browse_entity="loan",
            browse_template="loan_extended",
            browse_projection=[
                "loan_id", "country_name", "program_name", "loan_amount", "currency_code", "status",
            ],
            browse_limit=400,
        )

    if re.search(r"\b(installments?|installment\s+schedule)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="installment", browse_limit=500)

    if re.search(r"\b(disbursements?)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="loan_disbursement", browse_limit=500)

    if re.search(r"\b(repayments?|repayment\s+history)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="repayment", browse_limit=500)

    if re.search(r"\b(economic\s+indicators?|indicators?)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="economic_indicator", browse_limit=500)

    if re.search(r"\b(exchange\s+rates?|fx)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="exchange_rate", browse_limit=500)

    if re.search(r"\b(gdp|inflation)\b", t) and "record" in t:
        return NLQueryPlan(kind="browse", browse_entity="economic_record", browse_limit=500)

    if re.search(r"\b(financial\s+transactions?|transactions?)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="financial_transaction", browse_limit=500)

    if re.search(r"\b(audit\s*logs?|audit)\b", t) and re.search(r"\b(show|list|all)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="audit_log", browse_limit=500)

    if re.search(r"\b(officers?)\b", t):
        return NLQueryPlan(kind="browse", browse_entity="officer", browse_limit=200)

    if re.search(r"\b(economic\s+)?analyst", t):
        return NLQueryPlan(kind="browse", browse_entity="economicanalyst", browse_limit=200)

    return None


def legacy_rule_nl_plan(query: str, role: str) -> NLQueryPlan:
    """Regex / keyword planner; falls back to rule-based AnalyticsSpec parser."""
    plan = try_rule_nl_plan(query, role)
    if plan is not None:
        return plan
    try:
        return NLQueryPlan(kind="aggregate", aggregate=parse_natural_language_query(query))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not understand request") from exc
