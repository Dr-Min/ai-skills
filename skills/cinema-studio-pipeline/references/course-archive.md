# Cinema Studio Pro — Raw Lesson Archive
Source: https://higgsfield.ai/academy/courses/cinema-studio-pro
Scraped: 2026-07-23

---

## Lesson 1 — Introduction
URL: /academy/courses/cinema-studio-pro/introduction

The AI Filmmaking Pipeline — Introduction

This is not a feature tour. It's the pipeline our own team runs to take a film from idea to finished Seedance shots — taught in the same order we work it, with the same standards. By the last lesson you'll have built your own production kit — location, character, and prop Elements — and directed them in a finished Seedance shot. You'll also have judged your own frames the way we judge ours.

How the course works: Three sections, each closing with a section test, take you from the production system and project setup through model choices, asset craft, Seedance testing, and spotting slop. The tests are graded at 80% — they're checkpoints, not decoration; if one stings, the gap it found is the lesson worth re-reading.

This is hands-on work. You'll complete tasks in the live studio, and verified checklists pass only when the product confirms the real action. Academy's free generations are there so you can test, reject a weak take, and try again while you practice.

The course ends with a five-step capstone: make a scene for your own future film, from the project structure through a finished Seedance shot. Complete it and the course unlocks a certificate you can verify publicly and put on LinkedIn.

What to have ready: A Higgsfield account with Cinema Studio access, and Claude Cowork — the pipeline runs through it from lesson two onward. If you've never opened either, take the Complete Tour first; this course assumes the studio already feels familiar. YouTube walkthrough covers the studio end to end.

The bar: Everything here is opinionated: naming standards, model choices, the 25–30% portrait rule, "test in Seedance before you fall in love with a frame". You're allowed to disagree — after you can name why the rule exists. Name the flaw, don't just feel it.

---

## Lesson 2 — The pipeline, end to end
URL: /academy/courses/cinema-studio-pro/the-pipeline

Before you touch a single prompt, hold the whole pipeline in your head. Every project we make follows the same four moves. They are not four buttons; they are a chain of handoffs. A stage is finished only when it leaves a concrete input the next stage can trust.

The four stages — Four moves, one fixed order. Each clip is the real screen work of that stage, and its caption names the deliverable you walk away with. If you can't point at that deliverable, the stage isn't done.

Think — work with Claude until the brief and prompt say what the shot must be.

The order is the lesson. Skipping straight to "generate" is the single most common reason a project stalls — you end up re-prompting the same thing ten times instead of thinking once.

Follow the handoffs — each receiving stage gets something more useful than an idea:

| Handoff | What crosses it | Why the next stage needs it |
| Brief → setup | An agreed brief shaped with Claude: the shot, world, cast, props, and constraints | Setup can create the right homes instead of guessing what the production will need. |
| Setup → generation | A project, useful folders, and one naming contract | Every candidate has an address; approved work can become a reusable @loc_, @char_, or @prop_ asset instead of an orphaned file. |
| Generation → Seedance | Proofed, named location, character, and prop elements | Seedance combines the actual source pixels. A defect handed over here will be multiplied in motion. |
| Seedance → review | A motion test and a diagnosis, not just a video | Review can approve the shot or send one specific source back for correction. |

Setup defines the address; generation earns it. A file does not become production input merely because it exists. First inspect it, then approve it, name it, and save it as an element. Build the location before judging the character on it: the place is both the foundation of the shot and the test bed that lets you see whether the character really holds up.

Proof is the gate — A model description and a confident prompt are promises. The pixels are proof. Before anything reaches Seedance, inspect the source still against the same quality bar every time.

Review closes the loop — Test is not a finish line with only pass or fail. It tells you where to return. If the geography melts, fix the location. If identity drifts, fix the character sheet. If the assets are sound but the action is wrong, revise the Seedance direction. If the whole shot answers the wrong idea, reopen the brief with Claude. Correct the earliest broken handoff, approve it again, and retest; polishing a downstream symptom only hides the source.

Course map: Working in Claude and Turning thoughts into a prompt build the brief. Name your assets and Set up your first project make work retrievable. Choosing your image model and Proof, not promises establish evidence. Generating locations builds the world before Generating characters adds the cast. Test in Seedance and Spot the slop teach the review loop. The section tests and final exam check those junctions, and the capstone runs the whole chain with your own location, character, prop, and final Seedance shot.

---

## Lesson 3 — Working in Claude
URL: /academy/courses/cinema-studio-pro/working-in-claude

Almost everything we make starts as a conversation with Claude — but not a throwaway chat. We work in Cowork mode (the selector at the bottom-left of the message box, on the Home tab), because a project needs a memory and a place for its files.

Why Cowork, not a plain chat — A normal chat forgets between sessions. Cowork remembers.
- Memory across chats — inside a Cowork project, context carries over: the story, the characters, the look you've agreed on. You stop re-explaining the project every morning.
- Local files — your assets live in the project folder on your machine, where Claude can read and reuse them. For this, work in the desktop app.

Turn Memory on in settings before you start a real project. The whole value of Cowork — context that survives between chats — only works when memory is enabled.

Cowork now lives inside the Home tab — pick Cowork in the message-box selector (Chat / Cowork). If you don't see it, update the Claude app. Cowork is also available on web and mobile in beta (Max plans first), but local file access still requires the desktop app.

Handoff setup — enter Cowork, then turn on Generate memory from chat history so the project context survives the next chat.

Approved assets get saved in two places: the local Claude folder for the project, and your normal project folder where you keep every related file. Asset names start with @ — that's the hook that pulls them straight into a prompt later.

The three file types you'll meet:
- .md — A plain-text (Markdown) file — readable anywhere, rendered nicely in apps. We use it for notes, instructions, and skills.
- Skill — A folder of .md instructions (a SKILL.md) holding the rules for one topic — Claude opens it when a task fits and works to that standard.
- .jsx — Technically a code file, but we use it as a shotlist — a structured container for shot data (shot numbers, descriptions, timings, prompts) that Claude reads the fields of and pulls from.

A skill isn't magic — it's a pre-written handbook Claude loads at the right moment so it stays on one standard instead of improvising. A skill might hold the rules for building Seedance prompts. Not every .md is a skill; sometimes it's just a system prompt you attach to a chat.

One handoff, end to end — Don't ask Claude to "make the prompt" in isolation. Give it the production record first:
- Scene brief .md — Story beat and shot intent; Approved references and exact @ Element names; Character, location, and prop identity
- Relevant SKILL.md — Rules for this kind of prompt
- Current .jsx shotlist — Shot number, timing, and continuity

Tell Claude which files are authoritative; memory helps it recall the project, but it does not choose the latest brief for you.

Example request:
```
Use the scene brief, approved reference images, relevant SKILL.md, and current
.jsx shotlist in this Cowork project.

Prepare shot [number] only. Preserve the story beat, continuity, and approved Element
names. If a missing decision would change the shot, ask before writing. Do not invent
an Element.

Return one record with exactly this structure and no preamble:
{
shot: "[number]",
description: "[one-sentence action and framing]",
duration: "[seconds]",
elements: ["[@name]", "[@name]"],
prompt: "[one complete, standalone Cinema Studio prompt]"
}
```

Review the record in Claude, then save it into the current .jsx shotlist. Cinema Studio does not ingest that whole file: open the right project and folder, paste the prompt value into the Prompt Box, and select every elements entry through the @ picker. For a video shot, also carry over duration. Before you generate, the visible @ tags should match the record exactly.

---

## Lesson 4 — Turning thoughts into a prompt
URL: /academy/courses/cinema-studio-pro/turning-thoughts-into-a-prompt

Finish the Think handoff: turn a scattered idea into a shot direction the next stage can trust. Claude can assemble the language, but every creative addition should trace back to a decision you can see.

Six decisions, then one prompt — There's no universal sentence formula. There is a reliable decision pass: separate subject, action, setting, light, camera / motion, and constraints, then assemble those six answers into one paragraph. A rough thought may hint at a slot without resolving it; "hot summer day," for example, says nothing about light direction or shadow shape.

The final paragraph is not better because it is longer. Each clause now has a job: identify the subject, block the action, make the setting drawable, make the light coherent, direct the frame and motion, or prevent a known failure. If Claude adds an unchosen prop, style, weather condition, or camera move, ask what ambiguity it resolves — then approve it, replace it, or remove it.

Iteration works the same way. Change one decision — "move the house to the right third, keep the sun out of frame, make it sunset" — and have Claude rewrite the full prompt so every slot still agrees.

Save the method as Leera — Leera packages the same visible decision pass for locations as a 4-D method: Deconstruct the thought, Diagnose its gaps, Develop the direction, and Deliver the prompt with a decision log. Paste into a fresh Claude chat, or save as SKILL.md, then give it a rough location thought:

```
Leera.md
In this chat we build location prompts for a Higgsfield project.

You are Leera, a master-level prompt-optimization expert. Your mission: turn any rough,
half-formed input into a precise, production-ready location prompt for cinematic image
models. Run the 4-D method on every brief:

1. DECONSTRUCT — quote the useful words from my brief and map them into six slots:
subject, action, setting, light, camera/framing, and constraints. If the target is
video, include camera motion too. Mark each slot as explicit, implied, or missing.

2. DIAGNOSE — audit for clarity gaps and ambiguity. Check that the location makes
logical sense: one sun, believable doors and windows, shadows falling away from the
stated light sources. For every gap, either ask me or label the default you propose.
Never silently add weather, props, style, or camera movement.

3. DEVELOP — build the prompt from approved decisions: one clear subject and action,
the setting around them, a named anchor object (a sofa, a doorway, a banner) for later
character placement, explicit light (soft sources for interiors — hard visible rays
usually slop), a tonal palette with smooth falloff and no crushed shadows, and camera
angle (use a declared 3/4-view default for depth when I give no angle). Add motion only
for a video target. Finish with constraints that protect continuity. Concrete nouns over
quality words — "weathered wood siding", never "beautiful".

4. DELIVER — output the optimized prompt as one paragraph in English, then a decision
log. For every added or rephrased detail, name the ambiguity or failure it resolves.

Operating modes:
DETAIL (default for a new location) — ask 2-3 clarifying questions before optimizing,
then do a deep pass.
BASIC (quick fix) — skip the questions, use only the minimum clearly labelled defaults,
and deliver immediately.

Iteration rule: when I reply with changes ("move the house to the right third, sun out
of frame, make it sunset"), rewrite the FULL prompt with the change applied — never a
diff, never a fragment.

Response format:
Your optimized prompt: [the prompt]
Decision log: [source phrase or declared default → prompt decision → what it resolves]
Open questions: [only if something essential is still missing]
```

Load it as a skill or paste it into the chat. Either way, approve the decision log before you use the prompt; that keeps Claude in the assembly role and you in the director's chair.

---

## Lesson 5 — Name your assets
URL: /academy/courses/cinema-studio-pro/name-your-assets

An approved asset only pays off if you can retrieve it later. A fixed @type_project_name pattern gives Claude the exact Element address to carry in a shot record and gives you a predictable name to select with Cinema Studio's @ picker.

What an asset is, and where it lives — An asset is any approved piece you'll reuse across shots — a location plate, a character sheet, or a prop. Uploading its file from the Cowork project folder creates the reusable Element on Higgsfield. The local file and the Element are different: a later prompt calls the Element by its saved @ name.

The pattern — Three type prefixes, one shared project tag, then a descriptive name:

| Prefix | Names | Example |
| @loc_ | Locations | @loc_HG_museum_front |
| @char_ | Characters | @char_HG_jaxx |
| @prop_ | Props | @prop_HG_phone |

The middle tag is the project prefix — here HG for Hell's Grind, one of our film projects — so agree on your own short code with the team at kickoff and every asset name stays collision-free across films.

The final address includes @. Cinema Studio adds it when the Element is created; use that full address when you refer to or select the Element later.

Skip the standard and Claude can reference the wrong asset while you hunt through the Elements picker or re-attach media by hand. The type and project segments make retrieval reliable.

Drill it: enter @<prefix>_HG_<description> and join multiword descriptions with underscores (museum_front), not spaces or hyphens.

---

## Lesson 6 — Section test: the pipeline, Claude & naming
URL: /academy/courses/cinema-studio-pro/section-test-foundations
(Interactive quiz — graded at 80%. Covers pipeline stages/handoffs, Cowork vs plain chat, the six-slot prompt decision pass, and the @type_project_name asset-naming convention.)

---

## Lesson 7 — Set up your first project
URL: /academy/courses/cinema-studio-pro/set-up-your-project

Interactive walkthrough — each item ticks ✓ only when the studio confirms you actually did it. There's no skip button; the checklist is the finish. You start on the studio's home, exactly where a real production starts. Three moves take you from an empty workspace to your first shot.

Checklist:
1. Create and name a project — its workspace opens
2. Add a folder — name it and confirm to create it
3. Generate anything — wait for the shot to finish

That's the loop every production runs on: a project to work in, folders to keep it organized, and the pult to generate. Everything else in Cinema Studio builds on these three moves.

---

## Lesson 8 — Choosing your image model
URL: /academy/courses/cinema-studio-pro/choose-your-model

There's no permanently "best" model. Treat these four as today's candidates, then choose by the shot.

**Soul Cinema** — A from-scratch candidate when cinematic texture and atmosphere matter more than exact object control.
- Fit: Raking side light keeps materials tactile instead of CG-flat; haze softens the treeline creating depth; creative angles/color/light suit exploratory location work; realistic skin and clothing textures suit from-scratch character sheets; handles short and long prompts.
- Rule-out: distant small objects too small to verify as continuity anchors; creative variation means an exact composition can take several runs; specific props/monsters/creatures a weaker fit; can rework one picture but cannot attach multiple references or edit a finished image.
- Use for: atmosphere, material texture, or human realism that's hardest to repair; switch when exact control needed.

**GPT Image 2** — A control candidate for readable text, prop geometry, fine detail, reverse angles, and reference-guided work.
- Fit: three angles hold consistent body geometry; small stickers/labels stay legible; complex mechanical details render; material wear reads convincingly; 3/4 perspective adds depth cues.
- Rule-out: no lighting-variant resilience shown; no macro close-up; photo-of-people can look soft/artifacted; minor inconsistencies between views.
- Use for: readable text, controlled geometry, or exact detail that's hardest to repair.

**Nano Banana Pro** — An edit candidate when a finished image needs a bold wardrobe, face, or object change.
- Fit: armor language holds across full-body views; helmet/horn detail coherent in close-up; can attach a finished image for broad re-dressing or object edits; also fits monsters and creatures.
- Rule-out: visor can hide face cues so identity preservation unproven; edits can tint the whole image and damage gradients — mask only the changed region onto the original; uncovered faces can become symmetric and lifeless; from-scratch locations can look centered, staged, stock-like.
- Use for: a bold edit when landing the requested change matters more than pristine tones or faces.

**Seedream 4.5** — A character-sheet edit candidate when preserving skin and clothing texture matters more than exact pose.
- Fit: etched armor scrollwork and cape drape hold across front/back; freckles/pores/eye detail survive close-up; can attach a finished character sheet and avoid the common banana/oversharpened texture.
- Rule-out: after-only view cannot prove pose/proportions stayed locked; edits can shift pose or angle requiring longer mask-and-composite pass; can preserve texture yet miss part of the requested change.
- Use for: clean character texture that's hardest to repair; compare with Nano Banana Pro when landing the change matters.

**The decision rule:** Before every later location or character pass, name one must-preserve requirement. Inspect the output at its intended crop. Choose the model that proves the must-preserve requirement and leaves only failures you can afford to fix. If the roster changes, repeat this evidence test on the shot — do not carry today's ranking forward.

---

## Lesson 9 — Proof, not promises
URL: /academy/courses/cinema-studio-pro/proof-not-promises

Don't approve a generation because of the model name or the prompt behind it. Approve it because of what you can actually see: what changed, what stayed the same, and what's broken.

Judge the result, not the model — real generations from the team. Base the verdict only on what's in the image; a strong model can still produce a result that isn't ready. (Soul Cinema office example: desks, shelving, blinds, skyline read as clear depth under warm late-day light through one window bank — ready for reverse-angle and prop-interaction tests.)

A model's reputation can tell you what to try. Only the image in front of you can tell you if it worked.

Same edit, different verdicts — Ignore the note ("Nano Banana Pro one-pass re-dress"); judge the pixels. Check three things: does the horned identity hold, do all three views (front/back/portrait) still agree, is the new armor consistent everywhere. The verdict depends on downstream use: proceed if you just need an armor design; hold if it needs to carry the creature's face into Seedance (face no longer visible → still needs fixing). Same image, two different answers.

The same test, on a new edit — A pass on the last one tells you nothing about this one; check it fresh. (Blade-armed demon: face and body hold; new blade-arms' dark edges blend into black background — fix before animation.)

Watch for what changed that you didn't ask for — Ignore claim words like "cleanly." Check every part of the sheet, not just the new element. (Seedream wings+blood: good, but layout shifted un-requested → hold before Seedance and fix first.)

---

## Lesson 10 — Section test: studio & models
URL: /academy/courses/cinema-studio-pro/section-test-studio
(Interactive quiz — graded at 80%. Covers project/folder setup, the four image-model candidates and when to pick each, the must-preserve decision rule, and judging results by pixels not model reputation.)

---

## Lesson 11 — Generating locations
URL: /academy/courses/cinema-studio-pro/generating-locations

Locations are the foundation. A useful one is not merely a pretty frame: actors can be blocked inside it, the light has one logic, the camera can see depth, and a later view can repeat the same geography. Every shot inherits these decisions.

Turn the rough idea into a production contract — Start messy ("a big three-storey farmer's house in the middle of nowhere, red jeep out front, hot summer day"), then make the decisions the rough idea leaves open. Claude can assemble the wording but should not silently direct the location. Ask Claude to rewrite the full prompt and return a decision log. Compare that log with the five locks; if a lock disappears, restore it before generating. The evidence — not Claude's confidence — decides whether the location is usable.

Two easy-to-miss failures: an oversharpened, oily surface has no real texture, so it swims and smears the instant anything moves across it. Atmospheric haze is what tells the eye a background is far away — kill it and everything reads at the same sharpness: flat, and immediately readable as slop.

Shoot at 3/4, then test the reverse — A 3/4 view exposes side geometry and separates foreground/midground/background, giving later character placement visible floor and distance cues. A reverse is a separate generation and a continuity test: keep the anchor, openings, light side, materials, and palette locked, then compare the two frames. Leera defaults to 3/4 in her DEVELOP step. Shoot head-on and the location flattens into a backdrop; hidden side geometry stays unconstrained, so asking for an angle later lets the model invent doors, walls, object positions.

Give the frame an anchor — a clear object you attach blocking to (a big sofa, a front door, a specific street banner). Replace "the character stands on the left" with "the character stands between the sofa's hall-side arm and the window." The relationship is testable in a later frame; vague screen direction is not.

When one master wide is enough for b-roll — When no cut depends on exact off-frame geography (some b-roll, montage, action coverage), one wide plate can be enough. Use this shortcut only when that invention cannot break blocking or continuity.

**The six location locks:**
1. Geography before style — Name entrances, playable routes, and three depth planes before style; hidden geography is what later views reinvent.
2. One motivated light — Use one motivated source, direction, and falloff. Contradictory sources produce conflicting shadows or crushed regions.
3. 3/4, then reverse — A 3/4 master exposes side geometry. Approve its reverse only when anchor, openings, light, depth, and materials match.
4. Anchor the blocking — Block every action relative to one fixed object; screen-left alone can drift when the camera turns.
5. Qualify one wide — One wide works only when off-frame invention cannot break a later cut, blocking mark, or continuity claim.
6. Approve by locks — Proceed only when every named lock is visible in master and reverse; hold at the first failed lock.

---

## Lesson 12 — Editing locations
URL: /academy/courses/cinema-studio-pro/editing-locations

Editing is not a rescue step — it's part of developing a good input. Almost every good location still needs work: swapping details, removing clutter, color-correcting to your project. The skill is doing it without wrecking what already works.

Three models, run side by side — You don't pick one edit model; you run them in parallel and take the best result for each change.
- GPT Image 2 — Text, mathematically precise detail on complex objects
- Nano Banana Pro — Most edits that don't need GPT-level precision
- Seedream 4.5 — Run in parallel batches — rarely slops, but may miss the ask, so fire more tries

Real cafeteria pass: Nano Banana Pro cleaned grime off red metal, fixed fused stools, added trays and floor litter. GPT Image 2 swapped in lamps, TVs, and menu boards with readable text. Photoshop softened textures, removed objects in the back corridor, unified color, and composited every edit onto the original.

Every edit degrades the frame — An edit model never touches only what you asked for; it quietly re-renders the whole image. Every detail you add or remove gets masked onto the ORIGINAL in Photoshop — change only the patch that changed, leave the rest untouched. Never re-edit an edited image.

**The three edit locks:**
1. Edit the original — Composite each changed patch onto the original. Never stack edits — every full-frame rerender degrades untouched regions.
2. Run models in parallel — GPT Image 2 for text and precise detail, Nano Banana Pro for most edits, Seedream 4.5 in parallel batches.
3. Never re-edit an edit — A second pass re-renders the whole frame again, compounding slop. Always mask the change onto the master file.

---

## Lesson 13 — Generating characters
URL: /academy/courses/cinema-studio-pro/generating-characters

A character lives or dies on its character sheet — the reference image Seedance reads to know who this person is. Seedance reads it literally, so every flaw in the sheet becomes a flaw in every shot.

The pipeline — Four moves, always in this order:
1. Generate — Build the sheet from a prompt Claude writes: moodboard and description first, then one production prompt that packs every angle into a single generation.
2. Inspect — Check the sheet before anything downstream touches it — a stray rim light, a mismatched face, or plastic skin here bleeds into every shot.
3. Edit masked onto the original — Fix flaws with Photoshop masks composited onto the original sheet — never regenerate the whole thing, or drift and grime pile up.
4. Test in Seedance — Test the finished sheet on a good location — the test is the finish line, not the generation.

Which model generates it:
- Soul Cinema — First choice for generating characters
- Seedream 4.5 — Also works — run in parallel
- AI Cast (Cinema Studio) — A strong casting tool, worth exploring
- Nano Banana Pro — Editing a finished sheet only — never generating one
- GPT Image 2 — Creatures and precise add-ons only (on human skin it goes oversharp and slops; excellent for one precise addition on an existing character)

The character-sheet prompt (production template — works in any model). Two things never change: the deep neutral grey background and the split into columns with a dominant portrait (columns can be added when needed). Everything else — the whole CHARACTER block — you rewrite through Claude:

```
character-sheet-prompt.md
Character reference sheet of a single consistent female character, presented
on a pure clean deep neutral grey (#3a3a3c) seamless studio background, clean
editorial layout arranged in three vertical sections, horizontal landscape
composition read left to right, identical character identity, lighting and color
grading across every panel for perfect consistency:

— COLUMN 1 (largest, leftmost): chest-up portrait, front view, head and upper
chest in frame, sharp focus on the eyes, soft catchlights in both eyes.

— COLUMN 2: full-body front view, standing relaxed neutral A-pose, arms slightly
away from the body, weight evenly distributed, full figure head-to-toe inside
the frame with even margins.

— COLUMN 3 (rightmost): full-body back view, same standing pose mirrored,
showing hair fall, back posture, garment fit and shoe heels.

CHARACTER (must remain identical in all panels): woman, mid-20s, height ~175cm,
elegant proportions, oval face, sharp high cheekbones, defined but soft jawline,
straight nose, full natural lips, light scattered freckles across the nose and
cheeks, clear fair skin with realistic natural texture and subtle imperfections,
grey-green eyes with detailed iris, well-groomed natural brows, straight auburn
hair with a center part falling just past the shoulders with a soft natural
sheen, neutral calm relaxed expression.

LIGHTING & RENDER: clean soft even studio lighting, large diffused key light
with gentle fill, soft natural shadows, no harsh highlights, true-to-life skin
tones, neutral white balance, minimal high-fashion editorial presentation,
polished modern professional model sheet aesthetic, shot on full-frame camera
with an 85mm lens look, shallow yet controlled depth of field, crisp tack-sharp
detail, high dynamic range, 8k.
```

**The rules that make a sheet Seedance-proof:**
- Portrait = 25–30% of the sheet — where Seedance reads the face; every detail it will ever know comes from those pixels.
- Angle the portrait — Slightly off-frontal beats dead-on; it reads the head's volume instantly. Or add a smaller separate 3/4 portrait.
- Eyes are never black — Iris color must read clearly. Crushed-black eyes give Seedance no light info, so tones drift.
- Catchlight, or dead eyes — There's always a glint in the eye; no catchlight means dead eyes.
- Break the symmetry — Real faces are symmetric but never perfect. Perfect mirroring reads as AI.
- No 3D-game-render look — Seedance recognizes the game-model mood and animates like game footage.
- Grey is the golden middle — White bleeds into video and washes out your location; black eats detail. Deep neutral grey wins.
- Crop the head off the full-body panels — On a full-length panel the face always distorts and drifts from the portrait; remove it so Seedance is forced to take face textures from the portrait panel.

What a SLOP sheet looks like (three real fails):
- The dirty sheet — a mottled/grimy plate (from repeated whole-sheet re-generations layering grime that Seedance treats as part of the asset) + a full-body face that doesn't match the portrait (two competing identities → face/build drift). Fix: mask repairs onto the original, then audit again.
- The game render — plastic game-model textures (Seedance repeats and moves like game footage) + an orange rim light baked in (bleeds into every generation) + portrait too small (nowhere near 25–30%, so Seedance lacks facial evidence and invents it differently shot to shot).
- Standard Nano Banana slop — mirror symmetry (synthetic look Seedance preserves) + soapy poreless skin (reproduced as plastic skin) + no dominant portrait (six near-equal tiles, no authoritative face → identity drifts).

---

## Lesson 14 — Editing characters
URL: /academy/courses/cinema-studio-pro/editing-characters

A character sheet is read literally by Seedance, so editing it is surgery, not a redo. You never regenerate the whole sheet to fix one flaw — you mask the single change onto the original.

One defect, every shot — Seedance doesn't interpret the sheet; it reads it literally. A detective sheet with one orange rim light baked into the portrait → every shot generated from it gets tinted identically. One flaw in the sheet is one flaw in every shot.

Which model to edit with:
- Nano Banana Pro — Most sheet edits — never for generating a sheet
- GPT Image 2 — Precise add-ons and creatures — oversharpens human skin, so keep it to a small patch
- Seedream 4.5 — Run in parallel batches and take the cleanest result

Edits are applied surgically — Same principle as locations. Every change from Seedream 4.5, GPT Image 2, or Nano Banana Pro goes onto the original sheet through Photoshop masks: swap only the region that changed, keep the original untouched everywhere else. Never regenerate on top of an already-edited sheet — every pass re-renders the whole frame, so a second edit compounds grime and drift. Mask every change onto the master, always.

---

## Lesson 15 — Test in Seedance
URL: /academy/courses/cinema-studio-pro/test-in-seedance

A still is only a hypothesis. Run the motion your shot actually needs in Seedance, then change one variable at a time until the visible failure points to the source asset or the motion direction.

Start from a baseline you can diagnose — When the character is the question, keep the location out of it: use a plate that already holds its geometry, depth, materials, and light. A broken plate gives every character failure a second plausible cause. A percentage cannot approve a shot. The named source assets, required motion, and visible result are the evidence.

Diagnose the failing input — One bad clip is a symptom, not a diagnosis. Compare its first failure with the source stills, then read the controlled result:
- Source asset — Defect exists in the source or stays tied to the same feature when direction changes.
- Motion direction — Source is clean and the defect changes when only the suspect motion clause changes.
- Inconclusive (narrow the test) — Controls conflict or the failure follows neither variable.

This diagnosis applies to the tested asset and direction. It is not a universal claim about a model, and one rerun does not guarantee the next result.

---

## Lesson 16 — Spot the slop
URL: /academy/courses/cinema-studio-pro/spot-the-slop

Slop hides in stills and multiplies in motion. Inspect the exact crop you plan to use, name the visible defect, then decide whether that crop is safe to pass into Seedance.

The four tells (most slop is one of these four):
1. Light with no transitions — Flat-black pits instead of a smooth shadow ramp — they transfer onto every character you add.
2. Broken-but-plausible objects — Crates, railings, hardware you can almost read — in motion they turn to mush and multiply.
3. Local logic breaks — An effect in only part of the frame (rain that scratches one corner). Seedance's logic breaks with it.
4. Oily textures — Soapy surfaces lose their material; reflections crawl in motion, so the plate cannot hold continuity.

A visible still-frame defect is already a stop. Use Seedance only when the crop passes the still scan and you need motion to confirm an uncertain edge, reflection, or object.

Two models, two slop accents:
- Banana slop (Nano Banana Pro) — ruler-straight symmetry, everything parallel and set square, flat light and color with no contrast play → pretty but staged and lifeless, like stock photography. Textures detailed yet read as a 3D render. Hyperbolizes every edit: ask for graffiti on a wall and the whole location gets tagged; ask for "more alive and cinematic" and it litters the frame with junk and dirt.
- GPT slop (GPT Image 2) — sharpness and microcontrast cranked to the ceiling, hard halos on every edge. No depth: everything in focus, no bokeh, no plane separation. White balance pulled warm until the frame yellows, materials go plastic and licked-smooth, dynamic range squeezed to the middle → shadows and highlights meet halfway and the frame goes limp. Most damning tell: a single sickly texture pattern laid over the entire frame (same film-wrap pattern on cabinets and car bodies alike).

What clean looks like — Stare at good frames until your eye calibrates (surf, black rock, wet foliage all reading as material under one grey sky). There's a dedicated "Spot the Slop" practice app with a deeper pool of real frames, timed rounds, no repeats — run it before you choose a location or approve a final shot.

---

## Lesson 17 — Section test: locations, characters & slop
URL: /academy/courses/cinema-studio-pro/section-test-craft
(Interactive quiz — graded at 80%. Covers the six location locks, edit discipline (mask onto original, never re-edit an edit, parallel models), character-sheet rules (25–30% portrait, catchlight, break symmetry, crop heads, grey background), the Seedance one-variable diagnosis, and the four slop tells + two model accents.)

---

## Lesson 18 — Capstone: set up your production
URL: /academy/courses/cinema-studio-pro/capstone-setup

Start with the production structure you'll use through the rest of the capstone: one new project named for your scene, holding three folders — locations, characters, and props. Create the project after starting the course. When its workspace opens, use Add folder three times. The checklist reads your real studio activity; the folder row advances from 0/3 to 3/3. Success: the new project's workspace is open, its project rail shows locations, characters, and props, and both server-verified tasks are checked.

---

## Lesson 19 — Capstone: cast your characters
URL: /academy/courses/cinema-studio-pro/capstone-characters

Create one character for your capstone, then save the approved result as an Element.
- Step 1 — Generate a character that fits your scene. Refine it until you have one image you want to keep.
- Step 2 — On the approved result, choose Save character. This saves it as a character Element you can reference in the final video.
The task completes when the server finds at least one character Element you created after starting the course. Generating an image without saving it does not count; duplicating someone else's Element does not count.

---

## Lesson 20 — Capstone: build the location
URL: /academy/courses/cinema-studio-pro/capstone-location

Create one location for your capstone, then save the approved result as an Element.
- Step 1 — Generate a location that fits your scene. Refine it until you have one image to keep and reuse.
- Step 2 — On the approved result, choose Save location → an environment Element you can reference in the final video.
Success: your approved image is saved as a reusable location Element, and the server-verified task is checked.

---

## Lesson 21 — Capstone: dress the scene
URL: /academy/courses/cinema-studio-pro/capstone-props

Create one story-critical prop for your capstone, approve the result from visible evidence, then save it as an Element.
- Step 1 — Pick the object your scene cannot work without. Generate and refine until one image clearly shows the intended shape, material, wear, and story detail. Approve only a result you would reuse.
- Step 2 — On the approved result, choose Create Element (or Save as Element), give it a production-ready name, and choose Prop. Success is visible when the saved prop appears in Elements and can be selected by its @name in a prompt.
The task completes when the server finds at least one prop Element you created after starting the course.

---

## Lesson 22 — Capstone: shoot the scene
URL: /academy/courses/cinema-studio-pro/capstone-final-video

Everything you built now becomes one shot: your saved character, location, and prop Elements, together in a finished Seedance video.

Make the final shot — In Seedance 2.0, write one clear story beat, then attach all three saved Elements as real references — your character, your location, and your prop. Generate the shot and wait for the video to finish.

Know your free generation before you press the button — keep resolution and duration inside the listed caps so the shot stays free. A short shot is a scene, not a limitation — most shots in real films are shorter. Spend your seconds on one moment done properly.

What the server confirms — The task completes when Academy finds a completed Seedance 2.0 job whose recorded references include at least one Element you created after starting the course. Use all three Element types to complete the capstone outcome. When the checklist closes, your free course certificate is ready to claim.
