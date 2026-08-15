# 10 — Acting, dialogue, and voice continuity

Acting is behavior under pressure, not an emotion label. Give every visible person an
objective, interference, and changing physical tactics. Let emotion emerge from that
struggle.

## Character master profile

Create one reusable behavior profile before shooting dialogue:

- body build, posture, center of gravity, and dominant rhythm;
- habitual hand use, self-touch, gaze, blink, breath, and stillness;
- status behavior and how it breaks under pressure;
- how the character listens, hides information, changes tactic, and recovers;
- fixed voice descriptor: register, tempo, accent, manner, pronunciation.

Keep the voice descriptor verbatim across generations. Rewrite the acting profile for
the current moment; do not paste the entire biography into every shot.

Treat the fixed descriptor and approved sample as a `VOICE` asset when dialogue spans
multiple shots. Version and hash the exact descriptor text and sample bytes, approve
them through the normal ASSET decision, and bind that current voice asset in every
dependent shot. A changed descriptor is a new candidate, not an invisible prompt edit.
Every `audio.dialogue[]` line sets `voice_asset_id` to that exact `VOICE` asset, which
must also be active once in the shot's `AUDIO` role. A generic soundtrack asset does
not satisfy voice identity.
Set the VOICE asset's `lineage.parent_asset_id` to the owning character's immutable
identity asset. The line's `speaker_asset_id` must be an active `IDENTITY` or `STATE`
character, and its immutable-master identity must match that VOICE owner. Two speakers
therefore require two explicitly owned VOICE assets; an approved voice from another
character is still invalid.

## Five scene controls

For each active character, resolve:

1. **Objective** — an action verb aimed at a specific person now.
2. **Obstacle and stakes** — what blocks the objective and what failure costs.
3. **Tactic** — press, charm, shame, plead, provoke, bargain, threaten, stall, or
   another playable action.
4. **Beats** — a tactic ends when it fails, new information arrives, the objective is
   achieved, or power shifts. Make each change visible.
5. **Subtext** — what the character wants while saying something else. Show the leak
   through timing and behavior; do not label it for the audience.

Use 2–4 meaningful beat changes for a scene that can support them. A short shot may
need only one change. Do not overload the available seconds.

In an ensemble, direct one shared external event and then give each visible character
a separate task, gaze job, and physical channel. Do not prompt a group with one emotion
word and accept synchronized mannequin reactions.

## Write the body before the adjective

Translate “sad,” “angry,” “afraid,” or “shocked” into observable behavior:

- breath height and rhythm;
- jaw, cheek, nostril, brow, throat, shoulders, hands, and weight distribution;
- gaze target and the delay between eyes, head, and body;
- one visible micro-event every one or two seconds when a face would otherwise freeze;
- held tension instead of “nobody moves” or a frozen pose.

Give the hands a truthful task: repair, count, pour, clean, scroll, fold, or carry.
Stopping that task can mark the strongest event in the beat.

Use distance as drama. State measurable proximity and who closes, breaks, or refuses
the distance. Treat a change of distance as a beat change.

## Listening and reaction

- Let the listener understand before the speaker finishes; the eyes or body may react
  before the line ends.
- Give important information an assessment pause before the answer.
- Change tempo, volume, posture, or tactic in response to the partner.
- Let physical and emotional residue continue after the line and into the next clip.
- Prefer the reaction frame when it carries more story than the initiating action.

## Dialogue construction

Keep dialogue in `AUDIO`, separate from timed physical action:

```text
[NAME] voice (verbatim): "[fixed voice descriptor]."
[NAME] speaks only: "[exact scripted line]."
[physical and facial response is specified in ACTION_TIMING / CHARACTER_ACTING].
[everyone without a line remains silent].
```

Write the mix: clean close voice, matching room placement, continuous ambience, and
ambience ducking under speech when needed. Treat a written half-laugh or smile as
silent facial behavior unless sound is explicitly requested. Add pronunciation for an
unusual name rather than allowing repeated voice drift.

For clip seams, use prior dialogue only as audio context. When useful, carry the tail
of the previous line over the spatial first second or open the next generation with
the line that closed the prior clip. Do not visualize inactive people or objects merely
because the prior line mentions them.

## Performance QA

Reject or revise when:

- the character performs a generic emotion instead of pursuing an objective;
- the same tactic, tempo, posture, or expression persists across the whole scene;
- reaction begins only after every line is complete;
- breath and physical state contradict the action that just occurred;
- hands gesture theatrically without a task;
- the face freezes, over-grimaces, or looks into camera without intent;
- voice identity changes because the fixed descriptor was shortened or rewritten;
- unquoted ad-libs, chuckles, narration, subtitles, or offscreen voices appear.

When in doubt, simplify. Less acting can produce more truthful behavior.
