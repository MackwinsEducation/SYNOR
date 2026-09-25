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
import re
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
           "talking-head", "unboxing", "question-answer", "shop-visit",
           "counter-swap", "blind-guess", "one-question-nine",
           "wear-test-return", "complaint-desk")
# Formats where one product is a complete video; the rest need a comparison.
SINGLE_OK = ("talking-head", "unboxing", "question-answer", "complaint-desk")
# Lines that turn the shoot into a contest. Every one of these makes the other
# person the examinee and the camera the examiner, which buys a guarded answer
# — and a guarded answer is the one thing the format cannot use. Kept as a
# list rather than left to judgement because the phrasing arrives naturally
# while writing a hook and reads fine until somebody says it out loud.
CHALLENGE_TELLS = (
    "mera sunghega", "meri sunghega", "mera sungh ke",
    "dekhte hain kya bolta", "dekhte hain kya kehta", "dekhte hai kya bolta",
    "pata chal jayega usko", "unko pata chalega", "usko pata chalega",
    "challenge", "muqabla", "hara ke", "haraake", "haraana",
    "jhoot pakad", "expose kar",
)
# Too familiar for somebody standing behind his own counter.
TOO_FAMILIAR = (" tu ", " tu.", " tu,", "tera ", "tere ", "tujhe ", "tujhko ")

# Formats that put somebody who does not work here on camera. These carry the
# most weight with a viewer and are the only ones that can do real damage, so
# they need consent asked on camera, questions instead of lines, and a spoken
# disclosure of anything that changed hands.
WITH_PEOPLE = ("street-test", "shop-visit", "counter-swap", "blind-guess",
               "one-question-nine", "wear-test-return")

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
        "people": {
            "type": "object",
            "properties": {
                "who": _STR,
                # Why this person and not a passer-by. Said out loud, not
                # only written down — it is the line that turns the shoot
                # from a test into a favour being asked.
                "why_them": _STR,
                "consent": _STR,
                "disclosure": _STR,
                "questions": {"type": "array", "items": _STR},
                "listen_for": {"type": "array", "items": _STR},
                # Nobody knows what they will say, so both endings are
                # written before anyone walks in. The cold one is the video
                # worth more, and it is the one that never gets written
                # unless a sheet demands it in advance.
                "closing_if_warm": _STR,
                "closing_if_cold": _STR,
            },
            "required": ["who", "why_them", "consent", "disclosure",
                         "questions", "listen_for", "closing_if_warm",
                         "closing_if_cold"],
            "additionalProperties": False,
        },
        # The shot list is the edit. This is the performance: everything said
        # from walking in to walking out, most of which is cut. Without it the
        # person filming has twelve disconnected sentences and no idea how to
        # get somebody talking between them.
        "script": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene": _STR,
                    "camera": _STR,
                    "lines": {"type": "array", "items": _STR},
                    "their_turn": _STR,
                    "note": _STR,
                },
                "required": ["scene", "camera", "lines", "their_turn", "note"],
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
        "idea", "concept", "hook", "shots", "script", "people",
        "honest_negative", "b_roll",
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


def already_done() -> list[dict[str, str]]:
    """What has been planned before, so the day's idea is not yesterday's.

    Read off the sidecars rather than the queue, because the queue only knows
    about shoots somebody typed in, and an invented one never goes there.
    """
    done: list[dict[str, str]] = []
    if not SHOOTS_DIR.exists():
        return done
    for path in sorted(SHOOTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        done.append({
            "planned": str(data.get("planned", "")),
            "format": str((data.get("concept") or {}).get("format", "")),
            "title": str((data.get("idea") or {}).get("title", "")),
            "one_line": str((data.get("idea") or {}).get("one_line", "")),
        })
    return done


def invent(defaults: dict[str, Any], today: date,
           fmt: str | None) -> tuple[dict[str, Any], str]:
    """A shoot for today that nobody typed into the queue.

    Daily is the point of this: a hand-written queue is a few weeks of ideas
    and then an empty afternoon. So the format rotates on the date, the last
    thirty sheets are handed over as a do-not-repeat list, and the brief asks
    for the idea itself rather than supplying one.
    """
    recent = already_done()[-30:]
    if not fmt:
        # Rotate rather than choose at random: a random pick repeats a format
        # two days running often enough to be noticed, and the person filming
        # is the one who pays for that.
        fmt = FORMATS[(today.toordinal()) % len(FORMATS)]
        used_lately = [r["format"] for r in recent[-3:]]
        step = 0
        while fmt in used_lately and step < len(FORMATS):
            step += 1
            fmt = FORMATS[(today.toordinal() + step) % len(FORMATS)]

    shoot = {
        "id": f"daily-{today.isoformat()}",
        "status": "todo",
        "format": fmt,
        "seconds": 45,
        "where": defaults.get("city") or "Ahmedabad",
        "brief": "",
        "invented": True,
    }
    lines = [
        "",
        "## Today you are choosing the idea as well",
        "",
        "Nobody has written a brief for this one. Invent it, and hold it to "
        "the same bar as everything else here: one person, one phone, one "
        "hour, no money spent, and a reason for a stranger to stop scrolling "
        "that is not the bottle.",
        "",
        "Two tests before you commit to an idea. **Could this be filmed "
        "tomorrow, in this city, by somebody with no crew and no permission "
        "from anybody?** And **is there anything in it a viewer could check "
        "for themselves?** An idea that fails the first is a fantasy; one "
        "that fails the second is an advert.",
    ]
    if recent:
        lines += [
            "",
            "These have already been made. Do not repeat the idea, and do not "
            "repeat the shape of it with different scents:",
            "",
        ]
        lines += [
            f"- {r['planned']} · {r['format']} · {r['title']} — {r['one_line']}"
            for r in recent
        ]
    return shoot, "\n".join(lines)


def brief_block(shoot: dict[str, Any], defaults: dict[str, Any], today: date,
                extra: str = "") -> str:
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
    if extra:
        lines.append(extra)
    return "\n".join(lines)


# ------------------------------------------------------------ validation

def flat(text: str) -> str:
    """Lower case, no punctuation, single spaces — for comparing two lines.

    A line written in the shot list and the same line written in the script
    will differ by a comma or a dash often enough that a literal comparison
    would reject correct sheets and teach the next reader to ignore the check.
    """
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


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
    """Every string a viewer could ever see or hear, in one blob.

    The script belongs in here even though most of it is cut, and so do the
    lines in the people block. They are the largest body of spoken words in
    the sheet: the shot list is what survives an edit, but every one of these
    is said out loud in a room with a camera running, and a rival house's
    name said on the day is a name that can end up in the video.
    """
    people = sheet.get("people") or {}
    parts = [
        sheet["idea"]["title"], sheet["idea"]["one_line"],
        sheet["honest_negative"], sheet["caption"],
        sheet["youtube_title"], sheet["youtube_description"],
        sheet["thumbnail"], sheet["concept"]["shoot_notes"],
        " ".join(sheet["hashtags"]), " ".join(sheet["b_roll"]),
        in_the_video(sheet),
        people.get("why_them", ""), people.get("consent", ""),
        people.get("disclosure", ""),
        people.get("closing_if_warm", ""), people.get("closing_if_cold", ""),
        " ".join(people.get("questions") or []),
    ]
    for scene in sheet.get("script") or []:
        parts += [scene.get("scene", ""), scene.get("their_turn", ""),
                  scene.get("note", "")]
        parts += scene.get("lines") or []
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

    # 6b. Somebody else in the frame. These are the shoots that carry the
    # most weight with a viewer, and the only ones that can do real damage.
    people = sheet["people"]
    if fmt in WITH_PEOPLE:
        if not people["who"].strip():
            problems.append(
                f"A {fmt} puts somebody else on camera, so the sheet has to "
                "say who they are."
            )
        consent = people["consent"].strip()
        if len(consent.split()) < 8:
            problems.append(
                "The consent line is missing or too short. It is the first "
                "thing recorded, and it says who you are, what the video is "
                "for, where it goes, and asks if that is alright."
            )
        elif not ("?" in consent or any(
                w in consent.lower() for w in
                ("thik hai", "theek hai", "chalega", "ok hai", "permission",
                 "alright", "is that ok", "koi problem"))):
            problems.append(
                "The consent line never actually asks. It has to be a "
                "question they can say no to."
            )
        if not 3 <= len(people["questions"]) <= 6:
            problems.append(
                f"There are {len(people['questions'])} questions; a {fmt} "
                "needs 3 to 6. Their answers are the video, so the questions "
                "are the part that has to be right."
            )
        # A question that cannot be answered badly is not a question — it is
        # a line being put in somebody's mouth with a question mark on it.
        for q in people["questions"]:
            ql = q.lower().strip().rstrip("?").strip()
            for leading in ("hai na", "na", "right", "isn't it", "correct",
                            "sahi hai", "accha hai", "achha hai", "theek hai"):
                if ql.endswith(" " + leading):
                    problems.append(
                        f"The question {q!r} supplies its own answer. Ask it "
                        "so that a disappointing answer is a possible one."
                    )
                    break
        if not 4 <= len(people["listen_for"]) <= 8:
            problems.append(
                f"There are {len(people['listen_for'])} listen-for notes; it "
                "needs 4 to 8. These are what the edit keeps — the kinds of "
                "answer worth having, never words for anybody to say."
            )
        # Anything handed over has to be said out loud, in the video.
        gave = any(
            w in in_cut for w in
            ("tester de", "testers de", "dete hain", "de raha hoon", "gave",
             "giving", "chhod", "hand over", "handing", "de aaya", "de diya")
        )
        disclosure = people["disclosure"].strip()
        if gave and not disclosure:
            problems.append(
                "Something changes hands in this shoot and nothing discloses "
                "it. One spoken line says what was given. The code requires "
                "it, and a viewer who works it out later costs far more than "
                "the line does."
            )
        if disclosure and disclosure.lower() not in in_cut:
            problems.append(
                "The disclosure is written at the top of the sheet but is in "
                "no shot. It only counts if it is said in the video, word for "
                "word."
            )
    elif people["who"].strip():
        problems.append(
            f"A {fmt} has nobody else in the frame, but the sheet names "
            f"{people['who']!r}. Either change the format or drop the person."
        )

    # 6b2. The performance script. The shot list is what survives the edit;
    # this is what is actually said in the room, and a sheet without it hands
    # somebody twelve disconnected sentences and no way to get a stranger
    # talking between them.
    script = sheet["script"]
    if not 5 <= len(script) <= 12:
        problems.append(
            f"The script has {len(script)} scenes; it needs 5 to 12 — walking "
            "in, the asking, the scents, the real question, whatever changes "
            "hands, and walking out."
        )
    for i, scene in enumerate(script, 1):
        if not scene["lines"]:
            problems.append(
                f"Scene {i} ({scene['scene']!r}) has no lines. A scene with "
                "nothing said in it is not a scene."
            )
    # The cut has to be a subset of what was performed, or the two halves of
    # the sheet are describing different afternoons.
    said = flat(" ".join(l for s in script for l in s["lines"]))
    for label, line in ([("the hook", sheet["hook"]["spoken"])]
                        + [(f"shot {s['n']}", s["spoken"]) for s in shots]):
        bare = flat(line)
        if bare and bare not in said:
            problems.append(
                f"The line in {label} — {line!r} — is nowhere in the script. "
                "Every line in the cut has to be a line somebody actually "
                "says, so put it in the scene where it is said."
            )

    if fmt in WITH_PEOPLE:
        # Why this person, said out loud. Without it the shoot has no idea in
        # it beyond "somebody was standing there".
        why = people["why_them"].strip()
        if len(why.split()) < 8:
            problems.append(
                "people.why_them is missing or too short. Say why this person "
                "and not a passer-by — it is what turns the shoot from a test "
                "into a favour being asked, and it is the difference between "
                "a guarded answer and a real one."
            )
        elif flat(why) not in said:
            problems.append(
                "people.why_them is written in the sheet but never said in "
                "the script. It has to be spoken — to them or to camera — "
                "because the reason is what makes the asking land."
            )

        warm = people["closing_if_warm"].strip()
        cold = people["closing_if_cold"].strip()
        for name, text in (("closing_if_warm", warm), ("closing_if_cold", cold)):
            if len(text.split()) < 15:
                problems.append(
                    f"{name} is missing or too short. Nobody knows what they "
                    "will say, so both endings are written before anyone walks "
                    "in — otherwise the cold one never gets filmed, and the "
                    "cold one is the video worth more."
                )
        if warm and cold and flat(warm) == flat(cold):
            problems.append(
                "The two closings are the same words. If a bad review and a "
                "good one end the video identically, one of them is a lie."
            )

    # 6b3. Asking, not challenging. A favour framed as a contest reads as a
    # contest, and the person doing the favour hears it first.
    everything = flat(all_text(sheet))
    for tell in CHALLENGE_TELLS:
        if flat(tell) in everything:
            problems.append(
                f"The sheet says {tell!r}. That makes the other person the "
                "one being tested and us the one testing, which buys a "
                "guarded answer. Ask for their opinion because it is worth "
                "more than ours on this question, and say why."
            )
    if fmt in WITH_PEOPLE:
        padded = " " + everything + " "
        for word in TOO_FAMILIAR:
            if flat(word) and " " + flat(word) + " " in padded:
                problems.append(
                    f"The sheet uses {word.strip()!r}. Somebody standing "
                    "behind his own counter is `aap`, whatever his age."
                )
                break

    # 6c. Nobody else's words, ever. The sheet carries our questions; their
    # answers arrive on the day or they do not arrive at all. A fed review is
    # worthless the moment one viewer suspects it, and suspicion is cheap.
    for shot in shots:
        line = shot["spoken"].lower()
        for tell in ("he says", "he will say", "he'll say", "she says",
                     "they say", "woh kahega", "wo kahega", "woh bolega",
                     "wo bolega", "unhone kaha", "woh kehta", "wo kehta",
                     "dukaandar:", "shopkeeper:", "owner:", "customer:",
                     "he replies", "bolwana", "bulwana", "unse kehna ki bole"):
            if tell in line:
                problems.append(
                    f"Shot {shot['n']} writes what somebody else says "
                    f"({tell!r}). A spoken line in this sheet is only ever "
                    "yours. Put it in people.questions and let the answer be "
                    "whatever it turns out to be."
                )
                break

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
    ]

    # The person in the frame, printed before the shot list, because the
    # consent line is recorded before any of it and the questions are what
    # the shoot actually runs on.
    people = sheet.get("people") or {}
    if people.get("who", "").strip():
        out += [
            f"## The person in this: {people['who']}",
            "",
        ]
        if people.get("why_them", "").strip():
            out += [
                "**Why them — say this, do not just know it:**",
                "",
                f"> {people['why_them']}",
                "",
                "You are asking a favour of somebody who knows more than you "
                "do about one thing. A shoot that forgets to say so gets a "
                "guarded answer, and a guarded answer is the only kind this "
                "format cannot use.",
                "",
            ]
        out += [
            "**Record this first, before anything else:**",
            "",
            f"> {people['consent']}",
            "",
        ]
        if people.get("disclosure", "").strip():
            out += [
                "**Say this in the video, word for word:**",
                "",
                f"> {people['disclosure']}",
                "",
            ]
        out += ["**Ask — and then stop talking:**", ""]
        out += [f"{i}. {q}" for i, q in enumerate(people["questions"], 1)]
        out += [
            "",
            "**Keep these in the edit if they come:**",
            "",
        ]
        out += [f"- {x}" for x in people["listen_for"]]
        out += [
            "",
            "Do not put words in their mouth, do not ask again for a better "
            "answer, and do not cut the lukewarm one. A flat answer, left in, "
            "is worth more than a warm one that had to be fished for.",
            "",
        ]

    # The whole thing said out loud, in order. Printed before the shot list,
    # because this is what happens on the day and the shot list is what
    # happens afterwards at a laptop.
    script = sheet.get("script") or []
    if script:
        out += [
            "## The script — everything you say, in order",
            "",
            "This is not the shot list. This is walking in to walking out, "
            "eight to twelve minutes of it, and about eighty seconds will "
            "survive. Half of these lines never reach the video: they are "
            "there to get somebody talking, not to be watched.",
            "",
            "Where it says *their turn* — stop talking. The most valuable part "
            "of the video arrives after that silence, and filling it is the "
            "commonest way to lose it.",
            "",
        ]
        for i, scene in enumerate(script, 1):
            out += [f"### {i}. {scene['scene']}", ""]
            if scene.get("camera", "").strip():
                out += [f"*Camera: {scene['camera']}*", ""]
            for line in scene["lines"]:
                out += [f"> **{line}**", ">"]
            if out[-1] == ">":
                out.pop()
            out.append("")
            if scene.get("their_turn", "").strip():
                out += [f"**Their turn —** {scene['their_turn']}", ""]
            if scene.get("note", "").strip():
                out += [f"{scene['note']}", ""]

    if people.get("closing_if_warm", "").strip():
        out += [
            "## Two endings, because you do not know which one you will get",
            "",
            "Have both in your head before you walk in. Whichever happens, "
            "the video goes out.",
            "",
            "**If it went well:**",
            "",
            f"> {people['closing_if_warm']}",
            "",
            "**If it went badly or flat:**",
            "",
            f"> {people['closing_if_cold']}",
            "",
            "The second one will be the better video. Every brand posts the "
            "warm review, so a warm review is worth nothing now. Nobody posts "
            "the cold one — which is the only reason a stranger would believe "
            "anything else said on this account.",
            "",
        ]

    out += [
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
    parser.add_argument("--daily", action="store_true",
                        help="one idea for today: take the next queued shoot, "
                             "or invent one when the queue is empty")
    parser.add_argument("--format", dest="fmt", choices=FORMATS,
                        help="with --daily, force the format instead of "
                             "rotating it")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the sheet; write no files")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()

    queue_path = HERE / "vlog_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    today = date.today()
    extra = ""

    if args.daily and not args.shoot:
        # Prefer a brief somebody wrote — a person's idea beats an invented
        # one — and only invent once there are none left.
        try:
            shoot = pick_shoot(queue, None)
        except SystemExit:
            shoot, extra = invent(queue.get("defaults") or {}, today, args.fmt)
            print("→ queue empty; inventing today's idea", flush=True)
        else:
            if args.fmt and shoot.get("format") != args.fmt:
                shoot, extra = invent(queue.get("defaults") or {}, today,
                                      args.fmt)
                print(f"→ queue has no {args.fmt}; inventing one",
                      flush=True)
    else:
        shoot = pick_shoot(queue, args.shoot)
    print(f"→ shoot: {shoot['id']} ({shoot.get('format')})", flush=True)

    shop = shop_from_env()
    products = shop.catalogue()
    banned = forbidden_phrases(products)
    print(f"→ {len(products)} products in the catalogue", flush=True)

    sheet = run_rounds(
        anthropic.Anthropic(),
        cached_system("vlog-style.md", products),
        brief_block(shoot, queue.get("defaults") or {}, today, extra),
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

    if not shoot.get("invented"):
        shoot["status"] = "planned"
        shoot["sheet"] = f"bot/shoots/{stem}.md"
        shoot["planned_on"] = today.isoformat()
        queue_path.write_text(
            json.dumps(queue, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")

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
