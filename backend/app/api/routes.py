"""FastAPI routes for querying RepoBrain and inspecting graph evidence."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import get_agent_or_503, get_memory_repository
from app.api.models import FindingResponse, HealthResponse, QueryRequest, QueryResponse, SnapshotResponse, EvidenceResponse
from app.config import get_settings
from app.memory.models import FindingCreate, FindingUpdate
from app.memory.repository import MemoryRepository
from app.tenant import resolve_demo_tenant

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="repobrain-api",
        graph_configured=bool(settings.falkordb_host and settings.falkordb_port),
        ollama_configured=bool(settings.ollama_base_url and settings.agent_model),
    )


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    agent=Depends(get_agent_or_503),
    x_demo_tenant: str = Header(default="demo-alpha", alias="X-Demo-Tenant"),
    memory: MemoryRepository | None = Depends(get_memory_repository),
) -> QueryResponse:
    tenant_id = resolve_demo_tenant(x_demo_tenant if isinstance(x_demo_tenant, str) else "demo-alpha")
    response = agent.answer(request.question, snapshot_id=request.snapshot_id, tenant_id=tenant_id)
    session_id = None
    if isinstance(memory, MemoryRepository):
        session_id = memory.ensure_session(tenant_id, request.session_id)
        memory.record_interaction(tenant_id, session_id, request.question, request.snapshot_id, response)
    result = QueryResponse.from_agent(response)
    result.session_id = session_id
    return result


@router.get("/snapshots", response_model=list[SnapshotResponse])
def snapshots(agent=Depends(get_agent_or_503)) -> list[SnapshotResponse]:
    if getattr(agent, "tools", None) is not None:
        evidence = agent.tools.list_snapshots()
    else:
        evidence, _ = agent.gateway.invoke("list_snapshots", {"limit": 20})
    return [SnapshotResponse.model_validate(row) for row in evidence.rows]


@router.post("/sessions")
def sessions(
    session_id: str | None = None,
    x_demo_tenant: str = Header(default="demo-alpha", alias="X-Demo-Tenant"),
    memory: MemoryRepository = Depends(get_memory_repository),
) -> dict[str, str]:
    tenant_id = resolve_demo_tenant(x_demo_tenant)
    return {"session_id": memory.ensure_session(tenant_id, session_id)}


@router.get("/memory", response_model=EvidenceResponse)
def memory_recall(
    q: str = Query(min_length=1, max_length=2_000),
    snapshot_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    x_demo_tenant: str = Header(default="demo-alpha", alias="X-Demo-Tenant"),
    memory: MemoryRepository = Depends(get_memory_repository),
) -> EvidenceResponse:
    tenant_id = resolve_demo_tenant(x_demo_tenant)
    return EvidenceResponse.model_validate(memory.recall_context(tenant_id, q, snapshot_id, limit).to_dict())


@router.post("/findings", response_model=FindingResponse)
def create_finding(
    request: FindingCreate,
    x_demo_tenant: str = Header(default="demo-alpha", alias="X-Demo-Tenant"),
    memory: MemoryRepository = Depends(get_memory_repository),
) -> FindingResponse:
    tenant_id = resolve_demo_tenant(x_demo_tenant)
    return FindingResponse.model_validate(memory.create_finding(tenant_id, request))


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
def update_finding(
    finding_id: str,
    request: FindingUpdate,
    x_demo_tenant: str = Header(default="demo-alpha", alias="X-Demo-Tenant"),
    memory: MemoryRepository = Depends(get_memory_repository),
) -> FindingResponse:
    tenant_id = resolve_demo_tenant(x_demo_tenant)
    try:
        result = memory.update_finding(tenant_id, finding_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Finding not found for this tenant") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FindingResponse.model_validate(result)


def create_app() -> FastAPI:
    application = FastAPI(
        title="RepoBrain API",
        version="0.1.0",
        description="Evidence-backed repository reasoning over FalkorDB.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Demo-Tenant"],
    )
    application.include_router(router)
    return application


app = create_app()
