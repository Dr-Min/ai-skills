# 07 — The capstone: a full scene, end to end

The capstone runs the whole chain with the user's own assets: set up the production,
cast a character, build a location, dress the scene with a prop, then shoot one finished
Seedance shot. Each step is a real studio action — Higgsfield's checker verifies actual
server activity, so a generation only counts once it is **saved as an Element** (a bare
generation, or a duplicate of someone else's Element, does not count).

Use this as the checklist when helping a user produce a complete scene.

## Step 1 — Set up your production
One new **project** named for the scene, holding three folders: `locations`,
`characters`, `props`. Create the project, open its workspace, use *Add folder* three
times. Success: the project rail shows all three folders.

## Step 2 — Cast your character
Generate a character that fits the scene (see `references/05-characters.md` for the
sheet standards). Refine to one image worth keeping, then choose **Save character** to
create a reusable character Element. Name it `@char_<project>_<name>`.

## Step 3 — Build the location
Generate a location that fits the scene (see `references/04-locations.md` — apply the
six locks). Refine to one keepable, reusable image, then choose **Save location** to
create an environment Element. Name it `@loc_<project>_<name>`.

## Step 4 — Dress the scene with a prop
Pick the object the scene **cannot work without**. Generate and refine until one image
clearly shows the intended shape, material, wear, and story detail — approve only a
result you would reuse. Choose **Create Element / Save as Element**, name it
production-ready, and choose type **Prop** (`@prop_<project>_<name>`). Success: the prop
appears in Elements and can be selected by its `@name` in a prompt.

## Step 5 — Shoot the scene
In **Seedance 2.0**, write one clear story beat, then attach **all three** saved
Elements as real references — character, location, and prop. Generate and wait for the
video to finish.

- **A short shot is a scene, not a limitation** — most shots in real films are shorter.
  Spend your seconds on one moment done properly.
- Keep resolution and duration inside the free-generation caps so the shot stays free.
- The server confirms a completed Seedance 2.0 job whose references include at least one
  Element created for this production — but use all three types to complete the outcome
  the way a real shot needs them.

When the checklist closes, the free course certificate is ready to claim.

## Section tests (checkpoints, graded at 80%)
The course has three graded section tests plus a final. They are checkpoints, not
decoration — if one stings, the gap it found is the lesson worth re-reading.
- **Foundations** — pipeline stages/handoffs, Cowork vs plain chat, the six-slot prompt
  pass, the `@type_project_name` naming convention.
- **Studio & models** — project/folder setup, the four image-model candidates and when
  to pick each, the must-preserve decision rule, judging by pixels not reputation.
- **Locations, characters & slop** — the six location locks, edit discipline (mask onto
  original, never re-edit an edit, parallel models), character-sheet rules (25–30%
  portrait, catchlight, break symmetry, crop heads, grey background), the Seedance
  one-variable diagnosis, and the four slop tells + two model accents.
