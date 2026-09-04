# SYNOR — desktop layer

The storefront theme (`Updated copy of gokwikbundler`, live) was built
mobile-first. On a phone it is finished work; on a desktop it reads as a
narrow mobile page stretched across a wide screen. Three things cause that:

1. **No desktop navigation.** `sections/sa-header.liquid` renders a phone bar
   — hamburger, logo, search icon, cashback pill — and puts the whole menu in
   a left drawer. Its only desktop rule bumps padding and the wordmark by 4px.
   There was also no cart or account control anywhere in the header.
2. **Mobile type scale everywhere.** Footer links are 12.5px, secondary text
   9.5px, the crest tagline 7.5px. Those sizes are right at 390px and far too
   small at 1440px.
3. **Containers without content scale.** Sections cap at 1120–1200px but the
   controls, cards and type inside them stay phone-sized, so the page reads as
   a small column floating in white space.

## Approach

Everything desktop lives behind `@media (min-width: 900px)` in one
stylesheet, so the mobile experience is byte-for-byte unchanged. Liquid was
touched in only two places; the rest is CSS.

### Files

| File | Change |
| --- | --- |
| `assets/sa-desktop.css` | New. The whole desktop layer. |
| `assets/sa-desktop.js` | New. Mega-menu open/close, cart-count sync. |
| `snippets/sa-desktop-nav.liquid` | New. Desktop bar + mega-menu markup. |
| `sections/sa-header.liquid` | Two lines added: renders the snippet inside `<header class="sh">`. Nothing else changed. |
| `layout/theme.liquid` | Three lines added: loads the CSS and JS in `<head>`. |

Both edited files were reconstructed and verified byte-identical to the live
originals (md5) before the additions were applied, so nothing else moved.

### Specificity

Section styles are emitted inline as `#shopify-section-<id> .thing`. An ID
selector outranks any number of classes or attribute selectors, so
`body [id^="shopify-section-"] .thing` from a stylesheet **cannot** win — the
first version of this layer tried exactly that and silently did nothing.
Cross-section overrides therefore carry `!important`.

The header is the exception. `sa-header.liquid` renders
`sa-desktop-nav.liquid`, so that snippet emits its own ID-scoped rule
(`#shopify-section-{{ sid }} .sh .sh-in { display: none }` — one class deeper
than the section's own rule, and later in the document) and wins cleanly.

### Desktop header

The mobile bar (`.sh-in`) is hidden at ≥900px and `.shd` takes over, in two
rows:

- row 1 — logo left, search / account / cart / cashback right
- row 2 — the eight nav items, centred under a hairline

Two rows rather than one because the items do not fit beside the logo and the
actions: eight of them measure ~1125px against ~735px of free space at 1440px,
and a single row put the logo on top of "Men" and the last links under the cart.
Below 1280px the note pills ("100% back", "60 seconds") are dropped, which
brings the row down to ~840px and keeps it on one line at 1024px.

- each collection tab opens a full-width mega panel — banner on the left,
  six products and an "explore all" link on the right
- hover and keyboard (focus, Escape) both drive it, with open/close delays so
  it does not flicker when the pointer crosses between items
- the mobile drawer, tabs and JS are untouched and still run below 900px

The nav reads the **same** header blocks as the drawer, so a tab added in the
theme editor appears in both. There is no second menu to maintain.

### Footer

Layout was already three-column at desktop; only the type scale was lifted
(links 12.5→14px, contact rows, newsletter field, legal line) and the panel
widened to 1280px.

### The twine

The rope tied across the torn paper edge is an image sized by the merchant's
"Twine max width" setting, which renders as

```css
.twine { width: min(1600px, 100vw) }
```

1600px was picked while looking at a phone, where `100vw` is the smaller of the
two and the rope is a ~390px ribbon. On a desktop the other value wins: the
artwork is drawn 1600px across, and at about 3.9:1 that makes it ~410px tall.
It is centred on the tear line, so half of it hung over the handwritten note
and half reached up out of the footer into the page above. Measured at 1920px:
the rope overlapped the note by 138px and escaped 166px above the footer.

It now takes a measure of its own — `clamp(420px, 42vw, 700px)` — and the note
and the footer's own head-room grow with it. Measured after: the tails clear the
first line of the note by 44–54px at every width from 900 to 1920, and the rope
no longer leaves the footer. The phone is untouched: `100vw` still wins there.

The same result can be had in the theme editor by setting "Twine max width" to
around 620px, which would also leave the phone alone. This does it without
touching the setting.

### A rope that runs the whole width

Capping the rope keeps it in proportion, but it does not make it cross the
window, and a ribbon that stops short of both edges is not what the design
wants. A 3.9:1 photo cannot do that: crossing 1920px also makes it 410px tall.
A rope that runs the whole width has to be *drawn* long and thin.

So `sections/sa-footer.liquid` gains two settings — **Twine photo · desktop**
and **Twine height · desktop** — and, when the photo is set, emits its own
desktop rule. Nothing changes for anyone who leaves it empty, and nothing in it
runs below 900px, so the phone keeps its own photo either way.

The desktop photo is painted as a `background-image` rather than a second
`<img>`, because that lets the box be `100vw` wide at a **fixed height** with
`background-size: cover`. `cover` sizes the artwork by whichever axis needs
more, which here is the height — so the rope keeps one thickness and the bow
one size at every window width, and only the flat rope at the two ends is
cropped away. A plain `<img>` sized by width would go back to growing taller
as the window widens, which is the bug this whole section is about.

The footer's head-room and the note's are then computed from that height
(`calc(<height>/2 + …)`) rather than guessed, since the rope is centred on the
tear and half of it always sits above the paper.

What the photo has to be: about **15:1** (4800×320 works well), transparent
PNG, bow centred, and flat uniform rope running right to both edges — the ends
are what gets cropped, so they must be plain rope.

## Homepage sections

The homepage runs 15 live sections. Most carry desktop settings (`h_size_d`,
`card_w_d`, `height_d` …) and a `@media(min-width:900px)` block — but that
block usually only scales type and padding. Scaling a phone layout up is not
the same as designing for a desktop, so the test applied to each section is
**"is this pattern right for a mouse and a wide screen?"**, not "is it
responsive?".

The pattern that keeps failing that test is the **horizontal swipe rail**.
It is a thumb gesture. On a desktop there is nothing to swipe, and these
sections all hide the scrollbar (`scrollbar-width: none`), so the overflow is
not merely awkward — it is invisible.

| Section | Verdict |
| --- | --- |
| `sa-row` (Best Sellers, Founder's picks) | **Rebuilt as a grid.** The shelf scrolled horizontally and the cards were never given a desktop width, so they stayed 116px under a 175px photo box and filled ~900px of the 1120px row. Now 4 across at ~265px, with the photo box on an aspect ratio so it follows the column. The section's JS survives: its scroll listener stops firing and `scrollTo` becomes a no-op, so clicking a card still promotes it into the big slot. |
| `sa-drops` (New Drops) | **Rebuilt as a grid.** Eight cards needed ~1790px inside 1120px, so **692px sat off-screen** behind a scrollbar the browser never draws. Now 4×2. Click-to-flip is unaffected. |
| `sa-hero-card` | **Centred at desktop.** A text-only hero (no image is set) with copy left-aligned at 36ch. On a phone that fills the card; at 1440px the card is ~1104px and the text hugged the left third, leaving roughly 700px of empty gradient. The block is now centred at a 780px measure and the sentence runs to 54ch, so it fits one line. Height is left to the merchant's "Card height · desktop" setting — raising it from 250px would give the hero more presence. |
| `sa-story-rings` | No change. Seven circles need ~704px of 1120px; nothing overflows. Left alignment is the merchant's "Desktop alignment" setting. |
| `marquee-slider` | No change. Full-width ticker with its own `height_d` and `font_size_d`. |
| `sa-founder` | No change. Desktop puts the portrait left and the text right (`.8fr 1.2fr`, 48px gap). |
| `sa-calc` | No change. Desktop turns the card into a grid: shelf and slider left, the big return panel right. |
| `sa-standard` | No change. Desktop lays each rung out as percentage / text / bar in three columns. |
| `sa-scent-worlds` | No change. `arrange: quad` gives four full-bleed panels edge to edge at desktop. |
| `sa-occasion` | No change. An expanding accordion is a legitimate desktop pattern and the day bar already handles mouse drag. Panels open on click rather than hover — a possible enhancement, not a defect. |
| `sa-gift` | No change. `layout_d: split` puts the words beside the box (540px, 72px gap). |
| `sa-voices` (reviews) | No change. Already becomes a `repeat(auto-fit, minmax(220px, 1fr))` grid. Judge.me has 58 reviews at 4.76, so it renders. |
| `sa-faq-home` | No change. Desktop scales padding, title, question and answer; the 820px cap is a deliberate reading measure. |
| `sa-golden-pass` | No change. Desktop makes the benefits a multi-column grid and the button inline. |

Three of fifteen needed work.

## Breakpoint

The layer originally switched at 1000px, which was an arbitrary choice. The
theme's own breakpoint is **900px** — `sa-desktop`'s `dk_break`, and the
`@media(min-width:900px)` block in nearly every section — so between 900 and
999px the page went desktop while the header stayed a phone bar. The layer now
switches at 900px too, with an extra tier at 900–1023px that tightens the nav
(smaller padding and label size, narrower search) so the eight items still sit
on one line: they measure ~764px against ~852px of row.

## Product page

`sections/sa-desktop.liquid` is a full desktop layout for the product page,
written by the theme author: it restructures the DOM into a sticky gallery
beside the info column (56/44, max 1620px), moves the thumbnails to a vertical
strip, makes the buy pill sticky, and gives every section below its own
desktop grid — urgency 2-up, journey 1.15/.85, notes 1.05/.95, combo 3-up,
reviews .62/1.38, FAQ .7/1.3 with a two-column list, twins auto-fit. There is
also a tablet tier. Nothing there needs redesigning.

One thing did need fixing, and it was caused by this work: its "Photos stick
this far from the top" setting is 92px, measured against the old 58px phone
bar. The new desktop header is a two-row bar about 108px tall, so the gallery
would have slid under it. The layer pins the sticky offset to 124px instead.

## Collection

`sections/sa-collection.liquid` already steps the grid 2 → 3 at 750px → 4 at
1100px inside a 1240px container. Nothing to do.

## Cart

The cart had no desktop design at all, and it was the worst page on the site.
It is seven separate top-level sections stacked vertically — delivery road, bag
head, the items, the savings ladder, gift wrap, the bill, the checkout pill —
every one of them capped at `max-width: 520px` and centred, except the bag head
and the delivery road, which have no width of their own and so spanned the whole
1440px window. The checkout pill was `position: fixed` across the full width,
floating over the middle of the page and covering the gift block.

The desktop shape is the one every considered cart uses: **the goods on the
left, the money on the right, and the money follows you down the page.**

No markup moves. Each piece is already a direct child of `#MainContent` with a
known id from `templates/cart.json`, so `main[data-template='cart']` becomes a
four-track grid and each section is placed:

| Track | Contents |
| --- | --- |
| 1 | flexible gutter (min 32px) |
| 2 | road · head · items · ladder · gift wrap — max 720px |
| 3 | the bill, and the checkout — 380px |
| 4 | flexible gutter |

The gutters are grid tracks rather than padding on `main`, so `main` keeps its
full width and the white-to-cream fade `#MainContent::before` paints under the
header still runs edge to edge.

### The id that is not the id

The first version placed the two money sections with
`#shopify-section-sa_bag_bill` and `#shopify-section-sa_bag_pill`, taking the
keys straight from `templates/cart.json`. Those selectors match **nothing**.

A section inside a JSON template is rendered as

```
shopify-section-template--<number>__sa_bag_bill
```

where the number is the theme's own id for that template. So the grid applied,
the goods column was right, the checkout stopped floating — and the bill and the
checkout quietly stayed in the goods column, which is exactly what a silent
selector failure looks like. The bag head kept its 30px phone title for the same
reason.

They are matched by **what they contain** instead — the bill draws `.m4-bill`,
the checkout draws `.m4-go` — with an `[id$='__sa_bag_bill']` suffix selector
beside it for browsers without `:has()`. Sections identified by their schema
class (`sa-bagtop`, `sa-bagroad`, `sa-bagwrap`) are matched on that. Nothing in
this layer depends on a section id any more, so re-adding a section in the theme
editor cannot break it.

### The sticky pair

Column 3 holds two sections that have to behave as one sticky unit, and there is
no element wrapping them that could be made sticky. Both are therefore given the
**same** full-height grid area (`grid-row: 1 / -1`) and pinned to opposite ends
of it: the bill `align-self: start` + `top: 124px`, the checkout
`align-self: end` + `bottom: 28px`. One area, two ends — the total stays under
the header and the button stays at the foot of the window, with no fixed bar
covering the page.

Both come to rest on the area's bottom edge at the end of the page, which put
the checkout on top of the total in the last screenful. Sticky is clamped by the
element's **margin** box, so `margin-bottom: 196px` on the bill is what holds
them apart. Measured: the gap never falls below 46px at any scroll position.

### The checkout

`.m4-go` is `position: fixed` with its `bottom` written **inline** by the
section's own JS, and it carries `.down` to ride the phone tab bar. Setting it
`position: static` makes both inert — an inline `bottom` has nothing to act on
— so no JS had to be fought or unbound. Inside a 380px column the pill becomes
a card: what you pay, what comes back, then a full-width button.

### The rest

- the phone's `max-width: 520px` cap is lifted on `.m4` under any bag section —
  the pieces carry four different section classes (`sa-bagwrap`, `sa-bagtop`,
  `sa-bagroad`, `sa-bagladder`) but all wrap their content in the same `.m4`
- the bag head is now the page's title block: 30px → 42px
- from 1280px the line item is scaled up — a 104px bottle, a 19px name, wider
  figure columns. Not below that: at 1100px the goods column is ~510px and the
  larger tracks take more from the name than the size gives back. `.m4-row`
  animates itself away on remove by collapsing `max-height: 120px`, so that cap
  is raised to 190px or every row would be cropped
- an empty bag has no bill and no checkout, so a reserved 380px column would
  strand the message off to the left. `:has(.m4-empty)` collapses the page to
  one centred 640px column

Measured at 1440 / 1280 / 1200 / 1100 / 1024 / 900 / 390px: no horizontal
overflow, no truncated product name, no clipped row, and the mobile page is
byte-for-byte what it was.

The content pages, search and the account pages are next.

### A stray file

`assets/sa-desktop-sections.css` was created by mistake while considering
splitting this layer in two. Nothing links to it, so it has no effect. The
Admin API refuses to delete theme files, so it carries a comment saying as
much; remove it from Shopify admin if you want the theme tidy.

## Testing

`synorperfume.com` is blocked by this environment's egress policy, so the
storefront itself could not be opened. Instead the header was rebuilt as a
static harness (`scratchpad/render/`) from the real section settings, the real
`sa-desktop.css`/`sa-desktop.js`, and real product titles and prices, then
driven in headless Chromium at 1440 / 1280 / 1100 / 1024 / 990 / 390px. The
cart was tested the same way, from the real `templates/cart.json` settings and
the real compiled `sa-cart-m4-css.liquid`.

That caught three defects that code review had missed:

- the `[id^=...]` overrides never applied, so the phone bar stayed visible at
  every width
- the single-row nav overflowed and collided with the logo and the cart
- `.shd-cb` is a flex container, so the whitespace-only text node between the
  amount and the word was dropped and it read "₹49Back"

Hover, tab switching, pointer travel into the open panel, `Escape`,
`aria-expanded` and the cart badge were all exercised and pass with no console
errors. What the harness cannot cover is the rest of the page — `base.css`, the
real logo's proportions, and the other sections' styles — so still preview the
staging theme before publishing.

## One divergence to know about

`sections/sa-header.liquid` in this repository differs from the staging theme by
a single line: a code comment that still said "Hidden below 1000px" after the
breakpoint moved to 900px. It is inside `{%- comment -%}`, so it renders
nothing. The file is 34KB and the Admin API has to be sent the whole of it, so
the fix rides along with the next real change to that file rather than costing a
34KB push of its own. Everything else is byte-identical (verified by md5).
