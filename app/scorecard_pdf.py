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
