# The Per-Player Page — Design

**Status:** Approved in conversation 2026-09-10. Not yet implemented. Phase J of
`2026-09-06-audit-and-improvement-roadmap.md`, first half.

**Authority:** `2026-09-03-mplus-postmortem-design.md` remains the authority on analysers,
badges and refusals; §2.6 and §5.5 bind this document and are not reopened.
`2026-09-06-report-tabs-design.md` remains the authority on the report's navigation, and this
design nests a second tab group inside the one it defined. `2026-09-05-mplus-report-design.md`
remains the authority on the view model's shape.

**Companion:** the roadmap's Phase J lists five items. This design takes four of them. The
fifth — extending the top-parse comparison beyond the subject — is split out as J2 and
specified nowhere yet; §13 records why, and what it will cost.

## 1. What this builds

One sub-tab per player inside the Players tab. Each carries what that player's card carries
today, plus one drawing: a multi-track timeline of their run, on the same clock as the run
timeline in Summary.

The drawing answers two questions the page can currently only argue in prose:

- **Was the damage spike covered?** A bar with an empty column above it is a hit taken with
  nothing pressed.
- **Was the cooldown held past the pack worth spending it on?** A press mark sitting to the
  right of a shaded boss block, with a long unshaded stretch before it, is a cooldown that was
  ready and not used.

Both are alignment questions — did this happen at the same time as that — so both belong on
one shared x axis. Three separate charts would make the reader perform the alignment, which is
the one thing the drawing exists to do for them.

## 2. What already exists and is not rebuilt

Everything this draws is already fetched and already computed. No new query, no new analyser,
no change to the quota.

| Already in hand | Where |
| --- | --- |
| Every cast by every player, whole fight, every ability | `CASTS_QUERY`, `hostilityType: Friendlies`, no actor filter, fight-wide bounds — `adapters/wcl/queries.py` |
| Damage taken by every player, whole fight, unwindowed | `DAMAGE_TAKEN_QUERY`, same shape — `adapters/wcl/queries.py` |
| Pull boundaries, boss flags, the run's clock | `Run.pulls`, `Pull.is_boss` |
| The rule for when a cooldown may be judged at all | `analysis/throughput.py:ready_at` |
| Which pulls were worth a cooldown | `analysis/throughput.py:pulls_worth_a_cooldown` |
| Cooldown lengths per class and spec | `data/defensives.toml`, `data/throughput_cooldowns.toml` |
| An icon for any ability id | `LoadedRun.ability_icon_map`, `adapters/render/icons.py` |
| Nested tabs | `report.js.j2` — `show()` is scoped by tab group, `reveal()` walks the ancestor chain |
| The SVG idiom | `report/health_curve.py`, `report/timeline.py`, and `.track-label` / `.block-boss` in `report.css.j2` |

The tab script needs no change. This is worth stating plainly because the tabs design
predicted it: nested tabs were the argument for choosing a script over CSS in the first place.

## 3. The nested tab group

`_players.html.j2` gains a `<nav class="tabs" data-tab-group="players">` with one button per
player, and wraps each player's card in a `<div data-tab-panel="players" id="player-{slug}">`.

The slug comes from the roster's **disambiguated display name**, the one
`analysis/players.py:display_names` already produces, lowercased and reduced to characters an
HTML id and a URL fragment both survive. Two players who share a display name must not share a
sub-tab, and `display_names` is the function that already guarantees they do not.

Group rows stay where they are, below the sub-tabs: they are per-player rates that have not yet
found their player, and moving them into a player's tab would claim an attribution the analyser
did not make.

The player whose sub-tab opens first is the subject — the one `--player` names, defaulting to
the report owner. Today `subject` decides exactly one thing in the report (which card carries
the comparison rows, `report/players.py:90`); it now decides two.

## 4. The drawing

One `<svg>` per player, `TIMELINE_WIDTH` (680) units wide, spanning our own run from the first
pull's start to the last pull's end — `run_start_ms` and `run_seconds`, the same origin and span
the run timeline measures for our own track.

It does **not** share the run timeline's scale, and this design does not claim it does. That
drawing fits the longer of our run and its reference into the width (`longest = max(our_seconds,
their_seconds)`), so whenever a reference ran longer, a pull sits at a different x on the two
pictures. What matters instead is that every player timeline shares one scale with every other
player timeline: five players are read against each other, and they are drawn from one run.

Four layers, back to front:

1. **Pull blocks, shaded.** Same geometry as `report/timeline.py` produces for the run
   timeline, so a pack sits at a different x here than it does on the run timeline whenever a
   reference ran longer. Boss pulls keep `.block-boss`.
2. **A damage-taken track.** `LoadedRun.damage_taken` for this actor, summed into fixed
   buckets, drawn as bars from a baseline. Height scales to the player's own largest bucket,
   not the group's: this is not a ranking (§5.5), and a shared scale would make one.
3. **One row per cooldown**, ordered throughput first then defensives, each group in its data
   file's own order — `defensives_up_at` already returns abilities "in the order the abilities
   were given, so a caller controls the reading order rather than inheriting a set's", and this
   follows it.
4. **Marks, dimming, and one stretch that is not judged.** A mark at each press, carrying the
   ability's icon. After each press, the row is dimmed for the ability's cooldown. And the
   first `cooldown_seconds` of every row are drawn as *not judged* rather than as ready: casts
   are fetched per fight, so an ability pressed before the timer started is invisible, and
   `ready_at` already refuses to judge any window reaching back past the run's start for
   exactly that reason. Drawing that stretch as ready would be the one direction this project
   never guesses in.

**The bucket width is a constant to be chosen against a real run, not asserted here.** The rule
it must satisfy: narrow enough that one lethal spike is one bar, wide enough that a 1900-second
run does not emit hundreds of rects into a file that must stay openable. Five seconds is the
starting value; §12 says what to measure before fixing it.

## 5. Which rows appear, and why this is the honest set

**One row per ability the player cast at least once during the run.** Not every ability listed
for their specialisation.

This is not a display choice. `analysis/defensives.py:50` already fixes the rule and states the
reason: the data files are talent-gated, "and a player who did not take the talent casts it
nowhere — which looks exactly like having it and never pressing it. Reporting silence as
availability would accuse someone of not pressing a button they do not own."

A timeline row for an ability the player never took is that same accusation, drawn — and drawn
is worse than written, because an empty row reads as a whole run of missed presses. The row set
is therefore evidence of ownership, which is the same standard the death card already meets.

An ability the player owns and never pressed is a different claim and already has a home: the
`defensives.unused.*` and `throughput.*` findings say it in words, with the caveat that a
missing talent explains it just as well.

## 6. The badge is split, as the health curve's is

The drawing mixes two kinds of claim and must grade them where the reader meets them, the way
`health_curve.py` grades its dots against its line.

- **`measured`** — the damage bars and the press marks. Both are events the log emitted.
- **`inferred`** — the dimming. Base cooldowns are longer than talented ones, charges are
  ignored, and the log emits no cooldown-reset or cooldown-reduction event. Every one of those
  errs the same way: toward showing an ability as unavailable when it may have been ready.
- **Neither** — the not-judged stretch at the start of each row. It is not a claim about the
  ability at all, but about what the log can see, and it is drawn differently from both so no
  reader takes it for a cooldown running down.

That direction is the safe one and should be said in the legend. Understating what was ready
cannot produce a false accusation; overstating it would accuse a player of holding a cooldown
they did not have.

## 7. The view model

A new `src/wowperf/domain/report/player_timeline.py`, pure, emitting frozen types in viewBox
units. The template prints coordinates and decides nothing — the rule `report/timeline.py` and
`health_curve.py` already keep.

```
PlayerTimeline
  section: Section          # withheld like any other, with a reason
  width, height: float
  pulls: tuple[TimelineBlock, ...]      # reused, not re-invented
  damage: DamageTrack
  cooldowns: tuple[CooldownRow, ...]
  ticks: tuple[tuple[float, str], ...]
  legend: str
  badge_measured: Badge
  badge_inferred: Badge

DamageTrack
  baseline_y: float
  bars: tuple[DamageBar, ...]           # x, width, height, y
  peak_label: str                       # the largest bucket, in words

CooldownRow
  label: str
  ability_id: int | None                # for the icon; None keeps the row drawable
  baseline_y: float
  presses: tuple[Press, ...]            # x, icon class
  unavailable: tuple[Span, ...]         # x, width
```

`ability_id` is nullable for the same reason `LedgerRow.ability_id` is: a row whose icon cannot
be resolved still draws, without its picture. The finding-icons work established that seam and
tested it; this reuses it rather than adding a second convention.

Coordinates round to `PRECISION` tenths, as the health curve does and for the same reason: a
per-player drawing emits far more coordinates than the run timeline, and unrounded binary
fractions fill the page and its golden file with digits nobody can use.

One tested function per track, so the review granularity of three separate charts survives
inside one drawing.

## 8. Template and CSS

`_players.html.j2` gains the sub-tab nav and the per-player panel; a new `_player_timeline.html.j2`
partial holds the SVG, imported `with context` — the finding-icons review established that a
macro imported without it cannot see `icons_by_id`, and that the membership test fails silently
rather than raising.

CSS reuses `.track-label` and `.block-boss`. New rules for the damage bars, the press marks and
the dimmed spans. No new colour that carries meaning alone: the report is screenshotted and
recompressed, and `report/players.py` already refuses to let a colour be the only signal.

## 9. What this must not break

- **The page loads nothing.** No stylesheet link, no `@import`, no remote `src`, one inline
  script. Press-mark icons are data URIs through the existing resolver, and
  `tests/adapters/render/test_html_invariants.py` enforces every clause.
- **One inline script, which cannot fetch, write text, or read storage.** Nested tabs need no
  script change, so this is preserved by doing nothing.
- **No finding reaches the page twice** — `test_html_invariants.py:377`. This design adds no
  finding, so the invariant is untouched. J2 does add findings and will break it; §13.
- **No damage ranking** (§5.5). The damage track scales to the player's own peak, never the
  group's, and no player's drawing carries another player's figures.
- **No rotation scoring** (§2.6). The timeline says when; it never says wrong.
- **The domain performs no I/O.** `player_timeline.py` imports nothing that touches the
  network, the disk or a template.

## 10. Testing

- One test per track function, against a hand-built run: bars, marks, dimming, pull shading.
- The row set: an ability in the data file that the player never cast produces **no row**. This
  is the §5 rule and it must fail if the rule is removed.
- The dimming direction: an ability pressed at t produces an unavailable span covering
  `t + cooldown`, and a second press inside that span still draws its mark.
- Two players sharing a display name get two sub-tabs with distinct ids.
- Every sub-tab panel is reachable from a button in its group, and every button points at a
  panel that exists — the shape `test_every_panel_appears_once_in_tab_order` already asserts
  for the main group.
- The subject's sub-tab is the one that opens first.
- A player with no tracked casts renders a sub-tab with a withheld section and a reason, not an
  empty SVG.
- The golden file: `tests/adapters/render/golden/minimal.html` must stay byte-identical, or the
  change to it must be deliberate and reviewed.

**A gap this design does not close:** the render suite parses HTML strings in Python and cannot
observe layout. Nothing here can test that the drawing is legible, only that it is correct. The
deep-link defect note already names this gap; this design does not widen it, and does not fix
it.

## 11. The deep-link defect, recorded rather than fixed

`2026-09-08-deep-link-scroll-defect.md` records that opening the report at a fragment lands at
the wrong scroll offset, because the tab script hides inactive panels only after first layout,
in a document about three times taller than the final one.

This design makes the Players panel roughly five times taller in that pre-script document. It
changes the defect's magnitude, not its kind: the scroll is already wrong, and a wronger number
is the same bug.

**Decision, taken 2026-09-10:** ship this, and add a line to the defect note saying the
pre-layout document grew, so whoever builds the harness knows what they are measuring. Do not
fold the fix in. The note forbids shipping the obvious fix — emitting the `js` class from
`<head>` — without a deterministic harness first, on the grounds that a UI fix which cannot be
demonstrated is "a guess with a commit message". That reasoning is unchanged by this design.

Player sub-tabs get fragment ids and deep-link exactly as well, or as badly, as the six main
tabs do today.

## 12. Measurements taken

Recorded 2026-09-10 against report `6Kx1P9GbNXrcLdHa` fight 36 — five players, four deaths,
the same run `out/6Kx1P9GbNXrcLdHa-36.html` already held from 2026-09-09, rendered from this
codebase before this branch existed. That file, at 260,645 bytes, is the **before** used
below; it postdates the 257,988-byte figure once written here and is the closer, more honest
comparison for the same reason it was chosen: same run, same tool, immediately prior.

1. **Bucket width.** Re-rendering at 2, 5 and 10 seconds (`--no-compare`, so the three are
   comparable on structure alone) produced 3,266, 2,062 and 1,609 SVG rects across the
   document, at 721,206, 632,149 and 598,706 bytes. Checked against the four buckets
   surrounding each of the run's four deaths — the share of that neighbourhood's total damage
   landing in its single largest bucket:

   | death | 2 seconds | 5 seconds | 10 seconds |
   | --- | --- | --- | --- |
   | 1 | 52% | 58% | 72% |
   | 2 | 47% | 91% | 50% |
   | 3 | 79% | 50% | 54% |
   | 4 | 100% | 100% | 71% |

   No width concentrates every death's damage into one bar best: 5 seconds wins death 2
   outright, ties 2 seconds for death 4, sits between the other two for death 1, and is the
   worst of the three for death 3. Spike fidelity does not pick a winner, so rect count does:
   5 seconds holds well under 2 seconds' count for a comparable spread of outcomes, at the
   cost of a few hundred more rects than 10 seconds would use. `BUCKET_SECONDS` stays 5.0 —
   the assumed starting value was right, for this reason rather than the one first guessed.
2. **Page size.** 260,645 bytes before, 659,499 after: five player timelines add 398,854
   bytes. The report carried 63 distinct ability icons before this work and 76 after — 13
   newly introduced by a cooldown row that no death card or ledger row had already drawn, the
   other 63 reused from icons the report already carried. Of the 398,854-byte growth, 204,632
   bytes (51%) is icon-attributable: the entire document-level `<symbol>` sprite is new
   (175,402 bytes, needed so all 76 icons — reused ones included — can be referenced from
   inside an SVG via `<use>`, which cannot read a CSS `background-image`), of which only
   29,919 bytes belong to the 13 genuinely new icons; the remaining 145,431 bytes re-embed, in
   `<symbol>` form, icons whose data URI the page already carried once in its stylesheet. The
   other 194,222 bytes (49%) is the timelines' own structure — pull bands, damage bars,
   cooldown rows, press marks, ticks and labels for five players.
3. **Row count.** Per player, in cooldowns tracked and cast at least once: 6 (Shadow Priest,
   DPS), 5 (Blood Death Knight, tank), 4 (Elemental Shaman, DPS), 4 (Holy Paladin, healer), 5
   (Arcane Mage, DPS). All five sit at or under the assumed six-to-twelve range's floor, none
   near its ceiling, and none within striking distance of twenty — `ROW_HEIGHT` and the
   drawing's shape are unchanged.
4. **Pre-layout height.** With the `js` class removed after load (the same DOM and CSSOM state
   scripting-disabled would produce, since that class is the only thing either panel-hiding
   rule in `report.css.j2` keys on), `document.documentElement.scrollHeight` read, over
   `python -m http.server`, reproducibly across repeated loads:

   | | before | after |
   | --- | --- | --- |
   | post-layout (script has run) | 1,728 px | 1,728 px |
   | pre-layout (script's effect undone) | 13,323 px | 15,175 px |
   | Players panel alone, pre-layout | 2,798 px | 4,671 px |

   The whole document's pre-layout height grows 13.9% (13,323 to 15,175 px) — a multiple of
   8.78 against the shared 1,728 px post-layout height, against 7.71 for the same page before
   this work. The Players panel itself, which is what actually changed, grows 67% (2,798 to
   4,671 px) — not the roughly fivefold growth §11 estimates; §11 is not corrected here because
   this task's scope is §4 and §12, but whoever next touches §11's numbers should read this row
   rather than the estimate.

## 13. J2, split out and not specified here

The roadmap's fifth item — a top-parse comparison for every player rather than the subject —
is a different change and does not belong in this spec. It is not deferred for cost.

**What it would cost.** No measurement exists: `cli.py` has exactly one `top_parses` call, for
`subject.class_name, subject.spec`, and no run has ever fetched a second specialisation's
sample. Deriving from measured unit prices, four more specialisations at `SAMPLE_SIZE = 5` come
to roughly 165 points against an hourly budget of 3600 — about 4.6%, against a measured 83.39
for a full five-and-five run today. Probably an overestimate: reference runs are cached by
report code with no class or spec in the key, so any specialisation whose top parse comes from
an already-loaded report costs only its aura query. How often that happens is unmeasured.

**What actually blocks it.** Three things, none of them quota:

1. **Whether `characterRankings(metric: playerscore)` returns rows for tank and healer
   specialisations is not recorded.** `.claude/skills/wcl-api/SKILL.md` verifies that
   `playerscore` exists and is "used by WoW Mythic dungeons" (2026-09-03) and that `hps` and
   `tankhps` are separate metrics, but says nothing about whether a tank spec returns rows. If
   it does not, two of five sub-tabs carry a withheld comparison whatever the flag says. **One
   live query settles this, and it should be settled before J2 is designed.**
2. **Comparison finding ids carry no player.** They read `compare.spells.missing.{rank}`,
   `compare.talents`, `compare.uptime.*`. Five players collide, and
   `test_html_invariants.py:377` fails. J2 renames a finding family that appears in the
   findings JSON and in the page's element ids.
3. **`compare()` takes one player and one parse sample.** J2 splits it into a run half, run
   once, and a per-player half, run per player — and our own aura data is fetched for the
   subject alone (`cli.py`), so each additional player needs its own aura query on our side as
   well as the reference side's.

**What survives from the conversation that produced this design.** J2's scope should be a
runtime choice, not a design-time one: `--player` becoming repeatable, plus a way to say
"everyone", so a reader can ask for themselves, a few teammates, or the whole group and pay
accordingly. J1 draws all five sub-tabs unconditionally because they are free; J2's flag governs
only which of them carry a parse comparison.

## 14. Open questions

1. **Tank rows.** `data/roles.toml` already excludes tanks from the damage-against-median
   comparison, because a lone tank has no honest median. The damage *track* here is not a
   comparison — it is the player's own damage against their own peak — so the exclusion does
   not obviously apply. This design includes tanks. If that reads wrong on a real run, it is a
   one-line change and the plan should measure it before deciding. **Measured 2026-09-10:**
   on `6Kx1P9GbNXrcLdHa`-36, the run's Blood Death Knight drew the fullest damage track of the
   five players — 307 five-second buckets against the next-busiest player's 274 — a shape a
   tank's steady incoming damage produces on its own scale and no other player's drawing
   claims to rank against. It reads right; the inclusion stands.
2. **Ordering the cooldown rows.** Throughput before defensives, each in its file's order, is
   chosen for stability rather than for meaning. Ordering by first press would put the
   run's story in reading order but make two players' drawings incomparable. Left as
   specified; worth revisiting once a real run has been looked at. **Measured 2026-09-10:** on
   this run every player owned four to six rows, too few for file order to bury a row a reader
   would otherwise reach quickly by scrolling. A run with rows nearer the assumed ceiling would
   make the question sharper than this one does; this run does not settle it either way, and
   the ordering is unchanged here.
