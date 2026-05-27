from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from orchestration.knowledge import CodeAwareChunker, KnowledgeEntry, KnowledgeStore
from orchestration.knowledge.embedder import SimpleEmbedder
from orchestration.knowledge.index import VectorIndex


def test_chunker_python_ast() -> None:
    chunker = CodeAwareChunker()
    content = """
def foo():
    pass

class Bar:
    def baz(self):
        pass
"""
    chunks = chunker.chunk(content, language="python")
    assert len(chunks) >= 2
    names = [c.text.split("(")[0].strip().split()[-1] for c in chunks if c.text.strip()]
    assert any("foo" in c.text for c in chunks)
    assert any("Bar" in c.text for c in chunks)


def test_chunker_fallback() -> None:
    chunker = CodeAwareChunker(max_chunk_tokens=10)
    content = "\n".join(f"line {i}" for i in range(50))
    chunks = chunker.chunk(content, language="unknown")
    assert len(chunks) >= 3


def test_chunker_empty() -> None:
    chunker = CodeAwareChunker()
    assert chunker.chunk("") == []


def test_simple_embedder() -> None:
    emb = SimpleEmbedder(dimension=128)
    vec = emb.embed("hello world")
    assert len(vec) == 128
    assert all(isinstance(v, float) for v in vec)


def test_embedder_consistency() -> None:
    emb = SimpleEmbedder()
    v1 = emb.embed("same text")
    v2 = emb.embed("same text")
    v3 = emb.embed("different")
    assert v1 == v2
    assert v1 != v3


def test_vector_index_search() -> None:
    idx = VectorIndex(dimension=128)
    emb = SimpleEmbedder()
    v1 = emb.embed("python function")
    v2 = emb.embed("python function")
    idx.upsert("id1", v1, {"path": "a.py"})
    idx.upsert("id2", v2, {"path": "b.rs"})
    results = idx.search(emb.embed("python function"), k=2)
    assert len(results) == 2
    assert results[0].score == results[1].score


def test_vector_index_persistence() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "index.json"
        idx = VectorIndex(dimension=128)
        emb = SimpleEmbedder()
        idx.upsert("id1", emb.embed("text"))
        idx.save(path)
        idx2 = VectorIndex(dimension=128)
        idx2.load(path)
        assert idx2.size == 1


def test_knowledge_store_keyword_search() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(Path(td), vector_enabled=False)
        store.add_entry(KnowledgeEntry(path="a.py", symbol="foo", content="def foo(): return 42"))
        results = asyncio.run(store.search("foo", limit=5))
        assert len(results) == 1
        assert results[0].entry.symbol == "foo"


def test_knowledge_store_vector_search() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(Path(td), vector_enabled=True, embedding_backend="simple")
        store.add_entry(KnowledgeEntry(path="a.py", symbol="foo", content="def foo(): return 42"))
        results = asyncio.run(store.search("foo", limit=5))
        assert len(results) > 0


def test_knowledge_store_add_entries() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(Path(td), vector_enabled=False)
        entries = [
            KnowledgeEntry(path="a.py", symbol="foo", content="foo"),
            KnowledgeEntry(path="b.py", symbol="bar", content="bar"),
        ]
        ids = store.add_entries(entries)
        assert len(ids) == 2


def test_knowledge_store_persistence() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(Path(td), vector_enabled=False)
        store.add_entry(KnowledgeEntry(path="a.py", symbol="foo", content="test content"))
        store.save()
        store2 = KnowledgeStore(Path(td), vector_enabled=False)
        results = asyncio.run(store2.search("test", limit=5))
        assert len(results) >= 1


def test_knowledge_store_get_for_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(Path(td), vector_enabled=False)
        store.add_entry(KnowledgeEntry(path="a.py", symbol="foo", content="foo code"))
        store.add_entry(KnowledgeEntry(path="b.py", symbol="bar", content="bar code"))
        entries = store.get_for_file("a.py")
        assert len(entries) == 1
        assert entries[0].symbol == "foo"


def test_knowledge_store_rebuild_index() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(Path(td), vector_enabled=True, embedding_backend="simple")
        store.add_entry(KnowledgeEntry(path="a.py", symbol="foo", content="def foo(): return 42"))
        count = asyncio.run(store.rebuild_index())
        assert count > 0


def test_vector_index_search_with_filter() -> None:
    idx = VectorIndex(dimension=128)
    emb = SimpleEmbedder()
    idx.upsert("id1", emb.embed("python code"), {"path": "a.py"})
    idx.upsert("id2", emb.embed("rust code"), {"path": "b.rs"})
    results = idx.search_with_filter(
        emb.embed("code"),
        k=10,
        filter_fn=lambda m: m.get("path") == "a.py",
    )
    assert len(results) == 1
    assert results[0].chunk_id == "id1"
