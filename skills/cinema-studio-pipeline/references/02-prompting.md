# 02 — Image prompt construction

Build image prompts from approved production decisions. Do not paste a generic
“cinematic” persona or repeat a fixed composition across scenes.

## Scope

Use this reference for location plates, character images, props, concept stills, and
fresh image patches. For video, read `references/09-seedance-prompt-director.md`.

The prompt is a render of the current authority records. It does not outrank the story,
visual bible, asset state, shot card, reference-role contract, or actual model settings.

## Six decisions before prose

Resolve these slots before writing the final one-paragraph prompt:

1. **Subject** — the visual center and its approved identity or state.
2. **Action** — the drawable pose, gesture, or event at this exact instant.
3. **Setting** — scene-specific geography, surfaces, depth layers, and anchor objects.
4. **Light** — motivated source, direction, falloff, contrast, and color relationship.
5. **Camera** — framing, height, angle, lens intent, focus, and composition.
6. **Constraints** — continuity truths and failures this generation must avoid.

Add a seventh check before assembly: **why this frame exists in the film**. If another
location, lens, or light treatment would communicate the same beat equally well, the
mise-en-scene is not specific enough yet.

Every clause in the final prompt must trace to a visible decision. Concrete nouns and
spatial relationships are stronger than praise words such as “beautiful,” “epic,” or
“cinematic.” A longer prompt is not automatically more controlled.

## Location decision pass

For a new location, run four passes without turning them into a reusable persona:

1. **Deconstruct** — map the brief into the six slots and label each value explicit,
   implied, or missing.
2. **Diagnose** — check spatial logic, story function, repeated imagery, light
   motivation, and whether characters can perform the planned blocking.
3. **Develop** — propose only the smallest missing decisions, with their visual reason.
4. **Deliver** — write one coherent English prompt plus a decision log and open issues.

There is no universal 3/4-view, soft-light, shallow-focus, neon, fog, or teal-orange
default. Choose the camera and light from the beat, geography, and approved visual
bible. Repeating a tasteful default across scenes is one of the fastest ways to create
AI-slop sameness.

When a location must support later compositing or character placement, name stable
spatial anchors and keep the required negative space. Do not add observatory equipment,
architecture, weather, props, or background figures simply because they seem genre
appropriate.

## Character and asset prompts

- Reuse the exact approved identity and state descriptor; do not paraphrase it casually.
- Separate identity, wardrobe, pose, location, and look references by role.
- Match the requested crop. A face-approved close-up is not proof of full-body anatomy.
- For a new full-body source, generate from approved identity evidence rather than
  repeatedly editing an already degraded composite.
- Keep mutually exclusive states in separate records and separate generations.

## Image edits and fresh patches

Preserve the immutable source. Describe one region and one intended change, generate a
fresh patch from the source-quality input, and composite it as a derivative. Never make
the derivative the new identity master. If identity, anatomy, or overall image quality
degrades, stop patching and generate a fresh source.

## Iteration rule

Change one diagnostic variable per iteration. Rewrite the full prompt so its clauses
remain coherent, but record the exact changed slot and expected visible effect. Keep all
other model and UI settings fixed unless that single setting is the experiment.

Do not “improve everything” after a failed render. First name the earliest visible
failure: identity, state, geography, blocking, camera, light, anatomy, texture, or model
capability. Patch that authority layer.

## Required output before generation

```text
Prompt: <one coherent English paragraph>
Decision log: <brief source decision -> prompt clause mapping>
Active references: <asset id, exact hash, role, state>
Model/UI settings: <recorded outside the prompt>
Changed variable: <one field, or NONE for v01>
Expected visible proof: <what must be visible in the result>
Open issue: <only a material unresolved decision>
```

After generation, inspect the pixels at the intended crop. A clean job response or a
well-formed prompt is not visual proof.
