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

Everything desktop lives behind `@media (min-width: 1000px)` in one
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

The mobile bar (`.sh-in`) is hidden at ≥1000px and `.shd` takes over, in two
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
- the mobile drawer, tabs and JS are untouched and still run below 1000px

The nav reads the **same** header blocks as the drawer, so a tab added in the
theme editor appears in both. There is no second menu to maintain.

### Footer

Layout was already three-column at desktop; only the type scale was lifted
(links 12.5→14px, contact rows, newsletter field, legal line) and the panel
widened to 1280px.

## Not done yet

The homepage, product, collection, cart and content-page sections still use
their mobile scale at desktop width. They are the next pass — same mechanism,
adding rules to `assets/sa-desktop.css`.

## Testing

`synorperfume.com` is blocked by this environment's egress policy, so the
storefront itself could not be opened. Instead the header was rebuilt as a
static harness (`scratchpad/render/`) from the real section settings, the real
`sa-desktop.css`/`sa-desktop.js`, and real product titles and prices, then
driven in headless Chromium at 1440 / 1280 / 1100 / 1024 / 990 / 390px.

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
