#!/usr/bin/env python3
"""Turn an entry's shot briefs into a sheet somebody can work from.

The pictures are made by hand, with the real bottle attached as a reference so
its label comes out right. This prints everything that takes to do: the full
prompt, the size to generate at, and the exact reference photograph to attach
— looked up live, so it is the file that is on the product today.

    python bot/make_sheet.py --article gym-perfume-three-that-held-one-that-curdled
    python bot/make_sheet.py --article <handle> --out bot/shot-sheets/

Then the pictures get made, uploaded to Shopify Files, and their URLs come
back through `attach_shots.py`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from agent_common import HERE, shop_from_env
from synor_shopify import ShopifyError

# The page crops in-body pictures to exactly this, so anything else loses its
# top and bottom. It is not a preference.
RATIO = "3:2 landscape, 1536 × 1024"

NEGATIVE = """no faces, no portraits, no people looking at camera, no text, no lettering,
no watermark, no logo other than the one on the attached bottle, no extra
bottles, no duplicated bottles, no distorted or invented label text, no
studio backdrop, no stock-photo gloss, no HDR, no oversaturation, no lens
flare, no vignette, no beauty retouching, not clean, not tidy"""

ARTICLE = """
query($q: String!) {
  articles(first: 5, query: $q) {
    nodes { id handle title metafields(first: 30) { nodes { key value } } }
  }
}
"""

PRODUCT = """
query($h: String!) {
  productByHandle(handle: $h) {
    title
    media(first: 20) { nodes { ... on MediaImage { image { url } } } }
  }
}
"""


def reference(shop, handle: str, size: str) -> tuple[str, str]:
    """The photograph to attach, and a note when it had to be guessed.

    Filenames on this shop carry the size — `…-3ml-1.jpg`, `…-15ml-2.jpg` —
    so the right one can be picked out. Some products have another scent's
    photographs sitting in their media, which is why an exact size match is
    preferred over position and why a fallback says so out loud.
    """
    product = shop.gql(PRODUCT, {"h": handle})["productByHandle"]
    if not product:
        return "", f"**No product `{handle}` on the store.**"
    urls = [(n.get("image") or {}).get("url", "")
            for n in product["media"]["nodes"]]
    urls = [u for u in urls if u]
    stem = handle.replace("-extrait-de-parfum", "").replace("-copy", "")
    stem = re.sub(r"^\d+-", "", stem)

    exact = [u for u in urls if f"-{size}-" in u.lower()]
    if exact:
        return exact[0], ""
    own = [u for u in urls if stem.split("-", 1)[-1][:10] in u.lower()]
    if own:
        return own[0], (f"No `{size}` photograph on this product — this is its "
                        "first own image. Check it is the right scent.")
    if urls:
        return urls[0], ("**Could not find a photograph belonging to this "
                         "scent. Check before attaching.**")
    return "", "**This product has no photographs at all.**"


def sheet(shop, article: dict[str, Any], briefs: list[dict[str, Any]]) -> str:
    out = [
        f"# Image sheet — {article['title']}",
        "",
        f"`{article['handle']}` · {len(briefs)} image"
        + ("s" if len(briefs) != 1 else ""),
        "",
        f"Everything on this sheet is **{RATIO}**. That is not a preference —",
        "the article page crops in-body pictures to exactly 3:2, so anything",
        "else loses its top and bottom.",
        "",
        "**How to make each one:** attach the reference photograph linked",
        "below so the model copies the real bottle and the real label, paste",
        "the prompt, generate, upload.",
        "",
        "**Where the files go:** Shopify admin → Content → Files.",
        "",
        "**One rule that is not about looks.** No faces anywhere — hands,",
        "wrists, backs, shoulders and distant figures only. The people in a",
        "report are real people who really answered; a generated face turns",
        "them into a claim we did not earn. Each picture also carries a small",
        "`Illustration` on the page.",
        "",
        "---",
        "",
        "## Shared negative prompt",
        "",
        "Paste into the negative field on every one, or append to the prompt",
        "if the tool has no negative field.",
        "",
        "```", NEGATIVE, "```",
        "",
        "---",
        "",
    ]
    for i, brief in enumerate(briefs, 1):
        where = brief.get("after", "").strip()
        out += [f"## {i} — {where or 'Hero · top of the entry'}", ""]
        if not where:
            out += ["**Also set this one as the article's featured image "
                    "in Shopify.**", ""]
        ref_handle = brief.get("ref_handle", "").strip()
        ref_size = brief.get("ref_size", "").strip()
        if ref_handle:
            url, note = reference(shop, ref_handle, ref_size or "3ml")
            out += [f"**Attach** — {ref_handle} {ref_size or '3ml'}", ""]
            if url:
                out += [f"`{url.split('/')[-1].split('?')[0]}`", "", url, ""]
            if note:
                out += [note, ""]
        else:
            out += ["**Attach** — nothing. No bottle in this one.", ""]
        out += ["```", brief.get("prompt", "").strip(),
                "", RATIO + ".", "```", ""]
        out += [f"**Caption for the page:** {brief.get('caption', '')}", "",
                "---", ""]
    out += [
        "## After you upload",
        "",
        "Copy each file's URL out of Shopify Files, in order, and run:",
        "",
        "```bash",
        f"python bot/attach_shots.py --article {article['handle']} \\",
        "    --url <1> --url <2> --url <3> …",
        "```",
        "",
        "That puts them under the right headings, and in the Hinglish",
        "telling too.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the sheet for making an entry's pictures by hand.")
    parser.add_argument("--article", required=True)
    parser.add_argument("--out", default=str(HERE / "shot-sheets"),
                        help="where to write it (default bot/shot-sheets/)")
    args = parser.parse_args()

    shop = shop_from_env()
    nodes = shop.gql(ARTICLE, {"q": f"handle:{args.article}"})["articles"]["nodes"]
    article = next((n for n in nodes if n["handle"] == args.article), None)
    if not article:
        raise SystemExit(f"No article with handle {args.article!r}")
    mf = {m["key"]: m["value"] for m in article["metafields"]["nodes"]}
    raw = mf.get("shot_briefs")
    if not raw:
        raise SystemExit(
            f"{args.article} has no custom.shot_briefs. The writing agent "
            "fills it; an older entry needs one by hand."
        )
    briefs = json.loads(raw)

    text = sheet(shop, article, briefs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.article}.md"
    path.write_text(text, encoding="utf-8")
    print(f"✓ {path}")
    print(f"  {len(briefs)} image(s), {RATIO}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ShopifyError as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        sys.exit(1)
