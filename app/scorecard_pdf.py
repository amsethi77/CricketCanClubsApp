"""Generate downloadable PDF scorecards from the public match payload."""

from __future__ import annotations

import io
import re
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GREEN = colors.HexColor("#087f5b")
INK = colors.HexColor("#17212b")
MUTED = colors.HexColor("#64748b")
PALE = colors.HexColor("#edf7f2")
RULE = colors.HexColor("#d8e2dc")


def _pdf_text(value: Any) -> str:
    text = str("" if value is None else value).encode("cp1252", "replace").decode("cp1252")
    return escape(text).replace("\n", "<br/>")


# ---------------------------------------------------------------------------------------------------------------
# Nov 23 2026 (Dhruvika, with the Heartlake vs Afghan Eagles PDF: "This should be changed. Ensure that they are the
# same going forward"): the PDF of a live-scored match showed "Extras: 0 b, 0 lb, 0 w, 0 nb (total 19)", "st Nihal"
# (keeper missing) and no (c) / (vc) / (wk), while the match page showed "Extras (b 0, lb 0, w 17, nb 2) 19",
# "st Harsh b Nihal" and the tags. The match page works its figures out from the balls (inningsFacts / howOut /
# currentPair / tagHtml / renderScorecard in static/public_match.js). The functions below are the same rules,
# line for line, so the PDF shows exactly what the page shows. CHANGE BOTH TOGETHER (README "Scorecard PDF = match
# page"; tests/test_scorecard_pdf_matches_page.py checks it).
# ---------------------------------------------------------------------------------------------------------------
ROLE_TAGS = (("captain", "C"), ("vice_captain", "VC"), ("keeper", "WK"))


def _num(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_legal(ball: dict[str, Any]) -> bool:
    return str(ball.get("extras_type") or "none") not in {"wide", "no_ball", "retired_out"}


def overs_text(legal: int) -> str:
    return f"{legal // 6}.{legal % 6}"


def overs_short(legal: int) -> str:
    return overs_text(legal) if legal % 6 else str(legal // 6)


def run_rate(runs: int, legal: int) -> str:
    return f"{runs / (legal / 6):.2f}" if legal else "0.00"


def same_name(a: Any, b: Any) -> bool:
    return str(a or "").lower() == str(b or "").lower()


def how_out(ball: dict[str, Any]) -> str:
    """public_match.js howOut()"""
    bowler = str(ball.get("bowler") or "")
    fielder = str(ball.get("fielder") or "")
    kind = str(ball.get("wicket_type") or "")
    if kind == "bowled":
        return f"b {bowler}"
    if kind == "caught":
        return f"c & b {bowler}" if fielder and fielder == bowler else f"c {fielder or '?'} b {bowler}"
    if kind == "lbw":
        return f"lbw b {bowler}"
    if kind == "run_out":
        return f"run out ({fielder})" if fielder else "run out"
    if kind == "stumped":
        return f"st {fielder or '?'} b {bowler}"
    if kind == "hit_wicket":
        return f"hit wicket b {bowler}"
    if kind == "retired_hurt":
        return "retired hurt"
    return (kind or "out").replace("_", " ", 1)


def innings_facts(innings: dict[str, Any]) -> dict[str, Any]:
    """public_match.js inningsFacts(): extras, how out, fall of wickets, worked out from the balls."""
    balls = [ball for ball in innings.get("balls") or [] if isinstance(ball, dict)]
    summary = innings.get("summary") or {}
    extras = {"wd": 0, "nb": 0, "b": 0, "lb": 0}
    dismissal: dict[str, str] = {}
    retired_out_players: set[str] = set()
    fall_of_wickets: list[str] = []
    runs = wickets = legal = 0
    for ball in balls:
        extras_runs = _num(ball.get("extras_runs"))
        runs += _num(ball.get("runs_bat")) + extras_runs
        kind = str(ball.get("extras_type") or "none")
        if kind == "wide":
            extras["wd"] += extras_runs
        if kind == "no_ball":
            extras["nb"] += extras_runs
        if kind == "bye":
            extras["b"] += extras_runs
        if kind == "leg_bye":
            extras["lb"] += extras_runs
        if _is_legal(ball):
            legal += 1
        retired_out = str(ball.get("wicket_type") or "").lower() == "retired_out"
        for name in (ball.get("striker"), ball.get("non_striker"), ball.get("new_batter")):
            if name and name in retired_out_players:
                dismissal.pop(name, None)
                retired_out_players.discard(name)
        if ball.get("wicket") and not retired_out:
            wickets += 1
        player = ball.get("wicket_player")
        if (ball.get("wicket") or retired_out) and player:
            dismissal[player] = "retired out" if retired_out else how_out(ball)
            if retired_out:
                retired_out_players.add(player)
            else:
                fall_of_wickets.append(f"{runs}-{len(fall_of_wickets) + 1} ({player}, {overs_text(legal)})")
    return {
        "balls": balls,
        "legal": legal,
        "runs": _num(summary["runs"]) if summary.get("runs") is not None else runs,
        "wickets": _num(summary["wickets"]) if summary.get("wickets") is not None else wickets,
        "extras": extras,
        "extras_total": sum(extras.values()),
        "dismissal": dismissal,
        "fall_of_wickets": fall_of_wickets,
        "last": balls[-1] if balls else None,
        "batting": summary.get("batting") if isinstance(summary.get("batting"), list) else [],
        "bowling": summary.get("bowling") if isinstance(summary.get("bowling"), list) else [],
        "done": str(innings.get("status") or "").lower() == "completed",
        "started": bool(balls),
    }


def current_pair(facts: dict[str, Any]) -> tuple[str, str]:
    """public_match.js currentPair(): the two batters in now (striker first)."""
    ball = facts.get("last")
    if not ball:
        return "", ""
    striker, non_striker = str(ball.get("striker") or ""), str(ball.get("non_striker") or "")
    kind = str(ball.get("extras_type") or "none")
    ran = _num(ball.get("runs_bat")) + (_num(ball.get("extras_runs")) if kind in {"bye", "leg_bye"} else 0)
    if kind == "wide":
        ran += max(0, _num(ball.get("extras_runs") or 1) - 1)
    if ran % 2 == 1:
        striker, non_striker = non_striker, striker
    if _is_legal(ball) and facts["legal"] > 0 and facts["legal"] % 6 == 0:
        striker, non_striker = non_striker, striker
    if (ball.get("wicket") or str(ball.get("wicket_type") or "").lower() == "retired_out") and ball.get("wicket_player"):
        if striker == ball.get("wicket_player"):
            striker = str(ball.get("new_batter") or "")
        if non_striker == ball.get("wicket_player"):
            non_striker = str(ball.get("new_batter") or "")
    return striker, non_striker


def side_of_team(match: dict[str, Any], team: Any) -> str:
    return "club" if same_name(team, match.get("club_name")) else "opponent"


def role_tags(match: dict[str, Any], side: str, name: str) -> str:
    """public_match.js tagHtml(): " (c)", " (vc)", " (wk)", " (c & wk)"."""
    roles = (((match.get("lineups") or {}).get("roles") or {}).get(side) or {})
    tags = [tag for role, tag in ROLE_TAGS if roles.get(role) and roles.get(role) == name]
    return f" ({' & '.join(tag.lower() for tag in tags)})" if tags else ""


def match_code(match: dict[str, Any]) -> str:
    code = match.get("published_match_code") or "M-" + re.sub(r"[^0-9a-zA-Z]", "", str(match.get("id") or ""))[:8].upper()
    return "" if code == "M-" else code


def innings_view(match: dict[str, Any], innings: dict[str, Any]) -> dict[str, Any]:
    """Everything public_match.js renderScorecard() shows for one innings, as text."""
    facts = innings_facts(innings)
    striker, non_striker = current_pair(facts)
    side = side_of_team(match, innings.get("batting_team"))
    bowl_side = side_of_team(match, innings.get("bowling_team"))
    batted = [row for row in facts["batting"] if row.get("status") != "not_batted" or row.get("balls") or row.get("runs")]
    batting = []
    for row in batted:
        name = str(row.get("player_name") or "")
        out = facts["dismissal"].get(name)
        in_now = name in {striker, non_striker}
        how = out or ("not out" if facts["done"] or not in_now else "batting *" if name == striker else "batting")
        balls_faced = _num(row.get("balls"))
        batting.append({
            "name": name + role_tags(match, side, name),
            "how": how,
            "runs": _num(row.get("runs")),
            "balls": balls_faced,
            "fours": _num(row.get("fours")),
            "sixes": _num(row.get("sixes")),
            "sr": f"{_num(row.get('runs')) / balls_faced * 100:.2f}" if balls_faced else "0.00",
        })
    lineups = match.get("lineups") or {}
    lineup = (lineups.get("club") if side == "club" else lineups.get("opponent")) or []
    batted_names = {str(row.get("player_name") or "") for row in batted}
    yet_to_bat = [name + role_tags(match, side, name) for name in lineup if name not in batted_names]
    bowling = []
    for row in facts["bowling"]:
        if not (_num(row.get("legal_balls")) or _num(row.get("runs_conceded"))):
            continue
        name = str(row.get("player_name") or "")
        bowling.append({
            "name": name + role_tags(match, bowl_side, name),
            "overs": str(row.get("overs") or "0.0"),
            "maidens": _num(row.get("maidens")),
            "runs": _num(row.get("runs_conceded")),
            "wickets": _num(row.get("wickets")),
            "economy": f"{float(row.get('economy') or 0):.2f}",
        })
    extras = facts["extras"]
    return {
        "team": str(innings.get("batting_team") or f"Innings {innings.get('inning_number') or ''}"),
        "score": f"{facts['runs']}/{facts['wickets']}",
        "overs": overs_short(facts["legal"]),
        "started": facts["started"],
        "batting": batting,
        "extras_label": f"Extras (b {extras['b']}, lb {extras['lb']}, w {extras['wd']}, nb {extras['nb']})",
        "extras_total": facts["extras_total"],
        "total_label": f"Total ({facts['wickets']} wkts, {overs_short(facts['legal'])} Ov, RR {run_rate(facts['runs'], facts['legal'])})",
        "total": facts["runs"],
        "yet_to_bat": yet_to_bat,
        "fall_of_wickets": facts["fall_of_wickets"],
        "bowling": bowling,
    }


def match_state(match: dict[str, Any]) -> dict[str, Any]:
    """public_match.js matchState()"""
    innings = sorted(
        [item for item in (match.get("scorebook") or {}).get("innings", []) or [] if isinstance(item, dict)],
        key=lambda item: int(item.get("inning_number") or 1),
    )
    played = [item for item in innings if item.get("balls")]
    live = next((item for item in reversed(played) if str(item.get("status") or "").lower() == "live"), None)
    current = live or (played[-1] if played else None)
    result = str(match.get("result") or "")
    done = str(match.get("status") or "").lower() == "completed" or bool(result and result.strip().lower() != "tbd")
    first = next((item for item in innings if int(item.get("inning_number") or 0) == 1), None)
    first_facts = innings_facts(first) if first and first.get("balls") else None
    facts = innings_facts(current) if current else None
    is_chase = bool(current and int(current.get("inning_number") or 0) == 2 and first_facts)
    target = first_facts["runs"] + 1 if is_chase else None
    is_live = not done and bool(live) and not (facts and facts["done"])
    in_break = not done and bool(current) and not is_live
    first_bat = (first or {}).get("batting_team") or ""
    teams = (
        [first_bat, match.get("opponent") if same_name(first_bat, match.get("club_name")) else match.get("club_name")]
        if first_bat
        else [match.get("club_name") or "Team 1", match.get("opponent") or "Team 2"]
    )
    return {"played": played, "current": current, "done": done, "facts": facts, "target": target,
            "is_live": is_live, "in_break": in_break, "teams": teams}


def status_line(match: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    """public_match.js statusLine()"""
    state = state or match_state(match)
    current, facts, target = state["current"], state["facts"], state["target"]
    if state["done"]:
        return str(match.get("result") or "Match finished")
    if not current:
        when = ", ".join(str(item) for item in (match.get("scheduled_time"), match.get("date_label")) if item)
        return f"Match starts {when}. This page updates by itself." if when else "Scoring hasn't started yet. This page updates by itself."
    other = next((team for team in state["teams"] if not same_name(team, current.get("batting_team"))), "") or ""
    if state["in_break"] and int(current.get("inning_number") or 0) == 1:
        return f"Innings break · {other} need {facts['runs'] + 1} runs to win"
    if target:
        need = max(0, target - facts["runs"])
        left = _num(current.get("overs_limit") or 20) * 6 - facts["legal"]
        if need <= 0:
            return f"{current.get('batting_team')} have reached the target"
        return f"{current.get('batting_team')} need {need} run{'' if need == 1 else 's'} in {left} ball{'' if left == 1 else 's'}"
    if state["is_live"]:
        return f"{current.get('batting_team')} batting · {other} yet to bat"
    return "Waiting for the next innings"


def match_info_line(match: dict[str, Any]) -> str:
    """public_match.js renderHeader() info line."""
    venue = str(match.get("venue") or "")
    parts = [
        f"{match.get('club_name') or 'Team 1'} vs {match.get('opponent') or 'Team 2'}",
        match.get("match_type"),
        f"{match.get('overs')} overs" if match.get("overs") else "",
        venue if venue and venue.lower() != "venue tbd" else "",
        " ".join(str(item) for item in (match.get("date_label") or match.get("date"), match.get("scheduled_time")) if item),
    ]
    return ", ".join(str(part) for part in parts if part)


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_pdf_text(value), style)


def build_scorecard_pdf(match: dict[str, Any]) -> bytes:
    """Render a full innings-by-innings batting and bowling scorecard as a PDF."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=17 * mm,
        bottomMargin=16 * mm,
        title=f"{match.get('club_name') or 'Team'} vs {match.get('opponent') or 'Opponent'} scorecard",
        author="CricketClubApp",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ScorecardTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=5,
        ),
        "meta": ParagraphStyle(
            "ScorecardMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "result": ParagraphStyle(
            "ScorecardResult",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=GREEN,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "ScorecardSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=5,
        ),
        "subhead": ParagraphStyle(
            "ScorecardSubhead",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=GREEN,
            spaceBefore=7,
            spaceAfter=3,
        ),
        "cell": ParagraphStyle(
            "ScorecardCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "cell_right": ParagraphStyle(
            "ScorecardCellRight",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
        "note": ParagraphStyle(
            "ScorecardNote",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
            spaceBefore=4,
        ),
    }

    def cell(text: Any, right: bool = False) -> Paragraph:
        return _paragraph(text, styles["cell_right" if right else "cell"])

    def table(rows: list[list[Any]], widths: list[float]) -> Table:
        item = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PALE),
                    ("TEXTCOLOR", (0, 0), (-1, 0), GREEN),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, GREEN),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return item

    story: list[Any] = []
    title = f"{match.get('club_name') or 'Team 1'} vs {match.get('opponent') or 'Team 2'}"
    story.append(Paragraph(_pdf_text(title), styles["title"]))
    state = match_state(match)
    played = state["played"]
    done = state["done"]
    # the same status line as the match page (result / "X need N runs in M balls" / "Match starts ...")
    story.append(Paragraph(_pdf_text(status_line(match, state)), styles["result"]))
    # same info line, Match ID and innings IDs as the match page header (public_match.js renderHeader / matchIds)
    story.append(Paragraph(_pdf_text(match_info_line(match)), styles["meta"]))
    code = match_code(match)
    if code:
        test = bool(re.search(r"\btest\b|multi-day|two-day|2-day", str(match.get("match_type") or ""), re.I))
        chips = []
        teams = state["teams"]
        for number in range(1, max(4 if test else 2, len(played)) + 1):
            inn = next((item for item in played if int(item.get("inning_number") or 0) == number), None)
            team = inn.get("batting_team") if inn else teams[(number - 1) % 2]
            facts = innings_facts(inn) if inn else None
            text = f"{facts['runs']}/{facts['wickets']}" if facts else ("missing" if done else "to come")
            chips.append(f"{code}-I{number} {team or f'Innings {number}'} · {text}")
        story.append(Paragraph(_pdf_text(f"Match ID {code}   " + "   ".join(chips)), styles["meta"]))
    story.append(Spacer(1, 4))

    available_width = A4[0] - 30 * mm
    batting_widths = [
        available_width * 0.27,
        available_width * 0.32,
        available_width * 0.08,
        available_width * 0.08,
        available_width * 0.07,
        available_width * 0.07,
        available_width * 0.11,
    ]
    bowling_widths = [
        available_width * 0.44,
        available_width * 0.10,
        available_width * 0.10,
        available_width * 0.12,
        available_width * 0.09,
        available_width * 0.15,
    ]

    rendered_innings = 0
    for innings in played:
        view = innings_view(match, innings)
        rendered_innings += 1
        story.append(Paragraph(_pdf_text(f"{view['team']} Innings - {view['score']} ({view['overs']} Ov)"), styles["section"]))
        batting_rows: list[list[Any]] = [
            [cell("Batter"), cell(""), cell("R", True), cell("B", True), cell("4s", True), cell("6s", True), cell("SR", True)]
        ]
        for row in view["batting"]:
            batting_rows.append(
                [
                    cell(row["name"]),
                    cell(row["how"]),
                    cell(row["runs"], True),
                    cell(row["balls"], True),
                    cell(row["fours"], True),
                    cell(row["sixes"], True),
                    cell(row["sr"], True),
                ]
            )
        batting_rows.append([cell(view["extras_label"]), cell(""), cell(view["extras_total"], True), cell(""), cell(""), cell(""), cell("")])
        batting_rows.append(
            [Paragraph(f"<b>{_pdf_text(view['total_label'])}</b>", styles["cell"]), cell(""), Paragraph(f"<b>{view['total']}</b>", styles["cell_right"]), cell(""), cell(""), cell(""), cell("")]
        )
        story.append(table(batting_rows, batting_widths))
        if view["yet_to_bat"]:
            story.append(Paragraph(_pdf_text("Yet to bat: " + ", ".join(view["yet_to_bat"])), styles["note"]))
        if view["fall_of_wickets"]:
            story.append(Paragraph(_pdf_text("Fall of wickets: " + ", ".join(view["fall_of_wickets"])), styles["note"]))

        story.append(Paragraph("Bowling", styles["subhead"]))
        bowling_rows: list[list[Any]] = [
            [cell("Bowler"), cell("O", True), cell("M", True), cell("R", True), cell("W", True), cell("ECON", True)]
        ]
        for row in view["bowling"]:
            bowling_rows.append(
                [cell(row["name"]), cell(row["overs"], True), cell(row["maidens"], True), cell(row["runs"], True), cell(row["wickets"], True), cell(row["economy"], True)]
            )
        if len(bowling_rows) == 1:
            bowling_rows.append([cell("No overs bowled yet."), *[cell("", True) for _ in range(5)]])
        story.append(table(bowling_rows, bowling_widths))
        story.append(Spacer(1, 8))

    if not rendered_innings:
        story.append(Paragraph("No innings have been scored yet.", styles["note"]))

    def page_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(doc.leftMargin, 11 * mm, A4[0] - doc.rightMargin, 11 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 7 * mm, "CricketClubApp - Complete Scorecard")
        canvas.drawRightString(A4[0] - doc.rightMargin, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return buffer.getvalue()


def scorecard_pdf_filename(match: dict[str, Any]) -> str:
    stem = f"{match.get('club_name') or 'match'}-vs-{match.get('opponent') or 'opponent'}"
    safe = re.sub(r"[^A-Za-z0-9-]+", "-", stem).strip("-").lower()
    return f"{safe or 'match'}-scorecard.pdf"


# ---------------------------------------------------------------------------------------------------------------
# Nov 17 2026 (Amit: "once the match is uploaded, then we should have a PDF also to download or to review the
# scorecard for both uploaded as well as for online games"): a PDF of the digital scorecard exactly as the scorecard
# page shows it (uploaded cards and live-scored matches alike) - innings bar, batters with how out and (c) (vc) (wk),
# extras / total / did not bat, bowlers O M R W NB WD ECO, fall of wickets, partnerships and the match info.
# ---------------------------------------------------------------------------------------------------------------
BRAND = colors.HexColor("#e11d48")
ROSE = colors.HexColor("#fff1f2")
ROSE_INK = colors.HexColor("#9f1239")


def _card_tags(row: dict[str, Any], extra: list[str] | None = None) -> str:
    tags = [tag for tag in (extra if extra is not None else row.get("tags") or []) if tag in {"C", "VC", "WK"}]
    return f" ({' & '.join(tag.lower() for tag in tags)})" if tags else ""


def _card_score(runs: Any, wickets: Any) -> str:
    if runs is None or runs == "":
        return "-"
    return f"{runs}" + (f"-{wickets}" if wickets is not None and wickets != "" else "")


def build_card_pdf(card: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    title = str(card.get("title") or "Scorecard")
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title=f"{title} scorecard", author="CricketCanClubs")
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("CardTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=INK, alignment=TA_CENTER, spaceAfter=3)
    meta = ParagraphStyle("CardMeta", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=MUTED, alignment=TA_CENTER)
    result = ParagraphStyle("CardResult", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=BRAND, alignment=TA_CENTER, spaceBefore=3, spaceAfter=8)
    cell = ParagraphStyle("CardCell", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK)
    small = ParagraphStyle("CardSmall", parent=cell, fontSize=7.5, leading=10, textColor=MUTED)
    bold = ParagraphStyle("CardBold", parent=cell, fontName="Helvetica-Bold")
    bar = ParagraphStyle("CardBar", parent=cell, fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.white)
    bar_right = ParagraphStyle("CardBarRight", parent=bar, alignment=TA_RIGHT)

    def table(rows: list[list[Any]], widths: list[float], header: bool = True, zebra: bool = False) -> Table:
        t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), ROSE), ("TEXTCOLOR", (0, 0), (-1, 0), ROSE_INK), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        t.setStyle(TableStyle(style))
        return t

    story: list[Any] = [_paragraph(title, h1)]
    bits = [card.get("match_type"), f"{card.get('overs_limit')} overs" if card.get("overs_limit") else "", card.get("venue"), card.get("date_label")]
    story.append(_paragraph(" · ".join(str(bit) for bit in bits if bit), meta))
    if card.get("result"):
        story.append(_paragraph(card.get("result"), result))
    width = A4[0] - 28 * mm
    for innings in card.get("innings") or []:
        if not isinstance(innings, dict) or not (innings.get("has_data") or innings.get("batting") or innings.get("bowling")):
            continue
        head = Table([[Paragraph(_pdf_text(innings.get("team") or "Innings"), bar), Paragraph(_pdf_text(f"{_card_score(innings.get('runs'), innings.get('wickets'))}" + (f" ({innings.get('overs')} Ov)" if innings.get("overs") else "")), bar_right)]], colWidths=[width * 0.6, width * 0.4])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [Spacer(1, 8), head]
        rows: list[list[Any]] = [["Batter", "", "R", "B", "4s", "6s", "SR"]]
        for row in innings.get("batting") or []:
            how = str(row.get("dismissal") or ("not out" if row.get("not_out") else ""))
            rows.append([Paragraph(_pdf_text(f"{row.get('name')}{_card_tags(row)}"), cell), Paragraph(_pdf_text(how), small), Paragraph(f"<b>{_pdf_text(row.get('runs') if row.get('runs') is not None else '-')}</b>", cell)] + [_pdf_text(row.get(key) if row.get(key) not in (None, "") else "-") for key in ("balls", "fours", "sixes", "strike_rate")])
        if len(rows) > 1:
            story.append(table(rows, [width * 0.30, width * 0.34, width * 0.07, width * 0.07, width * 0.06, width * 0.06, width * 0.10]))
        overs_text = f"{innings.get('overs')} Overs" if innings.get("overs") else ""
        summary = [
            [Paragraph("<b>Extras</b>", cell), Paragraph(_pdf_text(f"{innings.get('extras') if innings.get('extras') is not None else '-'}" + (f" ({innings.get('extras_detail')})" if innings.get("extras_detail") else "")), cell)],
            [Paragraph("<b>Total</b>", cell), Paragraph(_pdf_text(_card_score(innings.get("runs"), innings.get("wickets")) + (f" ({overs_text})" if overs_text else "")), bold)],
        ]
        if innings.get("did_not_bat"):
            tags = innings.get("did_not_bat_tags") or {}
            summary.append([Paragraph("<b>Did not Bat</b>", cell), Paragraph(_pdf_text(", ".join(f"{name}{_card_tags({}, tags.get(name) or [])}" for name in innings["did_not_bat"])), cell)])
        story.append(table(summary, [width * 0.30, width * 0.70], header=False))
        bowling = [["Bowler", "O", "M", "R", "W", "NB", "WD", "ECO"]]
        for row in innings.get("bowling") or []:
            bowling.append([Paragraph(_pdf_text(f"{row.get('name')}{_card_tags(row)}"), cell)] + [("~" if key == "overs" and row.get("overs_approximate") or key == "runs" and row.get("runs_approximate") else "") + _pdf_text(row.get(key) if row.get(key) not in (None, "") else "-") for key in ("overs", "maidens", "runs", "wickets", "no_balls", "wides", "economy")])
        if len(bowling) > 1:
            story += [Spacer(1, 5), table(bowling, [width * 0.37] + [width * 0.09] * 7)]
        fow = innings.get("fall_of_wickets") or []
        if fow:
            rows = [["Fall of Wickets", "Score", "Over"]] + [[_pdf_text(item.get("batter") or ""), f"{item.get('runs')}-{item.get('wicket')}", _pdf_text(item.get("over") or "")] for item in fow]
            story += [Spacer(1, 5), table(rows, [width * 0.6, width * 0.2, width * 0.2])]
        partners = innings.get("partnerships") or []
        if partners:
            rows = [["Partnerships", "", ""]] + [[_pdf_text(f"{p.get('left')} {p.get('left_runs')}({p.get('left_balls')})"), f"{p.get('runs')}({p.get('balls')})", _pdf_text(f"{p.get('right_runs')}({p.get('right_balls')}) {p.get('right')}" if p.get("right") else "")] for p in partners]
            story += [Spacer(1, 5), table(rows, [width * 0.4, width * 0.2, width * 0.4])]
    info = [["Info", ""]]
    captains = [f"{c.get('name')} ({c.get('team')})" for c in card.get("captains") or [] if isinstance(c, dict) and c.get("name")]
    for label, value in (
        ("Match", card.get("title")),
        ("Series", card.get("season")),
        ("Date", card.get("date_label")),
        ("Toss", card.get("toss")),
        ("Venue", card.get("venue")),
        ("Result", card.get("result")),
        ("Captains", " · ".join(captains)),
        ("Man of the match", card.get("man_of_match") or (f"{card.get('man_of_match_auto')} (auto pick)" if card.get("man_of_match_auto") else "")),
        ("Match ID", card.get("match_code")),
    ):
        if value:
            info.append([Paragraph(f"<b>{_pdf_text(label)}</b>", cell), Paragraph(_pdf_text(value), cell)])
    if len(info) > 1:
        story += [Spacer(1, 10), table(info, [width * 0.3, width * 0.7])]
    story += [Spacer(1, 8), _paragraph("CricketCanClubs digital scorecard. (c) captain, (vc) vice-captain, (wk) wicket keeper, ~ approximate figure.", small)]
    document.build(story)
    return buffer.getvalue()


def card_pdf_filename(card: dict[str, Any]) -> str:
    stem = f"{card.get('title') or 'match'}-{card.get('date') or ''}"
    safe = re.sub(r"[^A-Za-z0-9-]+", "-", stem).strip("-").lower()
    return f"{safe or 'match'}-scorecard.pdf"
