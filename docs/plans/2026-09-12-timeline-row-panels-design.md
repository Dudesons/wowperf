# Player timeline row panels — design

Status: approved 2026-09-12. Implements §6.4 of
`docs/plans/2026-09-12-report-second-reading-design.md` and **corrects that section's account of
the four states**; see §8.

## 1. Why

Point 6 of the second reading was "the player tabs have no tooltips". §6.4 read that as a
complaint about presentation, on the ground that the rows already carry their facts as a native
`title` on each row group. Read against the rendered page, that ground is wrong twice over.

**The row's tooltip mostly does not fire.** Pull bands are drawn at `band_y` with
`column_height = height - 56`, so they run the full height of the chart behind every row. SVG
hit-tests the topmost painted element, and a row paints only where something happened. Across the
rest of the row the band beneath is what the pointer finds, and it answers with its own `title` —
the pull's name. Measured on the live page, one Death Knight row paints 16% of its track, so 84%
of that row answers a question nobody asked.

**A native title cannot grade a figure.** `_cooldown_hover` states measured figures only, and its
docstring says why: the row also draws the stretches the ability was unavailable, and those are a
base cooldown from `data/` laid over the presses rather than anything the log stated. An SVG title
carries no badge. So the chart draws an inferred claim and its tooltip is forbidden from stating
it.

Promoting the row to the page's own `.tip` panel answers both. The panel is a reliable hover
target, and it carries badges, which is what earns the right to state the inferred figures at all.
§6.4 undersells itself: this is not presentation alone.

## 2. What a row panel says

**Heading:** the ability's name, rendered by the template from `row.label` — the same string the
row's SVG `<text>` prints, so the heading and the drawn label cannot disagree.

| Line | Example | Tier |
| --- | --- | --- |
| Presses | `14` | measured |
| Not judged | `8%` | inferred |
| On cooldown | `88%` | inferred |
| Ready and unpressed | `4%` | inferred |
| Buff up | `646.0 s` | measured |

**Note:** where the run's aura tables say nothing about the ability, `NO_AURA_DATA` appears and
the *Buff up* line is absent. `_cover_bands` already distinguishes "no table for this ability"
from "a table that recorded no window", and that distinction is what the note exists to state.
Printing zero seconds of cover would state as a measured figure a thing nobody measured.

### 2.1 Why three shares and not four

§6.4 asks for "how much of the run the row spent in each of §5.2's four states". **The four states
do not partition a row.** Cover overlaps the cooldown almost always, because the buff is up while
the cooldown runs. Measured across all 19 rows of the live page:

| Row | Not judged | On cooldown | Cover | Sum |
| --- | --- | --- | --- | --- |
| Recklessness | 6% | 99% | 44% | **149%** |
| Dancing Rune Weapon | 8% | 93% | 42% | **143%** |
| Vampiric Blood | 6% | 85% | 22% | **112%** |
| Spell Reflection | 2% | 34% | 6% | 42% |
| Impending Victory | 2% | 4% | 0% | 6% |

Four shares that sum to 149% read as a broken panel, and a caveat explaining the overlap asks the
reader to absorb an explanation before any number means anything.

So the panel states a partition instead. Not judged, on cooldown, and **ready and unpressed** do
cover the track exactly once, and cover sits apart from them, in seconds rather than as a share.
The unit change carries meaning: seconds mark a measured count, shares mark an inferred split.

**Ready and unpressed is the figure worth having.** It is the complement of the other three — the
stretch that is judged, off cooldown, and unused — and it is the gap a reader can see on the chart
and cannot currently put a number to. On the same page it runs from 0% on Recklessness to 94% on
Impending Victory, and it is the same claim `defensives.ceiling.*` already makes in words.

### 2.2 Apportionment

Three shares rounded independently can sum to 99 or 101, and computing the third as
`100 - a - b` can land it at −1. The three are therefore apportioned by largest remainder: floor
all three, then hand the leftover points to the largest remainders. Standard, six lines, and it
makes "the shares sum to 100" a property the code guarantees rather than a coincidence the
rounding usually allows.

### 2.3 Tiers

Measured lines carry no badge. `TooltipLine.tier` has meant "None is measured" since it was
written, and that convention stands.

The three shares carry **inferred**, because the cooldown length is a base value from `data/`
that talents shorten and the log never records a reset — the same claim
`BADGE_INFERRED_CAPTION` already grades on the chart itself.

## 3. How it is drawn

A panel is HTML positioned against an HTML ancestor, and a row is SVG. The row is therefore not
the thing the panel hangs from. A transparent HTML strip is laid over each row inside a positioned
wrapper, and the panel hangs from the strip.

```html
<div class="timeline-wrap">
  <svg class="player-timeline" viewBox="0 0 680 204"> … </svg>
  {% for row in timeline.cooldowns %}
  <div class="row-hit" tabindex="0" aria-label="{{ row.label }}"
       style="top: {{ row.hit_top }}%; height: {{ timeline.row_hit_height }}%">{{ tip(row.tooltip, row.label) }}</div>
  {% endfor %}
</div>
```

```css
.timeline-wrap { position: relative; margin: 10px 0 2px; }
.player-timeline { display: block; width: 100%; margin: 0; }
.row-hit { position: absolute; left: 0; right: 0; }
.row-hit:hover .tip, .row-hit:focus-within .tip { display: block; }
```

`.tip` itself is untouched. The strip reveals the page's existing panel, so a row panel is not an
imitation of the 49 panels already on the page — it is the same panel.

### 3.1 The two numbers, and why they are exact

`hit_top = baseline_y / height × 100` per row, and `row_hit_height = row_height / height × 100`
once for the chart. This is the split `row_icon_x` and `row_icon_size` already use: what every row
shares belongs to the timeline, what differs belongs to the row. Both are computed in
`player_timeline.py`; the template still computes nothing.

The viewBox fixes the aspect ratio, so with `width: 100%` the rendered height is always
`renderedWidth × H / 680`. A row at `baseline_y` therefore sits at `baseline_y / H` of the rendered
height, at every window size, and a percentage `top` resolves against exactly that height.

**This is the answer to the trap §6.4 names.** The viewBox is not an obstacle to an HTML panel; it
is what makes the panel's position computable without measuring the page. The script stays as it
is — `test_the_script_resolves_a_marker_by_id_suffix_and_computes_no_position` forbids
`getBoundingClientRect`, `offsetLeft` and `getComputedStyle`, and nothing here needs one.

The margin moves from the svg to the wrapper deliberately. A margin inside the wrapper would
offset every strip by its own height.

### 3.2 The panel opens upward, always

`.tip` opens upward and keeps doing so. At a 1400px container the chart renders about 410px tall,
putting the first row about 190px down, which a panel of about 126px clears. Overhang begins only
below roughly a 1000px viewport, where it lands on an opaque panel over the stats line, with
nothing clipped — the stylesheet's only `overflow` rule is on `.icon-defs`.

Per-row flip logic would buy that narrow case at the cost of a field, a CSS variant and a test.
It is not bought.

### 3.3 Keyboard

Each strip takes `tabindex="0"` and an `aria-label` naming its ability, adding 19 tab stops to a
page that has 49. This is `ability()`'s documented rule applied unchanged — a tab stop only where
there is a panel to reveal — and every row has one. The browser's own focus ring lands on the
strip, which outlines the row the panel describes.

## 4. What this displaces

**The `<title>` on each row's `<g>` goes.** §5.2 already ruled it: one key beneath the chart, one
panel on the row, never two tooltips competing over one pointer. `CooldownRow.hover` and
`_cooldown_hover` become orphans and go with it. Their rule survives into the new builder, because
it is still right: the figures are summed from the drawn spans and never from the aura table's own
total, so the number a reader hovers and the rectangles they are looking at cannot disagree.

**The strips cover the pull bands where they run behind the rows.** This is the repair of §1, not
a loss. Bands stay hoverable in the damage track above the rows, which is where a reader pointing
at a pull already is.

**The damage buckets keep their native `title`.** All 1074 of them, from §5.3. Panels there would
put 1074 more panels into a page that is already about 600 KB. The chart carries two hover
vocabularies on purpose — rows answer with a panel, buckets with the operating system's tooltip —
and this design states that rather than leaving it to be found.

## 5. Where the code goes

**One panel markup, not two.** The `.tip` block is inline inside `ability()` today. It moves to a
`tip(tooltip, heading="")` macro in `_macros.html.j2`; `ability()` calls it with no heading, the
timeline calls it with the row's label. One place decides what a panel looks like, so the two
surfaces cannot drift. A new rule styles the heading:
`.tip-head { display: block; font-weight: 500; margin-bottom: 4px; }`.

**`model.py`.** `CooldownRow` loses `hover` and gains `tooltip: Tooltip | None` and
`hit_top: float`. `PlayerTimeline` gains `row_hit_height: float`.

**`player_timeline.py`.** `_cooldown_hover` is replaced by `_row_shares`, which apportions the
partition, and `_row_panel`, which builds the five lines and the note. `_chart_height(row_count)`
is extracted, because the stamping pass and `build_player_timeline` need the same formula and one
of them keeping its own copy is how the two drift.

Both halves of the panel read from the drawn windows and never from anything behind them, which is
the discipline `_cooldown_hover` already states: the panel's claim is about what the reader is
looking at, so the number and the rectangles cannot disagree. The units differ because the claims
do. The three shares divide the `Span` tuples the chart holds by the track's own width —
`TRACK_X1 - TRACK_ORIGIN_X`, 506 units — since a share is a share of the drawing. *Buff up* sums
the clipped aura bands in milliseconds, as it does today, since a duration is a duration.
Rounding a span to a tenth of a unit costs 0.02% on that track, below the printed precision.

**`_player_timeline.html.j2`.** The wrapper, the strips, and the deleted row `title`.

**The golden file** is regenerated, and its diff is read before it is accepted.

## 6. Testing

Eight tests, each named with the mutation that must turn it red.

| # | Layer | Pins | Mutation |
| --- | --- | --- | --- |
| T1 | domain | the three shares sum to 100 | round each share independently |
| T2 | domain | overlapping cooldown spans are unioned | sum the widths instead |
| T3 | domain | no aura table gives the note and no *Buff up* line | print `0.0 s` of cover |
| T4 | domain | the three shares carry the inferred badge | drop their tier |
| T5 | domain | `hit_top` is the percentage, not the unit | use `baseline_y` directly |
| T6 | render | the strips are siblings of the `<svg>` | move them inside it |
| T7 | render | no row `<g>` carries a `<title>` | restore `row.hover` |
| T8 | render | no `height` attribute, no `preserveAspectRatio` override | set `preserveAspectRatio="none"` |

Three of these earn their place from the failures of the last plan.

- **T2** is the defect the measurement found. A naive sum puts one row's cooldown alone at 101%.
- **T4** pins the `FindingFact` lesson in a second place. `tier=None` means measured, so an
  ungraded share would silently badge an assumed cooldown as read from the log.
- **T6 and T7 sit in the render suite, not the domain**, because that is the only layer where
  their mutations can fail. A strip emitted inside the `<svg>` positions against nothing and still
  satisfies any count made in the domain — which is the error the one-icon-per-row test made
  before it was moved.

The whole of it is then read on a real page. No API call is authorised by this design; the
rendered report on disk and the offline fixtures are enough to read every change here.

## 7. What this design refuses

- To give the 1074 damage buckets panels.
- To compute any position in the inline script.
- To flip a panel's direction per row.
- To state the four track states as four shares of the run.
- To restyle or recolour the track, which §5.2 settled.
- To use `<foreignObject>`. It would carry the existing `.tip` markup into the SVG unchanged, but
  its box is sized in viewBox units and its overflow is clipped, and the height depends on text
  wrapping, which Python cannot predict. A wrong guess clips the panel silently, and no test
  would catch it.

## 8. Amendments to the second reading

**§6.4's four states.** Corrected here by §2.1. The section asks for a share of the run in each of
four states; three of those four overlap, and the panel states a three-way partition with cover
beside it instead.

**§6.2's count was wrong, and that section now carries an amendment note saying so.** It promised
`ability_tooltip` for all five `defensives.ceiling.*` and `defensives.never.*` findings, and one
panel appeared on the live page. The cause is honest: `run_ability_tooltip` abstains where
`resolve_aura` finds nothing, the three `defensives.never.*` findings name abilities their player
never cast, and the Warrior's Impending Victory is one of three abilities the page already says
"No aura data for it" about on its own timeline row. The abstention is correct; the count was
wrong, because it counted findings rather than findings whose ability resolves an aura.
