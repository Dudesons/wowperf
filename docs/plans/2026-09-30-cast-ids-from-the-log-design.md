# Cast ids from the log

**Status:** approved and built, 2026-09-30.
**Area:** the hand-maintained ability data (`data/defensives.toml`,
`data/throughput_cooldowns.toml`, `data/externals.toml`) and the method that verifies it. The
analysers are unchanged: they match casts by `ability_id`, correctly. The ids they are handed
are wrong.

## 1. The defect

Every entry in these files was verified by looking its id up in the game's spell data and
checking that the name matched. That check proves an id **resolves**. It does not prove it is
the id the game **logs when the ability is pressed** today. Several of ours resolve correctly
to the right name, yet are never cast: the game now logs the press under another id, often
one from a later expansion. `data/throughput_cooldowns.toml`'s header already warns that the
spell data "still serves abilities removed from the game years ago". The check it describes
confirmed an ability still exists, not which id it now casts as.

Every analyser matches a press by id, so the tool cannot see these abilities being pressed.
The damage is concrete:
- **The death card prints a false sentence about a named player.** A monk who pressed
  Fortifying Brew, or a mage who pressed Alter Time, reads "not seen this run".
- **The defensives findings never judge those abilities.**
- **The throughput findings treat those presses as never made.**

A patch is not the cause. The live patch is 12.1 (live 2026-08-11). The hotfixes from
2026-09-03 to 2026-09-30 retuned numbers and changed no cooldown, charge or ability. Most of the
ids the log uses date from earlier expansions, so ours were wrong when they were written.

## 2. The evidence

The evidence was measured 2026-09-30, offline, from the warm cache, at no quota cost.

**Pass 1 (every id on its own):** across 1171 cached pages, every `type: "cast"` row was
collected. Each data entry was checked against those ids and against every report's
`masterData.abilities`.

**Pass 2 (per specialisation):** the eight fights that load with a roster were used:
- `cW38jmwdnZfbHVL4` fights 2, 30, 32, 8, 29, 31;
- `6Kx1P9GbNXrcLdHa` fight 36;
- `4vFcVAW1PB2CrD9z` fight 72.

Each same-named cast was attributed to the caster's class and specialisation.

**Confirmed.** In these cases the specialisation is present, our id is cast zero times, and
that specialisation casts the ability under another id:

| Ability | File | Specialisations | Our id | Id the log casts (count, 8 fights) |
| --- | --- | --- | --- | --- |
| Alter Time | defensives | Mage/Arcane, Fire, Frost | 108978 | 342245 (2) and 342247 (2), Arcane |
| Fortifying Brew | defensives | Monk/Mistweaver, Windwalker | 243435 | 115203 (2 and 15) |
| Bladestorm | throughput | Warrior/Arms, Fury | 227847 | 446035 (19 and 8) |
| Breath of Sindragosa | throughput | DeathKnight/Frost | 152279 | 1249658 (3) |
| Kingsbane | throughput | Rogue/Assassination | 192759 | 385627 (43) |
| Metamorphosis | throughput | DemonHunter/Havoc | 191427 | 200166 (11) |
| Odyn's Fury | throughput | Warrior/Fury | 205545 | 385059, 385060, 385062 (7 each) |
| The Hunt | throughput | DemonHunter/Havoc | 323639 | 370965, 370966 (19 each) |

**Likely, not confirmed.** In these cases no specialisation of ours was present in the eight
fights, and the other id was cast only in reference runs, where the pages name the class but
not the specialisation:
- Doom Winds, Enhancement: 384352 against 469270, cast 190 times;
- Killing Spree, Outlaw: 51690 against 474478, cast 5 times;
- Guardian of Ancient Kings, Protection Paladin: 86659 against 212641, cast 4 times;
- Metamorphosis, Vengeance: 187827 against 200166, which may be Havoc's;
- Berserk, Guardian: 50334 against 106951, which may be Feral's.

**Not suspects:**
- **Halo for Shadow** (120644) is right; Shadow casts it 47 times.
- **Halo for Holy** (120517) is never cast, and neither is any other Halo id, by a Holy priest
  who is present in 6 of the fights. That reads as a talent not taken.
- **About thirty other entries** are never named in any cached log at all, among them Ice
  Block, Champion's Spear and Eye of Tyr. The cache cannot tell a talent nobody took from a
  wrong id.

**The repository contradicts itself on Alter Time.**
- `.claude/skills/wcl-api/SKILL.md` (2026-09-11) says it is "cast `108978` against aura
  `342246`".
- Twenty-five lines later, the same skill records its two cast ids as `342245`/`342247`.
- The cache holds 108978 cast zero times in 1171 pages. The first line most likely recorded
  the data file's id rather than a measured cast.
- Comments in `tests/domain/report/test_build_deaths.py` and `tests/domain/test_cover.py`
  repeat it.

## 3. The rule

**An entry's id is the id the log casts when the ability is pressed.** The log is the authority
on which id, and the report's own ability table on its name. Both are recorded, dated, for
every changed entry.

Where one press logs several cast ids at once (Odyn's Fury's three, The Hunt's two, in equal
counts), the entry takes the one cast most often, the lowest id on a tie. The others are named
in a comment. Casts are **never summed across ids that share a name**: the skill records why,
and summing would count one press two or three times.

Alter Time is the case the rule has to state outright. Its first press, 342245, starts the
cooldown, and its second, 342247, ends the effect early. The entry takes 342245, so a press
counts once per cooldown.

**A corrected id keeps the entry's base cooldown, checked against the log.** *Decided
2026-09-30, over reading each new id's cooldown by hand.* It is the same ability, and its
cooldown was read from the spell data when the entry was written. No source this project may
script can confirm a new id's cooldown:
- **Wowhead's tooltip endpoint** is undocumented, ZAM's EULA prohibits scripted retrieval, and
  `wowhead.com/robots.txt` disallows `ClaudeBot`
  (`docs/plans/2026-09-08-icons-and-tooltips-spike.md`).
- **The Warcraft Logs `gameData`** fields for an ability's cooldown are unverified, and never
  invented.

**The log check.** For each corrected entry, the shortest gap between two presses of the new
id by one player, within one fight, is measured and recorded.
- **What it can show:** a gap shorter than the cooldown shows the data too long, or a talent
  shortening it. Both are the safe direction.
- **What it cannot show:** that the data is too short, the direction that would make a card say
  ready too early.
- **So:** that half is recorded as unverified, not assumed.

**The log decides between ids by what it casts.** Metamorphosis for Havoc is cast under 200166
alone in the eight fights, and no other Metamorphosis id is cast by that specialisation, so
200166 is what a press logs, whatever the spell data calls it.

## 4. What changes

- **The data files:**
  - the eight confirmed abilities, twelve entries in all, take the log's id and keep their
    base cooldown (§3), with the shortest same-player gap recorded beside each;
  - each file's header gains the rule in §3 and a dated line naming this pass;
  - the five likely ones are not changed. They are listed in the header as unconfirmed, with
    the evidence above, until a log of that specialisation confirms them.
- **The skill:** `.claude/skills/wcl-api/SKILL.md`'s Alter Time line is corrected, dated, and
  pointed at this design. The two test comments are reworded to the real pair: cast 342245,
  aura 342246. The resolver they test is still needed, since the cast id and the aura id still
  differ.
- **An audit command:** `wowperf audit-data [--cache-dir DIR]`. It is offline and reads only
  the local cache. For each of the three files it prints:
  - entries whose id was never cast;
  - for each of those, any same-named id that was cast, with counts;
  - ability and specialisation names only, never a player.

  It lives with the other commands so the next data pass runs the right check rather than
  rediscovering it. It adds a row to CLAUDE.md's command table, and `tests/test_skills.py`
  already checks every flag a skill names.

  *Rejected:* a one-off script kept in the skill. The check is needed every time the data
  changes, and a script nobody runs is the verification gap this design exists to close.

## 5. Testing

- **The audit command, test first, on a synthetic cache directory:**
  - an entry never cast whose name is cast under another id is reported, with its count;
  - an entry cast under its own id is not reported;
  - a same-named id seen only in an ability table, never cast, is not offered as the
    replacement;
  - no player name reaches the output;
  - every case is shown able to fail.
- **The data:**
  - the existing file tests pass: the no-overlap rule between files, and the toml loaders;
  - one test pins the twelve corrected ids, so a revert is caught. That test guards the data,
    not the game; the audit is what checks the game.
- **Live, warm, no points:**
  - for each of the eight abilities, on the eight fights: death-card rows by state for their
    owners, `unseen` before against the new distribution after;
  - the throughput and defensives findings that name them, before and after;
  - the audit's own output after the fix, which should list none of the eight;
  - for each corrected entry, the shortest gap between two presses of the new id by one
    player within one fight, against the data's cooldown;
  - any state that never occurs is recorded as open.
- **Goldens:** none should move, because none draws any of these abilities (checked
  2026-09-30).

**Live (2026-09-30, warm cache, offline).** The eight fights of §2 were read twice, once with the
old `defensives.toml` and `throughput_cooldowns.toml` taken from `main`, once with the corrected
files.

- **The audit.** Before the correction: "defensives: 34 of 139 entries never cast",
  "externals: 2 of 19 entries never cast", "throughput_cooldowns: 39 of 118 entries never cast".
  After: "defensives: 29 of 139 entries never cast", "externals: 2 of 19 entries never cast",
  "throughput_cooldowns: 32 of 118 entries never cast". Both read 1171 cached pages, and 1159
  distinct ability ids were cast. The twelve corrected entries left the lists: five in
  defensives, seven in throughput.
- **Death-card rows for the eight abilities, by state.** Rows were counted by ability as well as
  by state, and 24 rows carry one of the eight names on both sides. All 24 belong to Alter Time
  (11) and Fortifying Brew (13); no row named Metamorphosis, so Vengeance's unchanged defensive
  entry drew none on these fights, and the six throughput abilities draw no card row. Old: Alter
  Time 11 `unseen`, Fortifying Brew 13 `unseen`. New: Alter Time 1 `ready` and 10 `unseen`;
  Fortifying Brew 5 `cooldown`, 1 `pressed` and 7 `unseen`.
- **Findings naming one of the eight, by kind.** Old: none. New: 5 `defensives.ceiling` and 1
  `defensives.unused`.
- **Shortest gap between one player's presses of a corrected id, within one fight, against the
  entry's cooldown.** Each gap is the shortest for that id across every caster of it, whatever
  the caster's specialisation. An id can be pressed by more than one specialisation, each with
  its own entry, and the measurement does not say which caster the shortest gap came from.

  | Id | Ability | Shortest gap | Data cooldown |
  | --- | --- | --- | --- |
  | 342245 | Alter Time | 1033.4 s | 60 s |
  | 115203 | Fortifying Brew | 94.8 s | 420 s (Mistweaver, Windwalker) or 360 s (Brewmaster) |
  | 446035 | Bladestorm | 24.5 s | 90 s |
  | 1249658 | Breath of Sindragosa | 112.2 s | 120 s |
  | 385627 | Kingsbane | 60.3 s | 45 s |
  | 200166 | Metamorphosis | 121.1 s | 120 s |
  | 385059 | Odyn's Fury | 46.1 s | 45 s |
  | 370965 | The Hunt | 61.7 s | 90 s |

  Every id has a second press in these fights, so none reads "no second press". No cooldown was
  changed.
- **Two gaps sit under half their cooldown, and neither is explained.** Fortifying Brew's 94.8 s
  is under half of either 420 s or 360 s, so the conclusion holds whichever caster it came from,
  and Bladestorm's 24.5 s against 90 s is under half as well. Either might be a talent, a reset, or more than
  one cast row per press; the log cannot say which, and the cooldowns stand. Two more, Breath of
  Sindragosa and The Hunt, sit under their cooldown but above half of it. What the gaps cannot
  show is a cooldown set too short, so that half stays unverified (§3).
- **Fortifying Brew** keeps 420 s for Mistweaver and Windwalker beside Brewmaster's 360 s on
  purpose, since §3 keeps each entry's cooldown.
- **Two warm commands, as a reader sees them.** `wowperf raid` on fight 30 of
  `cW38jmwdnZfbHVL4` spent 1.00 point, and `wowperf analyze` on fight 36 of `6Kx1P9GbNXrcLdHa`
  spent 1.00 point. Counting `>None<`, `>null<`, `>nan<`, `{{` and `{%` in the two written pages
  gave 0 of each in both.

**Open.** These outcomes came out zero or never occurred, and none is a success:
- **The card states `held`, `faded` and `not judged`** were reached by no corrected row. Only
  `cooldown`, `pressed`, `ready` and `unseen` occurred, so the refinement of a press into `held`
  or `faded` was not exercised on these ids.
- **The throughput findings** named none of the eight, before or after, on either key. Nothing
  here shows that a corrected throughput id changes a throughput finding.
- **17 rows are still `unseen`: 10 for Alter Time and 7 for Fortifying Brew.** The log cannot
  say whether each is a player who never pressed the ability or an id still wrong. The audit no
  longer lists Alter Time or Fortifying Brew, which is the only check made; it still lists
  Vengeance Metamorphosis (187827), one of the five likely entries left unchanged.

## 6. Out of scope

- The five likely entries and the roughly thirty never named. They need logs from those
  specialisations. The audit will list them every time it runs.
- Modelling abilities whose one press logs several ids beyond choosing one.
- Talents that change an ability's id without changing its name; the audit surfaces them as
  they appear.
