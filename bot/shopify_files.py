"""Put a picture into Shopify Files and get back a CDN URL.

Three steps, and each one fails differently, which is why they are separated:

  1. `stagedUploadsCreate` hands back a Google Cloud Storage target and a set
     of signed form fields. It is not a Shopify URL and it expires in a day.
  2. The bytes go to that target as a multipart POST. Shopify never sees them.
  3. `fileCreate` tells Shopify the object is there. The file is not usable
     yet — it comes back UPLOADED and has to be polled until READY before the
     CDN URL exists.

Step 3 is the one people get wrong: reading `image.url` straight after
`fileCreate` returns null, not a URL.

Verified end to end against the live store before it was written.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from synor_shopify import Shop, ShopifyError

STAGED = """
mutation($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}
"""

CREATE = """
mutation($files: [FileCreateInput!]!) {
  fileCreate(files: $files) {
    files { id fileStatus }
    userErrors { field message code }
  }
}
"""

READY = """
query($id: ID!) {
  node(id: $id) {
    ... on MediaImage { id fileStatus image { url width height } }
  }
}
"""


def _multipart(fields: list[tuple[str, str]], filename: str,
               content: bytes, mime: str) -> tuple[bytes, str]:
    """Build the POST body by hand — no requests, no dependency."""
    boundary = f"----synor{uuid.uuid4().hex}"
    out = bytearray()
    for name, value in fields:
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += value.encode() + b"\r\n"
    out += f"--{boundary}\r\n".encode()
    out += (f'Content-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\n').encode()
    out += f"Content-Type: {mime}\r\n\r\n".encode()
    out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def upload(shop: Shop, path: Path, alt: str,
           poll_for: int = 60) -> dict[str, Any]:
    """Upload one picture. Returns {"id", "url", "width", "height"}."""
    content = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if not mime.startswith("image/"):
        raise ShopifyError(f"{path.name} is {mime}, not an image")

    # 1 — ask for somewhere to put it
    target = shop.gql(STAGED, {"input": [{
        "resource": "IMAGE",
        "filename": path.name,
        "mimeType": mime,
        "httpMethod": "POST",
    }]})["stagedUploadsCreate"]
    shop._check_user_errors(target, "stagedUploadsCreate")
    staged = target["stagedTargets"][0]

    # 2 — send the bytes there, not to Shopify
    fields = [(p["name"], p["value"]) for p in staged["parameters"]]
    body, content_type = _multipart(fields, path.name, content, mime)
    request = urllib.request.Request(
        staged["url"], data=body,
        headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            if response.status not in (200, 201, 204):
                raise ShopifyError(
                    f"The staged upload answered {response.status}")
    except urllib.error.HTTPError as exc:
        raise ShopifyError(
            f"The staged upload rejected {path.name}: HTTP {exc.code} "
            f"{exc.read().decode(errors='replace')[:300]}"
        ) from None
    except urllib.error.URLError as exc:
        raise ShopifyError(
            f"Could not reach the staged upload target: {exc.reason}") from None

    # 3 — register it, then wait. It is not usable the moment this returns.
    created = shop.gql(CREATE, {"files": [{
        "originalSource": staged["resourceUrl"],
        "contentType": "IMAGE",
        "alt": alt[:512],
        "filename": path.name,
    }]})["fileCreate"]
    shop._check_user_errors(created, "fileCreate")
    file_id = created["files"][0]["id"]

    waited = 0
    while waited < poll_for:
        node = shop.gql(READY, {"id": file_id})["node"] or {}
        status = node.get("fileStatus")
        if status == "READY" and (node.get("image") or {}).get("url"):
            image = node["image"]
            return {"id": file_id, "url": image["url"],
                    "width": image["width"], "height": image["height"]}
        if status == "FAILED":
            raise ShopifyError(f"Shopify could not process {path.name}")
        time.sleep(2)
        waited += 2
    raise ShopifyError(
        f"{path.name} is still processing after {poll_for}s. It is in Files "
        f"as {file_id}; re-run to pick up the URL."
    )


def delete(shop: Shop, file_ids: list[str]) -> list[str]:
    node = shop.gql(
        "mutation($ids: [ID!]!) { fileDelete(fileIds: $ids) "
        "{ deletedFileIds userErrors { field message } } }",
        {"ids": file_ids},
    )["fileDelete"]
    shop._check_user_errors(node, "fileDelete")
    return node["deletedFileIds"]
