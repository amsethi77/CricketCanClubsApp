"""AIDuplicateEngine: how likely two player records are the same person.

The score combines three kinds of evidence:
- names: full name and main name and every alias, including "Bim" vs "Bim B" (same first name plus an initial);
- clubs: the primary club and the secondary clubs of each record;
- match history: if both records appear as different batters in the same match, they are two people (veto).

Each part is explained in the returned reasons, so a club admin can see why a pair was suggested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable

try:
    from cricket_store import normalize_name
except ModuleNotFoundError:
    from app.cricket_store import normalize_name

NAME_WEIGHT = 0.7
CLUB_WEIGHT = 0.3
INITIAL_MATCH_SCORE = 0.9  # "Bim" vs "Bim B": same first name plus one initial
SAME_PRIMARY_CLUB = 1.0
SHARED_CLUB = 0.6
CLUB_NOT_RECORDED = 0.3  # neutral: missing club data is not evidence against a match
DIFFERENT_CLUBS = 0.0


@dataclass
class PairScore:
    score: float
    name_score: float
    club_score: float
    reasons: list[str] = field(default_factory=list)
    vetoed: bool = False


def identity_names(member: dict[str, Any]) -> list[str]:
    """Every name a player is known by: main name, full name and aliases, normalized and without duplicates."""
    names: list[str] = []
    for value in [member.get("name"), member.get("full_name"), *(member.get("aliases") or [])]:
        norm = normalize_name(str(value or ""))
        if norm and norm not in names:
            names.append(norm)
    return names


def club_keys(member: dict[str, Any]) -> tuple[set[str], str]:
    """All club ids a record is linked to, and its primary club id (empty when unknown)."""
    primary = str(member.get("primary_club_id") or "")
    keys: set[str] = {primary} if primary else set()
    for team in member.get("team_memberships") or []:
        if isinstance(team, dict) and team.get("club_id"):
            keys.add(str(team["club_id"]))
            if team.get("is_primary") and not primary:
                primary = str(team["club_id"])
    for link in member.get("club_memberships") or []:
        if isinstance(link, dict) and link.get("club_id"):
            keys.add(str(link["club_id"]))
    return keys, primary


def _name_pair(first: str, second: str) -> tuple[float, str]:
    if first == second:
        return 1.0, "same name"
    ratio = SequenceMatcher(None, first, second).ratio()
    short, long_ = sorted((first, second), key=len)
    extra = long_[len(short):]
    if long_.startswith(short) and extra.startswith(" ") and len(extra.strip()) <= 2:
        return max(ratio, INITIAL_MATCH_SCORE), "same first name with an initial"
    return ratio, "similar name"


def _name_evidence(first: dict[str, Any], second: dict[str, Any]) -> tuple[float, str]:
    best, reason = 0.0, "no similar name"
    for a in identity_names(first):
        for b in identity_names(second):
            score, why = _name_pair(a, b)
            if score > best:
                best, reason = score, why
    return best, reason


def _club_evidence(first: dict[str, Any], second: dict[str, Any]) -> tuple[float, str]:
    keys_a, primary_a = club_keys(first)
    keys_b, primary_b = club_keys(second)
    if not keys_a or not keys_b:
        return CLUB_NOT_RECORDED, "club not recorded on one record"
    if primary_a and primary_a == primary_b:
        return SAME_PRIMARY_CLUB, "same primary club"
    if keys_a & keys_b:
        return SHARED_CLUB, "shares a club (primary or secondary)"
    return DIFFERENT_CLUBS, "no club in common"


class AIDuplicateEngine:
    """Scores pairs of player records. `archives` is one set of normalized batter names per past match."""

    def __init__(self, archives: Iterable[set[str]] = ()) -> None:
        self._archives = [set(names) for names in archives]
        self._by_name: dict[str, set[int]] = {}
        for index, names in enumerate(self._archives):
            for name in names:
                self._by_name.setdefault(name, set()).add(index)

    def _in_same_match_as_two_players(self, names_a: set[str], names_b: set[str]) -> bool:
        matches_a = set().union(*(self._by_name.get(name, set()) for name in names_a))
        matches_b = set().union(*(self._by_name.get(name, set()) for name in names_b))
        for index in matches_a & matches_b:
            present = self._archives[index]
            hits_a, hits_b = present & names_a, present & names_b
            if any(x != y for x in hits_a for y in hits_b):
                return True
        return False

    def score(self, first: dict[str, Any], second: dict[str, Any], check_matches: bool = True) -> PairScore:
        name_score, name_reason = _name_evidence(first, second)
        club_score, club_reason = _club_evidence(first, second)
        if check_matches and self._in_same_match_as_two_players(set(identity_names(first)), set(identity_names(second))):
            return PairScore(0.0, name_score, club_score, ["both names played as different batters in the same match"], vetoed=True)
        score = NAME_WEIGHT * name_score + CLUB_WEIGHT * club_score
        return PairScore(round(score, 4), round(name_score, 4), round(club_score, 4), [name_reason, club_reason])
