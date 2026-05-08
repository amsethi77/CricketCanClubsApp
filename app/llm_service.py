from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

try:
    from cricket_brain import (
        _chunk_text_for_context,
        _contains_profanity,
        _cosine_similarity,
        _llm_embedding_for_text,
        _redact_profanity,
        answer_question,
        get_llm_status,
    )
    from cricket_store import load_store, refresh_llm_document_index, _connection, now_iso
    from llm_registry import build_prompt, prompt_manifest, prompt_value
except ModuleNotFoundError:
    from app.cricket_brain import (
        _chunk_text_for_context,
        _contains_profanity,
        _cosine_similarity,
        _llm_embedding_for_text,
        _redact_profanity,
        answer_question,
        get_llm_status,
    )
    from app.cricket_store import load_store, refresh_llm_document_index, _connection, now_iso
    from app.llm_registry import build_prompt, prompt_manifest, prompt_value


LLM_INFER_LIMIT = 8
LLM_CACHE_LIMIT = 200


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _safe_format(template: str, **kwargs: Any) -> str:
    class _Fallback(dict[str, Any]):
        def __missing__(self, key: str) -> str:  # type: ignore[override]
            return "{" + key + "}"

    return str(template).format_map(_Fallback(**kwargs))


def _document_embedding(document: dict[str, Any]) -> list[float]:
    raw = str(document.get("embedding_json") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    embedding: list[float] = []
    for value in parsed:
        if isinstance(value, (int, float)):
            embedding.append(float(value))
    return embedding


def _document_text(document: dict[str, Any]) -> str:
    title = str(document.get("title") or "").strip()
    content = str(document.get("content") or "").strip()
    parts = [part for part in [title, content] if part]
    return "\n".join(parts)


def _document_terms(document: dict[str, Any]) -> set[str]:
    text = f"{document.get('title') or ''} {document.get('content') or ''}".lower()
    return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 2}


def _query_terms(question: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _normalized_text(question)) if len(token) > 2}


def _llm_documents(store: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in store.get("llm_documents", []) if isinstance(item, dict)]


def list_prompt_manifest() -> list[dict[str, Any]]:
    return prompt_manifest()


def list_llm_documents(store: dict[str, Any], *, doc_type: str = "", club_id: str = "", query: str = "", limit: int = 200) -> list[dict[str, Any]]:
    documents = _llm_documents(store)
    clean_doc_type = _normalized_text(doc_type)
    clean_club_id = str(club_id or "").strip()
    clean_query = _query_terms(query)
    results: list[dict[str, Any]] = []
    for document in documents:
        if clean_doc_type and _normalized_text(document.get("doc_type", "")) != clean_doc_type:
            continue
        if clean_club_id and str(document.get("club_id") or "").strip() not in {clean_club_id, ""}:
            continue
        if clean_query:
            haystack = _document_terms(document)
            if not any(term in haystack for term in clean_query):
                continue
        results.append(document)
        if len(results) >= max(1, min(int(limit or 200), 500)):
            break
    return results


def _score_document(question: str, document: dict[str, Any], query_embedding: list[float] | None, llm_status: dict[str, Any]) -> float:
    score = 0.0
    question_terms = _query_terms(question)
    document_terms = _document_terms(document)
    if question_terms and document_terms:
        overlap = len(question_terms.intersection(document_terms))
        score += overlap * 4.0
    title = str(document.get("title") or "")
    if title and any(term in title.lower() for term in question_terms):
        score += 3.0
    doc_embedding = _document_embedding(document)
    if query_embedding and doc_embedding:
        score += _cosine_similarity(query_embedding, doc_embedding) * 25.0
    content_hash = str(document.get("content_hash") or "").strip()
    if content_hash:
        score += 0.5
    if str(document.get("doc_type") or "") == "prompt":
        score += 0.4
    if str(document.get("club_id") or "").strip():
        score += 0.15
    if llm_status.get("provider") != "ollama":
        score *= 0.85
    return score


def rank_llm_documents(
    question: str,
    store: dict[str, Any],
    *,
    focus_club_id: str = "",
    limit: int = LLM_INFER_LIMIT,
    llm_status: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    llm_status = llm_status or get_llm_status()
    query_embedding = _llm_embedding_for_text(question, llm_status)
    documents = _llm_documents(store)
    clean_focus_club_id = str(focus_club_id or "").strip()
    ranked: list[dict[str, Any]] = []
    for document in documents:
        doc_club_id = str(document.get("club_id") or "").strip()
        if clean_focus_club_id and doc_club_id and doc_club_id != clean_focus_club_id and str(document.get("doc_type") or "") != "prompt":
            continue
        score = _score_document(question, document, query_embedding, llm_status)
        if score <= 0:
            continue
        ranked.append(
            {
                **document,
                "score": round(score, 4),
            }
        )
    ranked.sort(key=lambda item: (-float(item.get("score", 0) or 0), str(item.get("updated_at") or ""), str(item.get("title") or "")))
    return ranked[: max(1, min(int(limit or LLM_INFER_LIMIT), 20))]


def _query_cache_key(question: str, focus_club_id: str, prompt_name: str, mode: str, llm_status: dict[str, Any], documents: list[dict[str, Any]]) -> str:
    payload = {
        "question": _normalized_text(question),
        "focus_club_id": str(focus_club_id or "").strip(),
        "prompt_name": str(prompt_name or "").strip().lower(),
        "mode": str(mode or "").strip().lower(),
        "provider": str(llm_status.get("provider") or "").strip().lower(),
        "model": str(llm_status.get("model") or "").strip().lower(),
        "embedding_model": str(llm_status.get("embedding_model") or "").strip().lower(),
        "documents": [f"{doc.get('id')}:{doc.get('content_hash')}:{doc.get('updated_at')}" for doc in documents],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _load_query_cache(key: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM llm_query_cache WHERE context_hash = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (key,),
        ).fetchone()
    return dict(row) if row else None


def _save_query_cache(
    *,
    key: str,
    question: str,
    answer: str,
    mode: str,
    source_provider: str,
    source_label: str,
    prompt_name: str,
) -> None:
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO llm_query_cache (id, question, answer, mode, source_provider, source_label, prompt_name, context_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              question = excluded.question,
              answer = excluded.answer,
              mode = excluded.mode,
              source_provider = excluded.source_provider,
              source_label = excluded.source_label,
              prompt_name = excluded.prompt_name,
              context_hash = excluded.context_hash,
              updated_at = excluded.updated_at
            """,
            (
                f"llmcache-{uuid.uuid4().hex[:16]}",
                str(question or "").strip(),
                str(answer or "").strip(),
                str(mode or "").strip(),
                str(source_provider or "").strip(),
                str(source_label or "").strip(),
                str(prompt_name or "").strip(),
                key,
                now_iso(),
                now_iso(),
            ),
        )
        connection.execute(
            """
            DELETE FROM llm_query_cache
            WHERE id NOT IN (
              SELECT id FROM llm_query_cache
              ORDER BY updated_at DESC, id DESC
              LIMIT ?
            )
            """,
            (LLM_CACHE_LIMIT,),
        )


def clear_query_cache() -> int:
    with _connection() as connection:
        before = int(connection.execute("SELECT COUNT(*) FROM llm_query_cache").fetchone()[0] or 0)
        with connection:
            connection.execute("DELETE FROM llm_query_cache")
        return before


def _build_context_block(documents: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for document in documents:
        text = _document_text(document)
        if not text:
            continue
        chunks = _chunk_text_for_context(text)
        for index, chunk in enumerate(chunks[:2], start=1):
            blocks.append(
                "\n".join(
                    [
                        f"[{document.get('doc_type') or 'document'}:{document.get('title') or document.get('id') or 'item'}#{index}]",
                        chunk,
                    ]
                )
            )
    return "\n\n".join(blocks)


def _render_inference_prompt(
    question: str,
    *,
    prompt_name: str = "",
    template_args: dict[str, Any] | None = None,
    focus_club_id: str = "",
    documents: list[dict[str, Any]] | None = None,
    store: dict[str, Any] | None = None,
) -> tuple[str, str]:
    documents = documents or []
    template_args = dict(template_args or {})
    manifest = {item["name"]: item["template"] for item in prompt_manifest()}
    system_prompt = prompt_value("SYSTEM_PROMPT") or "You are a cricket analytics assistant."
    doc_block = _build_context_block(documents)
    club_block = ""
    if store:
        club = dict(store.get("focus_club") or store.get("club") or {})
        club_name = str(club.get("name") or "").strip()
        club_id = str(club.get("id") or "").strip()
        if club_name or club_id:
            club_block = f"Focused club: {club_name or club_id}\n"
    if prompt_name and prompt_name in manifest:
        formatted_template = _safe_format(
            manifest[prompt_name],
            question=question,
            prompt=question,
            query=question,
            context=doc_block,
            context_block=doc_block,
            retrieved_context=doc_block,
            club_context=club_block,
            focus_club_id=focus_club_id,
            **template_args,
        )
        user_prompt = formatted_template
    else:
        user_prompt = "\n".join(
            [
                system_prompt.strip(),
                "",
                club_block.rstrip(),
                "Retrieved context:",
                doc_block or "No relevant indexed documents were found.",
                "",
                f"Question: {question}",
                "Answer only from the provided context and stored cricket data.",
            ]
        ).strip()
    return system_prompt, user_prompt


def _call_ollama_chat(model: str, system_prompt: str, user_prompt: str, llm_status: dict[str, Any], *, temperature: float = 0.2) -> str:
    response = httpx.post(
        f"{str(llm_status.get('base_url') or '').rstrip('/')}/api/chat",
        json={
            "model": model,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.85,
                "top_k": 40,
                "num_predict": 350,
                "repeat_penalty": 1.08,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=300.0,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("message", {}).get("content", "") or "").strip()


def reindex_llm_corpus(store: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current_store = load_store() if store is None else store
    with _connection() as connection:
        return refresh_llm_document_index(connection, current_store)


def infer(
    question: str,
    *,
    store: dict[str, Any] | None = None,
    focus_club_id: str = "",
    mode: str = "auto",
    prompt_name: str = "",
    template_args: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    limit: int = LLM_INFER_LIMIT,
) -> dict[str, Any]:
    current_store = load_store() if store is None else store
    llm_status = get_llm_status()
    if _contains_profanity(question):
        return {
            "answer": "Please keep the question cricket-focused and respectful.",
            "mode": "moderated",
            "source_provider": "heuristic",
            "source_label": "Content filter",
            "llm": llm_status,
            "prompt_name": prompt_name or "",
            "documents": [],
            "cached": False,
        }

    documents = rank_llm_documents(question, current_store, focus_club_id=focus_club_id, limit=limit, llm_status=llm_status)
    cache_key = _query_cache_key(question, focus_club_id, prompt_name, mode, llm_status, documents)
    cached = _load_query_cache(cache_key)
    if cached:
        return {
            "answer": str(cached.get("answer") or ""),
            "mode": str(cached.get("mode") or mode or "auto"),
            "source_provider": str(cached.get("source_provider") or "heuristic"),
            "source_label": str(cached.get("source_label") or ""),
            "prompt_name": str(cached.get("prompt_name") or prompt_name or ""),
            "documents": documents,
            "cached": True,
            "llm": llm_status,
        }

    if not llm_status.get("available") or llm_status.get("provider") != "ollama" or not llm_status.get("model"):
        fallback = answer_question(question, current_store, history=history)
        answer = str(fallback.get("answer") or "").strip()
        return {
            "answer": answer,
            "mode": str(fallback.get("mode") or mode or "heuristic"),
            "source_provider": str(fallback.get("source_provider") or "heuristic"),
            "source_label": str(fallback.get("source_label") or "Heuristic fallback"),
            "prompt_name": prompt_name or "",
            "documents": documents,
            "cached": False,
            "llm": llm_status,
        }

    system_prompt, user_prompt = _render_inference_prompt(
        question,
        prompt_name=prompt_name,
        template_args=template_args,
        focus_club_id=focus_club_id,
        documents=documents,
        store=current_store,
    )
    answer = _call_ollama_chat(
        str(llm_status.get("model") or ""),
        system_prompt,
        user_prompt,
        llm_status,
        temperature=0.35 if mode == "forecast" else 0.18,
    )
    answer = _redact_profanity(answer)
    if not answer:
        fallback = answer_question(question, current_store, history=history)
        answer = str(fallback.get("answer") or "").strip()
        source_provider = str(fallback.get("source_provider") or "heuristic")
        source_label = str(fallback.get("source_label") or "Heuristic fallback")
        mode_value = str(fallback.get("mode") or mode or "heuristic")
    else:
        source_provider = "ollama"
        source_label = "LLM online"
        mode_value = "inference" if mode == "auto" else mode
    _save_query_cache(
        key=cache_key,
        question=question,
        answer=answer,
        mode=mode_value,
        source_provider=source_provider,
        source_label=source_label,
        prompt_name=prompt_name,
    )
    return {
        "answer": answer,
        "mode": mode_value,
        "source_provider": source_provider,
        "source_label": source_label,
        "prompt_name": prompt_name or "",
        "documents": documents,
        "cached": False,
        "llm": llm_status,
        "prompt_preview": user_prompt[:4000],
        "system_prompt": system_prompt[:2000],
    }
