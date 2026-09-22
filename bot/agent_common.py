"""What both agents share: the Claude call, the catalogue, the store.

Track 2 (`write_draft.py`) writes blog entries. Track 3 (`write_shoot.py`)
writes shoot sheets. They ask Claude for very different things, but they read
the same catalogue, ban the same names and handle the same failures, so that
part lives here once.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import anthropic

from synor_shopify import Shop

HERE = Path(__file__).resolve().parent

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
# One entry or one shoot sheet is ~1,000 words, so a single non-streaming
# call finishes well inside the SDK's 10-minute default timeout.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# The closed sets the storefront navigates by. Nothing outside them is filed.
GENDERS = ("her", "him", "unisex")
OCCASIONS = ("daily", "office", "date", "party", "festive", "gym")
FAMILIES = ("fresh-aquatic", "woody-oud", "floral-fruity", "amber-sweet")


def shop_from_env() -> Shop:
    return Shop(
        os.environ.get("SHOPIFY_STORE", ""),
        os.environ.get("SHOPIFY_ADMIN_TOKEN", ""),
        os.environ.get("SHOPIFY_API_VERSION") or "2026-07",
    )


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def catalogue_block(products: list[dict[str, Any]]) -> str:
    """The catalogue as the writer sees it: name, handle, and only the tags it
    is allowed to reason from. Designer and celebrity tags are stripped here,
    so those names never enter the context in the first place."""
    keep = ("family-", "gender-", "occasion-", "mood-", "scent-", "season-",
            "longevity-", "band-", "tier-")
    lines = []
    for product in products:
        if "synor" not in product["handle"]:
            continue  # gift sets and bundles are not written about as scents
        tags = sorted(t for t in (product.get("tags") or []) if t.startswith(keep))
        if not any(t.startswith("family-") for t in tags):
            continue
        lines.append(f"- {product['title']} | {product['handle']} | {', '.join(tags)}")
    return "\n".join(lines)


def cached_system(style_file: str, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The style contract and the catalogue are identical on every run, so
    they go in a cached prefix; only the brief changes between calls."""
    return [
        {"type": "text",
         "text": (HERE / style_file).read_text(encoding="utf-8")},
        {"type": "text",
         "text": "# The catalogue\n\nName | handle | tags\n\n"
                 + catalogue_block(products),
         "cache_control": {"type": "ephemeral"}},
    ]


def call_claude(
    client: anthropic.Anthropic,
    system: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
) -> Any:
    kwargs: dict[str, Any] = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": schema},
        },
    )
    if os.environ.get("SYNOR_FALLBACKS", "").lower() != "off":
        # On a policy decline the API re-runs the same request on a fallback
        # model inside the same call, instead of the run simply failing.
        kwargs["betas"] = [FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return client.beta.messages.create(**kwargs)


def response_json(response: Any) -> dict[str, Any]:
    import json

    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise RuntimeError(
            "Claude declined this brief"
            + (f" ({detail.category}: {detail.explanation})" if detail else "")
            + ". Rewrite the brief in the queue."
        )
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "The answer was cut off by max_tokens. Shorten the brief or raise "
            "MAX_TOKENS in bot/agent_common.py."
        )
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError("Claude returned no text block")
    return json.loads(text)


def run_rounds(
    client: anthropic.Anthropic,
    system: list[dict[str, Any]],
    first_message: str,
    schema: dict[str, Any],
    checker,
    max_rounds: int,
) -> dict[str, Any] | None:
    """Ask, check, send the failures back, ask again.

    Every check failure is phrased for the writer, not for an operator, so it
    can go straight back as a rewrite instruction.
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": first_message}]
    import json

    for round_no in range(1, max_rounds + 1):
        candidate = response_json(call_claude(client, system, messages, schema))
        problems = checker(candidate)
        if not problems:
            print(f"→ passed the checks on round {round_no}", flush=True)
            return candidate
        print(f"→ round {round_no}: {len(problems)} problem(s) sent back", flush=True)
        for problem in problems:
            print(f"   · {problem}", flush=True)
        messages.append({"role": "assistant",
                         "content": json.dumps(candidate, ensure_ascii=False)})
        messages.append({
            "role": "user",
            "content": "This was checked and these need fixing:\n\n"
                       + "\n".join(f"{i}. {p}" for i, p in enumerate(problems, 1))
                       + "\n\nReturn the whole thing again, corrected. Keep "
                         "everything that was not flagged.",
        })
    return None


# The phrasings that mark writing as machine-made. A reader clocks these
# instantly, and once they have, nothing else in the entry matters.
MACHINE_TICS = (
    r"\bnot just\b.{0,40}\bbut\b", r"\bisn'?t just\b", r"\bis not just\b",
    r"\bmore than just\b", r"\bit'?s not about\b.{0,40}\bit'?s about\b",
    r"\bat the end of the day\b", r"\bthe truth is\b", r"\bhere'?s the thing\b",
    r"\bthat'?s the thing\b", r"\bthe reality is\b", r"\bin today'?s world\b",
    r"\bwhen it comes to\b", r"\blet'?s be honest\b", r"\bthe bottom line\b",
    r"\bdelve\b", r"\ba testament to\b", r"\bin conclusion\b",
    r"\bultimately,", r"\bthat said,", r"\bthat being said\b",
)


def prose_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def human_check(html: str, label: str, contractions_required: int) -> list[str]:
    """Measure the evenness that gives machine writing away.

    Every one of these is a *rhythm* fault, not a vocabulary one. Writing
    reads generated when its paragraphs are all the same size, its sentences
    all the same length, and every one of them lands neatly — which is
    exactly what an unprompted model produces, so it has to be measured
    rather than asked for.
    """
    import statistics

    problems: list[str] = []
    text = prose_of(html)
    words = len(text.split())
    if words < 50:
        return problems

    paragraphs = [prose_of(p) for p in re.findall(r"<p>(.*?)</p>", html, re.S)]
    lengths = [len(p.split()) for p in paragraphs if p]
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]

    if len(lengths) > 2:
        spread = statistics.stdev(lengths) / statistics.mean(lengths)
        if spread < 0.40:
            problems.append(
                f"The {label} paragraphs are all about the same length "
                f"({min(lengths)}–{max(lengths)} words, variation {spread:.2f}). "
                "Break the rhythm: one paragraph of two lines, one of eight, "
                "one that is a single sentence."
            )
        if min(lengths) > 22:
            problems.append(
                f"The shortest {label} paragraph is {min(lengths)} words. At "
                "least one should be very short — a line or two, on its own."
            )

    short = sum(1 for x in sentences if len(x.split()) <= 5)
    if short < max(4, len(sentences) // 12):
        problems.append(
            f"The {label} has {short} short sentences out of {len(sentences)}. "
            "Real writing punches: a four-word sentence after two long ones."
        )

    dashes = html.count("—")
    if dashes > max(4, words // 250):
        problems.append(
            f"The {label} uses {dashes} em-dashes in {words} words. Three or "
            "four in a whole entry. Full stops and commas do the same work "
            "without the tic."
        )

    if contractions_required:
        found = len(re.findall(r"\b\w+'(s|t|re|ve|ll|d|m)\b", text))
        if found < contractions_required:
            problems.append(
                f"The {label} has {found} contractions. Write it's, doesn't, "
                "wasn't, there's. A whole entry of 'it is' and 'do not' reads "
                "like a company notice, and it is the clearest tell there is."
            )

    tics = sorted({
        re.sub(r"\\b|\.\{0,40\}|\?|\\", "", t)
        for t in MACHINE_TICS if re.search(t, text, re.I)
    })
    if tics:
        problems.append(
            f"The {label} uses machine phrasing: {', '.join(tics)}. Cut it."
        )

    tricolons = len(re.findall(r"\w+, \w[\w ]{0,20}, and \w", text))
    if tricolons > 2:
        problems.append(
            f"The {label} has {tricolons} three-part lists. A machine reaches "
            "for that shape constantly. Keep one or two."
        )
    return problems


def name_hits(text: str, banned: list[str]) -> list[str]:
    return sorted({
        phrase for phrase in banned
        if re.search(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", text, re.I)
    })
