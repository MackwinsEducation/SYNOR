# SYNOR Diaries — the blog layer

The store had no blog. Both blogs in the admin were empty, and the theme had
no `blog.json`, no `article.json` and no blog sections, so a post published
today would have landed on Dawn's stock template with none of the store's
character and nothing on it to sell with.

This layer is the blog, and it is built as a **newspaper**: a front page with
a nameplate, a lead report and an index, and inside pages that carry one
report each.

## Why a newspaper

Not for the look. Because every piece of a newspaper's furniture already had
a job waiting for it here:

| Newspaper | What it became |
| --- | --- |
| Spot colour — old papers printed in black ink and *one* colour | The post's **fragrance family**. Four families, four colours, nothing else coloured. |
| The weather box in the corner | The **field log** — place, altitude, temp, humidity, hours held, people asked. A dispatch's weather is not decoration here: perfume behaves differently in 68% humidity, which is the whole point of going outside with a bottle. |
| The cover price on the front page | **₹49 a tester**, printed where a paper prints its price. |
| Classifieds — dense, plain, scannable | The **index**. Every entry, one line each. |
| The folio at the foot of the page | `Synor Diaries · No. 07 · synorperfume.com` |
| The letters page | Entries tagged `letter` — real customer reviews, set as letters. |

It also solved a constraint the owner set: **no black.** Newsprint stock is
cream and newspaper ink is a warm near-brown, so the register has no black in
it to begin with — `#F6F2E7` paper, `#26211A` ink. The brief and the medium
happened to want the same thing.

## Two voices, on purpose

The front page is **quiet** and the inside page is **loud**, which is the
reverse of a real paper. That is deliberate.

- **Front page** — fewer rules, no boxes, one large standfirst instead of two
  columns of small type, lighter weights, colour reduced to a single 6px
  square. Phone-sized two-column body text is the single clearest tell of
  cheap newsprint, so there is none.
- **Inside page** — 40px headline at weight 900, uppercase, a coloured kicker
  block, 2px rules, a drop cap in the family colour, pull quotes reversed out
  of that colour.

The reasoning: a reader on the index is *browsing* and needs calm to scan; a
reader who has opened a report has already committed, and that is the moment
to hold them and sell. Restraint where the eye chooses, force where the
decision happens.

## Files

| File | What it is |
| --- | --- |
| `templates/blog.json` | Points the blog listing at `sa-blog-list`. |
| `templates/article.json` | Points the article page at `sa-article`. |
| `sections/sa-blog-list.liquid` | Front page: nameplate, section bar, dateline, lead report, field row, index, pagination, empty state. |
| `sections/sa-article.liquid` | Inside page: strip, ribbon, headline, cut, field log, body, notes, products, share, closing notice, also-in-this-issue. |
| `snippets/sa-blog-field.liquid` | The field log. Renders only the values that exist. |
| `snippets/sa-blog-video.liquid` | YouTube as a thumbnail until clicked. |
| `snippets/sa-blog-product.liquid` | A product as a classified ad, tester first. |
| `snippets/sa-blog-taxbar.liquid` | The topic filter row, built from the blog's own tags. |
| `snippets/sa-blog-alsorow.liquid` | One row of "Also in this issue". |
| `snippets/sa-blog-seo.liquid` | JSON-LD — BlogPosting, BreadcrumbList, VideoObject. |

Nothing in `layout/theme.liquid` was changed, and no existing file was
touched. Each section carries its own `<style>`, scoped by section id, as
`sa-drops.liquid` does — see *Specificity* in `desktop-layer.md` for why a
stylesheet in `assets/` cannot win against a section's own ID-scoped rules.

## The tag language

Everything variable about an entry is read off its **tags**.

| Tag | Effect |
| --- | --- |
| `blog` `vlog` `review` `letter` | The kind. Also the section bar's filters. |
| `series-<slug>` | Part of a series; links the others at the foot of the page. |
| `yt-<VIDEOID>` | A film. Several allowed; they render in tag order. |
| `pick-<product-handle>` | That product appears as a classified ad. Up to 6. |
| `gender-*` `occasion-*` `family-*` `brand-*` | The topic filter row, and the spot colour. |

Tags rather than metafields for these, because a tag is one field the Admin
API writes in the same call that creates the post — no definitions, no app,
no second request. It also means the blog speaks the language the catalogue
already speaks.

### Only four namespaces are the shop's

The products carry more than the storefront navigates by. `season-*`,
`mood-*` and `scent-*` exist on every product, and there are collections
built on them — Winter Season, Bold & Powerful, Elegant — but the menu uses
none of them. What it uses is four: gender (3), occasion (6), fragrance type
(4), and the inspired house behind each scent (`brand-*`).

So the topic row is an allowlist of exactly those four. A reader should meet
the same handful of words on a post that they meet in the menu; offering them
"winter" sends them somewhere the shop does not sort by. The row also drops
the namespace before printing — `occasion-office` reads as "office". The
prefix is how the bot addresses the theme, not language for a customer.

## Metafields — the field log

Six numbers as six tags would be unreadable, so the field log comes from
article metafields in the `custom` namespace:

`field_place` · `field_alt` · `field_temp` · `field_humidity` ·
`field_held` · `field_asked` · `field_coords`

Also `youtube_ids` (comma-separated, wins over `yt-` tags — YouTube IDs are
case-sensitive and a tag's case can be mangled by an import), `notes_top` /
`notes_heart` / `notes_base` for the notes table, and `entry_no` for the
number in the masthead.

**Every one of them is optional.** A missing value drops its cell; all six
missing drops the whole block. That is what keeps a written guide clean and a
vlog dispatch instrumented, from one template.

The definitions still have to be created in the Shopify admin before the
fields appear there as boxes to type into. Until then the blocks simply
don't render — nothing breaks.

## "Latest first" is a label, not a button

Shopify's blog always returns newest first and Liquid cannot reorder it.
A sort control would therefore have to lie, or reorder only the current page,
which is worse. So the index states its order as a fact and the real filters
— kind and topic — are the ones that work.

## Video without the page-speed cost

A YouTube `<iframe>` pulls roughly 1.5MB of player before anyone presses
play, and page speed is a ranking factor. `sa-blog-video.liquid` renders a
thumbnail and a ring; no YouTube script loads until the visitor clicks, and
then the iframe is injected on `youtube-nocookie.com`.

The thumbnail is `hqdefault.jpg`, not `maxresdefault.jpg`: maxres does not
exist for every video and fails as a broken image, while hqdefault always
does. It is 480×360 with the 16:9 frame centred, so `object-fit: cover`
crops the letterboxing away exactly.

## Selling from inside a report

`sa-blog-product.liquid` leads with the **3ml tester at ₹49**, not the
bottle. Someone who has just read about a scent will agree to ₹49 far more
readily than to ₹1,499, and the tester is what brings them back. The ad links
to the product page with the tester variant pre-selected rather than adding to
cart, so the GoKwik and bundlr flows in `theme.liquid` are never bypassed.

## Installing it — read this first

The store has **more than one session working on it**. Themes were being
published from elsewhere while this layer was being built: the live theme
moved from `SYNOR work copy 4` to `SYNOR work copy 5`, and `SYNOR work copy 6`
was being edited the next morning.

**Publishing a theme replaces the whole theme, not your part of it.** So:

> Only one theme copy may ever be published, and it must be forked from the
> live theme at the moment of publishing.

Otherwise whoever publishes last wins and the other sessions' work is gone.

Because this layer is **new files only**, it should go in **last** and is the
easiest to merge:

1. The other sessions finish; one of their copies is published and becomes live.
2. Fork *that* theme, fresh.
3. Copy these files into the fork (`themeFilesCopy` between themes — no
   re-uploading).
4. Publish the fork.

`SYNOR blog preview` (id 188802629927) holds an early version of this layer
and was forked from `work copy 4`. **It must not be published** — it is two
generations behind and would roll the store back. Treat it as a holding pen.

Verified at build time: neither the live theme nor `work copy 6` contains any
`sa-blog-*` or `sa-article` file, and both still carry stock Dawn
`blog.json` / `article.json`. Nobody else is doing blog work, so the merge
has nothing to collide with. Re-check before installing.

`templates/blog.json` and `templates/article.json` do replace existing files;
the originals are kept in `docs/theme-backup/`.

## What this layer is not

The auto-poster and the social fan-out are deliberately absent. Neither
belongs in a theme: a theme renders what is already in Shopify, it cannot
write to it or run on a schedule. Both need a scheduled job outside the
storefront, talking to the Admin API — the tag language above is the contract
it will write against.

## Directions that were tried and dropped

Five went past the owner before this one, and the rejections were the useful
part:

1. **A conventional blog** — cards, pills, a hero. Competent and forgettable.
   Rejected for having no point of view.
2. **Dispatches** — an expedition journal with a near-black "night" register
   for vlogs. Rejected on the colour: *"black mane nathi gamtu."* The lesson
   was larger than the colour — "adventure means dark" was a lazy equation.
3. **Blotter** — every post a perfumer's test strip, dipped at one end, the
   stain coloured by fragrance family. The colour idea survived; everything
   else was still a list, and a list has no moment in it.
4. **The Index** — a book's contents page as the hero. Closer, but it wanted
   the furniture a periodical has, which is how the newspaper started.
5. **Naming.** *Sillage*, *Record*, *Ledger* were all cleverer than they were
   clear. The brief that settled it: a name should not need explaining, and
   should say what is inside. `Synor Diaries`, with the sections named as
   plainly as they are spoken — Blog, Vlog, Series, Review, Letters.

`Synorian` was offered as the paper's name and corrected: it is the
customers' name, the community's. So it sits under the nameplate instead —
*For the Synorians* — where a paper says who it is printed for.
