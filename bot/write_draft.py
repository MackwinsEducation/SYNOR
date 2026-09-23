#!/usr/bin/env python3
"""Write one SYNOR Diaries entry and file it as a draft.

The agent never publishes. It creates the article with `isPublished: false`
and prints the admin link, so the whole approval step is one tap by a human
who can see the finished page first.

    python bot/write_draft.py                  # first 'todo' topic in the queue
    python bot/write_draft.py --topic gym-bag-heat
    python bot/write_draft.py --dry-run        # write it, print it, file nothing

Environment:
    ANTHROPIC_API_KEY     required
    SHOPIFY_STORE         perfume-rat  (or perfume-rat.myshopify.com)
    SHOPIFY_ADMIN_TOKEN   custom app token with write_content + read_products
    SHOPIFY_API_VERSION   optional, defaults to 2026-07
    SYNOR_BLOG_HANDLE     optional, defaults to 'diaries'
    SYNOR_FALLBACKS       optional, 'off' disables the server-side fallback
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from typing import Any

import anthropic

from agent_common import (
    FAMILIES, GENDERS, HERE, OCCASIONS, cached_system, human_check, name_hits,
    run_rounds, shop_from_env, strip_tags,
)
from synor_shopify import ShopifyError, forbidden_phrases

KINDS = ("blog", "vlog", "review", "letter", "series")

# The theme reads these from the `custom` namespace. `field_*` fills the boxed
# field log, `notes_*` fills the notes strip, `entry_no` is the folio number.
TEXT_METAFIELDS = (
    "field_place", "field_alt", "field_temp", "field_humidity",
    "field_held", "field_asked", "field_verdict",
    "notes_top", "notes_heart", "notes_base",
    "youtube_ids", "title_hinglish",
)

# The two long ones. Stored as multi_line so the HTML body survives intact;
# the article page reads body_hinglish and shows the language switch when it
# is there, so an entry without them simply reads in English.
LONG_METAFIELDS = ("summary_hinglish", "body_hinglish")

ALLOWED_HTML_TAGS = {
    "p", "h2", "h3", "blockquote", "ul", "ol", "li", "strong", "em", "a", "br",
}

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "handle": {"type": "string"},
        "summary_html": {"type": "string"},
        "body_html": {"type": "string"},
        "kind": {"type": "string", "enum": list(KINDS)},
        "series_slug": {"type": "string"},
        "gender": {
            "type": "array",
            "items": {"type": "string", "enum": list(GENDERS)},
        },
        "occasion": {
            "type": "array",
            "items": {"type": "string", "enum": list(OCCASIONS)},
        },
        "family": {
            "type": "array",
            "items": {"type": "string", "enum": list(FAMILIES)},
        },
        "product_handles": {"type": "array", "items": {"type": "string"}},
        "field_place": {"type": "string"},
        "field_alt": {"type": "string"},
        "field_temp": {"type": "string"},
        "field_humidity": {"type": "string"},
        "field_held": {"type": "string"},
        "field_asked": {"type": "string"},
        "field_verdict": {"type": "string"},
        "notes_top": {"type": "string"},
        "notes_heart": {"type": "string"},
        "notes_base": {"type": "string"},
        "youtube_ids": {"type": "string"},
        "shot_briefs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "after": {"type": "string"},
                    "prompt": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["after", "prompt", "caption"],
                "additionalProperties": False,
            },
        },
        "title_hinglish": {"type": "string"},
        "summary_hinglish": {"type": "string"},
        "body_hinglish": {"type": "string"},
    },
    "required": [
        "title", "handle", "summary_html", "body_html", "kind", "series_slug",
        "gender", "occasion", "family", "product_handles",
        "field_place", "field_alt", "field_temp", "field_humidity",
        "field_held", "field_asked", "field_verdict",
        "notes_top", "notes_heart", "notes_base", "youtube_ids",
        "title_hinglish", "summary_hinglish", "body_hinglish", "shot_briefs",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- queue

def load_queue(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_queue(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pick_topic(queue: dict[str, Any], wanted: str | None) -> dict[str, Any]:
    topics = queue.get("topics") or []
    if wanted:
        for topic in topics:
            if topic.get("id") == wanted:
                return topic
        raise SystemExit(f"No topic with id {wanted!r} in the queue")
    for topic in topics:
        if topic.get("status") == "todo":
            return topic
    raise SystemExit(
        "Nothing left to write — every topic in bot/queue.json is done. "
        "Add one and run again."
    )


# ------------------------------------------------------------- prompting

def brief_block(topic: dict[str, Any], today: date) -> str:
    parts = [
        "# The brief for this entry",
        "",
        f"Today is {today.isoformat()}.",
        f"Entry kind: {topic.get('kind', 'blog')}",
        f"Where it was reported from: {topic.get('place', 'Ahmedabad')}",
        f"Month it happened in: {topic.get('month', today.strftime('%B'))}",
    ]
    if topic.get("angle"):
        parts.append(f"Territory it should cover: {topic['angle']}")
    parts += ["", "What the entry is:", "", topic.get("brief", "").strip()]
    parts += [
        "",
        "Write it now. Choose the products yourself from the catalogue above — "
        "only ones whose tags genuinely fit — and keep every rule in the house "
        "style, especially the ones about names and prices.",
    ]
    return "\n".join(parts)


# ------------------------------------------------------------ validation

def check(post: dict[str, Any], products: list[dict[str, Any]], banned: list[str],
          used_handles: set[str]) -> list[str]:
    """Everything a human would check before publishing, done cheaply.

    Anything this returns goes back to Claude as a rewrite instruction, so the
    messages are written to be read by the writer, not by an operator.
    """
    problems: list[str] = []
    by_handle = {p["handle"]: p for p in products}
    prose = " ".join([post["title"], strip_tags(post["summary_html"]),
                      strip_tags(post["body_html"])])

    # 1. No other house's name, no celebrity.
    hits = name_hits(prose, banned)
    if hits:
        problems.append(
            "These names appear in the text and must not: "
            + ", ".join(hits)
            + ". Remove every one of them and describe the scent itself instead."
        )

    # 2. Only real products, and enough of them.
    unknown = [h for h in post["product_handles"] if h not in by_handle]
    if unknown:
        problems.append(
            "These product handles are not in the catalogue: "
            + ", ".join(unknown)
            + ". Use only handles exactly as printed in the catalogue."
        )
    real = [h for h in post["product_handles"] if h in by_handle]
    if not 3 <= len(real) <= 6:
        problems.append(
            f"The entry recommends {len(real)} products; it needs between 3 and 6."
        )
    for handle in real:
        if by_handle[handle]["title"].lower() not in prose.lower():
            problems.append(
                f"{by_handle[handle]['title']} is filed as a pick but is never "
                "named in the text. Write about it or drop it."
            )

    # 3. Families must match the products actually recommended.
    product_families = {
        tag[len("family-"):]
        for handle in real
        for tag in by_handle[handle]["tags"] if tag.startswith("family-")
    }
    stray = [f for f in post["family"] if f not in product_families]
    if stray:
        problems.append(
            "These families are filed but no recommended product carries them: "
            + ", ".join(stray) + "."
        )
    if not post["family"]:
        problems.append("The entry has no fragrance family filed.")
    if not post["gender"]:
        problems.append("The entry has no gender filed.")

    # 4. Body shape.
    body = post["body_html"].strip()
    if not body.startswith("<p"):
        problems.append(
            "The body must open with a <p>, because the theme puts a drop cap "
            "on the first letter of the first paragraph."
        )
    words = len(strip_tags(body).split())
    if words < 600:
        problems.append(f"The body is {words} words; it needs at least 700.")
    if words > 1400:
        problems.append(f"The body is {words} words; keep it under 1100.")
    found_tags = {t.lower() for t in re.findall(r"<\s*([a-zA-Z0-9]+)", body)}
    bad_tags = sorted(found_tags - ALLOWED_HTML_TAGS)
    if bad_tags:
        problems.append(
            "These HTML tags are not allowed in the body: "
            + ", ".join(bad_tags) + "."
        )
    if "<blockquote" not in body:
        problems.append("The entry has no pull quote. Add one <blockquote>.")
    if "!" in strip_tags(post["title"]) or "!" in strip_tags(body):
        problems.append("Remove the exclamation marks.")

    # Does it read like a person wrote it, or like it was generated? Measured
    # rather than asked for, because an unprompted model writes evenly and
    # cannot hear that it is doing it.
    problems += human_check(body, "body", contractions_required=8)

    # 5. Summary length.
    summary_words = len(strip_tags(post["summary_html"]).split())
    if not 15 <= summary_words <= 45:
        problems.append(
            f"The summary is {summary_words} words; it should be 20 to 35."
        )

    # 6. Field log must be filled — the box is the spine of a dispatch.
    empty = [k for k in ("field_place", "field_temp", "field_humidity",
                         "field_held", "field_asked", "field_verdict")
             if not str(post.get(k, "")).strip()]
    if empty:
        problems.append("The field log is missing: " + ", ".join(empty) + ".")

    # 7. The Hinglish telling, checked as hard as the English one.
    hi_body = post["body_hinglish"].strip()
    if not hi_body:
        problems.append(
            "The entry has no Hinglish body. Every entry is written twice — "
            "English and Hinglish — because the page carries a switch."
        )
    else:
        hi_prose = " ".join([post["title_hinglish"],
                             strip_tags(post["summary_hinglish"]),
                             strip_tags(hi_body)])
        hi_hits = name_hits(hi_prose, banned)
        if hi_hits:
            problems.append(
                "These names appear in the Hinglish text and must not: "
                + ", ".join(hi_hits) + "."
            )
        if not hi_body.startswith("<p"):
            problems.append("The Hinglish body must also open with a <p>.")
        hi_words = len(strip_tags(hi_body).split())
        if hi_words < 600:
            problems.append(
                f"The Hinglish body is {hi_words} words against the English "
                f"{words}. It is the same report told again, not a summary."
            )
        hi_tags = {t.lower() for t in re.findall(r"<\s*([a-zA-Z0-9]+)", hi_body)}
        hi_bad = sorted(hi_tags - ALLOWED_HTML_TAGS)
        if hi_bad:
            problems.append(
                "These HTML tags are not allowed in the Hinglish body: "
                + ", ".join(hi_bad) + "."
            )
        if "<blockquote" not in hi_body:
            problems.append("The Hinglish body has no pull quote.")
        if hi_body.count("<h2") != body.count("<h2"):
            problems.append(
                f"The English body has {body.count('<h2')} sections and the "
                f"Hinglish one has {hi_body.count('<h2')}. The switch swaps "
                "one body for the other, so they have to match."
            )
        if not post["title_hinglish"].strip():
            problems.append("The Hinglish headline is missing.")
        # Contractions work differently in Hinglish, so only the rhythm
        # faults are measured there.
        problems += human_check(hi_body, "Hinglish body", contractions_required=0)

    # 8. The shot briefs — the pictures the entry is asking for.
    briefs = post["shot_briefs"]
    heads = [h.strip() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S)]
    heads = [strip_tags(h).strip() for h in heads]
    if not 3 <= len(briefs) <= 7:
        problems.append(
            f"There are {len(briefs)} shot briefs; an entry wants 4 to 6 — "
            "one for the top and one under each section."
        )
    for i, brief in enumerate(briefs, 1):
        words = len(brief["prompt"].split())
        if not 18 <= words <= 60:
            problems.append(
                f"Shot brief {i} is {words} words. Between 25 and 45: what is "
                "in frame, the light, the time of day, what is happening."
            )
        low = brief["prompt"].lower()
        for banned_word in ("bottle", "perfume bottle", "flacon", "label",
                            "packaging", "box of", "vial", "atomiser"):
            if banned_word in low:
                problems.append(
                    f"Shot brief {i} asks for a {banned_word}. The shop's own "
                    "photographs show every bottle already, and a drawn label "
                    "comes out as nonsense. Brief the place, not the product."
                )
                break
        for face_word in ("face", "portrait", "smiling", "looking at camera",
                          "his eyes", "her eyes", "expression"):
            if face_word in low:
                problems.append(
                    f"Shot brief {i} asks for a face. Hands, backs, shoulders "
                    "and distant figures only — a drawn face reads as a claim "
                    "about somebody who was really there."
                )
                break
        cap = len(brief["caption"].split())
        if not 3 <= cap <= 12:
            problems.append(
                f"Shot brief {i} has a {cap}-word caption; four to nine, in "
                "the paper's voice."
            )
        target = brief["after"].strip()
        if target and target not in heads:
            problems.append(
                f"Shot brief {i} sits after {target!r}, which is not one of "
                "this entry's headings. It has to match word for word, or the "
                "picture has nowhere to go. The headings are: "
                + "; ".join(heads) + "."
            )
    if briefs and not any(not b["after"].strip() for b in briefs):
        problems.append(
            "No shot brief is marked for the top of the piece. Leave one with "
            "an empty \"after\"."
        )
    hits = name_hits(" ".join(b["prompt"] for b in briefs), banned)
    if hits:
        problems.append(
            "These names appear in the shot briefs: " + ", ".join(hits) + "."
        )

    # 9. Handle must be new and URL-safe.
    handle = post["handle"].strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", handle):
        problems.append(
            f"The handle {post['handle']!r} must be lower-case words joined by "
            "hyphens, nothing else."
        )
    elif handle in used_handles:
        problems.append(
            f"The handle {handle!r} is already used on the blog. Choose another."
        )

    # 10. Series needs both tags, which means it needs a slug.
    if post["kind"] == "series" and not post["series_slug"].strip():
        problems.append(
            "A series entry needs a series_slug, e.g. 'matheran', because the "
            "theme files it under both `series` and `series-<slug>`."
        )
    return problems


def build_tags(post: dict[str, Any]) -> list[str]:
    tags = [post["kind"]]
    if post["kind"] == "series":
        slug = post["series_slug"].strip().lower()
        tags.append(f"series-{slug}")  # `series` itself is already the kind tag
    tags += [f"gender-{g}" for g in post["gender"]]
    tags += [f"occasion-{o}" for o in post["occasion"]]
    tags += [f"family-{f}" for f in post["family"]]
    tags += [f"pick-{h}" for h in post["product_handles"]]
    seen: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return seen


def build_metafields(post: dict[str, Any], entry_no: int) -> list[dict[str, str]]:
    out = [{
        "namespace": "custom",
        "key": "entry_no",
        "value": str(entry_no),
        "type": "number_integer",  # the definition in the admin is an integer
    }]
    for key in TEXT_METAFIELDS:
        value = str(post.get(key, "")).strip()
        if not value:
            continue
        out.append({
            "namespace": "custom",
            "key": key,
            "value": value,
            "type": "single_line_text_field",
        })
    if post.get("shot_briefs"):
        out.append({
            "namespace": "custom",
            "key": "shot_briefs",
            "value": json.dumps(post["shot_briefs"], ensure_ascii=False),
            "type": "multi_line_text_field",
        })
    for key in LONG_METAFIELDS:
        value = str(post.get(key, "")).strip()
        if not value:
            continue
        out.append({
            "namespace": "custom",
            "key": key,
            "value": value,
            "type": "multi_line_text_field",
        })
    return out


# ------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(description="Draft one SYNOR Diaries entry.")
    parser.add_argument("--topic", help="topic id from bot/queue.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="write the entry and print it; file nothing")
    parser.add_argument("--max-rounds", type=int, default=3,
                        help="how many times to send the checks back for a rewrite")
    args = parser.parse_args()

    queue_path = HERE / "queue.json"
    queue = load_queue(queue_path)
    topic = pick_topic(queue, args.topic)
    print(f"→ topic: {topic['id']}", flush=True)

    shop = shop_from_env()
    blog_handle = os.environ.get("SYNOR_BLOG_HANDLE") or "diaries"
    blog_gid = shop.blog_id(blog_handle)
    products = shop.catalogue()
    used_handles = shop.article_handles(blog_handle)
    banned = forbidden_phrases(products)
    print(f"→ {len(products)} products, {len(used_handles)} entries already filed",
          flush=True)

    post = run_rounds(
        anthropic.Anthropic(),
        cached_system("house-style.md", products),
        brief_block(topic, date.today()),
        POST_SCHEMA,
        lambda candidate: check(candidate, products, banned, used_handles),
        args.max_rounds,
    )
    if post is None:
        print(f"\n✗ Could not get a clean entry in {args.max_rounds} rounds. "
              "Nothing was filed.", file=sys.stderr)
        return 1

    tags = build_tags(post)
    entry_no = len(used_handles) + 1
    metafields = build_metafields(post, entry_no)

    if args.dry_run:
        print("\n--- DRY RUN, nothing filed -------------------------------")
        print(f"title    : {post['title']}")
        print(f"handle   : {post['handle']}")
        print(f"summary  : {strip_tags(post['summary_html']).strip()}")
        print(f"tags     : {', '.join(tags)}")
        print(f"field log: {post['field_place']} · {post['field_temp']} · "
              f"{post['field_humidity']} · held {post['field_held']} · "
              f"{post['field_asked']} asked · {post['field_verdict']}")
        print(f"words    : {len(strip_tags(post['body_html']).split())}")
        print("\n" + post["body_html"])
        return 0

    article = shop.create_draft_article(
        blog_id=blog_gid,
        title=post["title"],
        handle=post["handle"].strip().lower(),
        summary_html=post["summary_html"],
        body_html=post["body_html"],
        tags=tags,
        metafields=metafields,
    )
    link = shop.admin_url(article["id"], blog_gid)

    topic["status"] = "drafted"
    topic["article_id"] = article["id"]
    topic["drafted_on"] = date.today().isoformat()
    save_queue(queue_path, queue)

    print(f"\n✓ Draft filed, not published: {post['title']}")
    print(f"  {link}")
    print("  Open it, read it, and press Publish if it is right.")

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(
                f"### New Diaries draft\n\n"
                f"**{post['title']}**\n\n"
                f"{strip_tags(post['summary_html']).strip()}\n\n"
                f"Filed as a **draft**. Tags: `{'`, `'.join(tags)}`\n\n"
                f"[Open it in Shopify and publish]({link})\n"
            )
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
