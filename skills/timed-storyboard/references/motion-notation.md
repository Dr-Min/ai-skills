# Motion and blocking notation

## Coordinate and timing conventions

- Use integer frames as the source of truth.
- Treat `start_frame` as inclusive and `end_frame` as exclusive.
- Convert for display with `seconds = frame / fps`.
- Use normalized screen coordinates: top-left `(0, 0)`, bottom-right `(1, 1)`.
- When depth matters, use normalized camera-relative depth: `0` is nearest the camera and `1` is farthest within the planned playable space. This is ordering guidance, not measured world geometry.
- Record approximate user ranges separately as hints. Never overwrite the hint with the proposed timing.

## Line legend

Use line style plus a short label so annotations remain readable in grayscale.

| Mark | Meaning |
| --- | --- |
| solid arrow, `ACT` | character body travel |
| double-line arrow, `CAM` | camera travel or pan/tilt direction |
| dashed arrow, `GAZE` | eye-line or head-turn target |
| dotted arrow, `PROP` | independent prop travel |
| curved arrow, `ROT` | body, head, or object rotation |
| pale ghost silhouette | earlier or later body position |
| `X` | stop or final mark |
| frame-edge chevron | enter or exit frame |
| hatched overlap | planned occlusion |
| circled point, `CONTACT` | touch, impact, pickup, or handoff |

Place one legend per board page, not inside every panel.

## Action phases

Describe visible change using up to four phases:

1. `hold` - establish the initial pose or state.
2. `anticipation` - prepare the action through weight shift, gaze, breath, or reach.
3. `action` - perform the primary movement.
4. `settle` - arrive, absorb motion, and establish the closing image.

Each phase requires `start_frame`, `end_frame`, `pose`, `action`, `gaze`, and `speed`. Use concise visible language. Replace psychological verbs such as “realizes” with visible evidence such as “eyes stop on the moon; shoulders square.”

## Character blocking

For each visible character, record:

- start pose, middle pose when needed, and end pose;
- screen position and facing direction at each state;
- travel path as ordered waypoints;
- body rotation separately from travel;
- gaze target and head direction separately from body direction;
- entry/exit edge and exact frame;
- contact, pickup, release, collision, fall, or occlusion event;
- relationship distance to other characters.
- depth order and planned occlusion relative to other characters or landmarks.

For a moving subject, use at least two waypoints. Add a middle waypoint for a curve, speed change, obstacle, or important staging mark. Declare `stationary: true` when no travel occurs.

## Camera blocking

Declare one camera mode:

- `static`
- `pan`
- `tilt`
- `dolly_in`
- `dolly_out`
- `truck_left`
- `truck_right`
- `crane_up`
- `crane_down`
- `arc`
- `handheld_follow`
- `locked_subject_tracking`

Record start and end framing, angle, lens or lens feel, target, direction, speed curve, and path waypoints. A camera can be spatially stationary while panning or tilting; do not confuse orientation change with travel.

For compound moves, split the move into phases instead of writing “dynamic cinematic camera.”

## Screen direction and axis

- Record the established action axis for each scene.
- Preserve left-to-right or right-to-left travel across adjacent shots unless an axis crossing is intentional and shown.
- Add a neutral or on-axis shot when changing screen direction would otherwise read as a continuity error.
- Record which character owns screen-left and screen-right during dialogue or paired blocking.

## When one panel is insufficient

Use a three-panel micro-board when any of these is true:

- the start and end pose differ materially;
- the subject crosses another subject or an obstacle;
- the camera and subject move independently;
- an entry, exit, pickup, release, impact, or reveal occurs;
- an occlusion hides a critical transition.

Label panels `A start`, `B change`, and `C settle` with their frames or seconds. Keep the same shot ID.

## Example

```json
{
  "character_id": "woman",
  "stationary": true,
  "start_pose": "head lowered, shoulders rounded",
  "end_pose": "chin raised, shoulders squared",
  "path": [],
  "gaze": {
    "start_target": "ground",
    "end_target": "moon"
  },
  "action_phases": [
    {
      "name": "hold",
      "start_frame": 0,
      "end_frame": 24,
      "pose": "head lowered",
      "action": "remains still",
      "gaze": "ground",
      "speed": "still"
    },
    {
      "name": "action",
      "start_frame": 24,
      "end_frame": 72,
      "pose": "chin rises through a smooth arc",
      "action": "raises head",
      "gaze": "travels from ground to moon",
      "speed": "slow, easing out"
    },
    {
      "name": "settle",
      "start_frame": 72,
      "end_frame": 96,
      "pose": "chin raised, shoulders squared",
      "action": "holds final pose",
      "gaze": "moon",
      "speed": "still"
    }
  ]
}
```
