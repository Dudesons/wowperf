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
