"""Small standard-library client for Ollama's local embedding endpoint."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaEmbeddingError(RuntimeError):
    """Raised when the local Ollama service cannot generate valid embeddings."""


@dataclass(frozen=True)
class EmbeddingResult:
    """Validated vectors returned by one embedding request."""

    model: str
    vectors: list[list[float]]


class OllamaEmbeddingClient:
    """Generate embeddings locally without sending memory to a paid API."""

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, inputs: str | Sequence[str]) -> EmbeddingResult:
        values = [inputs] if isinstance(inputs, str) else list(inputs)
        if not values or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("inputs must contain at least one non-empty string")

        request = Request(
            f"{self.base_url}/api/embed",
            data=json.dumps({"model": self.model, "input": values, "truncate": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise OllamaEmbeddingError(f"Ollama embedding request failed: {exc}") from exc

        raw_vectors = payload.get("embeddings")
        if not isinstance(raw_vectors, list) or len(raw_vectors) != len(values):
            raise OllamaEmbeddingError("Ollama returned an unexpected embeddings payload")

        vectors: list[list[float]] = []
        dimensions: int | None = None
        for raw_vector in raw_vectors:
            if not isinstance(raw_vector, list) or not raw_vector:
                raise OllamaEmbeddingError("Ollama returned an empty embedding vector")
            try:
                vector = [float(value) for value in raw_vector]
            except (TypeError, ValueError) as exc:
                raise OllamaEmbeddingError("Ollama returned a non-numeric embedding vector") from exc
            if not all(math.isfinite(value) for value in vector):
                raise OllamaEmbeddingError("Ollama returned a non-finite embedding vector")
            if dimensions is None:
                dimensions = len(vector)
            elif len(vector) != dimensions:
                raise OllamaEmbeddingError("Ollama returned vectors with inconsistent dimensions")
            vectors.append(vector)

        returned_model = payload.get("model")
        return EmbeddingResult(model=returned_model if isinstance(returned_model, str) else self.model, vectors=vectors)
