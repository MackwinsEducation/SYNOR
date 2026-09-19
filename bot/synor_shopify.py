"""Shopify Admin API, only the parts the Diaries agent needs.

The Admin API is GraphQL over HTTPS with one header, so this is the standard
library and nothing else. Every call raises on `errors` *and* on `userErrors`,
because Shopify returns HTTP 200 with a `userErrors` array when a mutation is
rejected, and a bot that ignores that reports success while having written
nothing.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_API_VERSION = "2026-07"

# Namespaced tags the storefront navigates by. Everything else on a product is
# free text — a designer reference or a celebrity — and must never reach a post.
TAG_NAMESPACES = (
    "band-", "brand-", "family-", "gender-", "mood-", "occasion-",
    "scent-", "season-", "longevity-", "tier-", "pick-", "series-", "yt-",
)


class ShopifyError(RuntimeError):
    pass


class Shop:
    def __init__(self, store: str, token: str, api_version: str = DEFAULT_API_VERSION):
        if not store:
            raise ShopifyError("SHOPIFY_STORE is not set")
        if not token:
            raise ShopifyError("SHOPIFY_ADMIN_TOKEN is not set")
        # Accept "perfume-rat" or "perfume-rat.myshopify.com".
        host = store.strip().removeprefix("https://").removesuffix("/")
        if not host.endswith(".myshopify.com"):
            # The easy mistake: giving the customer-facing domain. The Admin
            # API only answers on the myshopify host, and that name is fixed
            # when the store is created — it is not the shop's real domain and
            # Shopify never lets it change. Caught here because the alternative
            # is a DNS failure on "synorperfume.com.myshopify.com", which tells
            # nobody anything.
            if "." in host:
                raise ShopifyError(
                    f"SHOPIFY_STORE is set to {store.strip()!r}, which looks "
                    "like the shop's public domain. It needs the myshopify "
                    "name instead — for SYNOR that is `perfume-rat`. Find it "
                    "in the Shopify admin URL: admin.shopify.com/store/<name>."
                )
            host = f"{host}.myshopify.com"
        self.host = host
        self.token = token.strip()
        self.endpoint = f"https://{host}/admin/api/{api_version}/graphql.json"

    # ---- transport ----------------------------------------------------

    def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.token,
                "Accept": "application/json",
            },
            method="POST",
        )
        last: Exception | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:400]
                if exc.code in (429, 500, 502, 503, 504):
                    last = ShopifyError(f"HTTP {exc.code}: {detail}")
                    time.sleep(2 ** attempt)
                    continue
                if exc.code in (401, 403):
                    raise ShopifyError(
                        f"HTTP {exc.code} from {self.host}. The admin token is wrong, "
                        f"expired, or missing a scope (needs write_content, "
                        f"read_products). {detail}"
                    ) from exc
                raise ShopifyError(f"HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                last = ShopifyError(f"Cannot reach {self.host}: {exc.reason}")
                time.sleep(2 ** attempt)
        else:
            raise last or ShopifyError("Admin API unreachable")

        if payload.get("errors"):
            raise ShopifyError(json.dumps(payload["errors"])[:800])
        return payload["data"]

    @staticmethod
    def _check_user_errors(node: dict[str, Any], where: str) -> None:
        errs = node.get("userErrors") or []
        if errs:
            lines = "; ".join(
                f"{'.'.join(e.get('field') or [])}: {e.get('message')}" for e in errs
            )
            raise ShopifyError(f"{where} rejected — {lines}")

    # ---- reads --------------------------------------------------------

    def blog_id(self, handle: str) -> str:
        data = self.gql(
            "query($h: String!) { blogs(first: 1, query: $h) { nodes { id handle } } }",
            {"h": f"handle:{handle}"},
        )
        for node in data["blogs"]["nodes"]:
            if node["handle"] == handle:
                return node["id"]
        raise ShopifyError(f"No blog with handle {handle!r} on {self.host}")

    def catalogue(self) -> list[dict[str, Any]]:
        """Every active product, with the tags the agent files by."""
        query = """
        query($cursor: String) {
          products(first: 100, after: $cursor, query: "status:active", sortKey: TITLE) {
            pageInfo { hasNextPage endCursor }
            nodes { handle title tags }
          }
        }
        """
        out: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = self.gql(query, {"cursor": cursor})["products"]
            out.extend(page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                return out
            cursor = page["pageInfo"]["endCursor"]

    def article_handles(self, blog_handle: str) -> set[str]:
        """Handles already used on the blog, so a draft never collides."""
        query = """
        query($h: String!, $cursor: String) {
          blogs(first: 1, query: $h) {
            nodes {
              articles(first: 250, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { handle }
              }
            }
          }
        }
        """
        handles: set[str] = set()
        cursor = None
        while True:
            nodes = self.gql(query, {"h": f"handle:{blog_handle}", "cursor": cursor})
            blogs = nodes["blogs"]["nodes"]
            if not blogs:
                return handles
            page = blogs[0]["articles"]
            handles.update(a["handle"] for a in page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                return handles
            cursor = page["pageInfo"]["endCursor"]

    # ---- write --------------------------------------------------------

    def create_draft_article(
        self,
        blog_id: str,
        title: str,
        handle: str,
        summary_html: str,
        body_html: str,
        tags: list[str],
        metafields: list[dict[str, str]],
        author: str = "Synor Diaries",
    ) -> dict[str, Any]:
        """Create the article unpublished. Publishing stays a human action."""
        mutation = """
        mutation($article: ArticleCreateInput!) {
          articleCreate(article: $article) {
            article { id handle title isPublished }
            userErrors { field message }
          }
        }
        """
        article = {
            "blogId": blog_id,
            "title": title,
            "handle": handle,
            "summary": summary_html,
            "body": body_html,
            "tags": tags,
            "isPublished": False,
            "author": {"name": author},
        }
        if metafields:
            article["metafields"] = metafields
        node = self.gql(mutation, {"article": article})["articleCreate"]
        self._check_user_errors(node, "articleCreate")
        return node["article"]

    def admin_url(self, article_gid: str, blog_gid: str) -> str:
        return (
            f"https://admin.shopify.com/store/{self.host.removesuffix('.myshopify.com')}"
            f"/content/blogs/{blog_gid.rsplit('/', 1)[-1]}"
            f"/articles/{article_gid.rsplit('/', 1)[-1]}"
        )


def is_namespaced(tag: str) -> bool:
    return tag.startswith(TAG_NAMESPACES)


def forbidden_phrases(products: list[dict[str, Any]]) -> list[str]:
    """Names the paper must never print, derived from the catalogue itself.

    Two sources. The `brand-*` tags give the houses SYNOR takes inspiration
    from. Every tag that is *not* namespaced is free text the shop uses for
    its own search — designer references ("CHANEL Bleu de Chanel") and
    celebrities ("Leonardo DiCaprio"). Both are filtering data, not language
    for a customer, and the list rebuilds itself whenever a product is added.
    """
    phrases: set[str] = set()
    for product in products:
        for tag in product.get("tags") or []:
            if tag.startswith("brand-"):
                # A house name is distinctive even at three letters ("ysl").
                name = tag[len("brand-"):].replace("-", " ")
                if len(name) >= 3:
                    phrases.add(name)
            elif is_namespaced(tag):
                continue
            elif (" " in tag or any(c.isupper() for c in tag)) and len(tag) >= 4:
                # A name always carries a capital or a space. Plain lower-case
                # tags like `bestseller`, `combo` or `new-arrival` are shop
                # bookkeeping, not somebody's name, and flagging them would
                # send the writer chasing a fault that isn't there.
                phrases.add(tag)
    return sorted(phrases)
