"""
routers/llm.py — LLM-compatible analytics proxy.

POST /llm/query        — NL → dashboard JSON (same pipeline as POST /analytics/query).
POST /llm/export/pdf  — NL → downloadable PDF with table + chart when applicable.
POST /llm/export/csv   — NL → downloadable CSV (tabular data only).
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, oauth2_scheme, decode_token
from app import models
from app.services.analytics_service import process_analytics_query
from app.services.dashboard_export_service import dashboard_to_csv_bytes, dashboard_to_pdf_bytes
from app.services.report_generation_service import generate_report_pdf, is_structured_report_prompt

router = APIRouter(tags=["LLM & Analytics"])


class LLMConversationTurn(BaseModel):
    role: str
    content: str


class LLMQueryRequest(BaseModel):
    question: str
    conversation: List[LLMConversationTurn] = Field(default_factory=list)


def get_current_user_with_role(
    credentials=Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user_id = int(payload["sub"])
    role = payload.get("role")
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user, role


@router.post("/llm/query")
def llm_query(
    body: LLMQueryRequest,
    user_and_role=Depends(get_current_user_with_role),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Natural-language fiscal question; returns dashboard JSON (table + optional chart + summary).
    """
    current_user, role = user_and_role
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    dashboard = process_analytics_query(
        db=db,
        user_id=current_user.user_id,
        role=role,
        query=q,
        conversation=[t.model_dump() for t in body.conversation],
    )
    return {
        "question": body.question,
        "dashboard": dashboard.model_dump(),
    }


@router.post("/llm/export/pdf")
def llm_export_pdf(
    body: LLMQueryRequest,
    user_and_role=Depends(get_current_user_with_role),
    db: Session = Depends(get_db),
) -> Response:
    """Natural language → analytics run → PDF (table plus chart when charts are requested)."""
    current_user, role = user_and_role
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    dashboard = process_analytics_query(
        db=db,
        user_id=current_user.user_id,
        role=role,
        query=q,
        conversation=[t.model_dump() for t in body.conversation],
    )
    if is_structured_report_prompt(q):
        pdf_bytes, fname = generate_report_pdf(db, q)
    else:
        pdf_bytes, fname = dashboard_to_pdf_bytes(dashboard)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/llm/export/csv")
def llm_export_csv(
    body: LLMQueryRequest,
    user_and_role=Depends(get_current_user_with_role),
    db: Session = Depends(get_db),
) -> Response:
    """Natural language → analytics run → CSV of result rows."""
    current_user, role = user_and_role
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    dashboard = process_analytics_query(
        db=db,
        user_id=current_user.user_id,
        role=role,
        query=q,
        conversation=[t.model_dump() for t in body.conversation],
    )
    csv_bytes, fname = dashboard_to_csv_bytes(dashboard)
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
