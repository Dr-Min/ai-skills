# CapCut JSON staging

CapCut draft JSON is undocumented and version-specific. The verified local shape for CapCut Desktop 9.1.0.3879 used `draft_content.json` schema version `360000` and new-version label `179.0.0`; treat these as observed values, not universal constants.

## Template requirement

Use a copied template draft that contains:

- one ordinary local video clip on a video track;
- one ordinary local audio clip on an audio track;
- no cloud-only, Pro-only, or missing media dependencies.

If multiple local templates qualify, show their draft name, last modification time, content schema version, and CapCut new-version label. Ask the user which draft to copy; do not silently choose the newest live project.

The adapter clones the template's material and segment prototypes, assigns new IDs, points materials to package clips, and writes exact target/source ranges.

## Safe sequence

1. Save and close CapCut before any live-root install.
2. Copy the template draft folder to a new output folder.
3. Keep the template untouched.
4. Rewrite the copy's `draft_content.json`, backup, temporary mirror when present, and `draft_meta_info.json` paths.
5. Validate JSON parsing, material references, segment order, gaps, overlaps, duration, and media existence.
6. Only then copy the staged folder into CapCut's draft root if the user explicitly requests installation.
7. Open CapCut and verify real playback before calling integration complete.

## Supported v1 behavior

- Populate a video track with ordered rendered package clips.
- Populate one continuous audio track.
- Preserve exact 30 fps timing from the approved package.
- Keep zoom and color treatments baked into clips for deterministic parity.
- Keep clip order and cut timing editable in CapCut. Effects are not native editable keyframes in v1.

Native CapCut transition presets, filters, and editable effect keyframes require sampled schemas from the active CapCut version and are not part of the safe v1 contract.
