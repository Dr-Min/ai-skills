# Analysis algorithm

## Signal path

1. Decode audio to mono PCM at 44.1 kHz.
2. Compute a 1024-sample Hann-window STFT with a 128-sample hop.
3. Limit attack analysis to 180 Hz through 12 kHz.
4. Combine positive log-spectral flux with positive RMS change.
5. Smooth with a three-point kernel and select local maxima.
6. Apply non-maximum suppression with a default 70 ms minimum spacing.
7. Build active regions from approximate user hints or sustained transient-density runs.

## Boundary policy

- A closed hint such as `4:6` means search around 4 and 6 seconds. It does not authorize hard boundaries at 4.000 and 6.000.
- Snap the start to a nearby attack after a separating gap or to the strongest nearby onset.
- For a closed hint, choose the real attack nearest the first global beat at or after the end hint.
- For an open hint such as `9:`, find the dense run and end at the first real attack after the separating gap.
- If no real attack supports a release, hold the current visual and warn instead of resetting silently.

## Frame policy

Detected audio times are continuous. Video cuts must land on frames:

```text
render_frame = ceil(detected_seconds * fps)
render_time = render_frame / fps
```

Keep both values in output so the user can distinguish audio evidence from the executable edit.

## Effect policy

- `zoom=off|subtle|medium|strong` maps to 0%, 3%, 6%, and 10%.
- `color=off|cycle` cycles restrained contrast/saturation treatments on cut segments.
- Do not enable white flash by default.
- Effects may be baked into split clips. The CapCut JSON mode places those exact clips for deterministic parity.
