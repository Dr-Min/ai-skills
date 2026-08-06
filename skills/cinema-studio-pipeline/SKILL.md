---
name: cinema-studio-pipeline
description: >-
  Direct Higgsfield Cinema Studio and Seedance filmmaking from brief through assets,
  shot prompts, motion tests, review, and post-production. Use for cinematic image or
  video generation; location, character, prop, or state assets; Soul Cinema, AI Cast,
  Nano Banana Pro, Seedream, or GPT Image routing; reusable @Elements; Seedance prompt
  writing or repair; spatial continuity, acting, dialogue, voice consistency, slop
  diagnosis, scene-block production, feature-film workflows, and finishing. Trigger
  for both single shots and multi-scene AI films even when the user does not name the
  pipeline. Apply these standards instead of improvising.
---

# Higgsfield Cinema Studio production pipeline

Run the user’s film through explicit handoffs. Treat prompts and model names as
promises; treat the rendered pixels and sound as proof. Do not advance a stage until
the receiving stage has an artifact it can trust.

## Core handoffs

1. **Think** — lock cause, goal, stakes, obstacle, discovery, choice, and the exact
   shot or scene requirement. Deliver an approved brief.
2. **Setup** — create the project structure, asset registry, naming contract, and
   authoritative production files. Deliver addresses for every candidate.
3. **Generation** — build and stress-test locations, characters, states, props, and
   voices. Deliver approved source assets and descriptors.
4. **Seedance** — direct one diagnosable shot or controlled sequence. Deliver the
   video, exact prompt version, active references, and diagnosis.
5. **Review** — correct the earliest broken handoff and retest. Do not hide a source
   failure with downstream polish.
6. **Post** — assemble while generating, then clean up, unify color, and finish sound.
   Deliver a checked sequence, not merely isolated generations.

Build the location before judging a character on it. A location is both the shot
foundation and the test bed that reveals whether identity, light, and physics hold.

## Route to the smallest relevant reference

Read every reference required by the current task, but do not load unrelated modules.

| Task | Read |
| --- | --- |
| Project setup, folders, asset names, handoffs | `references/01-pipeline-and-setup.md` |
| Image, location, character, or prop prompt construction | `references/02-prompting.md` |
| Image-model selection or pixel approval | `references/03-models-and-proof.md` |
| Location generation or repair | `references/04-locations.md` |
| Character-sheet generation or repair | `references/05-characters.md` |
| Seedance test diagnosis or slop review | `references/06-seedance-and-slop.md` |
| Academy five-step capstone | `references/07-capstone.md` |
| Multi-scene, team, long-form, or feature production | `references/08-feature-production-system.md` |
| Writing, fixing, or auditing a Seedance video prompt | `references/09-seedance-prompt-director.md` |
| Acting, dialogue, voice, gaze, or performance continuity | `references/10-acting-and-dialogue.md` |
| Edit assembly, cleanup, color, or sound finishing | `references/11-post-production.md` |

`references/course-archive.md` preserves the original 22 Academy lessons. Consult it
for original examples or course wording; treat the focused references above as the
current operational rules when they are more specific.

## Scope rules that prevent cross-contamination

- Use the six-slot, one-paragraph method for **image generation**. Do not use it as the
  final structure for a controlled Seedance shot.
- Use the structured Seedance document for **video**. Keep only current-shot context;
  remove stale tags, scene headers, and “same as before” language.
- Keep platform settings in the UI when the UI is authoritative. Put only settings
  that change the visible or audible story result into the prompt.
- Use actual saved `@` tags exactly as they exist. Never invent a tag. The project
  naming contract controls creation; the platform registry controls retrieval.
- Treat project-specific style prefixes as optional constants, not universal truth.
  Spatial, identity, action, physics, and audio locks outrank style language.

## Non-negotiables

- **Proof, not promises.** Inspect the intended crop and motion. Name what changed,
  what held, and the first visible failure.
- **One naming contract.** Create reusable assets as `@type_project_name` using
  `@loc_`, `@char_`, and `@prop_`; create separate state variants when appearance or
  function changes.
- **Edit the original, never an edit.** Generate a changed patch, composite only that
  patch onto the immutable master, and record the lineage.
- **Escalate edits deliberately.** Start with Nano Banana Pro for most edits; use
  Seedream for texture recovery; use GPT Image for precise local details, readable
  text, or view changes. Run models in parallel only when uncertainty or approval
  value justifies the extra cost.
- **One variable per diagnostic iteration.** Log the prompt version, changed line,
  result, and verdict. If 10–15 controlled attempts fail, simplify the shot.
- **Assets before shots.** Stress-test identity, states, geography, and voices before
  bulk generation.
- **Positive state first.** Describe what is visibly true; add short local negatives
  only for demonstrated or high-probability failures.
- **Direct, then assemble.** Every creative addition must trace to an approved story,
  spatial, performance, or technical decision.
