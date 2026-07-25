# 06 — Testing in Seedance & spotting slop

## Test in Seedance — one variable at a time

A still is only a **hypothesis**. Run the motion your shot actually needs in Seedance,
then change **one variable at a time** until the visible failure points to either the
source asset or the motion direction.

- **Start from a baseline you can diagnose.** When the character is the question, keep
  the location out of it — use a plate that already holds its geometry, depth,
  materials, and light. A broken plate gives every character failure a second plausible
  cause.
- **A percentage cannot approve a shot.** The named source assets, the required motion,
  and the visible result are the evidence — not a confidence number.

### Diagnosing a failing input
One bad clip is a symptom, not a diagnosis. Compare its **first** failure against the
source stills, then read the controlled result:

| Verdict | When |
| --- | --- |
| **Source asset** | The defect exists in the source, or stays tied to the same feature when direction changes. |
| **Motion direction** | The source is clean and the defect changes when only the suspect motion clause changes. |
| **Inconclusive** (narrow the test) | Controls conflict, or the failure follows neither variable. |

The diagnosis applies only to the tested asset and direction — it is **not** a universal
claim about a model, and one rerun does not guarantee the next result.

## Spot the slop

Slop hides in stills and multiplies in motion. Inspect the **exact crop** you plan to
use, name the visible defect, then decide whether that crop is safe for Seedance. **A
visible still-frame defect is already a stop.** Use Seedance only when the crop passes
the still scan and you need motion to confirm an uncertain edge, reflection, or object.

### The four universal tells
1. **Light with no transitions** — flat-black pits instead of a smooth shadow ramp; they
   transfer onto every character you add.
2. **Broken-but-plausible objects** — crates, railings, hardware you can *almost* read;
   in motion they turn to mush and multiply.
3. **Local logic breaks** — an effect in only part of the frame (rain that scratches one
   corner); Seedance's logic breaks with it.
4. **Oily textures** — soapy surfaces lose their material; reflections crawl in motion,
   so the plate cannot hold continuity.

### Two model "accents" (name the culprit from one frame)
- **Banana slop (Nano Banana Pro)** — ruler-straight symmetry, everything parallel and
  set square, flat light/color with no contrast play → pretty but staged and lifeless,
  like stock photography. Textures detailed yet read as a 3D render, not a photograph.
  **Hyperbolizes every edit:** ask for graffiti on a wall and the whole location gets
  tagged; ask for "more alive and cinematic" and it litters the frame with junk and dirt.
- **GPT slop (GPT Image 2)** — sharpness and microcontrast cranked to the ceiling, hard
  halos on every edge; no depth (everything in focus, no bokeh, no plane separation);
  white balance pulled warm until the frame yellows; materials go plastic and
  licked-smooth; dynamic range squeezed to the middle so shadows and highlights meet
  halfway and the frame goes limp. **Most damning tell:** a single sickly texture pattern
  laid over the entire frame (the same film-wrap pattern on cabinets and car bodies
  alike).

### Calibrate your eye
Stare at clean frames until your eye runs the checks automatically — good material
under one light (surf, black rock, wet foliage reading as material under one grey sky).
Higgsfield ships a dedicated **Spot the Slop practice app** (deeper pool of real frames,
timed rounds, no repeats); run it before choosing a location or approving a final shot.
