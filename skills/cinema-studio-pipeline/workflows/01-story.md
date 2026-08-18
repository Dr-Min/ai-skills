# 01 — Story contract

Use this gate before proposing a visual style, shot list, or generation prompt.

## Inputs

- `project.json`
- the user's idea, treatment, script, or scene request
- any fixed runtime, format, audience, rights, or delivery constraints

## Resolve

Write only decisions the user has made or explicitly approves:

- cause — what sets the story or scene in motion;
- protagonist and present condition;
- immediate goal;
- stakes and cost of failure;
- obstacle or opposing force;
- discovery or irreversible new information;
- choice and visible consequence;
- start image and end image;
- world, period, and prohibited contamination;
- dialogue, music, and rights constraints.

Stress-test every scene before approving it: name the active objective, obstacle,
playable tactic, reversal, and visible value shift. For an ensemble, add one shared
external event plus a distinct physical response channel for each active character.
Reject a scene whose situation does not change, even if its images sound attractive.

For a single shot, reduce the contract to the visible causal beat: `because X, the
character does Y, which changes Z`. Reject a shot that has movement without motive.

## Output

Fill `templates/STORY_CONTRACT.md` in the project's `01_story/` directory. Use the
stable approval subject ID `story-contract`. Before review, allocate the next unused
`vNNN`, copy identical bytes to
`01_story/history/story-contract/vNNN/STORY_CONTRACT.md`, and mirror any other
file-backed evidence below that version's `evidence/<project-relative-path>`.

Hash the current and archived copies after writing. Put both paths with the same hash
in the central `09_approvals/` record, add current/archive pairs for every supporting
file, set that approval to `USER_REVIEW_REQUIRED`, show the contract, and stop. The
contract itself has no approval-state field and must remain byte-identical through the decision.

## Gate

Advance only when a central `USER_APPROVED` decision targets the exact current
story-contract hash. A later story
revision follows the fixed-authority replacement protocol in
`references/12-invalidation-and-revisions.md`: verify the old archive, create the
successor approval as `DRAFT`, link both approvals, mark an old `USER_APPROVED` decision
`SUPERSEDED` without changing its target/evidence fields, then replace the current path.
An old `REJECTED` decision remains `REJECTED` while gaining the reciprocal successor link. The new
hash invalidates every downstream approval.
