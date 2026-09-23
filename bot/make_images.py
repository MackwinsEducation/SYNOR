#!/usr/bin/env python3
"""Draw the pictures an entry asks for, and put them on the page.

The writing agent ends each entry with a set of **shot briefs** — one per
section, describing the photograph that belongs there. This script turns those
briefs into images, uploads them to Shopify Files, and writes the resulting
CDN URLs into the article so the theme can place them.

    python bot/make_images.py --article gym-perfume-three-that-held-one-that-curdled
    python bot/make_images.py --article <handle> --dry-run   # print the briefs only

Environment:
    GEMINI_API_KEY        from aistudio.google.com
    SHOPIFY_STORE         perfume-rat
    SHOPIFY_ADMIN_TOKEN   needs write_files as well as write_content
    SYNOR_IMAGE_MODEL     optional, default gemini-3.1-flash-image
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent_common import HERE, shop_from_env
from synor_shopify import ShopifyError
import shopify_files

OUT = HERE / "shots"
MODEL = os.environ.get("SYNOR_IMAGE_MODEL") or "gemini-3.1-flash-image"
ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent")

# The look. Every picture on the paper shares it, so the page holds together
# instead of reading as a pile of unrelated stock.
HOUSE_LOOK = (
    "Documentary photograph, shot on 35mm film, natural available light, "
    "muted warm colour, slight grain, shallow depth of field, unstaged and "
    "a little imperfect. Real ordinary India — Ahmedabad, Gujarat. "
    "No text, no logos, no watermarks, no captions in the image."
)

# What a picture on this paper may never be. The first two protect the shop,
# the third protects the reader.
NEVER = (
    "Do not draw any perfume bottle, box or label of any kind. "
    "Do not show anybody's face; hands, backs, shoulders and distant figures "
    "only. "
    "Do not depict a specific named person, a celebrity, or any brand."
)


class ImageError(RuntimeError):
    pass


def draw(prompt: str, api_key: str) -> bytes:
    """One image from the model, as PNG bytes."""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["Image"]},
    }).encode()
    request = urllib.request.Request(
        ENDPOINT.format(model=MODEL),
        data=body,
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        # The key is never in the URL or the body, so nothing to scrub here.
        raise ImageError(f"The image API answered {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ImageError(f"Could not reach the image API: {exc.reason}") from None

    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
        reason = candidate.get("finishReason")
        if reason and reason not in ("STOP", "MAX_TOKENS"):
            raise ImageError(
                f"The model returned no image ({reason}). Usually the brief "
                "tripped a safety filter — rewrite it plainer."
            )
    raise ImageError("The model returned no image and gave no reason.")


# ------------------------------------------------------------------ article

ARTICLE = """
query($q: String!) {
  articles(first: 5, query: $q) {
    nodes {
      id handle title
      metafields(first: 30) { nodes { key value } }
    }
  }
}
"""


def load_article(shop, handle: str) -> dict[str, Any]:
    nodes = shop.gql(ARTICLE, {"q": f"handle:{handle}"})["articles"]["nodes"]
    for node in nodes:
        if node["handle"] == handle:
            node["mf"] = {m["key"]: m["value"] for m in node["metafields"]["nodes"]}
            return node
    raise SystemExit(f"No article with handle {handle!r} on the store")


def briefs_of(article: dict[str, Any]) -> list[dict[str, str]]:
    raw = article["mf"].get("shot_briefs")
    if not raw:
        raise SystemExit(
            f"{article['handle']} has no custom.shot_briefs metafield. The "
            "writing agent fills it; an older entry has to be given one by "
            "hand, or rewritten."
        )
    try:
        briefs = json.loads(raw)
    except ValueError:
        raise SystemExit("custom.shot_briefs is not valid JSON.") from None
    if not isinstance(briefs, list) or not briefs:
        raise SystemExit("custom.shot_briefs is empty.")
    return briefs


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


# --------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Draw an entry's pictures and put them on the page.")
    parser.add_argument("--article", required=True, help="the article handle")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the briefs and the full prompts; draw nothing")
    parser.add_argument("--keep", action="store_true",
                        help="keep the PNGs in bot/shots/ after uploading")
    args = parser.parse_args()

    shop = shop_from_env()
    article = load_article(shop, args.article)
    briefs = briefs_of(article)
    print(f"→ {article['title']}")
    print(f"→ {len(briefs)} shot(s) asked for")

    prompts = []
    for i, brief in enumerate(briefs, 1):
        scene = (brief.get("prompt") or "").strip()
        if not scene:
            raise SystemExit(f"Shot {i} has no prompt.")
        prompts.append(f"{scene}\n\n{HOUSE_LOOK}\n\n{NEVER}")

    if args.dry_run:
        for brief, prompt in zip(briefs, prompts):
            print("\n--- after heading:", brief.get("after") or "(top)")
            print("    caption:", brief.get("caption") or "(none)")
            print("   ", prompt.replace("\n", "\n    "))
        print("\nNothing drawn, nothing uploaded.")
        return 0

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set.")

    OUT.mkdir(exist_ok=True)
    shots = []
    for i, (brief, prompt) in enumerate(zip(briefs, prompts), 1):
        label = brief.get("after") or f"shot-{i}"
        print(f"\n[{i}/{len(briefs)}] {label}", flush=True)
        print("  drawing…", flush=True)
        png = draw(prompt, api_key)
        path = OUT / f"{args.article}-{i}-{slug(label)}.png"
        path.write_bytes(png)
        print(f"  {len(png) // 1024} KB", flush=True)

        print("  uploading…", flush=True)
        up = shopify_files.upload(
            shop, path, alt=brief.get("caption") or article["title"])
        print(f"  {up['url']}", flush=True)
        shots.append({
            "after": brief.get("after", ""),
            "url": up["url"],
            "caption": brief.get("caption", ""),
            "file_id": up["id"],
        })
        if not args.keep:
            path.unlink(missing_ok=True)

    shop.gql(
        """
        mutation($id: ID!, $article: ArticleUpdateInput!) {
          articleUpdate(id: $id, article: $article) {
            article { id handle }
            userErrors { field message }
          }
        }
        """,
        {"id": article["id"], "article": {"metafields": [{
            "namespace": "custom", "key": "shots",
            "value": json.dumps(shots, ensure_ascii=False),
            "type": "multi_line_text_field",
        }]}},
    )
    print(f"\n✓ {len(shots)} picture(s) on {article['handle']}")
    print("  Open the entry and look before you publish it — the model draws "
          "what it likes, not what happened.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ImageError, ShopifyError) as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n✗ stopped", file=sys.stderr)
        sys.exit(130)
