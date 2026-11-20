"""
Natural-language mutate planning helpers: validation, key resolution, rule fallback.

Used by unified_nl_service.execute_mutate and nl_rule_fallback.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.analytics_schemas.nl_plan import NLQueryPlan

# Required fields per entity on create (Pydantic / DB constraints).
CREATE_REQUIRED: Dict[str, List[str]] = {
    "currency": ["currency_code"],
    "country": ["currency_code", "name"],
    "loan_program": ["program_name"],
    "imf_account": ["account_number"],
    "users": ["name", "email", "password"],
    "loan": [
        "country_id",
        "program_id",
        "imf_account_id",
        "currency_code",
        "loan_amount",
        "no_of_installments",
    ],
    "loan_condition": ["condition_type"],
    "economic_indicator": ["country_id", "record_date"],
    "exchange_rate": ["from_currency", "to_currency", "rate", "rate_date"],
}

_TABLE_DELETE_PATTERNS = [
    re.compile(r"\bdelete\s+(?:all|every|entire)\b", re.I),
    re.compile(r"\b(?:drop|truncate)\s+(?:the\s+)?(?:whole\s+)?table\b", re.I),
    re.compile(r"\bdelete\s+(?:all\s+)?(?:users?|countries|loans?|currencies)\s*$", re.I),
    re.compile(r"\bremove\s+all\b", re.I),
    re.compile(r"\bclear\s+(?:the\s+)?(?:table|database)\b", re.I),
]


def _empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def validate_create_fields(entity: str, body: Dict[str, Any]) -> None:
    """Raise 400 listing missing required fields for create."""
    ent = entity.strip().lower()
    required = CREATE_REQUIRED.get(ent, [])
    missing = [f for f in required if _empty(body.get(f))]
    if missing:
        labels = ", ".join(missing)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add {ent.replace('_', ' ')}: required field(s) empty or missing: {labels}.",
        )


def guard_whole_table_delete(query: str, keys: Dict[str, Any], op: str) -> None:
    """Reject delete requests that target an entire table without row keys."""
    if op != "delete":
        return
    q = (query or "").lower()
    for pat in _TABLE_DELETE_PATTERNS:
        if pat.search(q):
            raise HTTPException(
                status_code=400,
                detail="Deleting an entire table is not allowed. Specify a single record (name, id, or code).",
            )
    if not keys:
        raise HTTPException(
            status_code=400,
            detail="Delete requires identifying the record (e.g. user name, country name, or primary key).",
        )


def _find_currency_code(db: Session, lookup: str) -> str:
    """Resolve currency_code from a code (USD) or display name (Indian Rupee)."""
    raw = (lookup or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Currency identifier is required.")

    if len(raw) <= 4:
        by_code = (
            db.query(models.Currency)
            .filter(models.Currency.currency_code.ilike(raw))
            .first()
        )
        if by_code:
            return str(by_code.currency_code)

    by_name = (
        db.query(models.Currency)
        .filter(models.Currency.currency_name.ilike(f"%{raw}%"))
        .order_by(models.Currency.currency_code)
        .all()
    )
    if len(by_name) == 1:
        return str(by_name[0].currency_code)
    if len(by_name) > 1:
        options = ", ".join(f"{c.currency_code} ({c.currency_name})" for c in by_name[:6])
        raise HTTPException(
            status_code=400,
            detail=f"Multiple currencies match '{lookup}': {options}. Specify the currency code.",
        )
    raise HTTPException(status_code=404, detail=f"No currency found matching '{lookup}'.")


def resolve_mutate_keys(
    db: Session,
    entity: str,
    op: str,
    keys: Dict[str, Any],
    body: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resolve natural-language identifiers to primary keys.
    Supports lookup by name / currency_code / program_name in mutate_keys or body.
    """
    ent = entity.strip().lower()
    resolved = dict(keys)

    if ent == "users":
        lookup = (
            resolved.pop("lookup_name", None)
            or resolved.pop("name", None)
            or body.pop("lookup_name", None)
            or body.pop("old_name", None)
        )
        if lookup and "user_id" not in resolved:
            hit = db.query(models.User).filter(models.User.name.ilike(str(lookup).strip())).first()
            if not hit:
                raise HTTPException(404, detail=f"No user found matching name '{lookup}'.")
            resolved["user_id"] = hit.user_id
        return resolved

    if ent == "country":
        lookup = (
            resolved.pop("lookup_name", None)
            or resolved.pop("name", None)
            or body.pop("lookup_name", None)
        )
        if lookup and "country_id" not in resolved:
            hit = db.query(models.Country).filter(models.Country.name.ilike(f"%{str(lookup).strip()}%")).first()
            if not hit:
                raise HTTPException(404, detail=f"No country found matching '{lookup}'.")
            resolved["country_id"] = hit.country_id
        return resolved

    if ent == "currency":
        lookup = (
            resolved.pop("lookup_name", None)
            or resolved.pop("currency_name", None)
            or body.pop("lookup_name", None)
            or body.pop("old_name", None)
            or body.pop("old_currency_name", None)
        )
        if lookup and not resolved.get("currency_code"):
            resolved["currency_code"] = _find_currency_code(db, str(lookup))
        code = resolved.get("currency_code") or body.get("currency_code")
        if code:
            resolved["currency_code"] = str(code).strip().upper()
        return resolved

    if ent == "loan_program":
        lookup = resolved.pop("program_name", None) or body.pop("lookup_name", None)
        if lookup and "program_id" not in resolved:
            hit = (
                db.query(models.LoanProgram)
                .filter(models.LoanProgram.program_name.ilike(f"%{str(lookup).strip()}%"))
                .first()
            )
            if not hit:
                raise HTTPException(404, detail=f"No loan program found matching '{lookup}'.")
            resolved["program_id"] = hit.program_id
        return resolved

    if ent == "loan":
        lid = resolved.get("loan_id")
        if lid is None and body.get("loan_id") is not None:
            resolved["loan_id"] = int(body["loan_id"])
        lookup = resolved.pop("lookup_label", None) or body.pop("lookup_label", None)
        if lookup and "loan_id" not in resolved:
            m = re.search(r"\d+", str(lookup))
            if m:
                resolved["loan_id"] = int(m.group())
        return resolved

    if ent == "economic_record":
        lookup = (
            resolved.pop("lookup_name", None)
            or resolved.pop("name", None)
            or resolved.pop("country_name", None)
            or body.pop("lookup_name", None)
            or body.pop("country_name", None)
        )
        if lookup and "record_id" not in resolved:
            resolved["lookup_name"] = str(lookup).strip()
        return resolved

    if ent == "economic_indicator":
        lookup = (
            resolved.pop("lookup_name", None)
            or resolved.pop("country_name", None)
            or body.pop("lookup_name", None)
        )
        if lookup and "indicator_id" not in resolved:
            hit = (
                db.query(models.Country)
                .filter(models.Country.name.ilike(f"%{str(lookup).strip()}%"))
                .first()
            )
            if not hit:
                raise HTTPException(404, detail=f"No country found matching '{lookup}'.")
            ind = (
                db.query(models.EconomicIndicator)
                .filter(models.EconomicIndicator.country_id == hit.country_id)
                .order_by(models.EconomicIndicator.record_date.desc())
                .first()
            )
            if not ind:
                raise HTTPException(404, detail=f"No economic indicator for '{hit.name}'.")
            resolved["indicator_id"] = ind.indicator_id
        return resolved

    if ent == "exchange_rate" and "exchange_rate_id" not in resolved:
        rid = body.get("exchange_rate_id")
        if rid is not None:
            resolved["exchange_rate_id"] = int(rid)
        return resolved

    if ent == "imf_account" and "imf_account_id" not in resolved:
        aid = body.get("imf_account_id") or keys.get("imf_account_id")
        if aid is not None:
            resolved["imf_account_id"] = int(aid)
        return resolved

    if ent == "loan_disbursement":
        if "loan_id" not in resolved and body.get("loan_id") is not None:
            resolved["loan_id"] = int(body["loan_id"])
        if "disbursement_no" not in resolved and body.get("disbursement_no") is not None:
            resolved["disbursement_no"] = int(body["disbursement_no"])
        return resolved

    if ent == "repayment":
        if "loan_id" not in resolved and body.get("loan_id") is not None:
            resolved["loan_id"] = int(body["loan_id"])
        if "repayment_no" not in resolved and body.get("repayment_no") is not None:
            resolved["repayment_no"] = int(body["repayment_no"])
        return resolved

    return resolved


def try_rule_mutate_plan(query: str) -> Optional[NLQueryPlan]:
    """
    Offline mutate routing for add / update / delete phrasing.
    Returns None if the query does not look like a mutation.
    """
    raw = query.strip()
    t = raw.lower()

    if not re.search(r"\b(add|create|insert|update|change|rename|delete|remove)\b", t):
        return None

    m_ccy_rename = re.search(
        r"\bupdate\s+([A-Za-z]{3})\b.*?\bto\s+([A-Za-z]{3})\b.*?\b(?:in\s+)?(?:the\s+)?(?:currency|currencies)\b",
        t,
        re.I,
    )
    if m_ccy_rename:
        old_c, new_c = m_ccy_rename.group(1).upper(), m_ccy_rename.group(2).upper()
        body: Dict[str, Any] = {"new_currency_code": new_c}
        m_name = re.search(r",\s*([^,]+?)\s+to\s+([^,]+?)(?:\s+in\s+|\s*$)", raw, re.I)
        if m_name:
            body["currency_name"] = m_name.group(2).strip().title()
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="currency",
            mutate_op="update",
            mutate_keys={"currency_code": old_c},
            mutate_body=body,
        )

    m_loan_inst = re.search(
        r"\bupdate\s+no_of_installments\s+to\s+(\d+)\s+for\s+loan\s+id\s*=\s*(\d+)\b",
        t,
        re.I,
    )
    if m_loan_inst:
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="loan",
            mutate_op="update",
            mutate_keys={"loan_id": int(m_loan_inst.group(2))},
            mutate_body={"no_of_installments": int(m_loan_inst.group(1))},
        )

    m_infl_country = re.search(
        r"\bupdate\s+inflation(?:\s+rate)?\s+for\s+(.+?)\s+to\s+([\d.]+)\s*(?:%|percent)?\b",
        t,
        re.I,
    )
    if m_infl_country:
        country = m_infl_country.group(1).strip().rstrip(".")
        val = float(m_infl_country.group(2))
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="economic_record",
            mutate_op="update",
            mutate_keys={"lookup_name": country.title() if country.islower() else country},
            mutate_body={"inflation": val},
        )

    # ── UPDATE ────────────────────────────────────────────────────────────
    m_up = re.search(
        r"\bupdate\s+(.+?)\s+to\s+(.+?)\s+in\s+(users?|countries?|country|currency|currencies|loans?|loan)\b",
        t,
        re.I,
    )
    if m_up:
        old_val, new_val, ent_word = m_up.group(1).strip(), m_up.group(2).strip(), m_up.group(3).lower()
        entity = _word_to_entity(ent_word)
        if entity == "users":
            return NLQueryPlan(
                kind="mutate",
                mutate_entity="users",
                mutate_op="update",
                mutate_keys={"lookup_name": old_val.title() if old_val.islower() else old_val},
                mutate_body={"name": new_val.title() if new_val.islower() else new_val},
            )
        if entity == "country":
            return NLQueryPlan(
                kind="mutate",
                mutate_entity="country",
                mutate_op="update",
                mutate_keys={"lookup_name": old_val},
                mutate_body={"name": new_val.title() if new_val.islower() else new_val},
            )
        if entity == "currency":
            new_name = new_val.title() if new_val.islower() else new_val
            return NLQueryPlan(
                kind="mutate",
                mutate_entity="currency",
                mutate_op="update",
                mutate_keys={"lookup_name": old_val},
                mutate_body={"currency_name": new_name},
            )

    m_rename_ccy = re.search(
        r"\b(?:rename|change)\s+(.+?)\s+to\s+(.+?)\s+in\s+(?:the\s+)?(?:currency|currencies)(?:\s+table)?\b",
        t,
        re.I,
    )
    if m_rename_ccy:
        old_val, new_val = m_rename_ccy.group(1).strip(), m_rename_ccy.group(2).strip()
        new_name = new_val.title() if new_val.islower() else new_val
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="currency",
            mutate_op="update",
            mutate_keys={"lookup_name": old_val},
            mutate_body={"currency_name": new_name},
        )

    # ── DELETE ────────────────────────────────────────────────────────────
    m_del_from = re.search(
        r"\b(?:delete|remove)\s+(.+?)\s+from\s+(users?|countries?|country|currency|currencies|loans?)\b",
        t,
        re.I,
    )
    if m_del_from:
        target, ent_word = m_del_from.group(1).strip(), m_del_from.group(2).lower()
        entity = _word_to_entity(ent_word)
        keys = _delete_target_keys(entity, target)
        return NLQueryPlan(kind="mutate", mutate_entity=entity, mutate_op="delete", mutate_keys=keys)

    m_del_user = re.search(r"\bdelete\s+user\s*#?(\d+)\b", t, re.I)
    if m_del_user:
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="users",
            mutate_op="delete",
            mutate_keys={"user_id": int(m_del_user.group(1))},
        )

    m_del_user2 = re.search(r"\bdelete\s+(user\d+)\b", t, re.I)
    if m_del_user2:
        label = m_del_user2.group(1)
        m_id = re.search(r"(\d+)", label)
        if m_id:
            return NLQueryPlan(
                kind="mutate",
                mutate_entity="users",
                mutate_op="delete",
                mutate_keys={"user_id": int(m_id.group(1))},
            )

    m_del_loan = re.search(r"\bdelete\s+loan\s*#?(\d+)\b", t, re.I)
    if m_del_loan:
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="loan",
            mutate_op="delete",
            mutate_keys={"loan_id": int(m_del_loan.group(1))},
        )

    # ── ADD ───────────────────────────────────────────────────────────────
    m_add_in = re.search(
        r"\badd\s+(.+?)\s+in\s+(countries?|country)\b",
        t,
        re.I,
    )
    if m_add_in:
        value = m_add_in.group(1).strip()
        return NLQueryPlan(
            kind="mutate",
            mutate_entity="country",
            mutate_op="create",
            mutate_body={"name": value.title()},
        )

    m_add_to = re.search(
        r"\badd\s+(.+?)\s+to\s+(countries?|country|users?|currency|currencies)\b",
        t,
        re.I,
    )
    if m_add_to:
        value, ent_word = m_add_to.group(1).strip(), m_add_to.group(2).lower()
        entity = _word_to_entity(ent_word)
        if entity == "country":
            return NLQueryPlan(
                kind="mutate",
                mutate_entity="country",
                mutate_op="create",
                mutate_body={"name": value.title()},
            )
        if entity == "users":
            return NLQueryPlan(
                kind="mutate",
                mutate_entity="users",
                mutate_op="create",
                mutate_body={"name": value.title()},
            )

    m_add_country = re.search(
        r"\badd\s+(?:country|a\s+country)\s+(.+?)(?:\s+with\s+|\s*,\s*|\s+using\s+)(.+)$",
        t,
        re.I,
    )
    if m_add_country:
        name_part = m_add_country.group(1).strip()
        rest = m_add_country.group(2)
        body: Dict[str, Any] = {"name": name_part.title()}
        ccy = re.search(r"\b([A-Z]{3})\b", rest.upper())
        if ccy:
            body["currency_code"] = ccy.group(1)
        return NLQueryPlan(kind="mutate", mutate_entity="country", mutate_op="create", mutate_body=body)

    return None


def _word_to_entity(word: str) -> str:
    w = word.lower().rstrip("s")
    if w in ("user", "users"):
        return "users"
    if w in ("country", "countries"):
        return "country"
    if w in ("currency", "currencies"):
        return "currency"
    if w in ("loan", "loans"):
        return "loan"
    return w


def _delete_target_keys(entity: str, target: str) -> Dict[str, Any]:
    target = target.strip()
    if entity == "users":
        m = re.search(r"\d+", target)
        if m:
            return {"user_id": int(m.group())}
        return {"lookup_name": target}
    if entity == "country":
        return {"lookup_name": target}
    if entity == "currency":
        if len(target) <= 4:
            return {"currency_code": target.upper()}
        return {"lookup_name": target}
    if entity == "loan":
        m = re.search(r"\d+", target)
        if m:
            return {"loan_id": int(m.group())}
    return {"lookup_name": target}
