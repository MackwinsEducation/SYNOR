# The shoot agent — an idea you can film today

Track 3. A bot plans one shoot and writes a **sheet**: the idea, the concept,
the hook, a numbered shot list with what to say and what to put on screen, the
kit to carry, and the caption and YouTube copy for afterwards.

It is not a script to read out. It is a sheet a person picks up and films with
a phone, alone, in about an hour.

## The one thing this is built around

**A camera cannot smell.** That single fact is why most perfume video is
worthless: a bottle rotating on a table while a voice says "luxurious" gives
the viewer nothing they did not already have.

So `bot/vlog-style.md` makes one rule structural rather than advisory —
**film the effect, not the object**:

| Not this | This |
| --- | --- |
| The bottle | The person who turned around |
| "Long lasting" | A clock at 9am and at 6pm, same shirt |
| "Fresh" | A wet towel, a gym bag, a lift door closing |
| "Notes of bergamot" | A thumb cutting into a lemon, close |

A shot that could be replaced with a stock photo of a bottle is rejected by
the checks. Something has to happen in it.

## What happens on a run

1. It takes the first shoot in `bot/vlog_queue.json` whose status is `todo`.
2. It reads the live catalogue from Shopify, and builds the forbidden-names
   list from it, the same way the writing agent does — so no other perfume
   house and no celebrity can reach a spoken line, the on-screen text, the
   caption, the YouTube copy or a hashtag.
3. Claude plans the shoot against `bot/vlog-style.md`.
4. The sheet is **checked** (below). Failures go back for a rewrite, up to
   three rounds. If it still fails, nothing is written.
5. `bot/shoots/YYYY-MM-DD-<id>.md` is written and committed, and the whole
   sheet is printed into the Actions run summary so it reads on a phone.
   A `.json` sidecar carries the caption, hashtags and YouTube copy for
   Track 4.

## Seven formats, and why each one holds

| Format | Why it works |
| --- | --- |
| `street-test` | Other people's faces are the only proof a camera can capture |
| `hands-only` | No face, no lighting problem, fastest to reshoot |
| `two-bottle-face-off` | A comparison gives the viewer a decision, which is why they stay |
| `day-in-scent` | Turns "long lasting" into something visible |
| `talking-head` | Works only if the claim is specific and slightly against interest |
| `unboxing` | The ₹49 tester *is* the product, so show it as the product |
| `question-answer` | The question does the hook for you |

## What the checks catch

| Check | Why |
| --- | --- |
| No other house's name, no celebrity's name, anywhere a viewer can reach | Those tags exist for filtering. A video does not say them. |
| The hook is 12 spoken words or fewer, and is not a greeting | "Hi guys, welcome back" is where a reel loses. |
| Hook on-screen text is four or five words, and not a copy of the spoken line | A viewer with the sound off has to get it too. |
| 6–14 shots, durations adding up to the target | A sheet whose shots total 20s against a 45s target is not a plan. |
| Every shot has a visual, and a line or on-screen text | A silent wordless shot is dead air. |
| No spoken line over 12 words | Longer ones get fumbled on take one. |
| An honest negative, written **into a shot** | The highest-value line in the video is the one against our own interest — so it is checked for in the shot list, not just at the top of the sheet. |
| Real product handles, each named in the hook or a shot | Named only in the YouTube description means it is not in the video. |
| Families belong to a product actually used | The family is what files the finished vlog on the right page. |
| Kit list has more than a phone | This is the part that saves a shoot: a wet towel, a friend, a lift. |
| Caption under 280, YouTube title under 70, 5–10 lowercase hashtags | They get cut off otherwise. |
| Every product linked in the YouTube description | Otherwise the video sells nothing. |
| The last shot is the ₹49 line | One sentence, no sales voice. |

## Language

Spoken lines are **Hinglish** by default — real conversational speech in Roman
script, not a translation of an English sentence. On-screen text is **English**
and short, because it carries the numbers and the product names.

Change it in one place: `defaults.language` in `bot/vlog_queue.json`
(`hinglish`, `english` or `gujarati`), or per shoot with a `language` field on
that entry.

## Files

| File | What it is |
| --- | --- |
| `bot/vlog-style.md` | The shoot contract: the formats, the hook rules, the voice, the hard rules, the shape of a sheet. **Edit this to change how the videos feel.** |
| `bot/vlog_queue.json` | The shoot queue, seeded with eight ideas. |
| `bot/write_shoot.py` | The agent: prompting, checks, the markdown sheet. |
| `bot/agent_common.py` | Shared with the writing agent: the Claude call, the catalogue, the rewrite loop. |
| `bot/shoots/` | Where the sheets land. |

## Running it

Same three secrets as the writing agent (`ANTHROPIC_API_KEY`,
`SHOPIFY_STORE`, `SHOPIFY_ADMIN_TOKEN`) — see
[`auto-post.md`](auto-post.md) for how to get the Shopify one.

**Actions → Vlog · plan a shoot → Run workflow.** Tick **dry run** the first
time: the sheet prints in the log and nothing is committed, which is the cheap
way to read the tone and adjust `bot/vlog-style.md`.

```bash
python bot/write_shoot.py --dry-run
python bot/write_shoot.py --shoot lift-test
```

## After the shoot

The sheet ends with the three things to do with the footage:

1. Post the reel with the caption and hashtags it wrote.
2. Upload to YouTube with the title and description it wrote.
3. Put the YouTube id in the entry's `custom.youtube_ids` metafield and tag
   that entry `vlog`. The article page then plays it as a still until someone
   taps it, and the front page marks the entry as film.

Step 3 is what makes Track 1 and Track 3 the same piece of work: a shoot
becomes a page on the paper, not just a post that scrolls away.
