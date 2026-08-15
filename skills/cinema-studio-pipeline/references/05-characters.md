# 05 — Character identity, state, and performance assets

A character reference is useful only when it preserves the approved person through the
actual crops, lighting, cast combinations, wardrobe states, and movement the film needs.
A character sheet is one possible container, not a universal solution.

## Character authority record

Lock these separately so one change does not silently rewrite the rest:

- **identity** — age range, facial geometry, skin, hair, distinctive anchors;
- **body and silhouette** — height relationship, build, posture, gait, handedness;
- **personality and behavior** — resting tension, gaze habit, gesture vocabulary;
- **wardrobe** — exact garment layers, fit, materials, footwear, accessories;
- **mechanical or story state** — dry/wet, clean/injured, intact/damaged, calm/panicked;
- **performance constraints** — what the actor must do and what must remain recognizable.

Create separate versioned assets for mutually exclusive wardrobe, injury, age, and
mechanical states. Do not combine them in one descriptor or reference sheet.

## Select the reference package by the shot

The current provider may accept one image, several role-specific references, an Element,
an AI Cast identity, or another binding mechanism. Verify the live limit, then assign
roles explicitly.

Possible packages include:

- one clean identity portrait for face-dominant shots;
- portrait plus body/silhouette evidence for wider shots;
- separate identity and wardrobe references when the provider can distinguish them;
- front/back or profile evidence when hair, garment construction, or a turn matters;
- state-specific reference for a wound, wetness, damage, or transformation.

Do not squeeze every view into one crowded sheet merely to look complete. A tiny,
distorted full-body face can compete with the approved portrait; an omitted rear head
can also remove necessary hair evidence. A/B test the package in the intended motion
and exclude the version that creates identity conflict.

## Fresh-generation rule

Create a new high-quality source when identity, anatomy, body proportion, overall light,
or resolution is wrong. Do not repeatedly edit a degraded sheet and promote it as the
new master. A local patch is acceptable only on an otherwise approved immutable source,
with the changed region composited as a derivative and its parent hash preserved.

## Model routing

AI Cast, current Soul routes, Nano Banana, Seedream, GPT Image, and other current models
are candidates, not fixed character jobs. Check live capabilities and run a controlled
test for the hardest requirement. A historical tendency such as good skin, precise
geometry, or strong editing does not prove current identity preservation.

## Stress-test matrix

Before asset lock, test only the cases the planned shots need, but cover every relevant
risk at least once:

| Risk | Test evidence |
| --- | --- |
| Face identity | close-up and intended expression range |
| Body/anatomy | required wide crop, sitting/standing, hands and feet visible as needed |
| View change | profile, back, turn, or camera orbit used by the film |
| Lighting | darkest and most colored approved scene light |
| Motion | fastest or most occluded required action |
| Ensemble | beside the other cast without face or wardrobe leakage |
| State | each mutually exclusive wardrobe/injury/mechanical version independently |

Record `required_takes`, `completed_takes`, `recognizable_takes`, the schema-defined
`NOT_RUN|PASS|FAIL` verdict, and diagnostic notes in `asset.stress_test`. There is no
magic fixed count. Test until every planned risk has evidence; more repeated easy clips
do not compensate for one untested hard shot.

## Character-reference approval

Inspect the reference itself and the stress-test clips. Keep it in `INTERNAL_REVIEW` or
set `REJECTED` when any of these affect the intended use:

- competing faces, ages, hairlines, or body proportions;
- missing or anatomically broken limbs, hands, feet, or joints;
- game-render surfaces, waxy skin, edge halos, or baked-in colored rim light;
- inconsistent garment construction between views;
- a pose or facial expression that the model reproduces involuntarily in every shot;
- background or props that activate unwanted scene content;
- insufficient face pixels for the intended close-up;
- a hidden face when identity must be proven downstream.

Background color, sheet layout, portrait size, lens look, and view count are testable
choices. Do not hardcode deep grey, a particular percentage, 85 mm, “8K,” perfect
symmetry, or shallow focus as universal character-sheet requirements.

## Performance continuity

Identity is not only a face. Carry the character's behavior contract into each shot:
body tension, hesitation, gaze target, breath, gesture preparation, contact with props,
and recovery after the action. This prevents a visually consistent character from
performing like an unrelated mannequin.
