# 05 — Generating & editing characters

A character lives or dies on its **character sheet** — the reference image Seedance
reads to know who this person is. **Seedance reads it literally**, so every flaw in the
sheet becomes a flaw in every shot generated from it.

## The four-move pipeline (always in this order)

1. **Generate** — build the sheet from a prompt Claude writes: moodboard and
   description first, then **one** production prompt that packs every angle into a
   single generation.
2. **Inspect** — check the sheet before anything downstream touches it. A stray rim
   light, a mismatched face, or plastic skin here bleeds into every shot.
3. **Edit masked onto the original** — fix flaws with Photoshop masks composited onto
   the original sheet; never regenerate the whole thing or drift and grime pile up.
4. **Test in Seedance** — on a good location. The **test is the finish line**, not the
   generation.

## Which model
- **Soul Cinema** — first choice for generating characters.
- **Seedream 4.5** — also works; run in parallel.
- **AI Cast (Cinema Studio)** — a strong casting tool, worth exploring.
- **Nano Banana Pro** — editing a finished sheet **only**; never generating one.
- **GPT Image 2** — creatures and precise add-ons only (oversharpens human skin; keep
  it to a small patch).

## The character-sheet prompt (production template — works in any model)

Two things **never change**: the deep neutral grey background, and the split into
columns with a **dominant portrait** (add columns when the character needs them).
Everything else — the whole `CHARACTER` block — you rewrite through Claude. Claude knows
what a character sheet is, so start by asking it for the prompt and learn the shape.

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

## The rules that make a sheet Seedance-proof

- **Portrait = 25–30% of the sheet** — this is where Seedance reads the face; every
  detail it will ever know comes from those pixels.
- **Angle the portrait** — slightly off-frontal beats dead-on (reads the head's volume
  instantly); or add a smaller, separate 3/4 portrait.
- **Eyes are never black** — iris color must read clearly; crushed-black eyes give
  Seedance no light info, so tones drift between generations.
- **Catchlight, or dead eyes** — like a photoshoot or film frame, there's always a glint
  in the eye.
- **Break the symmetry** — real faces are symmetric but never perfect; perfect mirroring
  reads as AI.
- **No 3D-game-render look** — Seedance recognizes the game-model mood and animates the
  character like game footage.
- **Grey is the golden middle** — white bleeds into the video and washes out your
  location; black eats detail. Deep neutral grey wins.
- **Crop the head off the full-body panels** — on a full-length panel the face always
  distorts and drifts from the portrait; remove it so Seedance is forced to take face
  textures from the **portrait panel**, where the pixels and precision are.

## Editing characters — surgery, not a redo

Editing a sheet is surgery. One flaw in the sheet is one flaw in **every** shot
(a baked-in orange rim light in the portrait tints every downstream generation). You
never regenerate the whole sheet to fix one flaw.

- **Which model:** Nano Banana Pro for most sheet edits (never generating); GPT Image 2
  for precise add-ons/creatures (keep it to a small patch — it oversharpens human skin);
  Seedream 4.5 in parallel batches, take the cleanest.
- **Apply surgically:** every change goes onto the original sheet through Photoshop
  masks — swap only the region that changed, keep the original untouched everywhere else.
- **Never regenerate on top of an already-edited sheet** — every pass re-renders the
  whole frame, so a second edit compounds grime and drift. Mask every change onto the
  master, always.

## What a SLOP sheet looks like (reject these)

- **The dirty sheet** — a mottled/grimy plate (from repeated whole-sheet re-generations
  layering grime Seedance treats as part of the asset) **+** a full-body face that
  doesn't match the portrait (two competing identities → face/build drift). Fix: mask
  repairs onto the original, then audit again.
- **The game render** — plastic game-model textures (Seedance repeats and moves like
  game footage) **+** an orange rim light baked in (bleeds into every generation) **+**
  a portrait too small (nowhere near 25–30%, so Seedance lacks facial evidence and
  invents it differently shot to shot).
- **Standard Nano Banana slop** — mirror symmetry (synthetic look Seedance preserves)
  **+** soapy poreless skin (reproduced as plastic skin) **+** no dominant portrait (six
  near-equal tiles, no authoritative face → identity drifts).
