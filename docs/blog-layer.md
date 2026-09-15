# SYNOR — blog layer

The store had no blog. Both blogs in the admin (`News`, `Our Blogs`) were
empty, and the theme had no `blog.json`, no `article.json` and no blog
sections — so a post published today would have landed on Dawn's stock
template, in Dawn's stock type, with none of the store's paper-and-gold
character and none of its selling surface.

This layer is the blog: a listing page, an article page, and the three
snippets they share. It is additive — new files only, nothing existing was
edited — in the same way the desktop layer was added.

(The live theme is `SYNOR work copy 4`. `desktop-layer.md` still calls it
`Updated copy of gokwikbundler`, which was its name when that layer was
written.)

The vision behind it is four words: **rank, SEO, sell, content**. The article
page is where those meet. It has to read like an editorial page, carry video
without wrecking page speed, put the product within one tap of the paragraph
that sells it, and emit the structured data that gets a post into Google's
rich results.

## Files

| File | What it is |
| --- | --- |
| `templates/blog.json` | New. Points the blog listing at `sa-blog-list`. |
| `templates/article.json` | New. Points the article page at `sa-article`. |
| `sections/sa-blog-list.liquid` | New. Listing: featured post, grid, topic pills, pagination, empty state. |
| `sections/sa-article.liquid` | New. The article page, top to bottom. |
| `snippets/sa-blog-seo.liquid` | New. JSON-LD — BlogPosting, BreadcrumbList, VideoObject. |
| `snippets/sa-blog-video.liquid` | New. YouTube thumbnail that becomes an iframe on click. |
| `snippets/sa-blog-product.liquid` | New. Product card for inside a post, 3ml tester first. |

Nothing was changed in `layout/theme.liquid`. The sections carry their own
`<style>` blocks, scoped by section id, exactly as `sa-drops.liquid` does —
see *Specificity* in `desktop-layer.md` for why a stylesheet in `assets/`
cannot win against a section's own ID-scoped rules.

## The tag language

Everything variable about a post — its videos, its products, its series, its
kind — is read off the article's **tags**.

| Tag | Effect |
| --- | --- |
| `vlog` (or `live`) | Video-first layout: the video sits above the writing, not below it. |
| `yt-<VIDEOID>` | A YouTube video. Several are allowed; they render in tag order. |
| `pick-<product-handle>` | That product gets a buy card under the post. Up to 6. |
| `series-<slug>` | Marks the post as part of a series, and links the others in it. |
| `guide` `review` `story` `news` | Sets the eyebrow word above the title. |
| `family-*` `occasion-*` `season-*` `scent-*` `mood-*` `gender-*` | Topic pills, linking to the filtered listing. |

Tags, rather than metafields, because a tag is one field on the article that
the Admin API can write in the same call that creates the post — no metafield
definitions, no app, no second request. It also means the blog speaks the
same language the catalogue already speaks: the 50 products are tagged
`family-woody-oud`, `occasion-wedding`, `season-winter` today, so a post
tagged the same way is filed beside them without a new vocabulary.

Internal tags (`yt-`, `pick-`, `series-`) are hidden from the listing's pill
row. They are instructions, not topics.

**One caveat.** YouTube IDs are case-sensitive (`dQw4w9WgXcQ`). Shopify
preserves tag case, so `yt-` tags work — but if a tag's case is ever mangled
by an import or a third-party app, the video breaks silently. For that case
the article metafield `custom.youtube_ids` (comma-separated) overrides the
tags when it is set. Belt and braces; the tags are the normal path.

## SEO

Dawn's `meta-tags` snippet, rendered from `theme.liquid`, already emits the
`og:` and `twitter:` tags for an article. Emitting them again here would give
every post two of each, so this layer does not touch them.

What Dawn does *not* emit is article-level JSON-LD, and that is what
`sa-blog-seo.liquid` adds:

- **BlogPosting** — headline, description, image, published and modified
  dates, author, publisher. This is what makes a post eligible for an article
  result rather than a plain blue link.
- **BreadcrumbList** — Home › Blog › Post, so the search result shows the
  path instead of a bare URL.
- **VideoObject** — only when the post has a video. A vlog post can then
  surface with a video thumbnail in search, which is a second way into the
  same page.

Every value passes through the `json` filter. That matters more than it
looks: `SYNOR Queen's Victory` contains an apostrophe, and one unescaped
apostrophe invalidates the whole block — at which point Google discards it
without reporting anything.

Reading time is counted in Liquid at 200 words per minute. The table of
contents is built in the browser from the `h2`s in the post body, because
Liquid cannot parse the HTML that `article.content` returns.

## Video without the page-speed cost

A YouTube `<iframe>` pulls roughly 1.5MB of player before anyone presses
play, and page speed is a ranking factor — so a blog built on embedded video
can lose on speed exactly what it wins on content.

`sa-blog-video.liquid` renders a thumbnail and a play button. No YouTube
script loads at all until the visitor clicks; then the iframe is injected
with `autoplay=1`, on `youtube-nocookie.com` so nothing is set on the
visitor until they have asked for the video.

The thumbnail is `hqdefault.jpg`, not `maxresdefault.jpg`: maxres does not
exist for every video and fails as a broken image, while hqdefault always
does. It is 480×360 with the 16:9 frame centred, so `object-fit: cover` on a
16:9 box crops the letterboxing away exactly.

## Selling from inside a post

`sa-blog-product.liquid` leads with the **3ml tester at ₹49**, not the 100ml
bottle. Someone who has just read about a scent will agree to ₹49 far more
readily than to ₹1299, and the tester is what brings them back for the
bottle. The card links to the product page with the tester variant
pre-selected rather than adding to cart directly, so the GoKwik and bundlr
flows in `theme.liquid` are never bypassed.

Each post also closes on the same offer, as a panel under the writing.

## Layout

Mobile-first, like the rest of the theme.

- The reading column is 760px by default — about 70 characters a line, which
  is where long-form reading is comfortable.
- At ≥900px the type scales up and the product cards go to two columns.
- At ≥1140px the table of contents becomes a sticky rail to the left of the
  text. The title, lead image and footer blocks take the same left offset
  from the same arithmetic as the grid, so the page keeps one left edge all
  the way down instead of the two that a guessed `calc()` produces.

The listing gives the newest post the full width on desktop, because the
first thing a visitor's eye lands on should be the newest thing written.

**The empty state is not decoration.** Both blogs have zero posts right now,
so without it the page would read as broken on the day it goes live. It says
the first post is coming and points at the shelf.

## How it was installed

The seven files were written straight into Shopify through the Admin API,
into a **duplicate of the live theme** named `SYNOR blog preview`, not into
the live theme itself. The live theme (`SYNOR work copy 4`) was not touched.

A copy rather than the live theme for two reasons. The obvious one: nobody
should find out a page is broken by being a customer looking at it. The less
obvious one: the person who has to approve this design cannot read Liquid, so
"it is correct" has to mean "you can look at it", and looking at it needs a
URL that is not the shop.

Each upload returned the file's MD5, and every one matched the working copy in
this repository byte for byte. The files in the preview theme are the files
here — not a close retyping of them.

Two validation errors came back from Shopify during the upload, both real:

- `templates/blog.json` was rejected before the sections existed, because a
  template cannot name a section type that is not in the theme yet. Sections
  and snippets first, templates last.
- `sa-blog-list.liquid` was rejected for `"default": ""` on a text setting.
  Shopify does not allow an empty-string default — the key has to be omitted.
  The Liquid already falls back to the blog's own name with a `default`
  filter, so nothing was lost by dropping it.

Both are the sort of thing a local checker should have caught, and the
checker now does.

### What is left to do by hand

1. **Publish** `SYNOR blog preview` in Shopify admin → Online Store → Themes.
   Theme publishing cannot be done through the API from here, by design, so
   this is a deliberate human step. Publishing the copy makes it live; any
   edit made to the current live theme in the meantime would be left behind
   in it, so publish while nothing else is in flight.
2. **At least one article has to exist** before the article page can be seen
   at all. Both blogs are empty, so `/blogs/*/…` has nothing to render.
3. Optionally adjust the section settings in the theme editor. Every word,
   colour, size and spacing is a setting; nothing is hard-coded.

The two buttons that would otherwise ship pointing nowhere are set in the
template files: the article's closing offer goes to `/pages/try-before-you-buy`,
and the listing's empty-state button to `/collections/all`. Shopify rewrites
`templates/*.json` whenever the theme editor saves, so those two values are
defaults, not settled facts — expect the files here and in the theme to drift
once the editor has been used.

## Not in this layer

The auto-poster and the social fan-out are deliberately absent. Neither
belongs in a theme: a theme renders what is already in Shopify, it cannot
write to it or run on a schedule. Both need a scheduled job outside the
storefront, talking to the Admin API — the tag language above is the contract
it will write against.
