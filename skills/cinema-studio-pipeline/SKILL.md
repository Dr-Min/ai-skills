---
name: cinema-studio-pipeline
description: >-
  The Higgsfield Cinema Studio "AI Filmmaking Pipeline" as taught by the Hell Grind
  team — the full production method for taking a film shot from idea to a finished
  Seedance video. Use this skill whenever the user is doing AI filmmaking, cinematic
  image/video generation, or working in Higgsfield Cinema Studio / Seedance: building
  or reviewing location plates, character sheets, or props; writing or optimizing
  cinematic image prompts; choosing between Soul Cinema, GPT Image 2, Nano Banana Pro,
  or Seedream 4.5; naming reusable @Elements; spotting "slop"; or directing a shot.
  Trigger this even when the user doesn't name the pipeline explicitly — e.g. "make a
  character sheet", "why does my AI video look fake", "which model for this edit",
  "turn this idea into a prompt", "build a location for my scene", "test this in
  Seedance". Follow this method and its standards instead of improvising.
---

# The AI Filmmaking Pipeline (Higgsfield Cinema Studio)

This skill encodes the production pipeline the Hell Grind team runs to take a film
from idea to a finished Seedance shot. It is opinionated on purpose: naming standards,
model choices, the 25–30% portrait rule, "test in Seedance before you fall in love
with a frame". The point of every rule is to **name the flaw, not just feel it** — so
when you apply a rule, understand *why* it exists and be able to explain it.

The golden principle running through everything: **a prompt and a model name are
promises; the pixels are proof.** Nothing advances a stage until you can point at the
visible evidence that it holds.

## The four stages (one fixed order)

Every project follows the same four moves. They are not four buttons — they are a
**chain of handoffs**. A stage is finished only when it leaves a concrete deliverable
the next stage can trust. If you can't point at that deliverable, the stage isn't done.

1. **Think** — work with the user (in Claude Cowork) until the brief and prompt say
   exactly what the shot must be. *Deliverable:* an agreed brief + prompt.
2. **Setup** — a project, useful folders, and one naming contract. *Deliverable:*
   every candidate has an address; approved work can become a reusable `@loc_`,
   `@char_`, or `@prop_` Element.
3. **Generation** — proofed, named location, character, and prop Elements.
   *Deliverable:* source stills that pass the quality bar. A defect handed over here
   is multiplied in motion.
4. **Seedance** — the motion test. *Deliverable:* a motion result **and a diagnosis**,
   not just a video.

Skipping straight to "generate" is the single most common reason a project stalls —
you re-prompt the same thing ten times instead of thinking once. **Build the location
before judging the character on it:** the place is both the foundation of the shot and
the test bed that reveals whether the character really holds up.

## Review closes the loop

A Seedance test is not pass/fail — it tells you *where to return*. Correct the
**earliest** broken handoff, approve it again, and retest. Polishing a downstream
symptom only hides the source.

- Geography melts → fix the **location**.
- Identity drifts → fix the **character sheet**.
- Assets sound but action wrong → revise the **Seedance direction**.
- Whole shot answers the wrong idea → reopen the **brief**.

## How to use this skill

Figure out which leg of the pipeline the user is on, then open the matching reference
file and apply its standards. Don't dump all the rules at once — load the reference
that fits the task.

| The user is... | Read |
| --- | --- |
| Setting up (Cowork, project, folders, asset naming, handoffs) | `references/01-pipeline-and-setup.md` |
| Turning a rough idea into a prompt (six-slot pass, the Leera method) | `references/02-prompting.md` |
| Choosing an image model or deciding whether a generation is approved | `references/03-models-and-proof.md` |
| Generating or editing a **location** | `references/04-locations.md` |
| Generating or editing a **character** sheet | `references/05-characters.md` |
| Testing in Seedance or hunting for **slop** | `references/06-seedance-and-slop.md` |
| Running the 5-step capstone (a full scene end to end) | `references/07-capstone.md` |

The complete, unedited text of all 22 course lessons is preserved in
`references/course-archive.md` — consult it when you need the exact original wording,
an example, or a detail not summarized elsewhere.

## Non-negotiables (the short version)

These recur across the whole pipeline; keep them in mind everywhere:

- **Proof, not promises.** Judge the pixels at the intended crop, never the model name
  or the prompt behind it. Name what changed, what stayed, and what's broken.
- **One naming contract.** Every reusable asset is `@type_project_name`
  (`@loc_`, `@char_`, `@prop_`), joined with underscores. Retrieval depends on it.
- **Edit the original, never an edit.** Every edit model silently re-renders the whole
  frame. Composite the single changed patch onto the original in Photoshop; a second
  pass on an edited image compounds grime and drift.
- **Run edit models in parallel.** GPT Image 2 for text/precise detail, Nano Banana Pro
  for most edits, Seedream 4.5 in parallel batches — take the best result per change.
- **Test in Seedance before you fall in love with a frame**, and change **one variable
  at a time** so the failure points at either the source asset or the motion direction.
- **You're the director; Claude assembles.** Every creative addition must trace back to
  a visible decision. If Claude adds an unchosen prop, weather, style, or camera move,
  ask what ambiguity it resolves — then approve, replace, or remove it.
