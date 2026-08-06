# 08 — Multi-scene and feature production system

Use this module when the work spans many scenes, multiple operators, a long runtime,
or enough assets that memory and ad-hoc filenames are unsafe. Keep the core pipeline
gates; expand the records underneath them.

## Contents

- Authoritative production records
- Asset lock gate
- Scene production loop
- Scale and complexity patterns
- Approval gates

## Authoritative production records

Maintain one source of truth for each layer:

- **Story brief** — cause, goal, stakes, obstacle, discovery, choice, and required
  continuity.
- **Asset registry** — actual `@` tag, type, descriptor, state, source master,
  approved crop, and stress-test verdict.
- **Scene map** — geography, landmarks, 180° axis, lighting direction, palette, and
  active location state.
- **Scene-block shotlist** — shot number, duration, active references, prompt version,
  result, change, verdict, and next action.
- **Constants** — approved descriptors, voice descriptors, and project-specific style
  wrappers. Edit a constant once; do not hand-copy divergent variants.

Split the film into scene blocks in story order. Assign responsibility by block when a
team is involved, but keep the registries and naming contract shared across the film.
Memory may help recall decisions; the current registry and shotlist decide what is
authoritative.

## Asset lock gate

Treat an asset as `descriptor + reference`, not as an image alone. Copy the approved
descriptor word for word into every prompt that uses the asset.

Before locking a character:

1. Test at least 10 useful variations across pose, distance, and lighting.
2. Test beside the other active characters.
3. Test in the actual location and light planned for the film.
4. Require recognizability and critical anchors to hold in every approved test.
5. Rewrite the descriptor or rebuild the source if the same feature fails repeatedly.

Create separate assets and descriptors for materially different states: dry/wet,
clean/bloodied, wardrobe A/B, intact/damaged, day/night/rain, prop visible/hidden, or
other changes that the model might mix. Do not put mutually exclusive states in one
descriptor.

Lock voices before dialogue production. Store register, tempo, accent, manner, and
pronunciation as a fixed voice descriptor, then stress-test it across generations.

## Scene production loop

For each scene block:

1. Lock assets and descriptors.
2. Lock the pure geography map and camera-side rule.
3. Prepare the shot records in story order.
4. Generate in batches small enough to review while context is fresh.
5. Assemble usable shots immediately and let the edit request missing wides, inserts,
   reaction shots, and cutaways.
6. Change one prompt line per diagnostic iteration and log the result.

Use this minimum iteration record:

```text
shot: [ID]
prompt_version: [V#]
changed_line: [one exact change]
kept_constant: [assets, geography, camera, timing, or other controls]
result: [observable outcome]
verdict: [approve / source asset / direction / inconclusive]
next_action: [one action]
```

After 10–15 controlled attempts, stop polishing wording. Split the shot, remove an
action, reduce the active space, change the angle, or replace the failing source.

## Scale and complexity patterns

- **Complex action** — open already in the important action state. Put the approach or
  wind-up in a separate shot.
- **Crowd** — use one crowd reference describing the range of heights and wardrobe;
  give only close-up lead extras separate assets. State the required visible count.
- **Space transition** — hold both location references at a doorway, arch, lift, or
  other threshold. Use a motivated light or palette contrast across the seam.
- **Giant scale** — repeat exact size plus two visible comparisons: a human scale
  anchor and a framing consequence. Define a visible failure condition.
- **Static dialogue** — stage it in one constrained corner instead of an entire room.

## Approval gates

Require explicit evidence at these gates:

- asset master and descriptor locked;
- state variant selected;
- location map and axis locked;
- first-frame occupancy readable;
- shot prompt version saved;
- motion result diagnosed;
- edit inserted into sequence;
- cleanup, color, and sound complete.

Do not claim that a remote project, folder, Element, or generation exists until the
actual service state is visible and verified.
