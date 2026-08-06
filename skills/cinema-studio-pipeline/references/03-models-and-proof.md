# 03 — Choosing your image model & proof, not promises

Covers: the four image-model candidates and when to pick each, the must-preserve
decision rule, and how to approve a generation from visible evidence alone.

## There is no permanently "best" model

Treat these four as **today's candidates**, then choose by the shot. If the roster
changes, repeat the evidence test — never carry today's ranking forward.

### Soul Cinema — from-scratch, atmosphere & realism
A candidate when cinematic texture and atmosphere matter more than exact object control.
Also a first manual-generation candidate for character sheets when the current Soul
character model is available; use AI Cast as the fast path when its automatic sheet is
sufficient.
- **Fits:** raking side light keeps materials tactile (not CG-flat); haze creates depth;
  creative angles/color/light suit exploratory location work; realistic skin and
  clothing textures suit from-scratch character sheets; handles short and long prompts.
- **Rule-out:** small distant objects too small to verify as continuity anchors;
  creative variation means an exact composition can take several runs; specific
  props/monsters/creatures a weaker fit; can rework one picture but **cannot attach
  multiple references or edit a finished image**.
- **Use when** atmosphere, material texture, or human realism is hardest to repair.

### GPT Image 2 — control, text & precise geometry
A candidate for readable text, prop geometry, fine detail, reverse angles, and
reference-guided work. The **creature model, not the human model** — oversharpens human
skin and slops, but excellent for one precise addition on an existing character.
- **Fits:** multiple angles hold consistent body geometry; small stickers/labels stay
  legible; complex mechanical detail renders; material wear reads convincingly; 3/4
  perspective adds depth cues.
- **Rule-out:** lighting-variant resilience often unproven; can look soft/artifacted on
  photos of people; minor inconsistencies between views.
- **Use when** readable text, controlled geometry, or exact detail is hardest to repair.

### Nano Banana Pro — bold edits on a finished image
An **edit** candidate when a finished image needs a bold wardrobe, face, or object
change. Never use it to *generate* a character sheet.
- **Fits:** re-dresses cohere across full-body views; can attach a finished image for
  broad re-dressing or object edits; also fits monsters and creatures.
- **Rule-out:** can leave identity preservation unproven; **edits can tint the whole
  image and damage gradients — mask only the changed region onto the original**;
  uncovered faces can become symmetric and lifeless; from-scratch locations can look
  centered, staged, stock-like.
- **Use when** landing the requested change matters more than pristine tones or faces.

### Seedream 4.5 — texture-recovery pass
A candidate when an otherwise approved frame needs skin, fabric, or surface texture
recovery. Do not make it the default for a discrete point edit.
- **Fits:** fine surface detail (scrollwork, drape) holds across front/back; freckles,
  pores, eye detail survive close-up; can attach a finished character sheet and avoid
  the common "banana"/oversharpened texture.
- **Rule-out:** after-only view can't prove pose/proportions stayed locked; edits can
  shift pose or angle (longer mask-and-composite pass); can preserve texture yet miss
  part of the requested change.
- **Use when** clean texture is hardest to repair. Lock composition, identity, light,
  and grade; name only the surfaces whose texture should recover.

### The decision rule
Before every location or character pass, **name one must-preserve requirement**.
Inspect the output at its **intended crop**. Choose the model that proves that
requirement and leaves only failures you can afford to fix.

### Production edit routing

Default to a cost-aware escalation instead of running every edit model automatically:

1. **Nano Banana Pro** — first attempt for most existing-frame edits.
2. **Seedream** — texture recovery when skin, fabric, or surfaces remain synthetic.
3. **GPT Image** — precise local detail, readable text, or a location view change that
   Nano Banana cannot hold.

Run parallel candidates only when model fit is genuinely uncertain or when a high-value
approval gate benefits from direct A/B evidence. Whatever model supplies the patch,
composite only the changed region onto the immutable original.

## Proof, not promises

Don't approve a generation because of the model name or the prompt behind it. Approve
it because of what you can actually **see**: what changed, what stayed the same, what's
broken. A model's reputation tells you what to *try*; only the image in front of you
tells you if it *worked*.

- **Same image, different verdicts.** The right call depends on downstream use. A
  one-pass re-dress may be fine if you just need an armor design, but a **hold** if it
  must carry a face into Seedance and the face is now hidden. Ask: does identity hold,
  do all views agree, is the change consistent everywhere?
- **A pass on the last frame tells you nothing about this one.** Check each fresh.
- **Ignore claim words** ("cleanly", "one-pass"). Check every part of the sheet, not
  just the new element — a strong model name doesn't excuse skipping the check. If the
  layout shifted in ways you didn't request, hold and fix that first.
