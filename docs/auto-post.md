# The writing agent — one tap to publish

Track 2. A bot writes a SYNOR Diaries entry and files it in Shopify as a
**draft**. Nothing goes live until a person opens it and presses Publish.

That split is the whole design. The expensive, slow part of a blog is not
publishing, it is writing: the reporting, the tagging, the field log, the six
products picked correctly, the HTML. The bot does all of that. The part a
person is actually needed for — reading it and deciding it is good enough to
carry the shop's name — stays a human action, and it costs one tap.

## What happens on a run

1. It takes the first topic in `bot/queue.json` whose status is `todo`.
2. It reads the live catalogue from Shopify. So the entry can only recommend
   products that exist right now, with the tags they actually carry today.
3. It builds the list of **names that must never be printed** from the
   catalogue itself — every `brand-*` tag and every free-text tag, which is
   where the designer references and celebrity names live. The catalogue the
   writer sees has those tags stripped out, so the names never enter the
   prompt to begin with.
4. Claude writes the entry against `bot/house-style.md`, returning it as
   structured JSON — title, summary, body HTML, filing tags, field log, notes.
5. The draft is **checked** (see below). Every failure is sent back as a
   rewrite instruction, up to three rounds. If it still fails, nothing is
   filed and the run ends red.
6. The entry is created with `isPublished: false`, tags and metafields
   attached, and the admin link is printed.
7. The topic is marked `drafted` in the queue and the change is committed.

## What the checks catch

The checks exist because a writer with no eyes on the storefront will make
exactly these mistakes, and each one would be visible on the live page.

| Check | Why |
| --- | --- |
| No other perfume house's name, no celebrity's name | The product tags carry them for filtering. The paper does not print them. |
| Only real product handles, three to six of them | An invented handle is a 404 in the middle of a post. |
| Every product filed as a pick is actually written about | Otherwise the `pick-*` tag sells something the entry never discussed. |
| Filed families must belong to a recommended product | The family drives the spot colour and the index square. |
| Body opens with a `<p>` | The theme sets a drop cap on the first paragraph's first letter. |
| Only the HTML tags the article page styles | A stray `<div>` or inline style breaks the column. |
| 700–1100 words, one pull quote, no exclamation marks | House style, mechanically. |
| Handle is URL-safe and not already used | Shopify would silently append `-1`. |
| Field log filled | The box is printed beside the text; a half-empty one looks broken. |
| A `series` entry has a slug | It needs **both** `series` and `series-<slug>`. |

## Files

| File | What it is |
| --- | --- |
| `bot/house-style.md` | The writing contract: what SYNOR is, the voice, the hard rules, the shape of an entry, the closed tag sets. **This is the file to edit to change how the paper reads.** |
| `bot/queue.json` | The topic queue. Each topic is a brief, a place and a month. |
| `bot/write_draft.py` | The agent. Prompting, the checks, the rewrite loop, filing. |
| `bot/synor_shopify.py` | The Admin API calls, and the forbidden-names list. |
| `.github/workflows/diaries-draft.yml` | Runs it. Manual for now. |

## Setting it up

Three secrets, in **GitHub → Settings → Secrets and variables → Actions →
New repository secret**. They are never written into the code and never
printed by a run.

| Secret | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | From console.anthropic.com → API keys. |
| `SHOPIFY_STORE` | `perfume-rat` — the **myshopify** name, not `synorperfume.com` |
| `SHOPIFY_ADMIN_TOKEN` | See below. |

Those two names confuse people, so: a Shopify store has a fixed
`*.myshopify.com` name from the day it is created, and a public domain put on
top of it later. `synorperfume.com` is the one customers see; `perfume-rat` is
the one the Admin API answers on, and Shopify never lets it change. It is the
last part of the admin URL: `admin.shopify.com/store/perfume-rat`. Giving the
public domain here is caught with a message saying so, rather than failing as
a DNS error on `synorperfume.com.myshopify.com`.

The admin token comes from a custom app, not from a password:

1. Shopify admin → **Settings → Apps and sales channels → Develop apps**.
2. **Create an app**, call it `SYNOR Diaries bot`.
3. **Configuration → Admin API integration → Configure**, and tick exactly
   two scopes: `write_content` (so it can create articles) and
   `read_products` (so it can read the catalogue). Nothing else — the bot has
   no business near orders or customers.
4. **Install app**, then reveal the **Admin API access token** once and paste
   it into the GitHub secret. Shopify shows it a single time.

Then: **Actions → Diaries · write a draft → Run workflow**. Tick **dry run**
the first time — it writes the entry and prints it in the run log without
touching Shopify, which is the cheap way to read the voice and adjust
`bot/house-style.md` before anything is filed.

## Running it locally

```bash
pip install -r bot/requirements.txt
export ANTHROPIC_API_KEY=...
export SHOPIFY_STORE=perfume-rat
export SHOPIFY_ADMIN_TOKEN=...
python bot/write_draft.py --dry-run
```

## Putting it on a schedule

Uncomment the `schedule` block at the foot of the workflow. It is written for
Tuesday and Friday at 09:00 IST. Do that once a few drafts have come out
right — not before, because a schedule on an untuned voice just fills the
drafts folder with entries nobody wants to publish.

## What it deliberately does not do

- **It does not publish.** There is no code path that sets `isPublished: true`.
- **It does not touch the theme.** Sections, snippets and templates are not
  its business.
- **It does not invent a customer quote.** If a brief has no real review in
  it, the entry does without one.
- **It does not choose products the tags do not support.** The catalogue is
  the only source, and a family filed without a matching product is a failed
  check, not a judgement call.

## Cost and model

It runs on `claude-opus-5` with adaptive thinking at high effort, because the
output is published under the shop's name and the difference between a good
entry and a passable one is the whole point of the exercise. One entry is a
single call plus, sometimes, a rewrite round. The house style and the
catalogue are sent as a cached prefix, so repeated runs pay full price only
for the brief.

Server-side refusal fallbacks are on by default: if the model declines a
brief on policy grounds, Anthropic re-runs the same request on a fallback
model inside the same call rather than the run simply failing. Set
`SYNOR_FALLBACKS=off` to turn that off.
