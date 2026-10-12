---
name: evidence
description: Answer "why" questions with CoAIch's own rule and the studies behind it, graded honestly. Use when the athlete asks "why 10 sets?", "why this rep range?", "why did my squat go up (or down, or stay)?", "is this backed by research?", "where does that number come from?", or doubts a target, a gate or a macro.
---

# Evidence

Answer from CoAIch's own files, never from memory. Every rule here has a row that names its grade and source.
If no row covers the question, say so: "CoAIch has no rule or study on that." Never invent a study, an author,
a PMID, a DOI or a number. This skill does not search the literature.

## 1. What kind of "why"?

- **Why does my target say X?** (a weight, reps, a hold, a cut) → 2.
- **Why does CoAIch do X?** (sets, rep ranges, reps left, easy weeks, frequency, macros, ratings) → 3.

## 2. Why did my target change

Find the week: the newest `plan/targets/targets_<week>.json` (or the week the athlete names). Then:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/progression.py" explain --dir . --week {week} --find "<exercise words>"
```

It prints before → after, the decision, the reason code in brackets, last week's grade and sets, and the
script's own sentence. Read nothing from the JSON by hand.

1. Say the sentence first, in the athlete's words ("You met every set at the top of the range, so the weight
   went up one step").
2. Find the reason code's row in the Decisions table of [rules.md](../progression/rules.md) and give the rule
   behind it in one line.
3. Then the evidence for that rule, from the Evidence list at the end of rules.md and 3 below. Most step sizes,
   caps and miss counts are **our rule**: say so.

A coach override shows its own reason ("Coach override: …"). It is a decision, not a rule: quote it.

## 3. Why does CoAIch do X

Search the references for the topic words (Grep is enough):

| Topic | File |
|---|---|
| sets, frequency, effort, reps left, rep ranges, rest, order, easy weeks, exercise choice, women, 60+ | [evidence.md](../../references/evidence.md) |
| MEV / MAV / MRV, effective sets, coaching bands | [volume-landmarks.md](../../references/volume-landmarks.md) |
| calories, protein, fat, weekly loss cap, safeguards | [nutrition.md](../../references/nutrition.md) |
| photo ratings, priorities, timelines | [muscle-rubric.md](../../references/muscle-rubric.md) |
| templates, prescriptions, placement, pain swaps | [starter-programs.md](../../references/starter-programs.md) |
| easy-week shape, week types | [periodization-system.md](../../references/periodization-system.md) |
| how targets move (steps, misses, reduce) | [rules.md](../progression/rules.md) |

Answer in this order, short:

1. **Our rule**: what CoAIch does, with the number as the file states it.
2. **Why**: one line per study row that backs it: the claim in plain words, then grade and source as written
   (`Currier et al. 2026 · SR/MA · PMID 41843416`). Two or three rows at most; the strongest first.
3. **What is not proven**: any number labelled P or "our rule", and any limit the row states ("in trained
   lifters only", "strength, not size"). A direction backed by studies with an exact number we chose is said
   that way: "the studies support more sets; the 10 is from one review of reviews; the 6 at short sessions is
   our rule".

Grades, in plain words: **SR/MA** = a review that pools many studies (strongest) · **RCT** = one randomised
trial · **Review** / **OBS** = an overview or a survey · **P** = coach practice or consensus · **our rule** = a
number CoAIch chose. Never present P or our rule as science, and never round a claim up past what its row says.

Words: say "reps left", "easy week", "starting weight". Never "RIR", "RPE" or "deload". No log line: this skill
reads only.
