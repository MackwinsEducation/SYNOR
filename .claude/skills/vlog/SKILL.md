---
name: vlog
description: Plan one SYNOR shoot — today's idea plus the full sheet a person picks up and films with a phone. Use when the user asks for a vlog idea, a reel idea, a shoot, a script, "aaj ka idea", or names a format such as shop-visit, blind-guess or street-test. Produces the sheet in chat, in Hinglish, ready to film.
---

# Plan one SYNOR shoot

The user is the person who will hold the phone. They are alone, they have
about an hour, and they are not going to spend money on this. Everything you
write has to survive that.

## Do this in order

1. **Read `bot/vlog-style.md`.** It is the contract — formats, the hook, the
   voice, the hard rules, and the section on having somebody else in the
   frame. Do not plan from memory; the rules change.
2. **Get the real catalogue.** Use the Shopify MCP tools to list products with
   their handles and tags. Never invent a product, a handle or a tag. If the
   shop is unreachable, say so and stop — a sheet naming a scent that does not
   exist wastes a whole afternoon.
3. **Read what has already been made:** the sidecars in `bot/shoots/*.json`
   and the briefs in `bot/vlog_queue.json`. Do not repeat an idea, and do not
   repeat the shape of one with different scents.
4. **Pick the format.** If the user named one, use it. Otherwise take the next
   `todo` in the queue — a brief a person wrote beats one you invented — and
   only invent when nothing is left.
5. **Write the sheet**, every section named in `bot/vlog-style.md`.
6. **Check it yourself** against the hard rules before showing it, and say in
   one line what you checked.

## Two tests before you commit to an idea

- **Could this be filmed tomorrow, in this city, by one person with no crew
  and no permission from anybody?** If not, it is a fantasy.
- **Is there anything in it a viewer could check for themselves?** If not, it
  is an advert, and it will be watched like one.

## The things most often got wrong

- **Spoken lines are Hinglish, Roman script, said the way people say it.**
  On-screen text is English and short. Never a translated-sounding sentence.
- **Never another perfume house's name or a celebrity's name**, anywhere —
  not in a line, the caption, the title, the description or a hashtag. The
  shop's own tags carry those names for filtering; a video does not say them.
- **The only prices that exist** are: a tester is ₹49, and the ₹49 comes back
  as credit on a bottle. No bottle price, no invented discount.
- **One honest negative, spoken out loud, inside a shot.** This is the single
  highest-value line in the video and the first thing a nervous writer cuts.
- **Nobody else's words are ever written.** If somebody who does not work for
  SYNOR is in the frame, the sheet carries the consent line, the questions,
  and what to listen for — never a line for them to say. A review that was fed
  to somebody is worth nothing the moment one viewer suspects it.
- **The last shot is the ₹49 line and nothing else.**
- **Write the script, not only the shot list.** The person asking is going to
  stand in a shop and talk; twelve ten-word fragments are not something anyone
  can perform. Give them every line from walking in to walking out, in scenes,
  and mark where they stop talking and let the other person answer. Every line
  in the shot list must be a line that appears in the script.
- **Two endings** on any shoot with somebody else in it, written before they
  leave the house: one for a warm answer and one for a cold or flat one. The
  cold one is the better video and the one nobody writes unless it was asked
  for in advance.

## How to hand it over

Print the sheet in the chat, formatted to be read on a phone while standing in
the street: the kit list and the consent line near the top, then the shot
table. Do not bury the questions inside the shots.

Then offer, in one line, to save it as `bot/shoots/<date>-<id>.md` with its
JSON sidecar, in the same shape `bot/write_shoot.py` writes — the social bot
reads that sidecar to post the finished video, so a sheet saved in the wrong
shape is a sheet the rest of the machine cannot see.
