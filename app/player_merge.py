"""Merge two member records into one (duplicate player management, Phase 2).

Pure store transformations. The caller saves the store (which rebuilds the member_*_stats tables from it)
and relinks the auth database. Scorecard player names are never changed, so historical text stays as written.
"""

from __future__ import annotations

from typing import Any

try:
    from cricket_store import normalize_name
except ImportError:
    from app.cricket_store import normalize_name

MEMBER_REF_KEYS = {"member_id", "heartlake_captain_member_id"}
MEMBER_REF_LIST_KEYS = {"member_ids", "selected_playing_xi_member_ids"}


class MergeError(ValueError):
    """Raised when two members cannot be merged safely. The message is shown to the reviewer."""


def _is_ref_key(key: str) -> bool:
    return key in MEMBER_REF_KEYS or key.endswith("_member_id")


def _is_ref_list_key(key: str) -> bool:
    return key in MEMBER_REF_LIST_KEYS or key.endswith("_member_ids")


def _collect_refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and _is_ref_key(key) and value.strip():
                found.add(value.strip())
            elif isinstance(value, list) and _is_ref_list_key(key):
                found.update(str(item).strip() for item in value if str(item).strip())
            else:
                _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)


def _rewrite_refs(node: Any, old: str, new: str) -> int:
    """Point every member reference from old to new. Returns how many references changed."""
    changed = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and _is_ref_key(key) and value.strip() == old:
                node[key] = new
                changed += 1
            elif isinstance(value, list) and _is_ref_list_key(key):
                replaced = [new if str(item).strip() == old else item for item in value]
                if replaced != value:
                    node[key] = list(dict.fromkeys(replaced))
                    changed += sum(1 for item in value if str(item).strip() == old)
            else:
                changed += _rewrite_refs(value, old, new)
    elif isinstance(node, list):
        for item in node:
            changed += _rewrite_refs(item, old, new)
    return changed


def _find_member(store: dict[str, Any], member_id: str) -> dict[str, Any] | None:
    return next((item for item in store.get("members", []) or [] if str(item.get("id") or "").strip() == member_id), None)


def _club_key(link: dict[str, Any]) -> str:
    return str(link.get("club_id") or "").strip() or normalize_name(str(link.get("club_name") or ""))


def choose_survivor(store: dict[str, Any], first_id: str, second_id: str) -> tuple[str, str]:
    """Return (survivor_id, removed_id). The older record survives; list order is treated as creation order."""
    members = store.get("members", []) or []
    order = {str(item.get("id") or "").strip(): index for index, item in enumerate(members) if isinstance(item, dict)}
    if first_id not in order or second_id not in order:
        raise MergeError("Player not found.")
    if order[first_id] <= order[second_id]:
        return first_id, second_id
    return second_id, first_id


def shared_records(store: dict[str, Any], first_id: str, second_id: str) -> list[str]:
    """Top-level records (fixtures, archives, ...) that already reference both members.

    Merging such a record would count the same player twice, so the merge is refused.
    """
    shared: list[str] = []
    for key, value in store.items():
        if key == "members" or not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            refs: set[str] = set()
            _collect_refs(item, refs)
            if first_id in refs and second_id in refs:
                shared.append(f"{key} {item.get('id') or item.get('name') or ''}".strip())
    return shared


def merge_members_in_store(store: dict[str, Any], first_id: str, second_id: str, keep_id: str | None = None) -> dict[str, Any]:
    """Merge the two members in place and return a summary. The older record survives unless keep_id names the other one."""
    first_id, second_id = str(first_id or "").strip(), str(second_id or "").strip()
    if not first_id or not second_id or first_id == second_id:
        raise MergeError("Choose two different players.")
    if keep_id and str(keep_id) in (first_id, second_id):
        keep_id, drop_id = str(keep_id), second_id if str(keep_id) == first_id else first_id
    else:
        keep_id, drop_id = choose_survivor(store, first_id, second_id)
    keep = _find_member(store, keep_id)
    drop = _find_member(store, drop_id)
    if not keep or not drop:
        raise MergeError("Player not found.")

    shared = shared_records(store, keep_id, drop_id)
    if shared:
        raise MergeError(
            "Both players appear in the same record (" + ", ".join(shared[:3]) + "). "
            "Merging them would count one player twice, so fix that record first."
        )

    references = _rewrite_refs(store, drop_id, keep_id)

    aliases = list(keep.get("aliases") or [])
    known = {normalize_name(str(name)) for name in [keep.get("name"), keep.get("full_name"), *aliases] if str(name or "").strip()}
    added_aliases: list[str] = []
    for candidate in [drop.get("name"), drop.get("full_name"), *(drop.get("aliases") or [])]:
        text = str(candidate or "").strip()
        if text and normalize_name(text) not in known:
            aliases.append(text)
            known.add(normalize_name(text))
            added_aliases.append(text)
    keep["aliases"] = aliases

    links = [link for link in keep.get("club_memberships") or [] if isinstance(link, dict)]
    seen = {_club_key(link) for link in links}
    added_links = 0
    for link in drop.get("club_memberships") or []:
        if isinstance(link, dict) and _club_key(link) not in seen:
            links.append(dict(link))
            seen.add(_club_key(link))
            added_links += 1
    keep["club_memberships"] = links

    store["members"] = [item for item in store.get("members", []) if item is not drop]
    return {
        "kept_member_id": keep_id,
        "kept_name": str(keep.get("name") or ""),
        "removed_member_id": drop_id,
        "removed_name": str(drop.get("name") or ""),
        "references_rewritten": references,
        "aliases_added": added_aliases,
        "club_links_added": added_links,
    }
