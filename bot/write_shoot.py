#!/usr/bin/env python3
"""Plan one SYNOR shoot and write the sheet.

Track 3. Output is a markdown sheet in `bot/shoots/` — a thing a person picks
up and films with a phone — plus a JSON sidecar so Track 4 can post the
finished video without re-deriving the caption.

    python bot/write_shoot.py                   # first 'todo' in the queue
    python bot/write_shoot.py --shoot lift-test
    python bot/write_shoot.py --dry-run         # print it, write no files

Environment: ANTHROPIC_API_KEY, SHOPIFY_STORE, SHOPIFY_ADMIN_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Any

import anthropic

from agent_common import (
    FAMILIES, GENDERS, HERE, OCCASIONS, cached_system, name_hits, run_rounds,
    shop_from_env,
)
from synor_shopify import ShopifyError, forbidden_phrases

SHOOTS_DIR = HERE / "shoots"

FORMATS = ("street-test", "hands-only", "two-bottle-face-off", "day-in-scent",
           "talking-head", "unboxing", "question-answer")
# Formats where one product is a complete video; the rest need a comparison.
SINGLE_OK = ("talking-head", "unboxing", "question-answer")

_STR = {"type": "string"}

SHOOT_SCHEMA = {
    "type": "object",
    "properties": {
        "idea": {
            "type": "object",
            "properties": {
                "title": _STR, "one_line": _STR,
                "why_it_works": _STR, "who_for": _STR,
            },
            "required": ["title", "one_line", "why_it_works", "who_for"],
            "additionalProperties": False,
        },
        "concept": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": list(FORMATS)},
                "seconds": {"type": "integer"},
                "where": _STR,
                "kit": {"type": "array", "items": _STR},
                "shoot_notes": _STR,
            },
            "required": ["format", "seconds", "where", "kit", "shoot_notes"],
            "additionalProperties": False,
        },
        "hook": {
            "type": "object",
            "properties": {"spoken": _STR, "on_screen": _STR},
            "required": ["spoken", "on_screen"],
            "additionalProperties": False,
        },
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "seconds": {"type": "integer"},
                    "visual": _STR,
                    "spoken": _STR,
                    "on_screen": _STR,
                },
                "required": ["n", "seconds", "visual", "spoken", "on_screen"],
                "additionalProperties": False,
            },
        },
        "honest_negative": _STR,
        "b_roll": {"type": "array", "items": _STR},
        "product_handles": {"type": "array", "items": _STR},
        "caption": _STR,
        "hashtags": {"type": "array", "items": _STR},
        "youtube_title": _STR,
        "youtube_description": _STR,
        "thumbnail": _STR,
        "diaries_tie_in": _STR,
        "gender": {"type": "array", "items": {"type": "string", "enum": list(GENDERS)}},
        "occasion": {"type": "array", "items": {"type": "string", "enum": list(OCCASIONS)}},
        "family": {"type": "array", "items": {"type": "string", "enum": list(FAMILIES)}},
    },
    "required": [
        "idea", "concept", "hook", "shots", "honest_negative", "b_roll",
        "product_handles", "caption", "hashtags", "youtube_title",
        "youtube_description", "thumbnail", "diaries_tie_in",
        "gender", "occasion", "family",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- queue

def pick_shoot(queue: dict[str, Any], wanted: str | None) -> dict[str, Any]:
    shoots = queue.get("shoots") or []
    if wanted:
        for shoot in shoots:
            if shoot.get("id") == wanted:
                return shoot
        raise SystemExit(f"No shoot with id {wanted!r} in bot/vlog_queue.json")
    for shoot in shoots:
        if shoot.get("status") == "todo":
            return shoot
    raise SystemExit(
        "Nothing left to plan — every shoot in bot/vlog_queue.json is done. "
        "Add one and run again."
    )


def brief_block(shoot: dict[str, Any], defaults: dict[str, Any], today: date) -> str:
    language = shoot.get("language") or defaults.get("language") or "hinglish"
    city = shoot.get("city") or defaults.get("city") or "Ahmedabad"
    spoken = {
        "hinglish": "Hinglish — Hindi grammar with English words, Roman script, "
                    "written the way it is actually said.",
        "english": "English, Indian conversational English.",
        "gujarati": "Gujarati in Roman script, the way it is actually spoken.",
    }.get(language, language)
    lines = [
        "# The brief for this shoot",
        "",
        f"Today is {today.isoformat()}. The city is {city}.",
        f"Format to use: {shoot.get('format', 'hands-only')}",
        f"Target length: {shoot.get('seconds', 40)} seconds",
        f"Where: {shoot.get('where', city)}",
        f"Spoken lines in: {spoken}",
        "On-screen text: English, short.",
        "",
        "What the shoot is:",
        "",
        (shoot.get("brief") or "").strip(),
        "",
        "Write the sheet now. Choose the products yourself from the catalogue "
        "above — only ones whose tags genuinely fit — and keep every rule in "
        "the shoot contract, especially the ones about names, prices and what "
        "one person can film alone in an hour.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------ validation

def in_the_video(sheet: dict[str, Any]) -> str:
    """Only what ends up in the cut: the hook and the shots.

    Kept separate from `all_text` because two checks need this narrower blob.
    A product named solely in the YouTube description is not in the video, and
    an honest negative written in the sheet but never spoken is not either —
    both would pass if they were checked against everything.
    """
    parts = [sheet["hook"]["spoken"], sheet["hook"]["on_screen"]]
    for shot in sheet["shots"]:
        parts += [shot["visual"], shot["spoken"], shot["on_screen"]]
    return " ".join(parts)


def all_text(sheet: dict[str, Any]) -> str:
    """Every string a viewer could ever see or hear, in one blob."""
    parts = [
        sheet["idea"]["title"], sheet["idea"]["one_line"],
        sheet["honest_negative"], sheet["caption"],
        sheet["youtube_title"], sheet["youtube_description"],
        sheet["thumbnail"], sheet["concept"]["shoot_notes"],
        " ".join(sheet["hashtags"]), " ".join(sheet["b_roll"]),
        in_the_video(sheet),
    ]
    return " ".join(parts)


def check(sheet: dict[str, Any], shoot: dict[str, Any],
          products: list[dict[str, Any]], banned: list[str]) -> list[str]:
    """Everything a person would catch before picking up the phone."""
    problems: list[str] = []
    by_handle = {p["handle"]: p for p in products}
    fmt = sheet["concept"]["format"]

    # 1. No other house's name, no celebrity, anywhere a viewer can reach.
    hits = name_hits(all_text(sheet), banned)
    if hits:
        problems.append(
            "These names appear in the sheet and must not: " + ", ".join(hits)
            + ". Remove every one — from the lines, the on-screen text, the "
              "caption, the YouTube copy and the hashtags — and describe the "
              "scent itself instead."
        )

    # 2. Real products, and enough of them for the format.
    unknown = [h for h in sheet["product_handles"] if h not in by_handle]
    if unknown:
        problems.append(
            "These product handles are not in the catalogue: "
            + ", ".join(unknown) + ". Use handles exactly as printed."
        )
    real = [h for h in sheet["product_handles"] if h in by_handle]
    low = 1 if fmt in SINGLE_OK else 3
    if not low <= len(real) <= 6:
        problems.append(
            f"The shoot uses {len(real)} products; a {fmt} needs between "
            f"{low} and 6."
        )
    in_cut = in_the_video(sheet).lower()
    for handle in real:
        if by_handle[handle]["title"].lower() not in in_cut:
            problems.append(
                f"{by_handle[handle]['title']} is listed as a product but is "
                "never named in the hook or in a shot. Put it in the video or "
                "drop it."
            )

    # 3. Families must belong to a product actually used.
    product_families = {
        tag[len("family-"):]
        for handle in real
        for tag in by_handle[handle]["tags"] if tag.startswith("family-")
    }
    stray = [f for f in sheet["family"] if f not in product_families]
    if stray:
        problems.append(
            "These families are filed but no product in the shoot carries "
            "them: " + ", ".join(stray) + "."
        )
    if not sheet["family"]:
        problems.append("The shoot has no fragrance family filed.")
    if not sheet["gender"]:
        problems.append("The shoot has no gender filed.")

    # 4. The format the brief asked for.
    if fmt != shoot.get("format", fmt):
        problems.append(
            f"The brief asked for a {shoot['format']}; this sheet is a {fmt}."
        )

    # 5. The hook. Three seconds is three seconds.
    hook_words = len(sheet["hook"]["spoken"].split())
    if hook_words > 12:
        problems.append(
            f"The hook is {hook_words} words; it has to be 12 or fewer, "
            "because it is spoken in the first three seconds."
        )
    opener = sheet["hook"]["spoken"].lower()
    for greeting in ("hi guys", "hello guys", "welcome back", "what's up",
                     "namaste dosto", "aaj hum", "today we"):
        if opener.startswith(greeting):
            problems.append(
                f"The hook opens with {greeting!r}. A hook is a claim, a "
                "question or a number, not a greeting."
            )
    if len(sheet["hook"]["on_screen"].split()) > 6:
        problems.append(
            "The on-screen text in the hook is too long to read in three "
            "seconds. Four or five words."
        )
    if sheet["hook"]["on_screen"].strip().lower() == opener.strip():
        problems.append(
            "The hook's on-screen text repeats the spoken line. It should be "
            "the shorter, readable version for a viewer with the sound off."
        )

    # 6. Shot list: shootable, timed, and something happening in every frame.
    shots = sheet["shots"]
    if not 6 <= len(shots) <= 14:
        problems.append(f"There are {len(shots)} shots; it needs 6 to 14.")
    total = sum(s["seconds"] for s in shots)
    target = sheet["concept"]["seconds"]
    if target and abs(total - target) > max(8, target * 0.25):
        problems.append(
            f"The shots add up to {total}s against a {target}s target. "
            "Adjust the durations or the number of shots."
        )
    wanted_seconds = shoot.get("seconds")
    if wanted_seconds and abs(target - wanted_seconds) > wanted_seconds * 0.25:
        problems.append(
            f"The brief asked for about {wanted_seconds}s; this sheet targets "
            f"{target}s."
        )
    for shot in shots:
        if not shot["visual"].strip():
            problems.append(f"Shot {shot['n']} has no visual.")
        if not shot["spoken"].strip() and not shot["on_screen"].strip():
            problems.append(
                f"Shot {shot['n']} has neither a spoken line nor on-screen "
                "text. A silent, wordless shot is dead air."
            )
        words = len(shot["spoken"].split())
        if words > 14:
            problems.append(
                f"Shot {shot['n']} has a {words}-word line. Keep spoken lines "
                "to 12 words or fewer — longer ones get fumbled."
            )
    negative = sheet["honest_negative"].strip()
    if not negative:
        problems.append(
            "The sheet has no honest negative. Every shoot needs one thing "
            "said out loud against our own interest."
        )
    elif negative.lower() not in in_cut:
        problems.append(
            "The honest negative is written at the top of the sheet but is "
            "not in any shot. Put it in a spoken line, word for word, so it "
            "is actually in the video."
        )
    if shots and "49" not in shots[-1]["spoken"] + shots[-1]["on_screen"]:
        problems.append(
            "The last shot should be the ₹49 tester line and nothing else."
        )

    # 7. Kit list — the part that saves a shoot.
    if len(sheet["concept"]["kit"]) < 2:
        problems.append(
            "The kit list needs everything to carry, including any person "
            "whose help is needed."
        )

    # 8. Copy that has to fit somewhere.
    if len(sheet["caption"]) > 280:
        problems.append(
            f"The caption is {len(sheet['caption'])} characters; keep it under 280."
        )
    if len(sheet["youtube_title"]) > 70:
        problems.append(
            f"The YouTube title is {len(sheet['youtube_title'])} characters; "
            "keep it under 70 or it is cut off."
        )
    if not 5 <= len(sheet["hashtags"]) <= 10:
        problems.append(
            f"There are {len(sheet['hashtags'])} hashtags; it needs 5 to 10."
        )
    for tag in sheet["hashtags"]:
        bare = tag.lstrip("#")
        if not bare.isalnum() or not bare.islower():
            problems.append(
                f"The hashtag {tag!r} must be lower case letters and digits "
                "only, no spaces and no punctuation."
            )
    for handle in real:
        if f"/products/{handle}" not in sheet["youtube_description"]:
            problems.append(
                f"The YouTube description is missing the link for {handle}. "
                "Use synorperfume.com/products/HANDLE."
            )
    return problems


# --------------------------------------------------------------- output

def to_markdown(sheet: dict[str, Any], shoot: dict[str, Any],
                products: list[dict[str, Any]], today: date) -> str:
    titles = {p["handle"]: p["title"] for p in products}
    c, idea = sheet["concept"], sheet["idea"]
    out = [
        f"# {idea['title']}",
        "",
        f"`{shoot['id']}` · {c['format']} · about {c['seconds']}s · "
        f"planned {today.isoformat()}",
        "",
        f"**{idea['one_line']}**",
        "",
        f"For: {idea['who_for']}  ",
        f"Why it works: {idea['why_it_works']}",
        "",
        "## Before you leave",
        "",
        f"**Where:** {c['where']}",
        "",
        "**Carry:**",
        "",
    ]
    out += [f"- {item}" for item in c["kit"]]
    out += [
        "",
        f"**Scents:** " + ", ".join(titles.get(h, h) for h in sheet["product_handles"]),
        "",
        f"**Notes:** {c['shoot_notes']}",
        "",
        "## First three seconds",
        "",
        f"> **Say:** {sheet['hook']['spoken']}",
        f"> **On screen:** {sheet['hook']['on_screen']}",
        "",
        "## Shot list",
        "",
        "| # | Sec | Camera sees | Say | On screen |",
        "| --- | --- | --- | --- | --- |",
    ]
    for shot in sheet["shots"]:
        cells = [
            str(shot["n"]), f"{shot['seconds']}s",
            shot["visual"].replace("|", "/"),
            shot["spoken"].replace("|", "/") or "—",
            shot["on_screen"].replace("|", "/") or "—",
        ]
        out.append("| " + " | ".join(cells) + " |")
    total = sum(s["seconds"] for s in sheet["shots"])
    out += [
        "",
        f"Total: **{total}s**",
        "",
        f"The honest line: *{sheet['honest_negative']}*",
        "",
        "## Grab these too (b-roll)",
        "",
    ]
    out += [f"- {item}" for item in sheet["b_roll"]]
    out += [
        "",
        "## After the shoot",
        "",
        "### Instagram",
        "",
        sheet["caption"],
        "",
        " ".join(f"#{t.lstrip('#')}" for t in sheet["hashtags"]),
        "",
        "### YouTube",
        "",
        f"**Title:** {sheet['youtube_title']}",
        "",
        sheet["youtube_description"],
        "",
        f"**Thumbnail:** {sheet['thumbnail']}",
        "",
        "### Then the paper",
        "",
        sheet["diaries_tie_in"],
        "",
        "Once it is on YouTube, put the video id in the entry's "
        "`custom.youtube_ids` metafield and tag the entry `vlog` — the article "
        "page plays it as a still until someone taps it.",
        "",
        "---",
        "",
        "Filed as: "
        + ", ".join(
            [f"`gender-{g}`" for g in sheet["gender"]]
            + [f"`occasion-{o}`" for o in sheet["occasion"]]
            + [f"`family-{f}`" for f in sheet["family"]]
        ),
        "",
    ]
    return "\n".join(out)


# ------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(description="Plan one SYNOR shoot.")
    parser.add_argument("--shoot", help="shoot id from bot/vlog_queue.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the sheet; write no files")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()

    queue_path = HERE / "vlog_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    shoot = pick_shoot(queue, args.shoot)
    print(f"→ shoot: {shoot['id']} ({shoot.get('format')})", flush=True)

    shop = shop_from_env()
    products = shop.catalogue()
    banned = forbidden_phrases(products)
    print(f"→ {len(products)} products in the catalogue", flush=True)

    today = date.today()
    sheet = run_rounds(
        anthropic.Anthropic(),
        cached_system("vlog-style.md", products),
        brief_block(shoot, queue.get("defaults") or {}, today),
        SHOOT_SCHEMA,
        lambda candidate: check(candidate, shoot, products, banned),
        args.max_rounds,
    )
    if sheet is None:
        print(f"\n✗ Could not get a clean sheet in {args.max_rounds} rounds. "
              "Nothing was written.", file=sys.stderr)
        return 1

    markdown = to_markdown(sheet, shoot, products, today)

    if args.dry_run:
        print("\n--- DRY RUN, nothing written -----------------------------\n")
        print(markdown)
        return 0

    SHOOTS_DIR.mkdir(exist_ok=True)
    stem = f"{today.isoformat()}-{shoot['id']}"
    (SHOOTS_DIR / f"{stem}.md").write_text(markdown, encoding="utf-8")
    # The sidecar is for Track 4: caption, hashtags and YouTube copy, already
    # checked, so posting the finished video needs no second pass.
    (SHOOTS_DIR / f"{stem}.json").write_text(
        json.dumps({"shoot_id": shoot["id"], "planned": today.isoformat(),
                    **sheet}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    shoot["status"] = "planned"
    shoot["sheet"] = f"bot/shoots/{stem}.md"
    shoot["planned_on"] = today.isoformat()
    queue_path.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n✓ Sheet written: bot/shoots/{stem}.md")
    print(f"  {sheet['idea']['title']} — {sum(s['seconds'] for s in sheet['shots'])}s, "
          f"{len(sheet['shots'])} shots")

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ShopifyError, RuntimeError) as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        sys.exit(1)
    except anthropic.AuthenticationError:
        print("\n✗ ANTHROPIC_API_KEY is missing or wrong.", file=sys.stderr)
        sys.exit(1)
    except anthropic.RateLimitError as exc:
        retry = exc.response.headers.get("retry-after", "60")
        print(f"\n✗ Rate limited. Try again in {retry}s.", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIStatusError as exc:
        print(f"\n✗ Anthropic API error {exc.status_code}: {exc.message}",
              file=sys.stderr)
        sys.exit(1)
    except anthropic.APIConnectionError:
        print("\n✗ Could not reach the Anthropic API.", file=sys.stderr)
        sys.exit(1)
