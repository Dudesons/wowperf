# Report second reading — design

Status: approved 2026-09-12. Extends `docs/plans/2026-09-11-report-density-and-interaction-design.md`
and **overturns its §4.5.1** on ledger card tooltips; see §6.1.

## 1. Why

The report was read a second time, against a real run: `G7MBJZfNakrcPvAx`, fight 3, Voidscar
Arena +16, timed. The first reading produced the density work of 2026-09-11. This one produced
seven points, and unlike the first it was made against a page rendered from the current code.

The points, as given:

1. On a death recap, a long event list pushes the health curve off the screen.
2. The event list carries the player's offensive casts, which say nothing about the death.
3. The card offers a healthstone to a group with no Warlock in it.
4. The green dots on the health curve are unexplained.
5. The player timeline is hard to read: grey areas, and icons that look cut.
6. The player tabs have no tooltips.
7. The interrupt tab should say whether a spell could be interrupted at all.

## 2. Scope

**In:** all seven.

**Order.** The four sections are independent and should be executed in the order they are
written. §4 and §5 are the ones the reader met first and are the cheapest; §6 is larger than the
other three together and should be a phase of its own, so that a difficulty there cannot hold
back the rest. §7 is an analysis change and is the only one that touches a finding's content.

**Out, with reasons:**

- **A hand-maintained table of which offensive abilities heal.** Point 2 was given as "remove
  offensive casts that do not heal, but keep Bloodthirst because it can". The log cannot support
  that rule: on this card the cast is named **Bloodbath** and its heal is named **Bloodthirst
  Heal**, two names and two ability ids with nothing joining them. Building the join means a
  per-specialisation table that rots every patch. §4.1 reaches the same outcome without it.
- **Whether a Healthstone survives a logout in the current patch.** Unknown, unverified, and
  §4.3 is designed so that nothing depends on knowing.
- **A per-dungeon table of interruptible spells.** §7 states what the log can prove instead.

## 3. What the page measures today

Every figure below was read from the rendered page on 2026-09-12, at a viewport of 1512x900 —
the width the report was read at — with `out/` served over `http.server` and the geometry taken
from the DOM. They are recorded because each one is the argument for a decision, and because a
later reading should be able to check whether the decision still holds.

| Figure | Value |
| --- | --- |
| Death card height | 2007 px |
| Health curve height | 298 px |
| Event table height | 1426 px, 45 event rows at ~31 px |
| Availability column height | 113 px |
| Event rows by kind | 28 heals, 11 casts, 5 hits, 1 absorb |
| Event rows that moved health by nothing | 16 |
| Rows before the first damage | 27, all at 99-100% health |
| Icons drawn across five player timelines | 281, one per press |
| Icons overlapping a neighbour | 67 |
| Worst row | Prismatic Barrier, 31 presses, 19 overlaps |
| Findings carrying an ability id | 13 of 34, across five families |

Two of these carry the design on their own. **The card is 2.2 screens tall and the table alone
is 1.6.** And **Rxmain was at full health for the first 27 rows, then died in three seconds** —
sixty percent of the table describes a period in which nothing happened.

## 4. The death card

### 4.1 Which rows survive

**Keep every hit, every absorb and every heal, whatever it healed for.** A heal of nought is
still a fact about who was healing and how hard, and the reader asked for them.

**Keep a cast row only when the cast put a buff on the player whose band the card can draw.**
That test already exists and is already trusted: `report/deaths.py::_band_of` resolves a press
to an aura band, and its result decides whether the row gets a cover rectangle on the curve.
A row with a band has something to say — how long the buff lasted, what arrived inside it. A row
without one is the bare fact that a button was pressed.

On this card the rule keeps `Whirlwind` at 2.1 s, which carries `Cover 6.4 s`, and drops ten:
Rampage four times, Charge twice, Whirlwind at 6.9 s, Execute, Raging Blow, Bloodbath. That is
the list the reader gave, reached from the log rather than from a table of ability names.

The healing those abilities did is not lost. It is already on the table as its own row, under
its own name, because a heal is a heal event and not a cast.

**The filter belongs to the report, not to the analysis.** `analysis/recap.py` keeps returning
the whole timeline and the findings file keeps carrying it. What a reader can hold is a question
about a page.

Table: 45 event rows to 35, 1426 px to about 1116 px. Still 1.24 screens, so this does not fix
point 1 on its own, which is why §4.2 exists.

### 4.2 The curve stays on screen

The curve, and the two legends beneath it that grade it, move into a wrapper that sticks to the
top of the viewport while the table scrolls under it.

`position: sticky` and nothing else. No script: the page's one inline script may show, hide and
highlight, and this asks it for none of the three.

**The alternative was rejected on a measurement.** Giving the table its own `overflow-y: auto`
box would clip every tooltip near its edges: `.tip` is absolutely positioned against `.ability`,
which is the only positioned ancestor it has, so a scroll container becomes its clipping box.
`overflow` appears exactly once in the stylesheet today, on `.icon-defs`, and nothing else in
the card's ancestry would break sticky positioning.

This also repairs an interaction that has never worked. Hovering a row lights a marker at that
row's moment on the curve, and a defensive press lights the window its buff covered. Both are
invisible today, because by the time a reader is among the rows the curve has left the screen.

### 4.3 The healthstone

`analysis/recap.py::consumable_state` stops turning a category nobody drank from into READY.
A category the player never used all run is not listed on the card at all.

This is not a new rule. It is the rule `analysis/consumables.py::consumables_up_at` already
applies, and whose docstring already records why: a real run put a healthstone line on every
death of every player, "true, unarguable and worth nothing". The finding learned it; the card
never did.

The page contradicts itself today, on this run. The Summary carries `consumables.never.Rxmain`,
"used no healthstone at any point in the run … this says none was used, not that none was
carried". The death card says `healthstone — ready`.

Nothing here depends on knowing whether a Healthstone can be carried without a Warlock. The
claim being withdrawn is one the log never supported in either direction.

### 4.4 The green dots

No change to the drawing. The dots are the log's own health readings and the dashed line between
them is arithmetic, and the two are already graded apart — measured tint with a ring for a
reading, derived tint and a dashed stroke for the reconstruction, with `READING_LEGEND` and
`LINE_LEGEND` naming both beneath the chart.

The question was asked by a reader who had those two sentences in front of him. That is worth
recording, but it is not worth a fourth rewording of a legend that already says the true thing.
§4.2 puts the curve and its legends in front of the reader for as long as he reads the table,
which is the change most likely to make the sentences land.

## 5. The player timeline

### 5.1 One icon per row

The icon moves to the gutter, beside the row's name. One per row, not one per press.

Today the template draws the ability's icon at every press, `ROW_HEIGHT` square, and then paints
a solid `press` rectangle on top of it. Two consequences, both visible on the page:

- **The press bar cuts the icon.** The rectangle is drawn after the `use`, in the same place.
  This is the "icons seem to be cut" of point 5, and it is a paint order, not a rendering fault.
- **Icons collide.** Sixteen units is about seventeen seconds of a twenty-three minute run, so
  any ability pressed oftener than that overlaps itself. Sixty-seven of 281 icons do.

Moving the icon to the gutter draws 19 icons instead of 281 and removes every collision. It also
frees the track to show what it was always meant to show.

### 5.2 The colours stay; the key arrives

**The track keeps its colours.** They are not decoration: grey is on cooldown, green is the buff
up, solid blue is a press, an open blue tick is the ability coming back. Those four states are
what the measured and inferred badges under the chart grade. Colouring the track by ability would
overwrite meaning with an identity the row label already carries.

What is missing is not colour but a key. `LEGEND` explains the mark, the cooldown stretch, the
pale unjudged opening and the open tick — **and never says what the green is.** The only mention
of cover anywhere near the chart is inside the measured badge's caption.

So: a four-swatch key beneath each timeline, naming each state in the colour it is drawn in.

**The key carries the explanation; the rectangles carry no tooltip of their own.** Giving each
state rectangle a native `title` was the first shape of this and it is wrong: a `title` on a
rectangle wins over the `title` on the group containing it, so hovering anywhere on a row would
answer "on cooldown" instead of giving the row's own figures — and §6.4 promotes those figures to
a panel that appears at once, leaving two tooltips competing over one pointer. One key beneath
the chart, one panel on the row.

### 5.3 Damage taken

Each damage bucket gains a `title` naming what it holds: the damage, the bucket's width, the
time, and the pull it fell in. Zero script, and it answers the question a spike actually raises,
which is which pull it belongs to.

Nothing further. A more interactive damage track was asked for in general terms, and there is no
specific question behind it yet to design against.

## 6. Tooltips beyond the deaths tab

### 6.1 What changed since the ruling

§4.5.1 of the 2026-09-11 design ruled that ledger card headings carry no tooltip, on three
grounds. The ruling is overturned on 2026-09-12, with its grounds answered rather than ignored:

- **"Every ability-carrying ledger card already prints its measured facts, as the evidence list
  three lines under the heading."** Answered by the second reading. The reader had the evidence
  list on screen and went looking for a tooltip anyway. A fact three lines from where a reader
  looks for it is a fact that was not delivered.
- **"There is no one panel to build … one tooltip builder per finding family."** Correct in
  shape, overstated in size. The five families that carry an ability id need **three** new
  builders, not five: `ability_tooltip` already fits both defensives families, since a defensive
  at a ledger card and a defensive at a death are the same ability measured over the same run.
- **"The death card heading names the killing blow, and the recap row below it already carries
  that hit's own figures."** Unanswered, and so it stands. See §6.3.

Add an amendment note to §4.5.1 of that design naming this one, as the repository's practice
requires.

### 6.2 The builders

> **Amended 2026-09-12.** The table below over-counts the defensives panels. It promises
> `ability_tooltip` for all five `defensives.ceiling.*` and `defensives.never.*` findings, and one
> panel appeared on the page. The cause is not a defect: `run_ability_tooltip` abstains where
> `resolve_aura` finds nothing, the three `defensives.never.*` findings name abilities their player
> never cast, and the Warrior's Impending Victory is one of three abilities the page already says
> "No aura data for it" about on its own timeline row. The abstention is right — a panel there
> would print assumptions. What is wrong is the count, which counted findings rather than findings
> whose ability resolves an aura. Recorded in
> `docs/plans/2026-09-12-timeline-row-panels-design.md` §8.

Thirteen of this run's 34 findings carry an ability id, across five families:

| Family | Count | Panel |
| --- | --- | --- |
| `defensives.ceiling.*` | 2 | `ability_tooltip`, as built |
| `defensives.never.*` | 3 | `ability_tooltip`, as built |
| `interrupts.ability.*` | 5 | new; see §7 |
| `compare.spells.rate.*` | 1 | new: our rate against the reference's, both sides named |
| `compare.uptime.self.*` | 1 | new: our boss-pull seconds against the reference's |
| `players.damage.*` | — | added 2026-09-12: this player's total against the group median |

> **Added 2026-09-12.** `players.damage.*` belongs in this table and was left out of it. The five
> families above were taken from one run's findings, and that count of thirteen has never matched
> the rows beneath it, which is how the omission survived. It qualifies on the same ground every
> other row here does: it sets two figures side by side — a player's unmitigated total from one
> ability against the median of the players who took it — and the analyser holds both at the
> moment it divides them, so the panel states them instead of leaving a reader to divide the
> title's multiple back out of the detail's amount. The multiple carries `derived` as the one
> division; the two amounts and the count of players are read off the log and carry no tier of
> their own. The panel states figures only: that a difference is not a mistake, and that no log
> records whether a hit was avoidable, stay in the detail where §5.5's refusal of "avoidable
> damage" put them.

**Nothing is threaded into `build_report`, and no string is parsed back.** Planning found that
the figures a panel wants are indeed all present, but present as prose and as evidence strings —
"range 0.7 to 2.1 casts a minute across 5 top parses" — which a builder would have to take apart
again. Two mechanisms avoid that, one per half of the table:

- **The defensives families are built where `build.py` already stands.** It holds `loaded`, the
  per-actor aura tables and the defensives data file, which is everything `ability_tooltip`
  needs. It builds a `dict[str, Tooltip]` keyed by finding id, and the row builders look the
  panel up rather than computing it. `ledger_row` stays a formatter, which is what the
  overturned ruling was right to protect.
- **The other three carry their figures on the finding.** `Finding` gains
  `facts: tuple[FindingFact, ...]`, a label, a value and an optional confidence tier, populated
  by the analyser at the moment it already has the numbers in hand. The report turns facts into
  tooltip lines and computes nothing. This is the same discipline as `evidence`, in a shape a
  panel can render: `evidence` is prose for a list, `facts` are figures for a panel.

`report/deaths.py::_ability_tooltip` is already generic over its window and its hits, and a
ledger card differs from a death only in passing the whole run instead of a run-up. It moves to
`report/tooltip.py` as a public function and `deaths.py` imports it, rather than a second copy
being written next to it.

`ledger_row` passes the panel to `ability()`, which has taken an optional tooltip since the day
it was written.

### 6.3 What still carries no tooltip

> **Amended 2026-09-12.** A third category, added after `compare.spells.missing.*` was found to
> sit in neither list: it carries an ability id, so "findings with no ability" below does not
> reach it, and §6.2's table does not name it, so it was unaddressed rather than decided. The
> ruling is that it carries no panel.
>
> The category is **a comparison with only one side**. Every family in §6.2's table sets two
> figures beside each other — our rate against theirs, our boss-pull seconds against theirs — and
> that is the whole of what a panel does which the card's prose does not. This family's own side
> is zero: the title already says the player never cast the ability anywhere in the run, and
> there is no second figure to lay beside the reference's count. Two things follow that make the
> absence cost nothing. The card's `evidence` list is rendered on the page, so a panel here would
> repeat three lines a reader already has without hovering. And nothing reads as broken for want
> of one: `.ability` is styled identically whether or not a panel is attached, so no affordance
> is offered and left unanswered.
>
> This settles that family and no other. `players.damage.*` also carries an ability id and is
> named in neither list, and the category above does **not** cover it: it sets one player's
> damage from an ability against the median of the players who took it, which is two sides. It
> was ruled on the same day and **does** carry a panel; see the addition to §6.2's table above.

- **The death card heading.** Its ground was never answered: the heading names the killing blow
  and the recap row beneath it already carries that hit's own figures, with `hit_tooltip` on
  them.
- **Findings with no ability.** Twenty-one of this run's 34. There is no ability to hover.
- **A comparison with only one side.** `compare.spells.missing.*` names an ability absent from
  our run altogether, so our side of it is zero and a panel would set nothing beside the
  reference's count. See the amendment above.

### 6.4 The timeline rows

The cooldown rows already carry their facts, as a native `title` on each row group — "Dancing
Rune Weapon — 14 presses, 646.0 s of cover". Point 6 was raised against a page where this was
true, which makes it a complaint about the presentation and not the content: a native tooltip
waits about a second, takes the operating system's styling, and holds one line of plain text,
next to the panels the deaths tab draws.

The rows are promoted to the page's own `.tip` panel, carrying the figures they carry now and,
beside them, how much of the run the row spent in each of §5.2's four states. This is a
presentation change to something the 2026-09-11 design deliberately built, not a reversal of it.

A panel is HTML and a row is SVG, so the panel is positioned against the chart rather than
against the row's own rectangles. That is the one piece of this section with no precedent on the
page, and the plan should treat it as the task most likely to need a second attempt.

## 7. Interrupts: what can be said about interruptible

**The log carries no interruptible flag.** `analysis/interrupts.py` opens by saying so, and the
verified field list in `.claude/skills/wcl-api/SKILL.md` for `dataType: Interrupts` holds no
such field. Nothing in this design invents one.

What the log does prove: **a spell kicked at least once in this run was interruptible.** That is
`measured` — it rests on interrupt events the report already fetches and already counts.

So each `interrupts.ability.*` card gains one line:

- Kicked at least once: **"interruptible: kicked N times this run"**, measured.
- Never kicked: **"never kicked this run; the log does not say whether it could be"**, and the
  card says exactly that rather than implying a miss.

The second half is the half that matters. Today `interrupts.ability.0` says "Forked Lightning
landed 18 times" and never says whether anybody could have stopped it. A reader supplies the
missing half himself, and supplies it wrongly.

This line is the interrupt family's tooltip panel from §6.2, beside what landed and what was
kicked.

## 8. Testing

Every change here is behaviour, and every one of them gets a test that fails when the decision
is mutated rather than when the code is merely touched.

- **§4.1** — a cast with a resolvable band survives the filter and a cast without one does not;
  a heal of nought survives. The mutation that must fail a test is dropping the band check and
  keeping every cast.
- **§4.2** — the html invariants test already forbids what this must not do. The sticky wrapper
  adds no script, no link, no remote source.
- **§4.3** — a player who drank nothing from a category gets no row for it; a player who drank
  and is still inside the cooldown gets COOLDOWN. The mutation that must fail is restoring the
  UNSEEN to READY mapping.
- **§5.1** — one icon per row whatever the press count. The mutation that must fail is emitting
  an icon per press.
- **§5.2** — the key names four states, and the colours it names are the colours the track uses.
- **§6.2** — each family's panel renders from a finding of that family, and renders correctly
  with no description present.
- **§7** — a spell kicked once is reported interruptible; a spell never kicked is reported
  unknown and not as a miss.

The whole of it is then read on a real page. `analyze --all-players` against this same run is
authorised once, for that reading, and a warm cache last measured 78.21 points of 3600.

## 9. What this design refuses

- To join a cast to its heal by name. Bloodbath and Bloodthirst Heal settle it.
- To state whether a Healthstone can be carried without a Warlock.
- To colour the player timeline's track by ability, which would cost the four states their
  meaning.
- To reword the health curve's legends, which already say the true thing.
- To claim a spell was interruptible because it looks like one.
