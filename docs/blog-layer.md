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

## A section only exists once something is filed under it

The strip across the top — All, Blog, Vlog, Series, Review, Letters — is built
from the tags the blog actually carries, not from a fixed list. A section with
no entries is left out, because a tab that leads to an empty page is worse than
no tab. **Hide a section with no entries** turns this off while the paper is
filling up.

Series needs **two** tags, and this is the one place the convention is not
obvious: a post in a series carries `series` *and* `series-matheran`. The bare
tag is what the Series tab looks for and what Shopify's tagged URL matches; the
slugged one is what ties a single trip together at the foot of a report. With
only the slugged tag the Series tab used to appear and lead nowhere — it now
stays hidden instead, which is the symptom, not the fix. Write both.

An empty section does not borrow the empty-blog copy. "The first report is on
its way" is true of a blog with nothing in it and false of a Vlog tab on a
paper that already has reports, so a filtered page with no entries says so in
its own words and offers the way back. Its heading is the section's own name,
which is also what the Index heading becomes on any filtered page: standing on
the Vlog page, the list is headed VLOG, not Index.

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

## Fonts are a setting, not a decision baked into the code

The type is Fraunces plus Space Grotesk and that is the default, but it is a
dropdown, not a fact. Each section carries a **Font set** setting with seven
ready pairings and a Custom option, so the type can be changed from the theme
editor without touching a file.

The CSS reads three variables rather than naming families directly:

| Variable | Used by |
|---|---|
| `--dh` | the nameplate, headlines, sub-headings, index titles, product names, the numbers in the field log |
| `--d`  | body text, standfirsts, the italic dek |
| `--s`  | every small uppercase label — kickers, bylines, furniture |

Three slots rather than two is what makes a set like *Tabloid* usable: Anton
can carry the headline while Newsreader carries the paragraph underneath. Two
slots would force one face to do both, and a display face set at 15px for
three hundred words is unreadable.

Each section fetches its own stylesheet from Google Fonts, built from the
chosen set. That is why changing the blog's type cannot affect the rest of the
store: nothing outside these two sections reads these variables or that link.

`font-synthesis-weight: none` is set on the section root. Several of the sets
ship only a regular weight, and a browser asked for 700 will otherwise smear
the outline to fake it. Refusing the fake is the lesser evil — the headline
renders lighter than the design intends, which reads as a different choice
rather than as a mistake.

The Custom option takes plain Google Fonts family names and requests only the
regular weight, because a v2 request naming a weight the family does not have
fails outright and takes the whole stylesheet down with it. Any slot left
empty keeps the house font, and the house stylesheet is then requested
alongside the custom one.

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
moved from `SYNOR work copy 4` to `SYNOR work copy 5`, `SYNOR work copy 6` was
being edited the next morning, and by that afternoon the work had moved on
again to `SYNOR work copy 7`.

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

Verified at build time: neither the live theme nor `work copy 6` contained
any `sa-blog-*` or `sa-article` file, and both still carried stock Dawn
`blog.json` / `article.json`. Nobody else is doing blog work, so the merge had
nothing to collide with. Re-check before installing into a new fork.

## Where it actually lives

The layer was installed into **`SYNOR work copy 6`** (188819407143), and
`SYNOR work copy 7` (188836217127) was forked from it afterwards, so copy 7
carries the whole layer already — all fourteen files, every checksum
identical:

| File | Bytes | md5 |
| --- | --- | --- |
| `sections/sa-blog-list.liquid` | 30132 | `e4d1a2de1fd5b145c201a6d81f8e0fae` |
| `sections/sa-article.liquid` | 42407 | `9ff799a515035e3d347a9a86ab8af0ad` |
| `snippets/sa-blog-list-css.liquid` | 15892 | `f3a2d94a3565a67f5d09e53f4bd89832` |
| `snippets/sa-blog-fieldbox.liquid` | 3026 | `5255a3fc318e76fbea1278c97da0e10c` |
| `snippets/sa-blog-taxbar.liquid` | 2668 | `760b6e387b77c79ca505d4d4a8c31b9e` |
| `snippets/sa-blog-field.liquid` | 2356 | `0658e622902a5d536fc0400bd88869b2` |
| `snippets/sa-blog-video.liquid` | 1445 | `fff2387f75ce80bfae1644d8cc9ea2f9` |
| `snippets/sa-blog-product.liquid` | 3046 | `0259aef64830faa8684d37003d3c83e8` |
| `snippets/sa-blog-alsorow.liquid` | 2000 | `36fdecc6677296f076713b6116cbb093` |
| `snippets/sa-blog-seo.liquid` | 3356 | `d8d30c573d8bfc623ffd487b2e5f47ce` |
| `templates/blog.json` | 172 | `6f7c5095da93e279671803490cf016ea` |
| `templates/article.json` | 179 | `624f3c42eb7f948f91f375c2f2e62769` |
| `sections/header-group.json` | 12140 | `0aadc815050e3f8f4d156a8739f5f147` |
| `sections/footer-group.json` | 9277 | `bc1461ff84a9faea1d3fb14ab080979b` |

**That checksum table is the point of this section.** A theme copy taken
from a copy looks fine and can quietly be missing a file, so the way to check
a new fork is to ask the Admin API for these fourteen filenames and compare
the md5s, not to open the editor and see that the blog looks right.

The table itself proved that. It was first written with thirteen rows, and
`sa-blog-seo.liquid` — the JSON-LD snippet, rendered from `sa-article.liquid`
line 236 — was the one left out. A list kept by hand drifts; the fix is to
generate the check from the files, which is what the loop below does.

```bash
# Compare a fork against this table. Prints every file and whether it matches.
for f in sections/sa-blog-list.liquid sections/sa-article.liquid \
         snippets/sa-blog-list-css.liquid snippets/sa-blog-fieldbox.liquid \
         snippets/sa-blog-taxbar.liquid snippets/sa-blog-field.liquid \
         snippets/sa-blog-video.liquid snippets/sa-blog-product.liquid \
         snippets/sa-blog-alsorow.liquid snippets/sa-blog-seo.liquid \
         templates/blog.json templates/article.json \
         sections/header-group.json sections/footer-group.json; do
  md5sum "$f"
done
```

The menu and footer entries came across with the two group files, so there is
nothing to add in the theme editor: `header-group.json` carries the
`l_diaries` block *and* has it in `block_order`, and `l2` (Find my scent) and
`l3` (Golden Scent Pass) are still in `blocks` but out of `block_order`, which
is how they stay hidden without being lost.

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
