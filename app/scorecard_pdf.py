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


def _dismissal_text(ball: dict[str, Any]) -> str:
    kind = str(ball.get("wicket_type") or "out").strip().lower()
    bowler = str(ball.get("bowler") or "").strip()
    fielder = str(ball.get("fielder") or "").strip()
    if kind == "retired_out":
        return "Retired out"
    if kind == "retired_hurt":
        return "Retired hurt"
    if kind == "run_out":
        return f"run out ({fielder})" if fielder else "run out"
    if kind == "caught":
        if fielder and fielder == bowler:
            return f"c & b {bowler}"
        return f"c {fielder} b {bowler}" if fielder and bowler else "caught"
    labels = {
        "bowled": "b",
        "lbw": "lbw b",
        "stumped": "st",
        "hit_wicket": "hit wicket b",
    }
    prefix = labels.get(kind, kind.replace("_", " "))
    return f"{prefix} {bowler}".strip() if bowler and kind in labels else prefix


def _dismissals(innings: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    retired: set[str] = set()
    for ball in innings.get("balls", []) or []:
        for name in (ball.get("striker"), ball.get("non_striker"), ball.get("new_batter")):
            key = str(name or "").strip().casefold()
            if key in retired:
                result.pop(key, None)
                retired.discard(key)
        name = str(ball.get("wicket_player") or "").strip()
        if not name or not (ball.get("wicket") or str(ball.get("wicket_type") or "").lower() == "retired_out"):
            continue
        key = name.casefold()
        result[key] = _dismissal_text(ball)
        if str(ball.get("wicket_type") or "").lower() == "retired_out":
            retired.add(key)
        else:
            retired.discard(key)
    return result


def _fall_of_wickets(innings: dict[str, Any]) -> list[str]:
    runs = 0
    legal = 0
    wickets: list[str] = []
    for ball in innings.get("balls", []) or []:
        runs += int(ball.get("runs_bat") or 0) + int(ball.get("extras_runs") or 0)
        extras = str(ball.get("extras_type") or "none").lower()
        if extras not in {"wide", "no_ball", "retired_out"}:
            legal += 1
        if ball.get("wicket") and str(ball.get("wicket_type") or "").lower() != "retired_out":
            wickets.append(f"{runs}-{len(wickets) + 1} ({ball.get('wicket_player') or 'Batter'}, {legal // 6}.{legal % 6})")
    return wickets


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
    details = [
        match.get("date_label") or match.get("date"),
        match.get("venue") if not str(match.get("venue") or "").lower().endswith("tbd") else "",
        match.get("match_type"),
        f"{match.get('overs')} overs" if match.get("overs") else "",
    ]
    story.append(Paragraph(_pdf_text(" | ".join(str(item) for item in details if item)), styles["meta"]))
    if match.get("result") and str(match.get("result")).strip().lower() not in {"", "tbd"}:
        story.append(Paragraph(_pdf_text(match["result"]), styles["result"]))
    else:
        story.append(Spacer(1, 5))

    innings_list = sorted(
        match.get("scorebook", {}).get("innings", []) or [],
        key=lambda item: int(item.get("inning_number") or 1),
    )
    available_width = A4[0] - 30 * mm
    batting_widths = [
        available_width * 0.23,
        available_width * 0.36,
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
    for innings in innings_list:
        summary = innings.get("summary") or {}
        batters = summary.get("batting") or []
        bowlers = summary.get("bowling") or []
        balls = innings.get("balls") or []
        if not balls and not any(row.get("status") != "not_batted" for row in batters):
            continue
        rendered_innings += 1
        runs = int(summary.get("runs") or 0)
        wickets = int(summary.get("wickets") or 0)
        legal = int(summary.get("legal_balls") or 0)
        team = innings.get("batting_team") or f"Innings {innings.get('inning_number', rendered_innings)}"
        story.append(
            Paragraph(
                _pdf_text(f"{team} innings - {runs}/{wickets} ({summary.get('overs') or f'{legal // 6}.{legal % 6}'} overs)"),
                styles["section"],
            )
        )
        dismissals = _dismissals(innings)
        batting_rows: list[list[Any]] = [
            [cell("Batter"), cell("Dismissal"), cell("R", True), cell("B", True), cell("4s", True), cell("6s", True), cell("SR", True)]
        ]
        batted_names: set[str] = set()
        for batter in batters:
            name = str(batter.get("player_name") or "").strip()
            if not name:
                continue
            status = str(batter.get("status") or "").lower()
            if status == "not_batted" and not int(batter.get("runs") or 0) and not int(batter.get("balls") or 0):
                continue
            key = name.casefold()
            batted_names.add(key)
            dismissal = dismissals.get(key, "")
            if not dismissal:
                dismissal = "Retired hurt" if status == "retired" else "not out"
            strike_rate = 100 * int(batter.get("runs") or 0) / int(batter.get("balls") or 0) if int(batter.get("balls") or 0) else 0
            batting_rows.append(
                [
                    cell(name),
                    cell(dismissal),
                    cell(int(batter.get("runs") or 0), True),
                    cell(int(batter.get("balls") or 0), True),
                    cell(int(batter.get("fours") or 0), True),
                    cell(int(batter.get("sixes") or 0), True),
                    cell(f"{strike_rate:.2f}", True),
                ]
            )
        story.append(table(batting_rows, batting_widths))

        extras_line = (
            f"Extras: {int(summary.get('byes') or 0)} b, {int(summary.get('legByes') or 0)} lb, "
            f"{int(summary.get('wides') or 0)} w, {int(summary.get('noBalls') or 0)} nb "
            f"(total {int(summary.get('extras') or 0)})"
        )
        story.append(Paragraph(_pdf_text(extras_line), styles["note"]))
        story.append(
            Paragraph(
                _pdf_text(
                    f"Total: {runs}/{wickets} in {summary.get('overs') or f'{legal // 6}.{legal % 6}'} overs "
                    f"(run rate {float(summary.get('run_rate') or 0):.2f})"
                ),
                styles["note"],
            )
        )

        yet_to_bat = [
            str(row.get("player_name") or "").strip()
            for row in batters
            if str(row.get("player_name") or "").strip()
            and str(row.get("player_name") or "").strip().casefold() not in batted_names
        ]
        if yet_to_bat:
            story.append(Paragraph(_pdf_text("Did not bat: " + ", ".join(yet_to_bat)), styles["note"]))
        fow = _fall_of_wickets(innings)
        if fow:
            story.append(Paragraph(_pdf_text("Fall of wickets: " + ", ".join(fow)), styles["note"]))

        story.append(Paragraph("Bowling", styles["subhead"]))
        bowling_rows: list[list[Any]] = [
            [cell("Bowler"), cell("O", True), cell("M", True), cell("R", True), cell("W", True), cell("ECON", True)]
        ]
        for bowler in bowlers:
            name = str(bowler.get("player_name") or "").strip()
            if not name:
                continue
            if not int(bowler.get("legal_balls") or 0) and not int(bowler.get("runs_conceded") or 0):
                continue
            bowling_rows.append(
                [
                    cell(name),
                    cell(bowler.get("overs") or "0.0", True),
                    cell(int(bowler.get("maidens") or 0), True),
                    cell(int(bowler.get("runs_conceded") or 0), True),
                    cell(int(bowler.get("wickets") or 0), True),
                    cell(f"{float(bowler.get('economy') or 0):.2f}", True),
                ]
            )
        if len(bowling_rows) == 1:
            bowling_rows.append([cell("No overs bowled"), *[cell("", True) for _ in range(5)]])
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
