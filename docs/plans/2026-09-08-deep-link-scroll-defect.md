# Deep-linking to a tab lands at the wrong scroll offset

Recorded 2026-09-08. A defect note, not a design: it states what was measured and what was
not, so the next session starts from evidence rather than from the guess this replaces.

## What happens

Opening the report at a fragment in a **fresh** tab — `…/6Kx1P9GbNXrcLdHa-36.html#deaths` —
selects the right tab and then leaves the reader scrolled thousands of pixels away from the
heading they asked for. The tab is correct; the position is not.

One measurement, taken over a real HTTP server:

| | |
| --- | --- |
| `location.hash` | `#deaths` |
| visible panel | `tab-deaths`, correct |
| `#deaths` heading, absolute top | 193 px |
| `window.scrollY` | 2274 px |

The heading sat 2081 px above the viewport. A reader following that link arrives inside the
deaths section with no idea they are not at its start.

## What this corrects

The defect was parked after Phase G's tab work on the belief that it appeared only in the
app's browser pane, which serves a local file as a `data:` snapshot and does not honour
fragments the way a served page does. That belief is wrong. The numbers above come from
`python -m http.server` over `http://localhost`, in a tab created fresh for the purpose.
It is a real defect in the report.

## The mechanism, as far as it was established

The tab script sits at the end of `<body>` in `src/wowperf/adapters/render/report.html.j2`.
Its first statement adds the `js` class to the root element, and the stylesheet rule
`.js .panel:not(.active) { display: none; }` only then begins to hide the five inactive
panels. Before that moment the document contains all six panels and is roughly three times
taller, so wherever the browser's own fragment scroll lands during parsing, it lands in a
document whose geometry is about to change underneath it.

The script does call `scrollIntoView()` on the fragment target, from `resolve()`, and binds
`resolve` to both `hashchange` and `load`. On the evidence that is not enough — but *why*
it is not enough was not established. A second load of the same URL reported a different
document height and a different scroll position from the first, and a manual
`scrollIntoView()` did not land where the element's own measured offset said it should.
Inconsistent readings across loads are what a race looks like, and they are also what an
unreliable measurement surface looks like. Which of the two this is remains open.

*Amended 2026-09-10:* the per-player page makes the pre-layout document taller again. The
Players panel gains a nested tab group with one sub-tab per player, each carrying a timeline
drawing, so before the `js` class lands the browser sees five players' content where it saw
one list. The defect's kind is unchanged — the scroll already landed in a document about to
change height — but its magnitude is not, and a harness built after that work should expect a
larger discrepancy than the 2081 px measured above. The decision to ship the page rather than
fix this first, and the reasoning behind it, are in `2026-09-10-per-player-page-design.md` §11.

## What not to do

Do not ship the obvious fix on this evidence. Emitting the `js` class from an inline script
in `<head>`, so the inactive panels are hidden before first layout and the browser's
fragment scroll only ever sees the final geometry, is sound in principle and cheap. It is
also unverifiable against a measurement surface that gave two different answers for the same
page, and a UI fix that cannot be demonstrated is a guess with a commit message.

## What to do

Use `superpowers:systematic-debugging`, and build a deterministic harness before touching
the template — the missing piece is a way to observe scroll position and document height at
known points in the load, reproducibly, rather than by sampling after the fact. Serve `out/`
over HTTP; `.claude/launch.json` in this repo has a `report` configuration that does exactly
that on port 8765. Confirm the reading in a real browser as well as the app's pane.

Then write the failing test first, as every change here does. What that test asserts is part
of the problem: the current render suite parses HTML strings in Python and cannot observe a
scroll position at all, so this defect is outside what any existing test could have caught.
That gap is worth naming in whatever replaces the render tests.

## Bearing on the UI rewrite

If the report is rebuilt as a React application, this defect either disappears with the
hand-rolled tab script or is faithfully recreated by a router that hides content after first
paint. Either way the requirement is the same and should be written down before that work
starts: **a deep link to a section must land at that section.** It is one line in a spec and
a day of confusion if it is missing.
