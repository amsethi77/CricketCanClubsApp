from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
READMELLM_FILE = REPO_ROOT / "READMELLM.md"


@lru_cache(maxsize=1)
def _registry_text() -> str:
    return READMELLM_FILE.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _parsed_prompts() -> dict[str, str]:
    text = _registry_text()
    prompts: dict[str, str] = {}
    pattern = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=\s*\"\"\"(.*?)\"\"\"", re.DOTALL | re.MULTILINE)
    for match in pattern.finditer(text):
        prompts[match.group(1)] = match.group(2)
    return prompts


def registry_module() -> dict[str, str]:
    return dict(_parsed_prompts())


def build_prompt(template: str, **kwargs: Any) -> str:
    return str(template).format(**kwargs)


def prompt_names() -> list[str]:
    return sorted(_parsed_prompts().keys())


def prompt_value(name: str, default: str = "") -> str:
    return str(_parsed_prompts().get(name, default))


def prompt_manifest() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name, value in _parsed_prompts().items():
        entries.append(
            {
                "name": name,
                "template": value,
                "description": value.strip().splitlines()[0][:200] if value.strip() else "",
            }
        )
    return sorted(entries, key=lambda item: item["name"])


def prompt_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for item in prompt_manifest():
        documents.append(
            {
                "doc_type": "prompt",
                "source_id": item["name"],
                "title": item["name"].replace("_", " ").title(),
                "content": item["template"],
                "source_json": {},
                "club_id": "",
                "season_year": "",
            }
        )
    return documents
