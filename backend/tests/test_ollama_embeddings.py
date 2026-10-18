from __future__ import annotations

import json

import pytest

from app.embeddings.ollama import OllamaEmbeddingClient, OllamaEmbeddingError


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_embed_posts_to_the_current_ollama_embedding_endpoint(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"model": "nomic-embed-text", "embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    monkeypatch.setattr("app.embeddings.ollama.urlopen", fake_urlopen)
    result = OllamaEmbeddingClient("http://127.0.0.1:11434/", "nomic-embed-text", 12).embed(["one", "two"])

    assert captured == {
        "url": "http://127.0.0.1:11434/api/embed",
        "payload": {"model": "nomic-embed-text", "input": ["one", "two"], "truncate": True},
        "timeout": 12,
    }
    assert result.vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_rejects_invalid_vectors(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.embeddings.ollama.urlopen",
        lambda request, timeout: FakeResponse({"embeddings": [[float("nan")]]}),
    )

    with pytest.raises(OllamaEmbeddingError, match="non-finite"):
        OllamaEmbeddingClient("http://127.0.0.1:11434", "nomic-embed-text").embed("test")
