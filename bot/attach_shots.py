#!/usr/bin/env python3
"""Put the finished pictures on the entry.

The pictures were made by hand and uploaded to Shopify Files. This takes their
URLs, in the order of the entry's shot briefs, and writes them into the
article's `custom.shots` metafield — which is what the article page reads to
place each one under the heading its brief named.

    python bot/attach_shots.py --article <handle> --url <1> --url <2> …
    python bot/attach_shots.py --article <handle> --clear
"""

from __future__ import annotations

import argparse
import json
import sys

from agent_common import shop_from_env
from synor_shopify import ShopifyError

ARTICLE = """
query($q: String!) {
  articles(first: 5, query: $q) {
    nodes { id handle title metafields(first: 30) { nodes { key value } } }
  }
}
"""

UPDATE = """
mutation($id: ID!, $article: ArticleUpdateInput!) {
  articleUpdate(id: $id, article: $article) {
    article { id handle }
    userErrors { field message }
  }
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach an entry's pictures.")
    parser.add_argument("--article", required=True)
    parser.add_argument("--url", action="append", default=[],
                        help="one per shot brief, in order")
    parser.add_argument("--clear", action="store_true",
                        help="take the pictures off the entry")
    args = parser.parse_args()

    shop = shop_from_env()
    nodes = shop.gql(ARTICLE, {"q": f"handle:{args.article}"})["articles"]["nodes"]
    article = next((n for n in nodes if n["handle"] == args.article), None)
    if not article:
        raise SystemExit(f"No article with handle {args.article!r}")
    mf = {m["key"]: m["value"] for m in article["metafields"]["nodes"]}

    if args.clear:
        shots = []
    else:
        briefs = json.loads(mf.get("shot_briefs") or "[]")
        if not briefs:
            raise SystemExit(f"{args.article} has no shot briefs to match.")
        if len(args.url) != len(briefs):
            raise SystemExit(
                f"{len(args.url)} URL(s) given for {len(briefs)} brief(s). "
                "They are matched in order, so give one for each — or run "
                "make_sheet.py again to see the order."
            )
        for url in args.url:
            if not url.startswith("https://"):
                raise SystemExit(f"{url!r} is not an https URL.")
        shots = [{
            "after": brief.get("after", ""),
            "url": url,
            "caption": brief.get("caption", ""),
        } for brief, url in zip(briefs, args.url)]

    shop.gql(UPDATE, {"id": article["id"], "article": {"metafields": [{
        "namespace": "custom", "key": "shots",
        "value": json.dumps(shots, ensure_ascii=False),
        "type": "multi_line_text_field",
    }]}})

    if not shots:
        print(f"✓ pictures taken off {args.article}")
        return 0
    print(f"✓ {len(shots)} picture(s) on {args.article}")
    for shot in shots:
        print(f"  {shot['after'] or '(top)':34} {shot['url'].split('/')[-1][:44]}")
    print("\n  Open the entry and look at it before you publish.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ShopifyError as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        sys.exit(1)
