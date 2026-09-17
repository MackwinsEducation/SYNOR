# The distribution agent — one piece, eight rooms

Track 4. A bot takes one piece of work — a shoot sheet from Track 3, or a
published Diaries entry from Track 2 — and writes **every channel's copy
separately**, plus a schedule that spreads it over about a week.

```bash
python bot/write_social.py --from-shoot 2026-09-17-lift-test
python bot/write_social.py --from-article office-perfume-six-that-dont-crowd-the-room
```

## The point

The same caption pasted everywhere is why most brand social reads like a
robot, and it is what a naive "auto-poster" would do. So this agent writes
nine pieces of copy, and the checks enforce that they are actually different
from each other.

| Where | The room it is written for |
| --- | --- |
| **Instagram reel** | Sound off, thumb moving. The first line carries everything; hashtags go in the first comment, never the caption. |
| **Instagram story** | Three frames, six words each, one sticker that asks a real question. |
| **Instagram carousel** | Someone who already stopped. 5–8 slides, one idea each. |
| **YouTube** | Search. People arrive months later with a question, so the title is the question they typed. |
| **YouTube Shorts** | Same footage, different audience. Title under 45 characters, `#shorts`, and **not** the YouTube title. |
| **Facebook** | Older, reads more, hates hashtag blocks. Longer and plainer. |
| **WhatsApp** | People who already bought — the warmest list there is. Gujarati or Hinglish, under 400 characters, one link, no hashtags ever. |
| **X** | A 2–4 post thread. First post is the claim, last is the link. |
| **Pinterest** | Search, saved for later. The title is a search phrase; the description is useful without the image. |

## WhatsApp can say no

The one channel the agent is allowed to decline. The WhatsApp list is people
who already spent money, and a message that is not genuinely useful costs more
than it earns — so the pack has a `worth_sending` flag, and if it is false the
agent has to say **why**. That is on purpose: an agent that always finds
something to send to your buyers will burn the list.

## What the checks catch

Every platform limit that silently truncates copy, and every habit that makes
a brand look cheap.

| Check | Why |
| --- | --- |
| No other house's name, no celebrity's name, on any channel | Those tags are for filtering. Social does not say them. |
| No price but ₹49, and no "limited time", "hurry", "sale", "% off" | The only two real claims are the tester price and the credit. Invented urgency is the fastest way to stop being believed. |
| No "tag 3 friends", "comment YES", "double tap" | Engagement bait reads as desperate and Instagram discounts it anyway. |
| Reel caption under 280, **first line under 90** | 90 characters is where Instagram cuts it. |
| No hashtags in the reel caption; 5–10 lowercase ones in the first comment | Caption space is for the sentence that earns the second line. |
| Exactly 3 story frames, under 70 characters each, sticker must ask something | A frame is on screen for five seconds. |
| 5–8 carousel slides, under 120 characters each | One idea per slide, readable at arm's length. |
| YouTube title under 70, description over 200 characters, 5–15 tags | Search is a different medium from a feed. |
| Shorts title under 45, contains `#shorts`, **differs from the YouTube title** | Otherwise it is the same post twice. |
| Facebook over 200 characters and no hashtag block | That room reads and does not tag. |
| WhatsApp under 400, one link, zero hashtags — or a stated reason not to send | The warmest list gets treated like people. |
| Thread 2–4 posts, each under 270 | Room for a quote-reply. |
| Pinterest title under 100, description 100–500 | It has to work without the image. |
| Every product linked somewhere clickable | A pack that mentions a scent and never links it sells nothing. |
| Every product the piece is about is in the pack | Track 3 chose those scents; the pack cannot quietly drop one. |
| Schedule is 4–7 posts, starts on day 0, never twice on one channel in one day | One piece is a week of posts, not one post. |
| An honest line exists | One channel has to say the thing that is not flattering. It is what makes the rest believable. |

## Output

`bot/social/YYYY-MM-DD-<source>.md` — the pack, committed, and printed into
the Actions run summary so every block can be copied out on a phone.

`bot/social/YYYY-MM-DD-<source>.json` — the same fields, structured, for a
publisher to post from.

## Running it

**Actions → Social · write the pack → Run workflow.** Fill in *either* the
shoot sheet stem *or* an article handle, pick the WhatsApp language, and tick
**dry run** the first time.

Same three secrets as the other two agents — see
[`auto-post.md`](auto-post.md).

## About actually posting it automatically

Worth being straight about this, because "automatic distribution" sounds like
one button and is not.

**What genuinely blocks it**, per platform:

- **Instagram and Facebook.** The Graph API can publish reels and images, but
  it needs a Business or Creator account linked to a Facebook Page, a Meta
  app with `instagram_content_publish`, a long-lived page token that has to be
  refreshed, and — the real catch — **the video already hosted at a public
  HTTPS URL**, because Instagram fetches the file rather than accepting an
  upload. There is a 25-posts-per-day cap. Stories and carousels have separate
  flows again.
- **YouTube.** `videos.insert` needs OAuth2 with a stored refresh token, not
  an API key, and it needs the video file itself. Since the file is on the
  phone that shot it, the upload is happening by hand anyway — which is the
  moment the title and description get pasted in.
- **WhatsApp.** Status has no API at all. Broadcast needs the WhatsApp
  Business Platform, a verified business, and pre-approved message templates,
  which do not fit a one-off message about a blog post.
- **X and Pinterest.** Both have APIs; X's posting tier is paid.

So the honest sequence is: **the pack is the part that saves real time** —
knowing what to write for nine different rooms, checked against every limit,
is the work. Tapping share is thirty seconds.

If you want the posting automated too, the two that are actually worth wiring
up are Instagram and Facebook, since they share one token. That needs from
you: a Meta app, an Instagram Business account on a Page, and a place the
video lives publicly — Shopify Files can host it and gives a CDN URL, so the
store you already have would do. Say the word and that becomes Track 5.

## The whole chain, end to end

1. **Track 3** plans a shoot. You film it.
2. You upload the video to YouTube with the title and description from the
   pack, and put the id in the entry's `custom.youtube_ids` metafield.
3. **Track 2** writes the entry; you publish it with one tap.
4. **Track 4** writes the pack from either the shoot or the entry.
5. You post it over the week the schedule lays out.

Four of those five steps are written for you. The two that are yours are the
two that need a person: pointing a camera, and deciding it is good enough to
publish.
