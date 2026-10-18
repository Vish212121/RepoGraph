"""FastAPI dependencies for shared RepoBrain services."""

from functools import lru_cache

from fastapi import HTTPException

from app.agent.orchestrator import ReasoningAgent
from app.config import get_settings
from app.graph.connection import get_graph
from app.memory.repository import MemoryRepository


@lru_cache(maxsize=1)
def get_agent() -> ReasoningAgent:
    """Construct the agent once per API process."""

    return ReasoningAgent()


def get_agent_or_503() -> ReasoningAgent:
    """Convert unavailable FalkorDB/Ollama setup into a useful HTTP error."""

    try:
        return get_agent()
    except Exception as exc:  # dependency boundary: preserve internal details in logs only
        raise HTTPException(
            status_code=503,
            detail="RepoBrain could not connect to its configured graph service. Start FalkorDB and retry.",
        ) from exc


@lru_cache(maxsize=1)
def get_memory_repository() -> MemoryRepository:
    settings = get_settings()
    return MemoryRepository(get_graph(settings), settings=settings)
