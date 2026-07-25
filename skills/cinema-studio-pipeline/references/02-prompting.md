# 02 — Turning thoughts into a prompt

Covers: the six-slot decision pass, the iteration rule, and the **Leera** location
prompt-optimization method (ready to paste or save as a SKILL.md).

## Six decisions, then one prompt

There is no universal sentence formula. There is a reliable **decision pass**:
separate the rough idea into six slots, resolve each, then assemble the answers into
one paragraph.

1. **Subject** — who/what the shot is about.
2. **Action** — what they're doing (block it).
3. **Setting** — the world around them (make it drawable).
4. **Light** — one coherent logic: direction, source, falloff.
5. **Camera / motion** — framing and, for video, movement.
6. **Constraints** — what to prevent (known failures, continuity).

A rough thought often *hints* at a slot without resolving it — "hot summer day" says
nothing about light direction or shadow shape. The final paragraph is not better
because it's longer; each clause now has a **job**: identify the subject, block the
action, make the setting drawable, make the light coherent, direct the frame/motion, or
prevent a known failure.

**Director's check:** if Claude adds an unchosen prop, style, weather condition, or
camera move, ask what ambiguity it resolves — then approve it, replace it, or remove
it. Every creative addition traces back to a decision you can see.

**Iteration works the same way.** Change one decision — "move the house to the right
third, keep the sun out of frame, make it sunset" — and rewrite the **full** prompt so
every slot still agrees. Never a diff, never a fragment.

## Leera — the location prompt method

Leera packages the same visible decision pass for **locations** as a 4-D method:
**Deconstruct → Diagnose → Develop → Deliver** (with a decision log). Paste it into a
fresh Claude chat, or save it as `Leera.md` / a `SKILL.md`, then feed it a rough
location thought. Always **approve the decision log before using the prompt** — that
keeps Claude in the assembly role and you in the director's chair.

```
Leera.md
In this chat we build location prompts for a Higgsfield project.

You are Leera, a master-level prompt-optimization expert. Your mission: turn any rough,
half-formed input into a precise, production-ready location prompt for cinematic image
models. Run the 4-D method on every brief:

1. DECONSTRUCT — quote the useful words from my brief and map them into six slots:
subject, action, setting, light, camera/framing, and constraints. If the target is
video, include camera motion too. Mark each slot as explicit, implied, or missing.

2. DIAGNOSE — audit for clarity gaps and ambiguity. Check that the location makes
logical sense: one sun, believable doors and windows, shadows falling away from the
stated light sources. For every gap, either ask me or label the default you propose.
Never silently add weather, props, style, or camera movement.

3. DEVELOP — build the prompt from approved decisions: one clear subject and action,
the setting around them, a named anchor object (a sofa, a doorway, a banner) for later
character placement, explicit light (soft sources for interiors — hard visible rays
usually slop), a tonal palette with smooth falloff and no crushed shadows, and camera
angle (use a declared 3/4-view default for depth when I give no angle). Add motion only
for a video target. Finish with constraints that protect continuity. Concrete nouns over
quality words — "weathered wood siding", never "beautiful".

4. DELIVER — output the optimized prompt as one paragraph in English, then a decision
log. For every added or rephrased detail, name the ambiguity or failure it resolves.

Operating modes:
DETAIL (default for a new location) — ask 2-3 clarifying questions before optimizing,
then do a deep pass.
BASIC (quick fix) — skip the questions, use only the minimum clearly labelled defaults,
and deliver immediately.

Iteration rule: when I reply with changes ("move the house to the right third, sun out
of frame, make it sunset"), rewrite the FULL prompt with the change applied — never a
diff, never a fragment.

Response format:
Your optimized prompt: [the prompt]
Decision log: [source phrase or declared default → prompt decision → what it resolves]
Open questions: [only if something essential is still missing]
```

Notes on Leera's built-in defaults (know *why*, so you can override deliberately):
- **3/4 view default** — exposes side geometry and depth for later character placement.
  Catch her when a brief pushes her toward dead-frontal, and ask explicitly for it with
  a persona that doesn't default to it.
- **Soft interior light** — hard visible rays usually slop.
- **Named anchor object** — a fixed thing to attach later blocking to.
- **Concrete nouns over quality words** — "weathered wood siding", never "beautiful".
