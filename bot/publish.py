#!/usr/bin/env python3
"""Post a distribution pack to Instagram and Facebook.

Track 5. Reads a pack written by Track 4 and publishes it. Instagram gets the
reel with its caption and the hashtags as the first comment; the Facebook Page
gets the text post with its link.

**Nothing is posted unless --publish is passed.** The default is a preflight:
it checks the tokens, resolves the account names, verifies the video is
actually reachable, re-checks the caption against the forbidden-names list,
and prints exactly what would go out. Publishing to a public account cannot be
undone, so it is never the default and never on a schedule.

    python bot/publish.py --pack 2026-09-17-lift-test \
        --video-url https://cdn.shopify.com/.../lift-test.mp4
    python bot/publish.py --pack 2026-09-17-lift-test --video-url ... --publish
    python bot/publish.py --pack 2026-09-17-lift-test --channels fb --publish

Environment:
    META_ACCESS_TOKEN   long-lived Page access token
    IG_USER_ID          the Instagram Business account's id
    FB_PAGE_ID          the Facebook Page's id
    SHOPIFY_STORE       only needed for the forbidden-names re-check
    SHOPIFY_ADMIN_TOKEN same
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from agent_common import HERE, name_hits, shop_from_env
from synor_shopify import ShopifyError, forbidden_phrases

SOCIAL_DIR = HERE / "social"
GRAPH = "https://graph.facebook.com/v25.0"

# Meta's own guidance is to poll a container's status about once a minute for
# no more than five minutes. These are the gaps between polls, in seconds.
POLL_GAPS = (10, 20, 30, 30, 45, 45, 60, 60)


class PublishError(RuntimeError):
    pass


def scrub(text: str) -> str:
    """Never let a token reach a log.

    This runs over every error string. A run happens in GitHub Actions where
    the output is kept, so a token echoed once in a stack trace is a token
    that has to be rotated.
    """
    text = re.sub(r"(access_token=)[^&\s\"']+", r"\1[redacted]", text)
    token = os.environ.get("META_ACCESS_TOKEN")
    if token and len(token) > 8:
        text = text.replace(token, "[redacted]")
    return text


# ------------------------------------------------------------- transport

def graph(path: str, params: dict[str, Any] | None = None,
          method: str = "GET") -> dict[str, Any]:
    """One Graph API call.

    The token always travels in the POST body, never in the query string, so
    that a URL appearing in an error message carries no secret.
    """
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    if not token:
        raise PublishError("META_ACCESS_TOKEN is not set")
    payload = dict(params or {})
    payload["access_token"] = token
    url = f"{GRAPH}/{path.lstrip('/')}"

    if method == "GET":
        request = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(payload), method="GET")
    else:
        request = urllib.request.Request(
            url, data=urllib.parse.urlencode(payload).encode(), method="POST")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            error = json.loads(body)["error"]
            raise PublishError(scrub(
                f"Graph API {exc.code} on {path}: {error.get('message')} "
                f"(type {error.get('type')}, code {error.get('code')}, "
                f"subcode {error.get('error_subcode')}, "
                f"trace {error.get('fbtrace_id')})"
            )) from None
        except (ValueError, KeyError):
            raise PublishError(
                scrub(f"Graph API {exc.code} on {path}: {body[:400]}")) from None
    except urllib.error.URLError as exc:
        raise PublishError(f"Cannot reach the Graph API: {exc.reason}") from None


def video_is_reachable(url: str) -> tuple[bool, str]:
    """Instagram fetches the file itself, so a URL only it can't read fails
    the whole publish minutes later with an unhelpful error. Check first."""
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=60) as response:
            kind = response.headers.get("Content-Type", "")
            size = response.headers.get("Content-Length")
            if not kind.startswith("video/"):
                return False, f"serves {kind or 'no content type'}, not a video"
            mb = f"{int(size) / 1e6:.1f} MB" if size else "unknown size"
            return True, f"{kind}, {mb}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} — Instagram has to be able to read it"
    except urllib.error.URLError as exc:
        return False, f"unreachable: {exc.reason}"


# ------------------------------------------------------------------ pack

def load_pack(name: str) -> tuple[str, dict[str, Any]]:
    path = SOCIAL_DIR / f"{name}.json"
    if not path.exists():
        matches = sorted(SOCIAL_DIR.glob(f"*{name}*.json"))
        matches = [m for m in matches if not m.name.endswith(".posted.json")]
        if not matches:
            raise SystemExit(
                f"No pack matching {name!r} in bot/social/. "
                "Run write_social.py first."
            )
        path = matches[-1]
    return path.stem, json.loads(path.read_text(encoding="utf-8"))


def posted_path(stem: str):
    return SOCIAL_DIR / f"{stem}.posted.json"


def load_posted(stem: str) -> dict[str, Any]:
    path = posted_path(stem)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def record(stem: str, channel: str, detail: dict[str, Any]) -> None:
    posted = load_posted(stem)
    posted[channel] = {"at": datetime.now(timezone.utc).isoformat(), **detail}
    posted_path(stem).write_text(
        json.dumps(posted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ig_caption(pack: dict[str, Any]) -> str:
    return pack["reel"]["caption"]


def ig_first_comment(pack: dict[str, Any]) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in pack["reel"]["hashtags"])
    note = pack["reel"]["first_comment"].strip()
    return f"{note}\n\n{tags}" if note else tags


# ------------------------------------------------------------- preflight

def preflight(pack: dict[str, Any], stem: str, video_url: str | None,
              channels: set[str], banned: list[str]) -> list[str]:
    """Everything checkable without posting. Returns blocking problems."""
    problems: list[str] = []
    posted = load_posted(stem)

    for channel in sorted(channels):
        if channel in posted:
            problems.append(
                f"This pack was already posted to {channel} at "
                f"{posted[channel]['at']}. Pass --again to post it a second time."
            )

    if "ig" in channels:
        ig_id = os.environ.get("IG_USER_ID", "").strip()
        if not ig_id:
            problems.append("IG_USER_ID is not set.")
        else:
            account = graph(ig_id, {"fields": "username,name"})
            print(f"  Instagram: @{account.get('username')} "
                  f"({account.get('name')})")
        if not video_url:
            problems.append(
                "Instagram needs --video-url. It fetches the file itself, so "
                "the video has to already be at a public HTTPS address — "
                "dropping it into Shopify → Content → Files gives you one."
            )
        else:
            ok, detail = video_is_reachable(video_url)
            print(f"  Video: {detail}")
            if not ok:
                problems.append(f"The video URL is not usable: {detail}")
            elif not video_url.lower().startswith("https://"):
                problems.append("The video URL has to be HTTPS.")

        caption = ig_caption(pack)
        if len(caption) > 2200:
            problems.append(
                f"The caption is {len(caption)} characters; Instagram's limit "
                "is 2,200."
            )
        comment = ig_first_comment(pack)
        if len(comment) > 2200:
            problems.append("The first comment is over Instagram's 2,200 limit.")
        print(f"  Caption: {len(caption)} chars, "
              f"first comment: {len(comment)} chars")

    if "fb" in channels:
        page_id = os.environ.get("FB_PAGE_ID", "").strip()
        if not page_id:
            problems.append("FB_PAGE_ID is not set.")
        else:
            page = graph(page_id, {"fields": "name,link"})
            print(f"  Facebook Page: {page.get('name')}")
        if not pack["facebook"]["text"].strip():
            problems.append("The pack's Facebook text is empty.")

    # The last line of defence. The pack was checked when it was written, but
    # it may have been hand-edited since, and this is the point of no return.
    blob = " ".join([
        ig_caption(pack), ig_first_comment(pack),
        pack["facebook"]["text"], pack["facebook"]["link"],
    ])
    hits = name_hits(blob, banned)
    if hits:
        problems.append(
            "The copy about to be posted contains names that must not be "
            "published: " + ", ".join(hits) + "."
        )
    for match in re.findall(r"₹\s?([\d,]+)", blob):
        if match.replace(",", "") != "49":
            problems.append(
                f"The copy states a price of ₹{match}. Only ₹49 may appear."
            )
    return problems


# --------------------------------------------------------------- publish

def publish_instagram(pack: dict[str, Any], video_url: str) -> dict[str, Any]:
    ig_id = os.environ["IG_USER_ID"].strip()

    print("→ creating the reel container", flush=True)
    container = graph(f"{ig_id}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": ig_caption(pack),
        "share_to_feed": "true",
    }, method="POST")
    creation_id = container["id"]
    print(f"  container {creation_id}", flush=True)

    print("→ waiting for Instagram to finish processing", flush=True)
    status = ""
    for gap in POLL_GAPS:
        time.sleep(gap)
        state = graph(creation_id, {"fields": "status_code,status"})
        status = state.get("status_code", "")
        print(f"  {status}", flush=True)
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise PublishError(
                "Instagram rejected the video while processing: "
                + str(state.get("status", "no detail given"))
                + ". Usually the aspect ratio, the length or the codec — "
                  "9:16, under 90 seconds, H.264/AAC in an MP4 is safe."
            )
    if status != "FINISHED":
        raise PublishError(
            "Instagram was still processing after five minutes. The container "
            f"({creation_id}) stays valid for 24 hours, so re-running with "
            "--publish will pick it up rather than re-upload."
        )

    print("→ publishing", flush=True)
    published = graph(f"{ig_id}/media_publish",
                      {"creation_id": creation_id}, method="POST")
    media_id = published["id"]

    detail: dict[str, Any] = {"media_id": media_id}
    try:
        detail["permalink"] = graph(media_id, {"fields": "permalink"})["permalink"]
    except PublishError as exc:
        print(f"  (could not read the permalink: {exc})", flush=True)

    # The reel is live at this point, so a failed comment must not fail the
    # run — it is a nicety, and the fix is one tap in the app.
    print("→ posting the hashtags as the first comment", flush=True)
    try:
        comment = graph(f"{media_id}/comments",
                        {"message": ig_first_comment(pack)}, method="POST")
        detail["comment_id"] = comment.get("id")
    except PublishError as exc:
        print(f"  ✗ the reel is up but the first comment failed: {exc}",
              file=sys.stderr)
        print("    Paste it by hand — it is in the pack.", file=sys.stderr)
        detail["comment_failed"] = True
    return detail


def publish_facebook(pack: dict[str, Any]) -> dict[str, Any]:
    page_id = os.environ["FB_PAGE_ID"].strip()
    params = {"message": pack["facebook"]["text"]}
    link = pack["facebook"]["link"].strip()
    if link:
        params["link"] = link if link.startswith("http") else f"https://{link}"
    print("→ posting to the Page", flush=True)
    post = graph(f"{page_id}/feed", params, method="POST")
    return {"post_id": post["id"],
            "url": f"https://facebook.com/{post['id'].replace('_', '/posts/')}"}


# ------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post a distribution pack to Instagram and Facebook.")
    parser.add_argument("--pack", required=True,
                        help="a pack stem in bot/social/")
    parser.add_argument("--video-url",
                        help="public HTTPS URL of the reel (required for Instagram)")
    parser.add_argument("--channels", default="ig,fb",
                        help="comma separated: ig, fb (default both)")
    parser.add_argument("--publish", action="store_true",
                        help="actually post. Without this it is a preflight only.")
    parser.add_argument("--again", action="store_true",
                        help="allow posting a pack that was already posted")
    args = parser.parse_args()

    channels = {c.strip().lower() for c in args.channels.split(",") if c.strip()}
    unknown = channels - {"ig", "fb"}
    if unknown:
        raise SystemExit(f"Unknown channel(s): {', '.join(sorted(unknown))}")

    stem, pack = load_pack(args.pack)
    print(f"→ pack: {stem}")
    print(f"→ channels: {', '.join(sorted(channels))}")

    banned = forbidden_phrases(shop_from_env().catalogue())

    print("\n--- preflight --------------------------------------------")
    problems = preflight(pack, stem, args.video_url, channels, banned)
    if args.again:
        problems = [p for p in problems if "already posted" not in p]
    if problems:
        print("\n✗ Not posting. Fix these first:\n", file=sys.stderr)
        for problem in problems:
            print(f"  · {problem}", file=sys.stderr)
        return 1
    print("  everything checks out")

    if not args.publish:
        print("\n--- this is what would go out ----------------------------")
        if "ig" in channels:
            print("\nInstagram reel caption:\n")
            print(ig_caption(pack))
            print("\nFirst comment:\n")
            print(ig_first_comment(pack))
        if "fb" in channels:
            print("\nFacebook post:\n")
            print(pack["facebook"]["text"])
            print(f"\nLink: {pack['facebook']['link']}")
        print("\nNothing was posted. Add --publish to post it for real.")
        return 0

    results: dict[str, dict[str, Any]] = {}
    if "ig" in channels:
        print("\n--- Instagram --------------------------------------------")
        results["ig"] = publish_instagram(pack, args.video_url)
        record(stem, "ig", results["ig"])
        print(f"✓ live: {results['ig'].get('permalink', results['ig']['media_id'])}")
    if "fb" in channels:
        print("\n--- Facebook ---------------------------------------------")
        results["fb"] = publish_facebook(pack)
        record(stem, "fb", results["fb"])
        print(f"✓ live: {results['fb']['url']}")

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(f"### Posted · {stem}\n\n")
            for channel, detail in results.items():
                link = detail.get("permalink") or detail.get("url") or ""
                handle.write(f"- **{channel}** — {link}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PublishError, ShopifyError) as exc:
        print(f"\n✗ {scrub(str(exc))}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n✗ stopped", file=sys.stderr)
        sys.exit(130)
