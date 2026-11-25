"""Weekly report: SQL computes the numbers, an LLM writes a short summary, we validate it,
and post to Discord. If the LLM fails in any way, a plain-number report goes out instead.

From the repo root:
    python -m pipeline.report --dry-run        # print the report; no saving, no posting
    python -m pipeline.report                  # latest complete week; skips if already posted
    python -m pipeline.report --week 2026-11-16 --force   # a specific Monday, re-post on purpose
"""

import argparse
import datetime as dt
import json
import logging
import os
import re
import unicodedata
from pathlib import Path

import requests

from pipeline.config import LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS, REPORT_MODELS
from pipeline.db import get_connection

log = logging.getLogger("pipeline.report")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEEKLY_SQL = Path(__file__).resolve().parent.parent / "sql" / "queries" / "weekly_summary.sql"
DISCORD_LIMIT = 2000      # Discord rejects messages longer than this
SUMMARY_MIN_CHARS = 150
SUMMARY_MAX_CHARS = 1100

SYSTEM_PROMPT = """You write a short weekly weather summary for people living in Laguna, Philippines.
The full table of numbers is shown to readers right above your summary, so do NOT repeat every
number. Describe the pattern instead: was the week wetter or drier than normal across Laguna,
which towns stood out (wettest, driest), and how it compared with the week before.
Say "more/less than last week" rather than "a change of".
Rules:
- Use ONLY the numbers in the data. Do not calculate anything: every number you write must
  appear in the data (rounding is fine). Differences and percentages are already provided.
- Mention every town by name (grouping towns with the same values is fine).
- No forecasts, no advice, no causes (like typhoons) unless they are in the data.
- 4 to 6 sentences of plain text. No headings, lists, links or emoji. Under 900 characters.
Field meanings: rain_mm = rain this week; rain_days = days with at least 1 mm;
last_week_rain_mm = rain the week before; change_from_last_week_mm = this week minus last week;
normal_rain_mm / normal_rain_days = the 1991-2020 average for the same 7 days;
percent_of_normal_rain = this week's rain as a % of normal; hottest_c / coolest_c = highest and
lowest temperature of the week; strongest_wind_kmh = strongest daily max wind."""


# ---------- numbers (SQL) ----------

def latest_complete_week(conn) -> dt.date | None:
    """The newest Monday whose 7 days have rain data for every town."""
    row = conn.execute("""
        SELECT max(week_start) FROM (
            SELECT date_trunc('week', date)::date AS week_start,
                   count(*) FILTER (WHERE precipitation_mm IS NOT NULL) AS days_with_data
            FROM daily_weather
            WHERE date >= current_date - 60
            GROUP BY 1
        ) weeks
        WHERE days_with_data = 7 * (SELECT count(*) FROM locations)
    """).fetchone()
    return row[0]


def weekly_facts(conn, week_start: dt.date) -> dict:
    """Run weekly_summary.sql for one week. Returns {"week": label, "towns": [...]}."""
    cur = conn.execute(WEEKLY_SQL.read_text(encoding="utf-8"), {"week_start": week_start})
    columns = [c.name for c in cur.description]
    towns = [{col: _plain(value) for col, value in zip(columns, row)} for row in cur.fetchall()]
    town_count = conn.execute("SELECT count(*) FROM locations").fetchone()[0]
    if len(towns) != town_count:
        raise RuntimeError(f"Week {week_start}: data for {len(towns)} of {town_count} towns")
    return {"week": week_label(week_start), "towns": towns}


def _plain(value):
    """Decimal -> int/float so the numbers serialise cleanly to JSON."""
    if hasattr(value, "is_integer") or type(value).__name__ == "Decimal":
        number = float(value)
        return int(number) if number.is_integer() else number
    return value


def week_label(week_start: dt.date) -> str:
    end = week_start + dt.timedelta(days=6)
    if week_start.month == end.month:
        return f"{week_start.day}–{end.day} {end:%b %Y}"
    return f"{week_start.day} {week_start:%b} – {end.day} {end:%b %Y}"


# ---------- LLM output validation (pure functions, tested in tests/test_report.py) ----------

def allowed_numbers(facts: dict) -> set[float]:
    """Every number the summary may contain: the data, plus the week label's numbers,
    the normals period (1991, 2020, 30 years), 7 days and the number of towns."""
    numbers = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", facts["week"])}
    for town in facts["towns"]:
        for value in town.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numbers.add(abs(float(value)))
    numbers |= {1991.0, 2020.0, 30.0, 7.0, float(len(facts["towns"]))}
    return numbers


def number_is_allowed(text_number: str, allowed: set[float]) -> bool:
    """True if the number, as written, could be an allowed value rounded.
    "12" matches 12.4 or 11.6 (within half a unit); "12.4" must match to 1 decimal."""
    decimals = len(text_number.split(".")[1]) if "." in text_number else 0
    value = float(text_number)
    half_unit = 0.5 * 10 ** -decimals
    return any(abs(a - value) <= half_unit + 1e-9 for a in allowed)


def _fold(text: str) -> str:
    """Lower-case and strip accents, so 'Los Banos' matches 'Los Baños'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def validate_summary(text: str, facts: dict) -> list[str]:
    """Return the list of problems; an empty list means the summary is usable."""
    if not text or not text.strip():
        return ["empty answer"]
    problems = []
    if not SUMMARY_MIN_CHARS <= len(text) <= SUMMARY_MAX_CHARS:
        problems.append(f"length {len(text)} outside {SUMMARY_MIN_CHARS}-{SUMMARY_MAX_CHARS}")
    if "http" in text.lower() or "@" in text:
        problems.append("contains a link or @mention")
    folded = _fold(text)
    for town in facts["towns"]:
        if _fold(town["town"]) not in folded:
            problems.append(f"doesn't mention {town['town']}")
    allowed = allowed_numbers(facts)
    for number in re.findall(r"\d+(?:\.\d+)?", text):
        if not number_is_allowed(number, allowed):
            problems.append(f"number {number} isn't in the data")
    return problems


# ---------- message formatting ----------

def numbers_block(facts: dict) -> str:
    lines = []
    for t in facts["towns"]:
        pct = f" ({t['percent_of_normal_rain']}% of normal)" if t["percent_of_normal_rain"] is not None else ""
        lines.append(
            f"• **{t['town']}**: {t['rain_mm']} mm rain, {t['rain_days']} "
            f"rain day{'' if t['rain_days'] == 1 else 's'}{pct} · "
            f"last week {t['last_week_rain_mm']} mm · normal {t['normal_rain_mm']} mm · "
            f"{t['coolest_c']}–{t['hottest_c']} °C · wind up to {t['strongest_wind_kmh']} km/h"
        )
    return "\n".join(lines)


def build_message(facts: dict, summary: str | None, model: str | None) -> str:
    header = (f"**Laguna weekly weather: {facts['week']}**\n"
              "_Latest complete week in the data (ERA5 runs about a week behind)._")
    if summary:
        footer = f"_Summary written by {model} using only the numbers above, which were computed in SQL._"
        return f"{header}\n\n{numbers_block(facts)}\n\n{summary.strip()}\n\n{footer}"
    footer = "_Numbers only this week: the AI summary was unavailable or failed validation._"
    return f"{header}\n\n{numbers_block(facts)}\n\n{footer}"


# ---------- LLM call ----------

def call_llm(model: str, facts: dict, api_key: str) -> str:
    response = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Data (JSON):\n" + json.dumps(facts, ensure_ascii=False)},
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": 0.3,  # low: we want plain description, not creativity
        },
        timeout=LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if "choices" not in body:
        raise RuntimeError(f"no choices in response: {body.get('error')}")
    return body["choices"][0]["message"].get("content") or ""


def generate_summary(facts: dict) -> tuple[str | None, str | None]:
    """Try each model in order. Returns (summary, model), or (None, None) for the fallback."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        log.warning("OPENROUTER_API_KEY not set: using the plain-number report")
        return None, None
    for model in REPORT_MODELS:
        try:
            text = call_llm(model, facts, api_key)
        except (requests.RequestException, RuntimeError, KeyError, ValueError) as error:
            log.warning("%s failed: %s", model, error)
            continue
        problems = validate_summary(text, facts)
        if problems:
            log.warning("%s summary rejected: %s", model, "; ".join(problems))
            continue
        log.info("%s summary accepted", model)
        return text.strip(), model
    log.warning("No model produced a valid summary: using the plain-number report")
    return None, None


# ---------- saving and posting ----------

def post_to_discord(webhook_url: str, message: str) -> None:
    response = requests.post(
        webhook_url,
        # parse: [] -> Discord ignores @everyone/@here/user mentions in the text
        json={"content": message, "allowed_mentions": {"parse": []}},
        timeout=30,
    )
    response.raise_for_status()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write and post the weekly weather report.")
    parser.add_argument("--week", type=dt.date.fromisoformat, help="Monday of the week to report")
    parser.add_argument("--force", action="store_true", help="post even if already posted")
    parser.add_argument("--dry-run", action="store_true", help="print only; don't save or post")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    webhook_url = os.environ.get("DISCORD_REPORT_WEBHOOK_URL")
    if not args.dry_run and not webhook_url:
        raise RuntimeError("DISCORD_REPORT_WEBHOOK_URL is not set")
    if args.week and args.week.isoweekday() != 1:
        parser.error(f"--week must be a Monday; {args.week} is a {args.week:%A}")

    with get_connection() as conn:
        week_start = args.week or latest_complete_week(conn)
        if week_start is None:
            raise RuntimeError("No complete week of data in the last 60 days")

        posted = conn.execute("SELECT posted_at FROM reports WHERE week_start = %s",
                              (week_start,)).fetchone()
        if posted and posted[0] and not args.force and not args.dry_run:
            log.info("Week of %s already posted at %s; nothing to do (use --force to re-post)",
                     week_start, posted[0])
            return

        facts = weekly_facts(conn, week_start)
        summary, model = generate_summary(facts)
        message = build_message(facts, summary, model)
        if len(message) > DISCORD_LIMIT:
            log.warning("Message too long (%d chars): dropping the summary", len(message))
            summary, model = None, None
            message = build_message(facts, None, None)

        if args.dry_run:
            print(message)
            return

        # Save first (posted_at NULL), post, then mark posted. If posting fails the job
        # fails loudly, and a re-run will try again because posted_at is still NULL.
        conn.execute("""
            INSERT INTO reports (week_start, summary_text, model)
            VALUES (%s, %s, %s)
            ON CONFLICT (week_start) DO UPDATE
                SET summary_text = EXCLUDED.summary_text,
                    model        = EXCLUDED.model,
                    created_at   = now(),
                    posted_at    = NULL
        """, (week_start, message, model or "fallback"))
        conn.commit()

        post_to_discord(webhook_url, message)
        conn.execute("UPDATE reports SET posted_at = now() WHERE week_start = %s", (week_start,))
        log.info("Posted the report for the week of %s (%s)", week_start, model or "fallback")


if __name__ == "__main__":
    main()
