from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol


class EmbedderProtocol(Protocol):
    def embed(self, text: str) -> list[float]: ...

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._dimension = 384

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )

    def embed(self, text: str) -> list[float]:
        self._load_model()
        assert self._model is not None
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        assert self._model is not None
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class SimpleEmbedder:
    def __init__(self, dimension: int = 128) -> None:
        self._dimension = dimension

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        result = [b / 255.0 for b in h]
        while len(result) < self._dimension:
            h = hashlib.sha256(h).digest()
            result.extend(b / 255.0 for b in h)
        return result[: self._dimension]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class EmbeddingCache:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache: dict[str, list[float]] = {}
        self._cache_dir = cache_dir

    def get(self, text: str) -> list[float] | None:
        key = self._key(text)
        if key in self._cache:
            return self._cache[key]
        if self._cache_dir is not None:
            entry = self._load_from_disk(key)
            if entry is not None:
                self._cache[key] = entry
                return entry
        return None

    def set(self, text: str, embedding: list[float]) -> None:
        key = self._key(text)
        self._cache[key] = embedding
        if self._cache_dir is not None:
            self._save_to_disk(key, embedding)

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_from_disk(self, key: str) -> list[float] | None:
        if self._cache_dir is None:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _save_to_disk(self, key: str, embedding: list[float]) -> None:
        if self._cache_dir is None:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{key}.json"
        try:
            path.write_text(json.dumps(embedding))
        except OSError:
            pass


def create_embedder(backend: str = "simple") -> tuple[EmbedderProtocol, int]:
    if backend == "local":
        embedder = LocalEmbedder()
        return embedder, embedder._dimension
    embedder = SimpleEmbedder()
    return embedder, embedder._dimension
