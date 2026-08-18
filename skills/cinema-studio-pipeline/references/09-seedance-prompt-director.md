# 09 — Seedance prompt director

Use this module to write, repair, or audit a Seedance video prompt. Build a sealed
current-shot document. Do not let image-prompt prose, previous-scene summaries, stale
tags, or production notes leak into it.

## Contents

- Intake and silent diagnosis
- Prompt skeleton
- Scene context and references
- Geography and first frame
- Format, optics, camera, action, physics, lighting, audio, and acting
- Constraints, UI settings, and pre-send QA

## Intake and silent diagnosis

Extract only what must be visible or audible in this shot:

- story beat and duration;
- active characters, location, props, vehicles, and exact `@` tags;
- first visible frame and spatial relationships;
- single take or controlled cuts;
- camera side, field of view, movement, and focus behavior;
- timed action, material physics, and lighting direction;
- acting state, dialogue, voice, ambience, and silence;
- known failure modes that need a local lock.

Reject unused tags, scene numbers, script headers, old prompt fragments, “previously,”
“continues,” “same as before,” and any offscreen person or object the current shot does
not need. Never invent an `@` tag.

Before writing, check the likely failures: empty first frame, late character entrance,
duplicates, flipped left/right, wrong gaze, crossed axis, remote landmark, wrong-hand
prop, lens drift, flat front light, floaty motion, mistimed dialogue, or a location
reference copied as composition instead of geography.

## Prompt skeleton

Use only the sections the shot needs, in this order:

```text
SCENE_CONTEXT
ACTIVE_REFERENCES
LOCATION_MAP
FIRST_FRAME_AND_SPATIAL_BLOCKING
FORMAT_MODE
OPTICS
CAMERA
ACTION_TIMING
PHYSICS
LIGHTING
AUDIO
CHARACTER_ACTING
STYLE
QUALITY
POSITIVE_CONSTRAINTS
```

Write the final prompt in clear cinematic English unless the user requests another
language. Keep present tense and direct physical verbs. The full prompt may be long
when control requires it, but keep each timed beat to at most about three short
sentences. Remove decorative adjectives before removing spatial or causal control.

## Section rules

### Scene context and references

State `EXACT N CHARACTERS — NO DUPLICATES` when count matters. List only active tags
and name each role: character identity, location geography/material, prop shape/state,
or vehicle identity. For a location reference, say to use the space, landmarks, and
materials without inheriting the source framing, angle, or grade unless requested.

References may be saved `@` Elements or platform-selected start/end images. Name the
role of every actual input, but do not invent an `@` tag for an uploaded boundary
frame. Keep file names, hashes, and platform settings in the shot record when the UI
already carries them; the prompt should describe their visual role.

For start-and-end-frame generation, treat the two images as boundary contracts:

- start on the supplied first-frame composition without an empty prelude;
- define one physically causal bridge between the boundaries;
- state which identity, geography, light, texture, and object states remain constant;
- arrive at the supplied end-frame state only at the intended final beat;
- inspect the rendered last frames before claiming that the model matched the target.

When both boundary images already lock one short shot’s composition and geography, a
compact map may be enough. Keep the full scene map when the result must cut against
other shots or when off-frame geography can still break continuity.

Avoid numeric age when it is unnecessary, when the person could be interpreted as a
minor, or when prior tests show filter sensitivity. Prefer role, build, wardrobe,
current state, and visible identity anchors. Use an adult age range only when the user
explicitly requires it and it is safe and story-critical.

### Geography and first frame

Write one pure scene map and repeat it unchanged across the scene:

```text
LOCATION_MAP (locked across this scene)
- [LANDMARK]: [frame position and world relationship]
- [LANDMARK]: [distance from the first landmark]
- 180° AXIS: camera stays on [named side] and never crosses the line.
- LIGHT: [source and direction relative to camera and landmarks].
```

Use `frame-left` and `frame-right`, named landmarks, and measured distance instead of
“near” or “to the hero’s left.” After every cut, restate position, torso direction,
gaze target, movement direction, and depth plane.

The first visible frame should already contain the required subjects and readable
relationships. When spatial continuity matters, spend roughly the first second on a
wide occupancy lock with no empty establishing beat. Keep the required people in that
frame; a spatial anchor is not an empty landscape.

### Format, optics, and camera

Default to one continuous take. Use controlled internal cuts only when the user asks
or when one camera position cannot show the required geography, reaction, and detail.
Name each cut type and define the first frame, active subjects, blocking, camera, lens
character, action, and duration for every segment. Do not let the model invent cuts.

Describe observable optics before brand metadata: physical camera distance, field of
view, perspective expansion or compression, subject size, environment visibility,
focus plane, and foreground occlusion. Use lens millimeters or field-of-view degrees
only when they add control. Never mix portrait compression, wide geography, and macro
detail inside one uncut lens beat.

Write camera movement as operator behavior: height, side, distance, path, reframe,
focus, and what remains fixed. Limit compound moves. “Handheld” means breathing,
weight, micro-settling, and human correction, not random digital jitter.

### Action and physics

Break action into feasible time blocks. Include position, visible action, camera
behavior, prop state, and the cause-and-effect physics needed in that interval.

Start complex actions in the decisive state: already mid-swing, already airborne,
already cracking. Put the approach or wind-up in another shot. Write the desired
positive state first: “lands on his stomach,” not only “does not land on his back.”

Name gravity, mass, inertia, friction, contact, weight transfer, follow-through,
cloth/hair delay, liquid viscosity, particle direction, vehicle mass, hinge resistance,
or weapon weight only where they affect the visible action.

### Lighting

Lock one motivated source, direction, camera side, exposure priority, shadow side, and
allowed highlights. Protect the required result locally: subject between camera and
bright background, camera on shadow side, rim and environmental bounce revealing the
form. Style language may refine the shot but cannot override the light map.

### Audio and acting

Put spoken words only in `AUDIO`. Quote the exact permitted line, specify the fixed
voice descriptor, and state that other characters remain silent when necessary. Keep
ambience below dialogue and forbid subtitles or music only when those are likely
failure modes or part of the deliverable contract. Read
`references/10-acting-and-dialogue.md` whenever performance matters.

### Style and quality

Keep `STYLE` compact and subordinate to identity, geography, action, physics, and
light. State observable texture, contrast, grain, and color behavior instead of a long
list of artist or film names. Use `QUALITY` only for visible stability and clarity
requirements that are not already authoritative UI settings.

### Constraints and UI settings

Describe the desired state before a negative lock. Use short local negatives only for
demonstrated or high-probability failures: no duplicate person, no extra prop, no
wrong-hand swap, no flat front light, no subtitle. Do not append a generic wall of
negatives.

Omit aspect ratio, resolution, model, seed, fps, shutter, and duration when the user
has already selected them authoritatively in the platform UI and they do not affect
story logic. Keep single take, real time, cut rules, slow motion, audio, and subtitle
rules when they change the visible or audible outcome.

## Silent pre-send QA

Before returning the prompt, verify:

- every active tag is real and used; no stale tag remains;
- the first frame and exact subject count are correct;
- positions, body directions, gaze lines, camera side, landmark distances, and axis
  are unambiguous;
- lens language matches the shot content and cannot drift silently;
- light direction, prop hands, wounds, dirt, water, and object states continue;
- actions fit the available time and obey physical cause and effect;
- dialogue contains only the scripted words and correct speaker;
- platform settings are not redundantly fighting the UI;
- analysis and QA notes are omitted unless the user asked for them.
