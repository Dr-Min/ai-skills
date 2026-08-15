# Handoff to sync-cuts-to-music

Use the separate `sync-cuts-to-music` skill only after the audio file and approved raw
source policy are known.

## Input contract

- immutable audio path, hash, and rights status;
- rough musical hints from the user;
- approved source-library IDs;
- story/editorial constraints and sections that must remain uncut.

## Output contract

Import a `music_events.json` containing event IDs, detected/transient time, confidence,
event type, suggested cut density, and the audio hash. Treat every event as an edit
proposal, not a command.

The editor decides cuts from story, action, gaze, emotion, and music together. Never
accelerate or retime a raw source merely to hit a detected event. Store exact cuts as
frames or rational time in `timeline.json` after approval.
