# 03 — Asset lock

Build references that survive motion. Treat an asset as `reference + verbatim
descriptor + state + role + provenance`, never as an image alone.

## Build by category

- Character: identity master, behavior profile, fixed voice, wardrobe, and material
  state variants. Read `references/05-characters.md` and
  `references/10-acting-and-dialogue.md`.
- Location: playable geography, landmarks, depth planes, reverse coverage, materials,
  and motivated light. Read `references/04-locations.md`.
- Prop/mechanism: scale, materials, contact points, neutral state, and separately
  referenced active states.
- Look: color and texture influence only; never let it override identity or geometry.

## State isolation

Create separate asset records for every mutually exclusive visible state: open/closed,
retracted/extended, intact/damaged, dry/wet, clean/bloodied, wardrobe A/B, day/night,
or any condition the model could mix. Do not put an unwanted active state in the same
sheet and expect a small label to suppress it.

## Stress test

Test production candidates across useful combinations of distance, angle, pose,
lighting, action, co-star, and actual location. Store contact sheets and verdicts.
Rebuild the source or descriptor when the same feature repeatedly fails. Do not lock
an asset because one portrait looks good.

## Output and gate

Save each authority record at `04_assets/records/<asset-id>/asset.json`; treat
`04_assets/asset-index.json` as derived. Validate with `scripts/validate_project.py`,
then use `scripts/prepare_review.py` with subject type `ASSET`, the exact project/media
hashes, and `--apply`. It creates the central `USER_REVIEW_REQUIRED` request; show the
immutable master plus crop/motion evidence and stop. From that moment the master and
hashed `asset.json` evidence are immutable. Only the central approval is decision state.
ASSET_LOCK closes only when every current `storyboard.asset_plan` item has one matching
central `USER_APPROVED` ASSET decision and every extra candidate has a terminal central
`REJECTED`, `SUPERSEDED`, or `EXCLUDED_FROM_INPUTS` decision. Approval evidence binds
the exact master, immutable `asset.json`, and current visual-bible path/hash. Do not
edit a reviewed candidate; changed content or metadata requires a new `asset_id`.
A look or approved-asset change invalidates dependent shots and later gates per
`references/12-invalidation-and-revisions.md`. Store remote Element IDs only after verification.
