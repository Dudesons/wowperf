# Audit of the shipped tool, and a roadmap for what comes next

Date: 2026-09-06. Status: **proposal, not yet approved.** Nothing below has been built. Each
phase becomes its own design and plan under `docs/plans/` once RwlRwlRwlRwl has decided the open
questions in §5.

## 1. What was checked

- Every module under `src/wowperf/`, read against the approved design
  (`2026-09-03-mplus-postmortem-design.md`), the report design, the inference-layer design, and
  the three skills.
- The one real output in `out/` — report `6Kx1P9GbNXrcLdHa`, fight 36, Den of Nalorakk +16 —
  opened in a browser and cross-checked against the cached raw events it was built from.
- Five live schema probes against Warcraft Logs, 9.45 points in total, recorded with today's date
  in `.claude/skills/wcl-api/SKILL.md` under "The event stream, probed for a death recap".

The short version: the architecture is sound and the discipline is real. The domain layer performs
no I/O, every finding carries a badge, the tests exercise behaviour rather than mocks, the pull
alignment and keystone-gap withholding are implemented as designed, and the wording rules keep
the tool from overclaiming. The defects below are the kind that only show on real data — the
same lesson every earlier plan recorded.

## 2. Defects, ranked by what they do to the reader

Confidence labels: **confirmed** means reproduced against the cached events; **likely** means
read from the code and not yet reproduced.

### D1. Pull alignment fails on chained pulls, so the biggest number on the page is an artefact — confirmed

The design (§6.3) aligns pulls on the exact multiset of NPC types. Warcraft Logs merges packs that
were chain-pulled without a combat drop into one `dungeonPull`. On the real run, our pull 10 is a
324-second stretch covering several packs that the reference fought as separate pulls, so its
signature matches nothing. Result: 4 of 12 pulls aligned, 8 "only ours", 8 "only theirs", and the
top ranked loss reads "The reference skipped the pack at pull 10 — 5:24" for a pack the reference
plainly did fight. Four of the five "skipped pack" findings, 11 minutes of "loss", are the same
artefact. The timeline shows it too: two thirds of both tracks are drawn as skipped or extra.

Fix: amend §6.3. Align on **set overlap with merge tolerance** — a pull on one side may match a
run of consecutive pulls on the other when the union of their NPC types covers it — and price a
skipped pack only when the match rate for the run is high enough to trust. Below that rate,
withhold the skipped findings with the reason stated, exactly as the keystone gap is handled
today. The summary finding should say how many pulls aligned so the reader can weigh the rest.

### D2. Skipped packs are priced per NPC type, not per enemy — confirmed

`comparison/route.py::_forces` sums `npcCountMap` over `pull.enemies`, but `enemyNPCs` lists one
entry per NPC *type* (the schema has no `instanceCount`; rejected live today). The same pull 10 is
priced at 83 forces by the route finding and 160 forces by the trash finding on the same page.
`analysis/trash.py` already computes forces from the enemy deaths inside the pull window, which
is correct. Route must use the same figure.

### D3. The death cost anchor produces impossible numbers — confirmed, cause open

`Death.seconds_until_next_action` is death → the player's next `cast` event. On the real run two
of four deaths show a cast 3.4 s and 5.6 s after death, followed by 20+ seconds of silence, with
no resurrection cast by anyone in between. Whatever those casts are, they are not the player
playing again. The four deaths therefore total "15 s of play" while the same page shows the timer
penalty was 60 s, and the finding's fixed sentence "which is longer than the timer penalty" is
false on this run.

Fix: a spike first — read the `All` stream around those two deaths and find what a resurrection
and a release look like in this schema (there is no `Resurrects` data type). Then anchor the cost
on evidence of being alive again — a resurrection cast targeting the player, a self-resurrection,
or the player's first damage or healing *done* — and make the detail sentence conditional on the
comparison it states. Section 5.2 of the design gets an amendment.

### D4. A finished, tested analyser is not wired in — withdrawn

The audit's review agent reported that `analyse_consumables_never_used` was never called from
`analysis/service.py`. That was wrong: the service calls it, and the real report carries its three
`consumables.never.*` findings. Checked 2026-09-06 before Phase G was planned. Nothing to do; kept
here so the numbering in the plan stays stable.

### D5. Affixes are printed as identifiers — confirmed

The header reads "Affixes 9, 10, 147". The design (§3.5) says affix names resolve from `gameData`
at runtime. Nothing resolves them.

### D6. A tank taking melee damage is reported as an outlier — confirmed

"Dudesons took 210.2× the group median from Melee" is a Blood Death Knight doing the job. The skill
excuses this with "the tool cannot tell which specs tank", but the roster carries the spec name,
and spec → role is a table of thirty-nine rows that changes once an expansion. Add
`data/roles.toml` with a verified-on date, and suppress melee-type outliers for the tank rather
than printing the loudest false positive on the page.

### D7. `analyze` never reads the rate limit — confirmed

Design §3.3 and the risk table both require `rateLimitData` before and after every phase. Only
`fetch` reads it. The command that spends the points does not, so the "roughly 28 points" figure
in the skill has no instrument behind it.

### D8. The cache never expires anything — confirmed; terms-of-service shape is the concern

`adapters/cache/disk.py` keeps every response forever, including leaderboard rows and every
reference run's full event streams. Two consequences: a "fastest run" reference never refreshes,
and repeated use accumulates exactly the standing store of other players' logs that RPGLogs §5d
forbids and the skill promises not to build. Design §3.3 promised a tiered policy. Implement it:
finished-fight data may stay, rankings expire in hours, and reference-run event streams are
removed once the comparison that fetched them is written.

### D9. Death findings are shown twice — confirmed

Each death's "defensives off cooldown" and "consumables clear" appear on the death card *and*
again as findings under "Other findings", with the same three-sentence caveat repeated per player.
The "every finding exactly once" test passes because the death card is not a finding, but the
reader sees the same claim six times. The death section should own these; the observations
section should not repeat them.

### D10. Documentation drift, three places — confirmed

- The event-stream fields `ingest.py` reads (`killingAbilityGameID`, `unmitigatedAmount`,
  `sourceInstance`, `targetInstance`, `extraAbilityGameID`, …) were verified in the Plan B plan
  file and never carried into `wcl-api/SKILL.md`, which CLAUDE.md names as the only authority.
- `--throughput-ceiling` exists in the CLI and is absent from `analyzing-a-run`; the drift test
  checks only that named flags exist, not that every flag is named.
- The design still lists `--deep` in §3.6 and 0.5 for the ceiling fraction in §5.7; the code
  shipped neither, for reasons recorded only in code comments and §11.

### D11. Smaller reader-facing defects — confirmed

- `interrupts.ability.*` details print raw integers ("102801762 unmitigated damage") while the
  evidence line beside them is formatted.
- `time.gap.*` and `trash.pull.*` still print "map position x=488860, y=467099", which no reader
  can use; the report design §12 said this would be aligned with the route findings.
- The affix list on both references is captured and never compared (design §6.2 asks for the
  difference to be displayed).
- The debuff half of the uptime comparison ships inert, as recorded; it should either be removed
  or replaced by the group-wide figure the API does give.

## 3. What the audit did *not* find

No I/O in the domain layer. No finding without a badge. No hardcoded season identifiers. No
GraphQL field invented. No arithmetic error in the residual, the chain grouping, the aura band
union, the ceiling maths, or the keystone-gap withholding. No test asserting only on a mock. The
comparison logic, once alignment is fixed, is trustworthy.

## 4. Roadmap

Four phases. G is fixes and can start on approval. H, I and J are new work and each needs the
brainstorm → design → plan cycle CLAUDE.md prescribes; the notes below are the starting position
for those brainstorms, not their conclusion.

### Phase G — make the current page true

D1 through D11, in that order. D1 and D3 amend the design (§6.3, §5.2); the rest are bounded.
Every fix follows TDD and is re-checked against the real run in `out/`, because that is where each
of these was found. Expected outcome: the top of the ledger names real losses, the death costs are
believable, and the header names the affixes.

### Phase H — restructure the report into tabs

The report design's §11 ruled out navigation and interactivity on the argument that a report
needing navigation is too long. Seventy cards on one page for a clean +16 has settled that
argument: the page is too long *and* the reader needs all of it, because different readers want
different parts. Proposed tabs, one question each:

| Tab | Question it answers | Content |
| --- | --- | --- |
| Summary | Did we time it, and where did the time go? | header, narrative, the three decomposition rows, the timeline, top five ranked losses |
| Route & tempo | What did the route cost us against the reference? | skipped and extra packs, gaps, downtime, trash rate, route summary, confounds |
| Deaths | Why did each death happen, and what was available? | one recap per death (Phase I) |
| Players | What can each player look at? | one sub-tab per player (Phase J) |
| Interrupts | What got through? | as today, formatted |
| Provenance | Where did this come from, and what was withheld? | as today, plus the badge legend and the rate-limit reading |

Two ways to build tabs while keeping the page a single offline file:

- **CSS only**, with `:target` or hidden radio inputs. Preserves the "no script" invariant test
  untouched. Deep links work with `:target`; nested per-player sub-tabs do not, because only one
  element is the target at a time.
- **A small inline script**, restricted to showing and hiding. Nested tabs and remembering the
  last tab are trivial. Requires amending §11 and rewording the invariant: the page fetches
  nothing and the script writes no text, so the template still decides nothing.

Recommendation: the inline script, with every section visible when scripting is off so the
no-script page degrades to today's layout. The "decides nothing" rule is about judgement, not
about navigation.

Every existing invariant survives: one file, no external resource, every finding once, no
total row, withheld sections keep their heading and reason.

### Phase I — the death recap

The target is the Details! death log RwlRwlRwlRwl pasted: the last seconds before a death as one
timeline of damage taken, healing received, absorbs, and the player's own health, and beside it
the state of every defensive and consumable at the moment of death. Verified today, everything
this needs is available:

- **Damage taken** — already fetched. Add `absorbed` and `mitigated`, already in the payload.
- **Healing received and absorbs** — `dataType: Healing` scoped by `targetID`, including
  `absorbed` events naming the shield that soaked the hit.
- **Health over time** — `includeResources: true` on the player's own `cast` and
  `resourcechange` events, which carry the source's `hitPoints`/`maxHitPoints`. The hits they took
  do not carry it, so the curve is stepwise and the badge is `derived`.
- **Overkill and the killing blow** — the `Deaths` table gives both, per death.
- **Cooldown status** — extend `defensives_up_at` and `consumables_up_at` to return, for each
  ability the player cast somewhere in the run, either "ready" or "on cooldown, at most N s
  remaining by base cooldown"; abilities never cast in the run are listed as "not seen this run"
  rather than judged. Badge stays `inferred`, and the reason stays on the card: the log records
  no cooldown resets, charges or talent reductions, so a remaining time is an upper bound.
- **Resurrection** — from D3's spike; the card should show how the player came back and when.

Cost: two more event queries per fight (healing per dying player, casts with resources), measured
at run time via D7.

### Phase J — a per-player page

What readers know from WoWAnalyzer, rebuilt from what this project already measures, and without
overturning two recorded refusals: no hand-written rotation rules (design §2.6) and no damage
ranking (§5.5). Per player, one sub-tab:

- **Cast activity per pull** — casts against pull time, as a bar per pull rather than one line.
  Derived, coarse, and said to be.
- **Cooldown usage timeline** — every tracked throughput and defensive cooldown as a row, with
  presses marked on the run's clock and the big pulls shaded. This is the throughput-alignment
  finding drawn instead of written, and it makes "held for the next pack" visible rather than
  arguable.
- **Damage taken against defensives pressed** — the damage-taken stream summed per few seconds,
  with defensive casts overlaid, so a spike with nothing pressed is visible.
- **Deaths, interrupts, damage taken by ability against the median** — as today, gathered.
- **Comparison against a top parse** — spells never cast, casts per minute, talents, uptime, as
  today for the subject. Extending it to every player costs one parse reference per spec, roughly
  five to ten points per run; the flag `--player` becomes optional rather than the default scope.

What this phase does not do, unless RwlRwlRwlRwl decides otherwise in the brainstorm: score a
rotation, grade a player, or rank damage.

## 5. Decisions needed before any of this is built

1. **Tabs**: inline script with a no-script fallback (recommended), or CSS only?
2. **Death cost**: approve the D3 spike and the §5.2 amendment that follows it.
3. **Alignment**: approve replacing exact-signature matching (§6.3) with overlap-and-merge
   matching plus a match-rate gate.
4. **Personal page**: stay inside the design's refusals (recommended), or add a per-spec rulebook
   the way WoWAnalyzer does, accepting that it must be maintained by hand every patch?
5. **Parse references**: for the subject only, as today, or for every player at the extra quota
   cost?
6. **Cache policy**: agree the tiers in D8, in particular that reference-run event streams are
   deleted after the report is written.
7. **Order**: G → H → I → J is the proposal. I before H is defensible if the death recap matters
   more than navigation.
