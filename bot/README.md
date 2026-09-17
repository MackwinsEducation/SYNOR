# bot — the SYNOR Diaries writing agent

Full explanation: [`../docs/auto-post.md`](../docs/auto-post.md).

The short version: `write_draft.py` takes a topic from `queue.json`, writes an
entry against `house-style.md`, checks it, and files it in Shopify as a
**draft**. A person publishes it.

```bash
pip install -r requirements.txt
python write_draft.py --dry-run          # write it, print it, file nothing
python write_draft.py                    # file it as a draft
python write_draft.py --topic gym-bag-heat
```

Needs `ANTHROPIC_API_KEY`, `SHOPIFY_STORE`, `SHOPIFY_ADMIN_TOKEN` in the
environment. In CI they come from GitHub secrets. **Never put a key in a file
in this repository.**

To change how the paper reads, edit `house-style.md`. To change what it writes
about, edit `queue.json`. Neither needs a code change.
