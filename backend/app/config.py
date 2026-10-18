"""Validated configuration for the RepoBrain backend."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and .env."""

    falkordb_host: str = "127.0.0.1"
    falkordb_port: int = Field(default=6379, ge=1, le=65535)
    falkordb_password: str | None = None
    repo_graph: str = "repobrain"
    target_repo: str = "pallets/flask"
    target_sha: str | None = None
    data_dir: Path = Path("data/raw")
    github_token: str | None = None
    github_api_base_url: str = "https://api.github.com"
    snapshot_commit_limit: int = Field(default=25, ge=1, le=100)
    snapshot_max_files: int = Field(default=10_000, ge=1, le=100_000)
    ingest_batch_size: int = Field(default=100, ge=1, le=1_000)
    ollama_base_url: str = "http://127.0.0.1:11434"
    agent_model: str = "llama3.2:3b"
    agent_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    ollama_embedding_model: str = "nomic-embed-text"
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    memory_vector_candidate_multiplier: int = Field(default=10, ge=1, le=50)
    memory_vector_max_candidates: int = Field(default=100, ge=1, le=500)
    memory_vector_min_score: float = Field(default=0.25, ge=-1.0, le=1.0)
    tool_mode: str = "mcp"
    mcp_server_command: str = "python"
    mcp_server_module: str = "app.mcp.server"
    mcp_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    evaluation_model: str | None = None
    dependency_extraction_enabled: bool = True
    dependency_max_files: int = Field(default=1_000, ge=1, le=10_000)
    dependency_content_max_bytes: int = Field(default=200_000, ge=1_000, le=2_000_000)
    dependency_max_hops: int = Field(default=3, ge=1, le=5)
    review_pr_limit: int = Field(default=50, ge=1, le=200)
    decision_source_limit: int = Field(default=25, ge=1, le=100)
    decision_comment_limit: int = Field(default=100, ge=1, le=500)
    decision_excerpt_length: int = Field(default=800, ge=200, le=2_000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("falkordb_password", mode="before")
    @classmethod
    def empty_password_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("repo_graph")
    @classmethod
    def validate_graph_name(cls, value: str) -> str:
        if not value or not value.replace("_", "").isalnum():
            raise ValueError("repo_graph must contain only letters, digits, and underscores")
        return value

    @field_validator("tool_mode")
    @classmethod
    def validate_tool_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"mcp", "direct"}:
            raise ValueError("tool_mode must be either 'mcp' or 'direct'")
        return value

    @field_validator("ollama_embedding_model")
    @classmethod
    def validate_embedding_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ollama_embedding_model must not be empty")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""

    return Settings()
