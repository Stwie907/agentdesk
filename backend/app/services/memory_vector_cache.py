"""Read cached documents, embed every query, and write only in Runtime."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import re

import requests
from sqlalchemy import literal, select, tuple_
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.memory import Memory
from app.models.user_memory import UserMemory
from app.models.memory_vector_cache import MemoryVectorCache
from app.services.memory_embeddings import SemanticMemoryUnavailable, normalize_vector


MOCK_DIGEST = sha256(b"agentdesk-mock-fixtures-v1").hexdigest()


def namespace(settings):
    endpoint = "offline" if settings.provider == "mock" else settings.base_url.rstrip("/")
    return sha256(json.dumps([1, settings.provider, settings.model, endpoint]).encode()).hexdigest()


def source_key(row):
    return ("agent", row.agent_id, row.id) if isinstance(row, Memory) else ("user", row.user_id, row.id)


def content_hash(content):
    return sha256(content.encode("utf-8")).hexdigest()


def model_digest(settings):
    if settings.provider == "mock":
        return MOCK_DIGEST
    try:
        with requests.Session() as client:
            client.trust_env = False
            response = client.get(settings.base_url.rstrip("/") + "/api/tags",
                                  timeout=min(5, settings.memory.timeout_seconds), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                return None
            body = response.json()
        models = body.get("models") if isinstance(body, dict) else None
        if not isinstance(models, list):
            return None
        names = {settings.model, settings.model + ":latest"}
        matched = [row for row in models if isinstance(row, dict)
                   and any(name in names for name in (row.get("model"), row.get("name")) if isinstance(name, str))]
        if len(matched) != 1:
            return None
        digest = matched[0].get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", digest):
            return None
        return digest.removeprefix("sha256:")
    except (requests.RequestException, ValueError):
        # Caching is optional; embed all texts if model identity is unavailable.
        return None


def invalidate_memory_vectors(db, source_type, owner_id, memory_id):
    """Called in the same transaction as a successful source edit or delete."""
    db.query(MemoryVectorCache).filter_by(source_type=source_type, owner_id=owner_id,
                                         memory_id=memory_id).delete(synchronize_session=False)


def _cached_vector(entry, snapshot, digest):
    source_type, owner_id, memory_id, content, created_at = snapshot
    if (not isinstance(entry.vector_json, str) or type(entry.dimensions) is not int
            or not 0 < entry.dimensions <= 16384 or entry.model_digest != digest or entry.content_hash != content_hash(content)
            or entry.source_created_at != created_at
            or entry.vector_hash != content_hash(entry.vector_json)):
        return None
    try:
        vector = normalize_vector(json.loads(entry.vector_json))
    except (ValueError, SemanticMemoryUnavailable):
        return None
    return vector if len(vector) == entry.dimensions else None


def cached_embeddings(db, rows, query, settings, embed, *, populate=False):
    snapshots = [(*source_key(row), row.content, row.created_at) for row in rows]
    keyspace = namespace(settings)
    stats = {"version": 1, "status": "active", "documents": len(rows), "hits": 0,
             "misses": len(rows), "written": 0, "provider": settings.provider, "model": settings.model}
    try:
        entries = []
        for offset in range(0, len(snapshots), 200):
            entries.extend(db.query(MemoryVectorCache).filter(MemoryVectorCache.namespace == keyspace,
                tuple_(MemoryVectorCache.source_type, MemoryVectorCache.owner_id, MemoryVectorCache.memory_id).in_(
                    [snapshot[:3] for snapshot in snapshots[offset:offset + 200]])).all())
    except (SQLAlchemyError, ValueError, TypeError):
        stats["status"] = "storage_unavailable"
        return embed([query, *(snapshot[3] for snapshot in snapshots)], settings), stats
    # A cold read-only preview does not need a model identity lookup.
    digest = model_digest(settings) if entries or populate else None
    if digest is None:
        stats["status"] = "digest_unavailable" if entries or populate else "read_only_cold"
        return embed([query, *(snapshot[3] for snapshot in snapshots)], settings), stats
    found = { (row.source_type, row.owner_id, row.memory_id): row for row in entries }
    documents = [None if snapshot[:3] not in found else _cached_vector(found[snapshot[:3]], snapshot, digest)
                 for snapshot in snapshots]
    missing = [index for index, value in enumerate(documents) if value is None]
    generated = embed([query, *(snapshots[index][3] for index in missing)], settings)
    if len(generated) != len(missing) + 1 or not generated or len({len(vector) for vector in generated}) != 1:
        raise SemanticMemoryUnavailable("Embedding vectors do not match the scoped memory rows.")
    query_vector = generated[0]
    for index, vector in zip(missing, generated[1:]):
        documents[index] = vector
    # Stored dimensions must also match the freshly embedded query.
    missing_set = set(missing)
    incompatible = [index for index, vector in enumerate(documents)
                    if index not in missing_set and len(vector) != len(query_vector)]
    if incompatible:
        fresh = embed([snapshots[index][3] for index in incompatible], settings)
        if len(fresh) != len(incompatible) or any(len(vector) != len(query_vector) for vector in fresh):
            raise SemanticMemoryUnavailable("Embedding dimensions changed during retrieval.")
        for index, vector in zip(incompatible, fresh):
            documents[index] = vector
        missing.extend(incompatible)
    stats["hits"], stats["misses"] = len(rows) - len(missing), len(missing)
    if settings.provider == "ollama" and (stats["hits"] or (populate and missing)):
        if model_digest(settings) != digest:
            raise SemanticMemoryUnavailable("Local embedding model identity changed during retrieval. Retry after the model update finishes.")
    if populate and missing:
        try:
            with db.begin_nested():
                for index in missing:
                    source_type, owner_id, memory_id, content, created_at = snapshots[index]
                    if created_at is None:
                        continue
                    source = Memory if source_type == "agent" else UserMemory
                    owner_column = source.agent_id if source_type == "agent" else source.user_id
                    encoded = json.dumps(documents[index], separators=(",", ":"), allow_nan=False)
                    values = {"source_type": source_type, "owner_id": owner_id, "memory_id": memory_id,
                              "namespace": keyspace, "model_digest": digest, "content_hash": content_hash(content),
                              "source_created_at": created_at, "dimensions": len(documents[index]),
                              "vector_json": encoded, "vector_hash": content_hash(encoded),
                              "created_at": datetime.now(timezone.utc).replace(tzinfo=None)}
                    # Conditional insert-select prevents late writes from recreating
                    # a cache for a deleted or concurrently edited source record.
                    selection = select(*(literal(value) for value in values.values())).select_from(source).where(
                        source.id == memory_id, owner_column == owner_id, source.content == content,
                        source.created_at == created_at)
                    statement = insert(MemoryVectorCache).from_select(list(values), selection)
                    statement = statement.on_conflict_do_update(
                        index_elements=["source_type", "owner_id", "memory_id", "namespace"],
                        set_={key: getattr(statement.excluded, key) for key in values if key not in
                              {"source_type", "owner_id", "memory_id", "namespace"}})
                    stats["written"] += db.execute(statement).rowcount
        except SQLAlchemyError:
            stats["written"] = 0
            stats["status"] = "write_unavailable"
    return [query_vector, *documents], stats
