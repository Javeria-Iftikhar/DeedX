"""
routers/analytics.py — Dynamic analytics endpoints.

NEW ENDPOINTS (do not replace existing /llm/* or /dashboard/* routes):

  POST /analytics/query     — natural language → dynamic dashboard JSON
  POST /analytics/dashboard — same as /analytics/query (alias kept for spec)
  POST /analytics/export/pdf  — NL query → downloadable PDF (table + chart when applicable)
  POST /analytics/export/csv — NL query → downloadable CSV (rows only)
  GET  /analytics/history   — paginated audit history of analytics queries

SECURITY:
  - All endpoints require a valid JWT.
  - Role is read from the token; no role override is accepted from the body.
  - Business logic lives entirely in services/; this file only handles
    HTTP concerns (request parsing, response serialisation, dependency injection).

BACKWARDS COMPATIBILITY:
  The old POST /analytics/query in routers/llm.py executed raw text() SQL.
  This router REPLACES that endpoint with a safe ORM-based implementation.
  The /llm/query endpoint is preserved unchanged.
"""

from typing import Any, Dict, List
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, oauth2_scheme, decode_token
from app import models
from app.services.analytics_service import process_analytics_query
from app.services.dashboard_export_service import dashboard_to_csv_bytes, dashboard_to_pdf_bytes
from app.services.report_generation_service import generate_report_pdf, is_structured_report_prompt
from app.services.dashboard_service import get_query_history
from app.analytics_schemas.dashboard import DashboardResponse, AnalyticsHistoryResponse
from app.audit import write_audit_log

router = APIRouter(prefix="/analytics", tags=["Dynamic Analytics"])
logger = logging.getLogger(__name__)


# ── Shared dependency: authenticated user + role ──────────────────────────────

def _get_user_and_role(
    credentials=Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    Returns (user, role) from a valid access token.
    Raises 401/403 on invalid or missing token.
    """
    from fastapi import HTTPException, status
    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role = payload.get("role")
    if not role:
        raise HTTPException(status_code=403, detail="No role assigned to this account.")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user, role


# ── Request schemas ───────────────────────────────────────────────────────────


class ConversationTurn(BaseModel):
    """One prior chat utterance — pair with latest `query` for follow-ups."""
    role: str
    content: str


class AnalyticsQueryRequest(BaseModel):
    """
    Body for `/analytics/query` and `/analytics/dashboard`.

    Send prior turns under `conversation` and the NEW user text in `query`.
    Clients that only send single-shot questions may omit `conversation`.
    """

    query: str
    conversation: List[ConversationTurn] = Field(default_factory=list)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=Dict[str, Any],
    summary="Natural language analytics query",
    description=(
        "Submit a natural language question. The backend parses it into a structured "
        "analytics spec, validates your role's permissions, executes a safe ORM query, "
        "and returns a dashboard-ready JSON response.\n\n"
        "**Example queries:**\n"
        "- `Show active loans by country`\n"
        "- `Average GDP by country in the last 2 years`\n"
        "- `Top 5 countries by inflation`\n"
        "- `Total repayments by loan`\n"
        "- `Show overdue installments`"
    ),
    responses={
        400: {"description": "Query could not be parsed or contains invalid fields"},
        403: {"description": "Your role does not have permission to access the requested data"},
        500: {"description": "Internal error during query execution"},
    },
)
def analytics_query(
    body: AnalyticsQueryRequest,
    user_and_role=Depends(_get_user_and_role),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    user, role = user_and_role
    try:
        dashboard = process_analytics_query(
            db=db,
            user_id=user.user_id,
            role=role,
            query=body.query,
            conversation=[t.model_dump() for t in body.conversation],
        )
        write_audit_log(db, user.user_id, f"Analytics query: {body.query[:120]}", "Analytics")
        return {"dashboard": dashboard.model_dump()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Unhandled error in analytics_query for user_id=%s role=%s query=%r: %s",
            user.user_id, role, body.query, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again or contact support.",
        )


@router.post(
    "/dashboard",
    response_model=Dict[str, Any],
    summary="Dynamic dashboard (alias for /analytics/query)",
    description="Alias for POST /analytics/query. Returns the same dashboard JSON.",
    responses={
        400: {"description": "Query could not be parsed or contains invalid fields"},
        403: {"description": "Your role does not have permission to access the requested data"},
        500: {"description": "Internal error during query execution"},
    },
)
def analytics_dashboard(
    body: AnalyticsQueryRequest,
    user_and_role=Depends(_get_user_and_role),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    user, role = user_and_role
    try:
        dashboard = process_analytics_query(
            db=db,
            user_id=user.user_id,
            role=role,
            query=body.query,
            conversation=[t.model_dump() for t in body.conversation],
        )
        write_audit_log(db, user.user_id, f"Analytics dashboard query: {body.query[:120]}", "Analytics")
        return {"dashboard": dashboard.model_dump()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Unhandled error in analytics_dashboard for user_id=%s role=%s query=%r: %s",
            user.user_id, role, body.query, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again or contact support.",
        )


@router.post(
    "/export/pdf",
    summary="Export analytics as PDF",
    description=(
        "Runs the same natural-language analytics pipeline as POST /analytics/query, "
        "then renders the result table and (when applicable) chart into a PDF file. "
        "Example: *Export average GDP by country as a PDF chart*."
    ),
    responses={
        400: {"description": "Empty or invalid query"},
        403: {"description": "Role cannot access requested data"},
    },
)
def analytics_export_pdf(
    body: AnalyticsQueryRequest,
    user_and_role=Depends(_get_user_and_role),
    db: Session = Depends(get_db),
) -> Response:
    user, role = user_and_role
    q = (body.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        dashboard = process_analytics_query(
            db=db,
            user_id=user.user_id,
            role=role,
            query=q,
            conversation=[t.model_dump() for t in body.conversation],
        )
        write_audit_log(db, user.user_id, f"Analytics export PDF: {q[:120]}", "Analytics")
        if is_structured_report_prompt(q):
            pdf_bytes, fname = generate_report_pdf(db, q)
        else:
            pdf_bytes, fname = dashboard_to_pdf_bytes(dashboard)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "analytics_export_pdf failed user_id=%s role=%s query=%r: %s",
            user.user_id, role, q, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build PDF export. Please try again or contact support.",
        )


@router.post(
    "/export/csv",
    summary="Export analytics as CSV",
    description=(
        "Runs the same pipeline as POST /analytics/query and returns the tabular `data` "
        "rows as a UTF-8 CSV (with BOM for Excel)."
    ),
    responses={
        400: {"description": "Empty or invalid query"},
        403: {"description": "Role cannot access requested data"},
    },
)
def analytics_export_csv(
    body: AnalyticsQueryRequest,
    user_and_role=Depends(_get_user_and_role),
    db: Session = Depends(get_db),
) -> Response:
    user, role = user_and_role
    q = (body.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        dashboard = process_analytics_query(
            db=db,
            user_id=user.user_id,
            role=role,
            query=q,
            conversation=[t.model_dump() for t in body.conversation],
        )
        write_audit_log(db, user.user_id, f"Analytics export CSV: {q[:120]}", "Analytics")
        csv_bytes, fname = dashboard_to_csv_bytes(dashboard)
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "analytics_export_csv failed user_id=%s role=%s query=%r: %s",
            user.user_id, role, q, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build CSV export. Please try again or contact support.",
        )


@router.get(
    "/history",
    response_model=AnalyticsHistoryResponse,
    summary="Analytics query history",
    description=(
        "Returns the paginated audit log of analytics queries.\n\n"
        "- **Admin**: sees all users' queries.\n"
        "- **Officer / Analyst**: sees only their own.\n\n"
        "Use `page` and `page_size` for pagination."
    ),
)
def analytics_history(
    page:      int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    user_and_role=Depends(_get_user_and_role),
    db: Session = Depends(get_db),
) -> AnalyticsHistoryResponse:
    user, role = user_and_role
    try:
        return get_query_history(
            db=db,
            user_id=user.user_id,
            role=role,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Unhandled error in analytics_history for user_id=%s role=%s: %s",
            user.user_id, role, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve query history. Please try again or contact support.",
        )
