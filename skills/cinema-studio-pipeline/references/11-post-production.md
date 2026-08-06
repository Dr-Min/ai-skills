# 11 — Assembly, cleanup, color, and sound

Post-production begins during generation. A finished generation is raw material; a
finished film is an assembled, cleaned, unified, and checked sequence.

## Edit while generating

As usable shots arrive, place them into the sequence and record what the cut needs:

- wider geography;
- reaction or listening close-up;
- hands, prop, or environment insert;
- cutaway to hide a continuity break;
- alternate entrance, exit, or action phase;
- cleaner dialogue or ambience handle.

Let the edit shape remaining production. Do not wait for every planned shot before
discovering that the scene lacks a bridge.

AI generations often carry slow starts, settling, and edge drift. Plan usable handles
and expect to test trimming roughly the first and last half-second; inspect the actual
clip before applying a fixed trim.

## Finishing order

Use this order:

1. **Picture assembly and timing** — choose takes, cut rhythm, continuity, and missing
   coverage.
2. **Picture lock** — stop creative shot replacement before destructive finishing.
3. **Cleanup** — repair hands, faces, text, boiling textures, edge warps, and other
   frame defects.
4. **Color unification** — match neighboring shots within each scene, then refine the
   intended look.
5. **Dialogue cleanup and sound design** — stabilize voice timbre, place voices in the
   room, build continuous ambience, add effects and music.
6. **Final QA** — inspect the delivery crop, resolution, frame rate, sync, loudness,
   transitions, and narrative clarity.

Do not color-grade before cleanup; defects become harder to isolate and repairs may no
longer match. The location assets should already contain the scene’s light and palette
logic, so color refines and unifies rather than inventing a different look.

## Cleanup decisions

Prioritize faces and hands in close-up, then readable text and story-critical props.

- Retouch a small localized defect frame by frame or with a tracked patch.
- Regenerate a fully broken shot from the saved final prompt, changing one line and
  preserving the logged assets and controls.
- Do not pass an already edited master through another full-frame model. Return to the
  immutable source and composite a new patch.
- Recheck temporal stability after any repair; a correct still is not proof of a clean
  moving result.

## Sound continuity

Treat continuous ambience as spatial glue across generated shots. Maintain room tone,
wind, traffic, machinery, crowd bed, or other scene atmosphere across cuts even when
the picture changes slightly.

Use generated lip-synced dialogue when it is usable: remove noise, match timbre and
level between clips, and place it acoustically in the space. Re-record only when the
generation has no salvageable performance or the delivery contract requires it. Add
music in post unless the user explicitly needs generated music in the source clip.

## Final evidence

Before delivery, verify the actual sequence rather than the prompt history:

- story cause and effect read without explanation;
- screen direction, geography, identity, wardrobe, wounds, and props hold;
- no visible extra fingers, duplicated people, boiling textures, fake text, or edge
  drift remains at the intended display size;
- dialogue belongs to the correct mouth and emotional beat;
- ambience and color make neighboring generations feel like one scene;
- no unresolved approval gate is described as complete.
