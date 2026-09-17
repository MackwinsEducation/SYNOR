#!/usr/bin/env python3
"""Turn one piece of work into a distribution pack.

Track 4. Takes a shoot sheet (from Track 3) or a published Diaries entry
(from Track 2) and writes every channel's copy separately — reel, story,
carousel, YouTube, Shorts, Facebook, WhatsApp, X, Pinterest — plus a posting
schedule across about a week.

    python bot/write_social.py --from-shoot 2026-09-17-lift-test
    python bot/write_social.py --from-article office-perfume-six-that-dont-crowd-the-room
    python bot/write_social.py --from-shoot 2026-09-17-lift-test --dry-run

The pack is markdown, committed and printed into the Actions run summary, so
it can be copied out on a phone. A JSON sidecar holds the same fields for a
publisher to post from later.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from typing import Any

import anthropic

from agent_common import (
    HERE, cached_system, name_hits, run_rounds, shop_from_env, strip_tags,
)
from synor_shopify import ShopifyError, forbidden_phrases

SOCIAL_DIR = HERE / "social"
SHOOTS_DIR = HERE / "shoots"

_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}

PACK_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": _STR,
        "honest_line": _STR,
        "product_handles": _STRS,
        "reel": {
            "type": "object",
            "properties": {
                "caption": _STR,
                "first_comment": _STR,
                "hashtags": _STRS,
                "cover_text": _STR,
            },
            "required": ["caption", "first_comment", "hashtags", "cover_text"],
            "additionalProperties": False,
        },
        "story": {
            "type": "object",
            "properties": {
                "frames": _STRS,
                "sticker": _STR,
                "link_text": _STR,
            },
            "required": ["frames", "sticker", "link_text"],
            "additionalProperties": False,
        },
        "carousel": {
            "type": "object",
            "properties": {
                "slides": _STRS,
                "caption": _STR,
            },
            "required": ["slides", "caption"],
            "additionalProperties": False,
        },
        "youtube": {
            "type": "object",
            "properties": {
                "title": _STR,
                "description": _STR,
                "tags": _STRS,
                "pinned_comment": _STR,
            },
            "required": ["title", "description", "tags", "pinned_comment"],
            "additionalProperties": False,
        },
        "shorts": {
            "type": "object",
            "properties": {"title": _STR, "description": _STR},
            "required": ["title", "description"],
            "additionalProperties": False,
        },
        "facebook": {
            "type": "object",
            "properties": {"text": _STR, "link": _STR},
            "required": ["text", "link"],
            "additionalProperties": False,
        },
        "whatsapp": {
            "type": "object",
            "properties": {
                "worth_sending": {"type": "boolean"},
                "message": _STR,
                "why_not": _STR,
            },
            "required": ["worth_sending", "message", "why_not"],
            "additionalProperties": False,
        },
        "x_thread": _STRS,
        "pinterest": {
            "type": "object",
            "properties": {"title": _STR, "description": _STR, "board": _STR},
            "required": ["title", "description", "board"],
            "additionalProperties": False,
        },
        "schedule": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "integer"},
                    "channel": _STR,
                    "what": _STR,
                },
                "required": ["day", "channel", "what"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "headline", "honest_line", "product_handles", "reel", "story",
        "carousel", "youtube", "shorts", "facebook", "whatsapp", "x_thread",
        "pinterest", "schedule",
    ],
    "additionalProperties": False,
}

STORE = "synorperfume.com"


# ---------------------------------------------------------------- source

def from_shoot(stem: str) -> tuple[str, str, dict[str, Any]]:
    """The sidecar Track 3 wrote. Everything is already checked."""
    path = SHOOTS_DIR / f"{stem}.json"
    if not path.exists():
        matches = sorted(SHOOTS_DIR.glob(f"*{stem}*.json"))
        if not matches:
            raise SystemExit(
                f"No shoot sidecar matching {stem!r} in bot/shoots/. "
                "Run write_shoot.py first."
            )
        path = matches[-1]
    sheet = json.loads(path.read_text(encoding="utf-8"))
    lines = [
        "This is a **video** that has been shot. It is going out as a reel and",
        "on YouTube, and the written entry follows.",
        "",
        f"Working title: {sheet['idea']['title']}",
        f"In one line: {sheet['idea']['one_line']}",
        f"Who it is for: {sheet['idea']['who_for']}",
        f"Format: {sheet['concept']['format']}, "
        f"about {sheet['concept']['seconds']} seconds",
        f"Where it was shot: {sheet['concept']['where']}",
        "",
        f"The hook, as spoken: {sheet['hook']['spoken']}",
        f"The honest line in it: {sheet['honest_negative']}",
        "",
        "What happens, shot by shot:",
    ]
    for shot in sheet["shots"]:
        lines.append(f"  {shot['n']}. {shot['visual']} — \"{shot['spoken']}\"")
    lines += [
        "",
        "Products in it: " + ", ".join(sheet["product_handles"]),
        "",
        "The thumbnail: " + sheet["thumbnail"],
    ]
    return path.stem, "video", {"brief": "\n".join(lines),
                                "handles": sheet["product_handles"]}


def from_article(shop, handle: str) -> tuple[str, str, dict[str, Any]]:
    """A published entry, read back off the store."""
    data = shop.gql(
        """
        query($q: String!) {
          articles(first: 5, query: $q) {
            nodes { handle title summary body tags }
          }
        }
        """,
        {"q": f"handle:{handle}"},
    )
    nodes = [n for n in data["articles"]["nodes"] if n["handle"] == handle]
    if not nodes:
        raise SystemExit(f"No article with handle {handle!r} on the store")
    article = nodes[0]
    handles = [t[len("pick-"):] for t in article["tags"] if t.startswith("pick-")]
    body = strip_tags(article["body"] or "")
    body = re.sub(r"\s+", " ", body).strip()
    brief = "\n".join([
        "This is a **written entry** that is published on the paper. It is",
        f"live at {STORE}/blogs/diaries/{handle}.",
        "",
        f"Title: {article['title']}",
        f"Standfirst: {strip_tags(article['summary'] or '').strip()}",
        "",
        "The entry itself:",
        "",
        body[:6000],
    ])
    return handle, "article", {"brief": brief, "handles": handles}


def brief_block(source: dict[str, Any], kind: str, language: str,
                link: str, today: date) -> str:
    return "\n".join([
        "# The piece being distributed",
        "",
        f"Today is {today.isoformat()}. Day 0 of the schedule is today.",
        f"The link to send people to: {link}",
        f"WhatsApp and any spoken copy in: {language}",
        "",
        source["brief"],
        "",
        "Write the whole pack now. Write each channel for its own room — a "
        "caption that would work on all of them is too vague for any of them. "
        "Keep every hard rule, especially the ones about names and prices.",
    ])


# ------------------------------------------------------------ validation

def pack_text(pack: dict[str, Any]) -> str:
    """Every string a person could read, in one blob."""
    p = pack
    parts = [
        p["headline"], p["honest_line"],
        p["reel"]["caption"], p["reel"]["first_comment"], p["reel"]["cover_text"],
        " ".join(p["reel"]["hashtags"]),
        " ".join(p["story"]["frames"]), p["story"]["sticker"], p["story"]["link_text"],
        " ".join(p["carousel"]["slides"]), p["carousel"]["caption"],
        p["youtube"]["title"], p["youtube"]["description"],
        " ".join(p["youtube"]["tags"]), p["youtube"]["pinned_comment"],
        p["shorts"]["title"], p["shorts"]["description"],
        p["facebook"]["text"], p["whatsapp"]["message"],
        " ".join(p["x_thread"]),
        p["pinterest"]["title"], p["pinterest"]["description"],
        " ".join(entry["what"] for entry in p["schedule"]),
    ]
    return " ".join(parts)


def check(pack: dict[str, Any], products: list[dict[str, Any]],
          banned: list[str], wanted_handles: list[str]) -> list[str]:
    problems: list[str] = []
    by_handle = {p["handle"]: p for p in products}
    blob = pack_text(pack)

    # 1. No other house's name, no celebrity, on any channel.
    hits = name_hits(blob, banned)
    if hits:
        problems.append(
            "These names appear in the pack and must not: " + ", ".join(hits)
            + ". Remove every one from every channel and describe the scent "
              "itself instead."
        )

    # 2. Prices: only the two real claims.
    for match in re.findall(r"₹\s?([\d,]+)", blob):
        if match.replace(",", "") != "49":
            problems.append(
                f"The pack states a price of ₹{match}. The only price that may "
                "appear is ₹49 for a tester, which comes back as credit."
            )
    for word in ("limited time", "hurry", "only today", "last chance",
                 "sale", "flat off", "% off"):
        if word in blob.lower():
            problems.append(f"Remove the false urgency: {word!r}.")

    # 3. Engagement bait.
    for bait in ("tag 3", "tag three", "comment yes", "double tap",
                 "like and share", "comment below if"):
        if bait in blob.lower():
            problems.append(f"Remove the engagement bait: {bait!r}.")

    # 4. Real products, and the ones the piece is actually about.
    unknown = [h for h in pack["product_handles"] if h not in by_handle]
    if unknown:
        problems.append(
            "These product handles are not in the catalogue: "
            + ", ".join(unknown) + "."
        )
    if wanted_handles:
        missing = [h for h in wanted_handles if h not in pack["product_handles"]]
        if missing:
            problems.append(
                "The piece is about these products but the pack leaves them "
                "out: " + ", ".join(missing) + "."
            )
    real = [h for h in pack["product_handles"] if h in by_handle]
    linked = " ".join([pack["youtube"]["description"], pack["facebook"]["text"],
                       pack["pinterest"]["description"], pack["whatsapp"]["message"],
                       " ".join(pack["x_thread"])])
    for handle in real:
        if f"/products/{handle}" not in linked:
            problems.append(
                f"{handle} is never linked. Use "
                f"{STORE}/products/{handle} somewhere a link can be clicked — "
                "the YouTube description, Facebook, Pinterest or the thread."
            )

    # 5. Instagram reel.
    reel = pack["reel"]
    if len(reel["caption"]) > 280:
        problems.append(
            f"The reel caption is {len(reel['caption'])} characters; under 280."
        )
    first_line = reel["caption"].split("\n", 1)[0]
    if len(first_line) > 90:
        problems.append(
            f"The reel's first line is {len(first_line)} characters. Instagram "
            "cuts it at about 90, and the first line is the whole job."
        )
    if "#" in reel["caption"]:
        problems.append(
            "The reel caption carries hashtags. They belong in the first "
            "comment, not the caption."
        )
    if not 5 <= len(reel["hashtags"]) <= 10:
        problems.append(
            f"There are {len(reel['hashtags'])} hashtags; it needs 5 to 10."
        )
    for tag in reel["hashtags"]:
        bare = tag.lstrip("#")
        if not bare.isalnum() or not bare.islower():
            problems.append(
                f"The hashtag {tag!r} must be lower case letters and digits "
                "only, no spaces and no punctuation."
            )
    if len(reel["cover_text"].split()) > 6:
        problems.append("The reel cover text is too long. Six words at most.")

    # 6. Story — three frames, readable in five seconds each.
    frames = pack["story"]["frames"]
    if len(frames) != 3:
        problems.append(f"The story has {len(frames)} frames; it needs 3.")
    for i, frame in enumerate(frames, 1):
        if len(frame) > 70:
            problems.append(
                f"Story frame {i} is {len(frame)} characters. Six words, "
                "because it is on screen for five seconds."
            )
    if "?" not in pack["story"]["sticker"]:
        problems.append(
            "The story sticker should ask something. As written it asks nothing."
        )

    # 7. Carousel — one idea a slide, readable at arm's length.
    slides = pack["carousel"]["slides"]
    if not 5 <= len(slides) <= 8:
        problems.append(f"The carousel has {len(slides)} slides; it needs 5 to 8.")
    for i, slide in enumerate(slides, 1):
        if len(slide) > 120:
            problems.append(
                f"Carousel slide {i} is {len(slide)} characters. One idea, "
                "readable at arm's length."
            )

    # 8. YouTube and Shorts.
    yt = pack["youtube"]
    if len(yt["title"]) > 70:
        problems.append(
            f"The YouTube title is {len(yt['title'])} characters; under 70 or "
            "it is cut off in search."
        )
    if len(yt["description"]) < 200:
        problems.append(
            "The YouTube description is too thin. Three or four sentences, "
            "then the product links."
        )
    if not 5 <= len(yt["tags"]) <= 15:
        problems.append(f"There are {len(yt['tags'])} YouTube tags; it needs 5 to 15.")
    shorts = pack["shorts"]
    if len(shorts["title"]) > 45:
        problems.append(
            f"The Shorts title is {len(shorts['title'])} characters; under 45."
        )
    if "#shorts" not in (shorts["title"] + shorts["description"]).lower():
        problems.append("The Shorts entry is missing #shorts.")
    if yt["title"].strip().lower() == shorts["title"].strip().lower():
        problems.append(
            "The Shorts title is the same as the YouTube one. Shorts is a "
            "different audience and a much shorter line."
        )

    # 9. Facebook — plainer, no hashtag block.
    fb = pack["facebook"]["text"]
    if fb.count("#") > 1:
        problems.append(
            "The Facebook post carries a hashtag block. That room does not "
            "read them."
        )
    if len(fb) < 200:
        problems.append("The Facebook post is too short for that room.")

    # 10. WhatsApp — the warmest list, so it is allowed to say no.
    wa = pack["whatsapp"]
    if wa["worth_sending"]:
        if not wa["message"].strip():
            problems.append("WhatsApp is marked worth sending but has no message.")
        if len(wa["message"]) > 400:
            problems.append(
                f"The WhatsApp message is {len(wa['message'])} characters; "
                "under 400."
            )
        if "#" in wa["message"]:
            problems.append("No hashtags on WhatsApp, ever.")
        if wa["message"].count("http") + wa["message"].count(STORE) > 1:
            problems.append("One link in a WhatsApp message, not more.")
    elif not wa["why_not"].strip():
        problems.append(
            "WhatsApp is marked not worth sending, but with no reason. Say why."
        )

    # 11. X thread.
    thread = pack["x_thread"]
    if not 2 <= len(thread) <= 4:
        problems.append(f"The thread has {len(thread)} posts; it needs 2 to 4.")
    for i, post in enumerate(thread, 1):
        if len(post) > 270:
            problems.append(f"Thread post {i} is {len(post)} characters; under 270.")

    # 12. Pinterest.
    pin = pack["pinterest"]
    if len(pin["title"]) > 100:
        problems.append("The Pinterest title is over 100 characters.")
    if not 100 <= len(pin["description"]) <= 500:
        problems.append(
            "The Pinterest description should be 100 to 500 characters and "
            "useful without the image."
        )

    # 13. The schedule.
    schedule = pack["schedule"]
    if not 4 <= len(schedule) <= 7:
        problems.append(
            f"The schedule has {len(schedule)} entries; one piece is 4 to 7 "
            "posts across about a week."
        )
    seen: set[tuple[int, str]] = set()
    for entry in schedule:
        key = (entry["day"], entry["channel"].lower())
        if key in seen:
            problems.append(
                f"The schedule posts to {entry['channel']} twice on day "
                f"{entry['day']}. Never two on one channel on one day."
            )
        seen.add(key)
        if entry["day"] < 0 or entry["day"] > 14:
            problems.append(
                f"A schedule entry is on day {entry['day']}; keep it inside 0 to 14."
            )
    if schedule and min(e["day"] for e in schedule) != 0:
        problems.append("Nothing goes out on day 0. The reel should.")

    # 14. The honest line has to actually be somewhere.
    honest = pack["honest_line"].strip()
    if not honest:
        problems.append(
            "The pack has no honest line. One channel has to say the thing "
            "that is not flattering."
        )
    return problems


# --------------------------------------------------------------- output

def to_markdown(pack: dict[str, Any], stem: str, kind: str, link: str,
                products: list[dict[str, Any]], today: date) -> str:
    titles = {p["handle"]: p["title"] for p in products}
    out = [
        f"# {pack['headline']}",
        "",
        f"`{stem}` · {kind} · pack written {today.isoformat()}",
        "",
        f"Link: {link}",
        f"Scents: " + ", ".join(titles.get(h, h) for h in pack["product_handles"]),
        "",
        f"The honest line, which has to survive editing: *{pack['honest_line']}*",
        "",
        "## Schedule",
        "",
        "| Day | Date | Channel | What goes out |",
        "| --- | --- | --- | --- |",
    ]
    for entry in sorted(pack["schedule"], key=lambda e: e["day"]):
        when = today + timedelta(days=entry["day"])
        out.append(
            f"| {entry['day']} | {when.strftime('%a %d %b')} | "
            f"{entry['channel']} | {entry['what']} |"
        )

    reel = pack["reel"]
    out += [
        "",
        "## Instagram · reel",
        "",
        f"**Cover text:** {reel['cover_text']}",
        "",
        "**Caption**",
        "",
        "```",
        reel["caption"],
        "```",
        "",
        "**First comment** (hashtags go here, never the caption)",
        "",
        "```",
        reel["first_comment"].strip(),
        "",
        " ".join(f"#{t.lstrip('#')}" for t in reel["hashtags"]),
        "```",
        "",
        "## Instagram · story",
        "",
    ]
    for i, frame in enumerate(pack["story"]["frames"], 1):
        out.append(f"{i}. {frame}")
    out += [
        "",
        f"**Sticker:** {pack['story']['sticker']}",
        f"**Link sticker:** {pack['story']['link_text']}",
        "",
        "## Instagram · carousel",
        "",
    ]
    for i, slide in enumerate(pack["carousel"]["slides"], 1):
        out.append(f"**Slide {i}** — {slide}")
        out.append("")
    out += [
        "**Caption**",
        "",
        "```",
        pack["carousel"]["caption"],
        "```",
        "",
        "## YouTube",
        "",
        f"**Title:** {pack['youtube']['title']}",
        "",
        "**Description**",
        "",
        "```",
        pack["youtube"]["description"],
        "```",
        "",
        "**Tags:** " + ", ".join(pack["youtube"]["tags"]),
        "",
        f"**Pinned comment:** {pack['youtube']['pinned_comment']}",
        "",
        "## YouTube Shorts",
        "",
        f"**Title:** {pack['shorts']['title']}",
        "",
        "```",
        pack["shorts"]["description"],
        "```",
        "",
        "## Facebook",
        "",
        "```",
        pack["facebook"]["text"],
        "```",
        "",
        f"Link: {pack['facebook']['link']}",
        "",
        "## WhatsApp",
        "",
    ]
    if pack["whatsapp"]["worth_sending"]:
        out += ["```", pack["whatsapp"]["message"], "```"]
    else:
        out += [f"**Not sending this one.** {pack['whatsapp']['why_not']}"]
    out += ["", "## X", ""]
    for i, post in enumerate(pack["x_thread"], 1):
        out += [f"**{i}/{len(pack['x_thread'])}**", "", "```", post, "```", ""]
    out += [
        "## Pinterest",
        "",
        f"**Board:** {pack['pinterest']['board']}",
        f"**Title:** {pack['pinterest']['title']}",
        "",
        pack["pinterest"]["description"],
        "",
    ]
    return "\n".join(out)


# ------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write the distribution pack for one piece of work.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-shoot", metavar="STEM",
                        help="a sheet stem in bot/shoots/, e.g. 2026-09-17-lift-test")
    source.add_argument("--from-article", metavar="HANDLE",
                        help="a published Diaries article handle")
    parser.add_argument("--language", default="hinglish",
                        choices=("hinglish", "gujarati", "english"),
                        help="the language for WhatsApp (default hinglish)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()

    shop = shop_from_env()
    products = shop.catalogue()
    banned = forbidden_phrases(products)

    if args.from_shoot:
        stem, kind, src = from_shoot(args.from_shoot)
        link = f"{STORE}/blogs/diaries"
    else:
        stem, kind, src = from_article(shop, args.from_article)
        link = f"{STORE}/blogs/diaries/{args.from_article}"
    print(f"→ {kind}: {stem}", flush=True)
    print(f"→ {len(products)} products in the catalogue", flush=True)

    today = date.today()
    pack = run_rounds(
        anthropic.Anthropic(),
        cached_system("social-style.md", products),
        brief_block(src, kind, args.language, link, today),
        PACK_SCHEMA,
        lambda candidate: check(candidate, products, banned, src["handles"]),
        args.max_rounds,
    )
    if pack is None:
        print(f"\n✗ Could not get a clean pack in {args.max_rounds} rounds. "
              "Nothing was written.", file=sys.stderr)
        return 1

    markdown = to_markdown(pack, stem, kind, link, products, today)

    if args.dry_run:
        print("\n--- DRY RUN, nothing written -----------------------------\n")
        print(markdown)
        return 0

    SOCIAL_DIR.mkdir(exist_ok=True)
    name = f"{today.isoformat()}-{stem}"
    (SOCIAL_DIR / f"{name}.md").write_text(markdown, encoding="utf-8")
    (SOCIAL_DIR / f"{name}.json").write_text(
        json.dumps({"source": stem, "kind": kind, "link": link,
                    "written": today.isoformat(), **pack},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    posts = len(pack["schedule"])
    print(f"\n✓ Pack written: bot/social/{name}.md")
    print(f"  {posts} posts across "
          f"{max(e['day'] for e in pack['schedule'])} days")

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
