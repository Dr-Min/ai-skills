# 06 — Motion stress tests and synthetic-image diagnosis

A still is a hypothesis. Test the motion, occlusion, camera relationship, and crop the
film actually needs, then diagnose the earliest visible failure.

## One-variable test

1. Name the tested asset, shot requirement, and expected visible proof.
2. Hold all approved references, settings, and prompt sections fixed.
3. Change one suspect variable.
4. Inspect first, middle, and last frames plus the first moment of failure.
5. Classify the failure and record the next test.

| Verdict | Evidence |
| --- | --- |
| **SOURCE_ASSET_FAILURE** | defect is present in the input or stays tied to the same feature across controlled directions |
| **DIRECTION_FAILURE** | input is clean and failure changes when only the motion/acting/camera direction changes |
| **MODEL_FAILURE** | required control cannot be expressed or repeatedly fails with sound sources and direction |
| **INCONCLUSIVE** | more than one variable changed or the evidence does not isolate a cause |
| **PASS** | intended use holds through the inspected clip and no first failure exists |

When the character is the variable, use an already approved location. When location
geometry is the variable, use the simplest approved action. A clip with two broken
inputs cannot identify its cause.

## Synthetic-image symptom clusters

Do not name a model as the culprit from one frame. Name the visible symptom:

- **flat or discontinuous light** — crushed pits, unmotivated highlights, shadows that
  change direction;
- **broken topology** — plausible-looking hands, limbs, railings, furniture, hardware,
  or reflections that cannot survive motion;
- **uniform treatment** — identical sharpness, noise, or surface pattern across skin,
  fabric, metal, and background;
- **plastic material response** — oily, waxy, soapy, or game-render surfaces;
- **composition cliché** — automatic symmetry, centered subject, generic shallow focus,
  neon/fog/debris added without story function;
- **motion without intention** — mannequin acting, robotic interpolation, floating
  contact, or camera movement that merely decorates a static beat;
- **local logic break** — rain, smoke, hair, cloth, shadow, or particles behaving in
  only part of the frame;
- **temporal identity drift** — face, age, wardrobe, prop state, or anatomy changing
  between frames.

Different models may show different combinations over time. Record the actual model ID
and setting with the clip, but keep the diagnosis tied to observable evidence.

## Stop conditions

- A visible source defect in the intended crop is already a stop; more motion is not a
  repair strategy.
- After repeated controlled failure, simplify the shot, split the action, change the
  generation mode, or return to the earliest broken asset.
- Do not hide failure with arbitrary speed changes, frame interpolation, aggressive
  sharpening, grain, glow, or a faster edit.
- Do not approve by confidence score or generation success message.

## Review evidence

Extract deterministic review frames and a contact sheet, but inspect the original video
too. A contact sheet can reveal drift; it cannot prove motion quality, audio, or sync.
Record exact time/frame, symptom, affected asset, intended use, and one schema-defined
`take.diagnosis.verdict`; use `NOT_REVIEWED` until the inspection is complete.
