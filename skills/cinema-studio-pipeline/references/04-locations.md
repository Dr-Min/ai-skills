# 04 — Generating & editing locations

Locations are the foundation — every shot inherits their decisions, so slow down here.
A useful location is not a pretty frame: actors can be **blocked** inside it, the light
has **one logic**, the camera can see **depth**, and a later view can **repeat the same
geography**.

## From rough idea to production contract

Start messy — "a big three-storey farmer's house in the middle of nowhere, red jeep out
front, hot summer day" — then make the decisions the idea leaves open. Ask Claude to
rewrite the **full prompt** and return a **decision log**; compare that log against the
six locks below, and if a lock disappears, restore it before generating. Conversation
makes revision fast, but the **evidence — not Claude's confidence — decides** whether
the location is usable.

Two failures are easy to miss:
- **Oversharpened / oily surfaces** have no real texture to hold on to, so they swim and
  smear the instant anything moves across them.
- **Killing atmospheric haze** removes the cue that tells the eye a background is far
  away — everything near and far reads at the same sharpness: flat, immediately slop.

## The six location locks

Approve only when every named lock is visible in **both** the master and its reverse;
hold at the first failed lock.

1. **Geography before style** — name entrances, playable routes, and three depth planes
   *before* style; hidden geometry is what later views reinvent.
2. **One motivated light** — one source, direction, and falloff. Contradictory sources
   produce conflicting shadows or crushed regions.
3. **3/4, then reverse** — a 3/4 master exposes side geometry and separates
   foreground/midground/background (giving later character placement floor and distance
   cues). A **reverse is a separate generation and a continuity test**: keep the anchor,
   openings, light side, materials, and palette locked, then compare the two frames
   before calling them the same location. (Shoot head-on and the location flattens into
   a backdrop; the hidden side geometry stays unconstrained, so asking for an angle
   later lets the model invent doors, walls, and object positions.)
4. **Anchor the blocking** — block every action relative to **one fixed object** (a big
   sofa, a front door, a specific street banner). Replace "the character stands on the
   left" with "the character stands between the sofa's hall-side arm and the window."
   The relationship is testable in a later frame; vague screen direction is not.
5. **Qualify one wide** — one wide plate is enough only when no cut depends on exact
   off-frame geography (some b-roll, montage, action coverage) — i.e. when off-frame
   invention cannot break a later cut, blocking mark, or continuity claim.
6. **Approve by locks** — proceed only when every lock is visible in master and reverse.

Frames that **pass**: an overcast avenue with one soft light source, even cool tonality
across every plane, nothing crushed; a sunlit avenue with one sun, consistent shadow
direction on every tree and building, and clean falloff into skyline haze.

## Editing locations

Editing is **not a rescue step** — it's part of developing a good input. Almost every
good location still needs work: swapping details, removing clutter, color-correcting to
your project. The skill is doing it **without wrecking what already works**.

### Escalate edits deliberately
Start with **Nano Banana Pro** for most edits. Use **Seedream** when an otherwise sound
frame needs skin, fabric, or surface texture recovery. Use **GPT Image** for readable
text, mathematically precise local detail, or a reverse/view change that the first pass
cannot hold. Run models in parallel only when the best route is uncertain enough that
an A/B comparison is worth the cost.

(Real cafeteria pass: Nano Banana Pro cleaned grime off red metal, fixed fused stools,
added trays/litter; GPT Image 2 swapped in lamps, TVs, and menu boards with readable
text; Photoshop softened textures, removed corridor objects, unified color, and
composited every edit onto the original.)

### The three edit locks
1. **Edit the original** — every detail you add or remove gets **masked onto the
   ORIGINAL** in Photoshop. Change only the patch that changed; leave the rest untouched.
2. **Use the narrowest capable model route** — start with Nano Banana, then escalate;
   parallelize only for a deliberate comparison.
3. **Never re-edit an edit** — an edit model never touches only what you asked for; it
   quietly **re-renders the whole image**. A second pass on an edited image re-renders
   again and compounds slop. Always mask the change onto the master file.
