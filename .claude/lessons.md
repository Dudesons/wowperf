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
