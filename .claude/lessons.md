# Lessons

A log of corrections. Every time RwlRwlRwlRwl corrects a mistake, what gets written here is
the **rule** that would have avoided it — not the story of the incident.

To be re-read at the start of a session, before working on this repository.

## Format

```markdown
## YYYY-MM-DD — Short title of the rule

**What happened:** one or two factual sentences.
**The rule:** the imperative to apply next time.
**Scope:** where it applies (file, domain, or "everywhere").
```

A lesson that cannot be phrased as an imperative is not one: it is an anecdote, and it does
not belong here. If two lessons say the same thing, merge them.

---


## 2026-09-11 — Compute a drawing's geometry; never eyeball it

**What happened:** A mockup of the run timeline drew buff cover windows 26-52px wide. At the
real scale — 570px for a 1980-second run — a five-second buff is 1.4px. The drawing overstated
those durations by more than an order of magnitude, and it took RwlRwlRwlRwl asking what the
picture meant to expose it.

**The rule:** Derive every coordinate in a chart, diagram or mockup from the real values, in
code, before drawing it. A picture that misstates a quantity is a false claim exactly as a wrong
number is, and it is harder to catch because nothing type-checks it. If the honest scale makes
something too small to read, say so and move the readable version somewhere the scale allows —
do not draw it bigger.

**Scope:** everywhere, and especially any SVG this project renders or proposes.

## 2026-09-11 — Enumerate every ref before calling a cleanup complete

**What happened:** After rewriting every commit's author email, the backup branch was dropped
and the job described as finished. A stale worktree branch still held 325 commits on the old
address, so the repository was not clean and the claim was wrong.

**The rule:** Before saying a thing has been removed from a repository, list every ref, worktree
and reflog that could still reach it, and show the count is zero. "The obvious holder is gone"
is not evidence; `git log --all` finding nothing is.

**Scope:** any history rewrite, branch deletion, or dependency removal.

## 2026-09-11 — State a git flag before running it, not after

**What happened:** Two branch merges used `--ff-only` without announcing it first. The flag is
not on the forbidden list and is the safer choice, so both merges were fine; the process was
not. The second happened after the first had already been noticed and named, which is what
makes it a lesson rather than a slip.

**The rule:** Say the flag, why, and that it is not forbidden, in the message *before* the
command runs. A safe flag does not exempt you: the rule exists so RwlRwlRwlRwl can see the
intent before the effect, and a flag chosen silently is indistinguishable from one chosen
carelessly. The same applies to `git add -u` — stage by name.

**Scope:** every git invocation.

## 2026-09-11 — A measurement's method is part of its claim

**What happened:** Ability-id collisions were measured by grouping cast events by cache file.
One report's event stream is paginated across several files, so one actor's presses were split
and overlapping events were counted twice. Four aggregate figures survived the error; three of
five per-ability rows did not, including the exemplar the code was written for. The wrong
figures reached a skill file whose whole discipline is verified claims, and a reviewer caught
them by re-measuring.

**The rule:** When recording a measured figure, record how it was measured in the same breath —
the grouping, the de-duplication, the window. Then re-derive the headline claim by a second
grouping before writing it down. A cache is a set of pages, not a set of runs; join them by
report and de-duplicate events before counting anything.

**Scope:** anything written into `.claude/skills/`, and any figure quoted in a docstring.

## 2026-09-12 — A harness needs its own spot check

**What happened:** A mutation harness rewrote one module in a loop to prove which test pinned
which line. CPython validates a cached `.pyc` on source mtime and size, and four of the
mutations deleted the same guard line at four call sites, so consecutive runs produced files of
identical size milliseconds apart and each one executed the previous one's compiled module.
The table it printed attributed three of four call sites to the wrong test. The aggregate —
zero surviving mutations — was correct throughout, so nothing looked wrong. Two direct
single-mutation runs exposed it.

**The rule:** A tool built to produce a measurement is not itself evidence. Before believing a
harness's table, reproduce one row of it by hand; if the hand-run disagrees, the table is
wrong, not the hand-run. Distrust a per-item breakdown whose aggregate looks healthy — an
aggregate over a set survives a corrupt partition, and the per-item rows are precisely what it
corrupts. When the harness rewrites source between runs, disable bytecode caching outright.

**Scope:** mutation batteries, benchmark loops, anything that edits a file and re-executes it.

## 2026-09-12 — Commit before you hand a file to a script

**What happened:** Reverting one mutation with `git checkout <file>` discarded the whole
uncommitted implementation the mutations were testing, because the work had never been
committed. It was recoverable only because the edit had been applied by a saved script.

**The rule:** Commit the work before running anything that reverts files, and back up any
generated file a script will overwrite. `git checkout <path>` and `git restore <path>` destroy
uncommitted changes silently and are the natural way to undo a scripted edit.

**Scope:** any script that writes to tracked files.

## 2026-09-28 — A replacement sentence is a claim; verify it before ruling it in

**What happened:** A task review found the night page saying "No reference run was fetched"
on pulls that had fetched reference kills. The controller ruled in a replacement pointing the
reader at `raid --fight N` for the missing comparison, without checking what `raid` draws on
a wipe. It draws none: the parse axis is withheld on every wipe. The fix swapped one false
sentence for another, reached two of the four places the old one printed, and a test pinned
the new falsehood. Only the final whole-branch review caught it.

**The rule:** Before writing or ruling in any sentence the page will show, find the code path
that makes it true on every pull it can reach, and grep every site that prints the sentence
being replaced. When a spec says "the page X draws", reuse X's own sentence rather than
composing a new one.

**Scope:** any user-facing reason, notice or disclosure text, and any ruling that supplies one.

## 2026-09-29 — A fixture clock that starts at zero hides every origin bug

**What happened:** Every test of the heavy-moment analyser used a span starting at 0 ms, and
the Mythic+ service fixture's first pull started at 0 too. Two defects passed four task
reviews that way. First, a cooldown pressed before a key's first pull printed "pressed at
-1:45": a keystone's casts are read from the fight's start, but the page's clock starts at
the first pull. Second, passing 0 instead of the span's start as the visibility origin would
have turned "not judged" into "cooldowns ready" on real, report-relative timestamps, and no
test could fail on it. The final whole-branch review found both by reading how the live
report's timestamps were built.

**The rule:** When code subtracts an origin, give the test helper a non-zero origin by default,
so every clock assertion runs off one. Then ask whether any input stream can start before
that origin (casts, deaths, auras read from the fight's start while the clock starts later),
and pin that case with a test.

**Scope:** any analyser or builder that turns timestamps into clocks, cooldown windows or
visibility cut-offs.
