"""
main.py — FastAPI application entry point.

Routers:
  /auth           — register, login, refresh, logout, me
  /users          — user management + role assignments (RBAC: admin)
  /loans          — currency, country, loan program, IMF account, loan,
                    condition, mapping, disbursement, repayment, installment
  /               — transactions, financial automation endpoints
  /indicators etc — economic data (indicators, records, exchange rates)
  /dashboard      — stats and reports (static)
  /audit-logs     — audit log access (RBAC enforced)
  /llm            — POST /llm/query; POST /llm/export/pdf | /llm/export/csv (Groq when configured)
  /analytics      — NEW: dynamic AI-ready analytics engine (safe ORM, RBAC)

BACKWARDS COMPATIBILITY:
  All existing routes are preserved unchanged.
  The new /analytics/query route replaces the unsafe text()-based
  implementation that was previously in /llm (routers/llm.py).
  The /llm/query endpoint is still available for backwards compatibility.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.database import Base, engine
from app import models  # ensures all models are registered

# ── Routers ───────────────────────────────────────────────────────────────────
from app.routers import users, loans, transactions, economic
from app.routers import auth as auth_router
from app.routers import dashboard as dashboard_router
from app.routers import llm as llm_router
from app.routers import audit_logs as audit_logs_router
from app.routers import analytics as analytics_router   # NEW
from app.routers import reports as reports_router

app = FastAPI(
    title="IMF Loan Management ERP System",
    description=(
        "Backend API for managing IMF loans, repayments, economic data, and user roles.\n\n"
        "## Authentication\n"
        "Use **POST /auth/login** to get a JWT token, then click **Authorize** and enter:\n"
        "`Bearer <your_access_token>`\n\n"
        "## Role-Based Access Control\n"
        "- **Admin**: full access to all endpoints, audit logs, user management\n"
        "- **Officer**: loan processing, disbursements, repayments, financial operations\n"
        "- **Economic Analyst**: economic indicators, records, exchange rates, analytics\n\n"
        "## Audit Logging\n"
        "All mutating operations are automatically logged. Logs are append-only.\n"
        "Admins can view all logs at **GET /audit-logs/**. "
        "Any user can view their own logs at **GET /audit-logs/my**.\n\n"
        "## Dynamic Analytics (NEW)\n"
        "Use **POST /analytics/query** with a natural language question to get\n"
        "dashboard-ready JSON. The engine uses Groq + LangChain (when GROQ_API_KEY is set)\n"
        "to plan safe ORM queries, with a rule-based fallback. No raw SQL from user input.\n"
        "**POST /analytics/export/pdf** downloads the same NL result as a PDF (includes a chart\n"
        "image when chart_type is not `table`). **POST /analytics/export/csv** returns the rows as CSV.\n"
        "**POST /llm/export/pdf** and **POST /llm/export/csv** mirror export with the `/llm` request shape.\n"
        "**POST /reports/generate** builds a full economic PDF (intro, table, charts, conclusion) from a prompt.\n"
        "Use **GET /analytics/history** to audit past queries."
    ),
    version="4.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError):
    """Return a clear 400 instead of 500 for foreign-key / unique violations."""
    msg = str(exc.orig).lower() if exc.orig else str(exc).lower()
    if "currency" in msg or "currency_code" in msg:
        detail = "Invalid currency code. Add the currency under Currencies first, then try again."
    elif "foreign key" in msg:
        detail = "Referenced record does not exist. Check related data and try again."
    else:
        detail = "Could not save: a database constraint was violated."
    return JSONResponse(status_code=400, content={"detail": detail})


@app.on_event("startup")
def startup():
    from app.services.analytics_llm_service import ensure_analytics_dotenv

    ensure_analytics_dotenv()
    Base.metadata.create_all(bind=engine)


# ── Routers ───────────────────────────────────────────────────────────────────
# Analytics router is included BEFORE llm_router so that /analytics/query
# is handled by the new safe implementation (the llm router also declares
# POST /analytics/query — registering analytics first wins).
app.include_router(analytics_router.router)   # includes /analytics/export/pdf and /csv
app.include_router(reports_router.router)
app.include_router(users.router)
app.include_router(loans.router)
app.include_router(transactions.router)
app.include_router(economic.router)
app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(llm_router.router)
app.include_router(audit_logs_router.router)


@app.get("/", tags=["Health"])
def home():
    return {"message": "IMF Loan Management API is running", "version": "4.0.0"}
