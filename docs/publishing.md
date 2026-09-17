# The publisher — posting it for real

Track 5. Reads a pack written by Track 4 and posts it. Instagram gets the reel
with its caption and the hashtags as the first comment; the Facebook Page gets
the text post with its link.

```bash
python bot/publish.py --pack 2026-09-17-lift-test \
    --video-url https://cdn.shopify.com/s/files/.../lift-test.mp4
```

That command posts **nothing**. Read on.

## Publishing is never the default

A draft article can be deleted. A published reel has already been seen. So
this is the one agent in the set where the safe path is the default one:

- **Without `--publish`, it is a preflight.** It checks the tokens, resolves
  and prints the account names it is about to post as, verifies the video is
  actually reachable and really is a video, re-checks the copy, and prints
  exactly what would go out. Then it stops.
- **`--publish` is the only way anything goes live**, and in the workflow the
  "Actually post" box defaults to off.
- **There is no schedule.** Manual trigger only. A scheduled poster is how a
  shop wakes up to something it did not approve.
- **A pack that already went out is refused** — the publisher writes
  `bot/social/<pack>.posted.json` with the media id and the permalink, and
  will not post the same pack twice unless you pass `--again`.

## The copy is re-checked at the point of no return

Track 4 checked the pack when it wrote it. The publisher checks it **again**,
right before posting, because a pack is a file and a file can be hand-edited
after it was approved. Two things are re-run against the live catalogue: the
forbidden-names list, and the rule that ₹49 is the only price that may appear.

## Tokens never reach the log

A run happens in GitHub Actions, and Actions logs are kept. A token echoed
once in a stack trace is a token that has to be rotated. So:

- The access token is sent in the **POST body**, never in the query string,
  so a URL in an error message carries no secret.
- Every error string goes through a scrubber that redacts both
  `access_token=…` patterns and the literal token value.

## What happens on an Instagram publish

The Reels flow is three calls and a wait, not one upload:

1. `POST /{ig-user-id}/media` with `media_type=REELS`, the `video_url` and the
   caption. This returns a **container id** — nothing is posted yet.
2. Instagram fetches and transcodes the video on its own time. The publisher
   polls `GET /{container-id}?fields=status_code` until it reads `FINISHED`,
   backing off from 10s up to a five-minute ceiling, which is Meta's own
   guidance.
3. `POST /{ig-user-id}/media_publish` with the container id. Now it is live.
4. `POST /{ig-media-id}/comments` puts the hashtags in the first comment.

Step 4 is deliberately **non-fatal**. By then the reel is public, so a failed
comment must not fail the run — it prints the text and tells you to paste it,
which is one tap.

If step 2 times out, the container stays valid for 24 hours, so re-running
picks it up instead of re-uploading.

If Instagram returns `ERROR` while processing, it is almost always the video:
**9:16, under 90 seconds, H.264 video and AAC audio in an MP4** is the safe
envelope.

## Getting the video to a public URL

This is the one thing the publisher cannot do for you, and it is worth
understanding why: **Instagram fetches the file itself.** It does not accept
an upload from the API. So the video has to already be sitting at an address
Instagram's servers can read.

The easy way, using the store you already have:

1. Shopify admin → **Content → Files**.
2. Drag the video in.
3. Click the copy-link icon. That gives a `cdn.shopify.com` URL, which is
   public and fast.
4. Paste it into the workflow's **video_url** box.

The preflight does a HEAD request on whatever you paste and tells you the
content type and the file size before spending an API call, so a wrong link
fails in two seconds rather than five minutes.

## Setting it up

Three more secrets, alongside the ones the other agents use.

| Secret | Value |
| --- | --- |
| `META_ACCESS_TOKEN` | A long-lived **Page** access token |
| `IG_USER_ID` | The Instagram Business account's numeric id |
| `FB_PAGE_ID` | The Facebook Page's numeric id |

Getting them, once:

1. The Instagram account has to be a **Business or Creator** account, and it
   has to be **linked to a Facebook Page**. Instagram app → Settings →
   Account type and tools. This is the step people skip; nothing below works
   on a personal account.
2. **developers.facebook.com** → My Apps → **Create App** → type **Business**.
3. Add the **Instagram Graph API** and **Facebook Login for Business**
   products.
4. In the **Graph API Explorer**, pick your app, and request these
   permissions: `instagram_basic`, `instagram_content_publish`,
   `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`,
   `pages_manage_posts`.
5. Generate a user token, then exchange it for a **long-lived Page token** —
   `GET /me/accounts` returns your Pages each with its own `access_token` and
   `id`. The `id` is your `FB_PAGE_ID`; that `access_token` is
   `META_ACCESS_TOKEN`.
6. `GET /{page-id}?fields=instagram_business_account` returns the
   `IG_USER_ID`.
7. Put all three into **GitHub → Settings → Secrets and variables → Actions**.

Then: **Actions → Social · post it → Run workflow**. Fill in the pack stem and
the video URL and **leave "Actually post" off**. Read what the preflight
prints. When it looks right, run it again with the box ticked.

## Limits worth knowing

- **25 Instagram posts per rolling 24 hours** per account, API-wide.
- The Page token expires if the app's permissions change or the password is
  reset. When that happens the preflight fails with a clear Graph API message
  rather than posting half a pack.
- Stories and carousels are separate publishing flows and are **not** wired
  up. The pack writes that copy; you post those two by hand. Carousels need
  the slide images to exist, and nothing generates those yet.

## What is still yours

| Step | Who |
| --- | --- |
| Point the camera | you |
| Drop the video into Shopify Files, copy the link | you |
| Decide the draft is good enough to publish | you |
| Reel to Instagram, first comment, post to Facebook | the bot |
| Story, carousel, YouTube, WhatsApp, X, Pinterest | you, from the pack |

YouTube stays manual on purpose: `videos.insert` needs the file, and the file
is on the phone that shot it — so the upload is happening by hand anyway, and
that is exactly the moment the title and description get pasted in from the
pack.
