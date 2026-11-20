"""Costs and AI accuracy report - for Dhruvika and Amit only, not on the site (Nov 20 2026, Dhruvika: "remove the cost
and ai accuracy mode from the site, that is for my info only"). README "Costs and AI accuracy report".

Run from the project folder, on a copy of the live database (or on Azure in the Kudu / SSH console):

    python scripts\\costs_and_accuracy.py
    python scripts\\costs_and_accuracy.py --gemini-in 0.5 --gemini-out 3 --whatsapp 0.0034 --azure 13

Costs: every Gemini / Claude call the app made (table app_ai_usage, counted since Nov 18 2026) and every WhatsApp
message sent (app_whatsapp_log), per month for the last 6 months, with the prices given (Gemini per 1 million tokens
in / out - thinking tokens count as out - WhatsApp per message, Azure per month). Estimates: the bills are the real
numbers.

AI accuracy: every scorecard a person fixed after the AI read it, compared field by field with the AI's own reading
(app/ai_accuracy.py) - overall, by group, the weakest fields and card by card. No AI call is made.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def _months(count: int) -> list[str]:
    today = datetime.now(timezone.utc)
    year, number = today.year, today.month
    out = []
    for _ in range(count):
        out.append(f"{year:04d}-{number:02d}")
        year, number = (year - 1, 12) if number == 1 else (year, number - 1)
    return out


def costs(app, args) -> None:
    import usage_meter

    print("COSTS (estimates - the Google, Meta and Azure bills are the real numbers)")
    with app._auth_connection() as connection:
        connection.execute(usage_meter.CREATE_SQL)
        connection.execute(app._WHATSAPP_LOG_TABLE)
        for month in _months(6):
            ai = connection.execute(
                "SELECT purpose, model, COUNT(*), SUM(ok), SUM(input_tokens), SUM(output_tokens), SUM(thinking_tokens) "
                "FROM app_ai_usage WHERE substr(at, 1, 7) = ? GROUP BY purpose, model ORDER BY COUNT(*) DESC",
                (month,),
            ).fetchall()
            wa = connection.execute(
                "SELECT kind, COUNT(*) FROM app_whatsapp_log WHERE status = 'sent' AND substr(sent_at, 1, 7) = ? GROUP BY kind",
                (month,),
            ).fetchall()
            ai_cost = sum(
                int(row[4] or 0) / 1e6 * args.gemini_in + (int(row[5] or 0) + int(row[6] or 0)) / 1e6 * args.gemini_out for row in ai
            )
            messages = sum(int(row[1] or 0) for row in wa)
            wa_cost = messages * args.whatsapp
            total = ai_cost + wa_cost + args.azure
            print(f"\n{month}: total ${total:.2f}  (AI ${ai_cost:.2f}, WhatsApp ${wa_cost:.2f}, Azure ${args.azure:.2f})")
            for purpose, model, calls, answered, tokens_in, tokens_out, thinking in ai:
                failed = int(calls) - int(answered or 0)
                print(f"   AI  {purpose:<32} {model:<24} {calls:>5} calls{f' ({failed} failed)' if failed else ''}  "
                      f"in {int(tokens_in or 0):,}  out {int(tokens_out or 0) + int(thinking or 0):,}")
            for kind, count in wa:
                print(f"   WhatsApp  {kind:<12} {count:>5} messages")
            if not ai and not wa:
                print("   nothing counted (AI calls are counted from Nov 18 2026)")


def accuracy(app) -> None:
    import ai_accuracy

    store = app.load_store()
    total = ai_accuracy.Score()
    cards = []
    for upload in app.canonical_archive_uploads(store.get("archive_uploads", []) or []):
        read = ai_accuracy.ai_reading(upload)
        if not read:
            continue
        truth = app._scorecard_pick_template(upload) or {}
        meta = truth.get("meta") if isinstance(truth.get("meta"), dict) else {}
        if str(meta.get("source") or "") not in {"manual-entry", "manual-import", "checked-example"} or not app.ai_vision._template_adds_up(truth):
            continue
        score = ai_accuracy.compare(truth, read)
        if not score.checked:
            continue
        total.merge(score)
        card = app._scorecard_from_archive(upload)
        cards.append((str(card.get("date") or ""), str(card.get("title") or upload.get("id")), score))
    print("\nAI ACCURACY (cards a person fixed after the AI read them; goal 90%)")
    if not total.checked:
        print("   no fixed AI-read cards yet")
        return
    print(f"   OVERALL {100 * total.right / total.checked:.1f}%  ({total.right}/{total.checked} fields on {len(cards)} cards)")
    for group in ai_accuracy.group_scores(total.fields):
        print(f"   {group['group']:<16} {group['percent']:5.1f}%  ({group['right']}/{group['checked']})")
    print("   weakest fields:")
    for field in ai_accuracy.field_scores(total.fields)[:6]:
        print(f"      {field['field']:<22} {field['percent']:5.1f}%  ({field['right']}/{field['checked']})")
    print("   card by card:")
    for date, title, score in sorted(cards, reverse=True):
        print(f"      {100 * score.right / score.checked:5.1f}%  {date}  {title}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gemini-in", type=float, default=0.0, help="Gemini price per 1M tokens in (0 = free tier)")
    parser.add_argument("--gemini-out", type=float, default=0.0, help="Gemini price per 1M tokens out")
    parser.add_argument("--whatsapp", type=float, default=0.0034, help="price per WhatsApp message (Utility, US/Canada)")
    parser.add_argument("--azure", type=float, default=0.0, help="Azure plan price per month")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    import main as app

    costs(app, args)
    accuracy(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
