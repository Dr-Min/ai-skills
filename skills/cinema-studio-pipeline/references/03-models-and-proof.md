# 03 — Model routing and proof

Provider capabilities and model behavior change. Read
`providers/higgsfield/capabilities.yaml`, then verify the authenticated live UI before
relying on a model name, reference count, mode, aspect ratio, duration, resolution,
cost, or availability.

## Route by the hardest requirement

Do not choose a model because it is the skill's permanent favorite. Name the one
requirement that would be most expensive to repair, then choose a currently available
candidate whose live controls can express it.

| Hard requirement | Capability to test |
| --- | --- |
| From-scratch atmosphere and materials | coherent light, depth, texture, authored composition |
| Character identity | usable identity binding and consistency across crop and motion |
| Exact text or geometry | legibility, local control, repeatable structure |
| Existing-frame change | edit/reference mode and preservation outside the requested region |
| Surface recovery | natural skin, fabric, hair, and material texture without geometry drift |
| Video continuity | the required reference, boundary, motion, or audio input mode |

Soul, AI Cast, Nano Banana, Seedream, GPT Image, and Seedance are routing candidates
only when the current account actually exposes the relevant capability. Historical
results may suggest which candidate to try first; they do not prove the next output or
justify an absolute “never use this model for that” rule.

## Controlled model comparison

When fit is uncertain, make a small A/B test:

1. Hold the authority records, active reference hashes, crop, and expected proof fixed.
2. Change only the candidate model or one declared model setting.
3. Record actual model ID, visible UI settings, job ID, output hash, and cost if shown.
4. Inspect the same crop and the same failure checklist.
5. Select the output that preserves the must-preserve requirement, not the most
   superficially impressive frame.

Do not run every model automatically. Parallel candidates are justified only when the
approval value exceeds the extra cost or one controlled comparison will answer a real
routing question.

## Image-edit boundary

An edit model may re-render pixels outside the requested region. Preserve the immutable
source, create a fresh candidate from the highest-quality approved input, and composite
only the accepted patch as a derivative. Do not repeatedly feed the derivative back for
another whole-frame edit. If the base identity, anatomy, grade, or texture is already
bad, return to source generation rather than hiding it with more patches.

## Proof, not promises

Prompts, model names, job success, and preview thumbnails are not approval evidence.
Inspect the actual output at its intended use:

- identity and required state;
- anatomy, hands, feet, face, and object topology;
- geography, eyeline, screen axis, and continuity anchors;
- motivated light, material response, depth separation, and texture;
- exact first, middle, and last frames for video;
- audio presence, sync, and unintended artifacts when audio is expected;
- crop safety at final aspect ratio and resolution.

The verdict is use-specific. A frame can pass as distant montage coverage and fail as a
face master. Use the authority record's schema-defined values: asset stress tests use
`NOT_RUN|PASS|FAIL`; take diagnosis uses `PASS`, `SOURCE_ASSET_FAILURE`,
`DIRECTION_FAILURE`, `MODEL_FAILURE`, `INCONCLUSIVE`, or `NOT_REVIEWED`. Put the first
visible failure and next single-variable test in their dedicated fields or notes.
