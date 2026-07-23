# Prompt design for parallax cinematic shots

This is ONE creative recipe, not the creative direction itself. It documents a single
proven shot type — the slow parallax arc around a small figure — because its prompts
are tricky to get right. Creative direction always starts from the user's intent and
from scratch; never default to this recipe or treat its formula as required. Use it
only when the concept the user actually wants happens to be this kind of shot, and
even then adapt freely.

## An awe recipe (one example, not a rule)

One shot type that makes viewers go "whoa" on sight combines:

```
something colossal  +  a very small figure  +  drifting light particles  +  occlusion reveal
```

- **Colossal**: a galaxy, a whale overhead, a giant moon, a waterfall cliff. "Near-huge"
  (a whale directly above) hits harder than "far-huge" (a distant galaxy) because the
  scale contrast is legible.
- **Small figure**: a lone person, seen from behind, anchored dead center. Small on
  purpose — the tininess *is* the scale cue. Back-to-camera keeps them a silhouette so
  face artifacts never matter.
- **Light particles**: fireflies, bioluminescent plankton, embers, dust motes. They add
  huge apparent detail cheaply and, because they sit at many depths, they become extra
  parallax cues in motion.
- **Occlusion reveal**: something in front (clouds, a whale's body, a branch) partially
  hides the colossal thing, then the camera move *reveals* more of it. The background
  stays locked; only the occluder moves. This is what sells "living 3D space."

## Five-layer depth staging (the load-bearing idea)

Parallax only reads if the scene has clearly separated depth planes moving at different
speeds. Write the still prompt in explicit layers, closest to farthest:

```
Layer 0  extreme foreground, TOUCHING THE LENS   out-of-focus leaves/petals/bubbles, big bokeh
Layer 1  near foreground                          a dark occluder (tree, coral, rock) at one edge
Layer 2  midground ANCHOR                          the small figure, dead center, back to camera
Layer 3  moving mid/far layer                      clouds / the colossal creature — partially hides L4
Layer 4  infinity                                  the sky / sun / galaxy — the locked backdrop
```

Why each matters in motion:

- **Layer 0 is the parallax engine.** Something pressed against the lens sweeps across the
  whole frame even on a tiny camera move — that fast sweep against a still background is the
  entire illusion. If the still lacks a lens-close layer, the move looks flat. It's normal
  and correct for Layer 0 to sweep out of frame within the first couple seconds.
- **Layer 1 at an edge** gives a mid-speed cue and, if it exits the frame during the move,
  hides the "invented" area behind it so the model has less to hallucinate.
- **Layer 3 occludes Layer 4**, so the camera move can *reveal* the backdrop rather than
  pan it. Put the galaxy/sun *behind gaps* in the clouds; that seeds the reveal.
- Name **atmospheric depth haze** between layers — it forces the model to separate the
  planes instead of flattening them.

Only `gpt_image_2` produces true 4K stills on Higgsfield, so it's the stage-1 default.

## Arc vs orbit: it's the same circle, the angle is everything

An "arc" is just a shallow orbit — same path, fewer degrees. The angle is the whole game:

- A **shallow arc (~15–30°)** keeps the figure centered, the backdrop in frame, and the
  back-of-head silhouette intact while still generating strong parallax off Layers 0–1.
- A **wide orbit (toward 180°)** swings the camera past the subject: it loses the entire
  backdrop (which lives on one side of the scene) and exposes the figure's face. For a shot
  whose value is all in one direction (galaxy/sun/whale ahead of the figure), that destroys
  the composition.

So in the **motion prompt**, specify the angle numerically and lock the subject:

> camera slowly arcs to the right around the figure, a gentle 20–30 degree lateral orbit,
> subject stays centered and unmoving, foreground sweeps across the lens, the sky/backdrop
> stays locked at infinity and never follows the foreground, [occluder] gradually reveals
> more of [backdrop] as it passes. slow, dreamy, single continuous shot, no cuts.

## Guard the failure modes in the motion prompt

- **Background drifting with the foreground** = the shot became a flat pan. Explicitly say
  the backdrop is "locked at infinity, never follows the foreground." This is the single
  most important line and the pass/fail test when you review the clip.
- **A living colossus melting** (whale, dragon, etc.): add "moving as one rigid graceful
  form, anatomy preserved." Rigid subjects (mountains, ruins) don't need this.
- **Invented area behind an exiting occluder**: keep the occluder at an *edge* so it leaves
  the frame, and keep what's behind it simple (sky, not architecture). Complex structures
  behind an occluder tend to smear when revealed.

## Reviewing a clip from stills

You can judge most of a clip from its first and last frame (the pipeline's stage-2 output).
The last frame is where the arc has traveled farthest, so artifacts are most exposed there.
Check, in priority order: (1) is the backdrop still where it was, or did it slide with the
foreground; (2) is the newly revealed area clean; (3) did reflections/hair/anatomy survive.
But interpolation and micro-jitter only show in playback — always tell the user to actually
play it before the final commit.
