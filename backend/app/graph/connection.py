"""FalkorDB client and graph selection helpers."""

from falkordb import FalkorDB

from app.config import Settings, get_settings


def create_client(settings: Settings | None = None) -> FalkorDB:
    """Create a FalkorDB client from validated settings."""

    active_settings = settings or get_settings()
    return FalkorDB(
        host=active_settings.falkordb_host,
        port=active_settings.falkordb_port,
        password=active_settings.falkordb_password,
    )


def get_graph(settings: Settings | None = None):
    """Select and return the configured graph."""

    active_settings = settings or get_settings()
    return create_client(active_settings).select_graph(active_settings.repo_graph)
