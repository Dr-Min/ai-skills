from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from beatcut_core import (
    analyze_audio,
    compute_stft_attack,
    decode_audio,
    export_capcut_json,
    load_plan,
    locate_ffmpeg,
    parse_hint,
    render_package,
    validate_capcut_stage,
    validate_plan,
    verify_package,
    write_json,
)


def ui_font(size: int, bold: bool = False):
    candidates = [
        Path(r"C:\Windows\Fonts\malgunbd.ttf") if bold else Path(r"C:\Windows\Fonts\malgun.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf") if bold else Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def palette(values: np.ndarray) -> np.ndarray:
    stops = np.array(
        [[5, 12, 22], [16, 37, 74], [26, 92, 136], [69, 202, 215], [255, 200, 87], [255, 248, 224]],
        dtype=np.float32,
    )
    scaled = np.clip(values, 0, 1) * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.int32)
    upper = np.minimum(lower + 1, len(stops) - 1)
    mix = (scaled - lower)[..., None]
    return (stops[lower] * (1 - mix) + stops[upper] * mix).astype(np.uint8)


def spectrogram_image(spectrum, freqs, times, start, end, width, height):
    tm = (times >= start) & (times <= end)
    fm = (freqs >= 0) & (freqs <= 12000)
    data = 20 * np.log10(spectrum[tm][:, fm] + 1e-6)
    low, high = np.percentile(data, [12, 99.4])
    norm = np.clip((data - low) / max(1e-9, high - low), 0, 1)
    return Image.fromarray(palette(np.flipud(norm.T)), "RGB").resize((width, height), Image.Resampling.BILINEAR)


def draw_dashed(draw, x, y0, y1, color, width=4, dash=10):
    y = y0
    while y < y1:
        draw.line((x, y, x, min(y + dash, y1)), fill=color, width=width)
        y += dash * 2


def render_diagnostic(audio_path: Path, plan_path: Path, output: Path, ffmpeg_path: Path) -> None:
    plan = load_plan(plan_path)
    duration = float(plan["timeline"]["duration_seconds"])
    fps = int(plan["timeline"]["fps"])
    audio, rate = decode_audio(audio_path, ffmpeg_path, duration)
    spectrum, freqs, times, attack = compute_stft_attack(audio, rate)

    bg, panel, ink, muted, grid = "#071018", "#0d1923", "#eef7fb", "#9db0be", "#29404d"
    cut_color, release_color, candidate_color = "#65e6ff", "#ff6b7a", "#ffc857"
    width = 2600
    zoom_count = min(4, len(plan["windows"]))
    height = 1040 + zoom_count * 520
    canvas = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(canvas)
    draw.text((85, 52), "음악 공격음 · 컷 타임라인 진단", font=ui_font(48, True), fill=ink)
    draw.text(
        (85, 118),
        f"0–12kHz 스펙트로그램 · 공격음 180Hz–12kHz · BPM {plan['analysis']['estimated_bpm']:.2f} · {fps}fps",
        font=ui_font(27), fill=muted,
    )
    draw.text((85, 163), "청록=실제 컷 프레임  빨강 점선=제안 복귀  노랑 점선=후속 후보", font=ui_font(27), fill=muted)

    left, top, plot_w, plot_h = 120, 245, 2360, 500
    draw.rounded_rectangle((70, 210, 2530, 890), radius=20, fill=panel)
    spec = spectrogram_image(spectrum, freqs, times, 0, duration, plot_w, plot_h)
    canvas.paste(spec, (left, top))
    draw = ImageDraw.Draw(canvas)
    for khz in (0, 3, 6, 9, 12):
        y = top + plot_h - int(khz / 12 * plot_h)
        draw.line((left, y, left + plot_w, y), fill=grid, width=1)
        draw.text((left - 56, y - 13), f"{khz}k", font=ui_font(22), fill=muted)
    for second in range(0, int(math.ceil(duration)) + 1):
        x = left + int(second / duration * plot_w)
        draw.line((x, top, x, top + plot_h), fill=grid, width=1)
        draw.text((x - 13, top + plot_h + 9), f"{second}", font=ui_font(20), fill=muted)
    for cut in plan["timeline"]["cuts"]:
        x = left + int(float(cut["render_time"]) / duration * plot_w)
        draw.line((x, top, x, top + plot_h + 85), fill=cut_color, width=2)
    for window in plan["windows"]:
        x = left + int(float(window["release_render_time"]) / duration * plot_w)
        draw_dashed(draw, x, top, top + plot_h + 85, release_color, width=4)

    attack_norm = attack / max(1e-9, float(np.percentile(attack, 99.5)))
    attack_norm = np.clip(attack_norm, 0, 1)
    points = []
    for time_value, value in zip(times, attack_norm):
        if time_value > duration:
            break
        points.append((left + int(time_value / duration * plot_w), top + plot_h + 105 - int(value * 70)))
    if len(points) > 1:
        draw.line(points, fill="#c0f6ff", width=2)
    draw.text((left, top + plot_h + 118), "공격음 변화량", font=ui_font(22), fill=muted)

    card_top = 960
    candidates = plan["analysis"]["candidate_times"]
    for index, window in enumerate(plan["windows"][:zoom_count]):
        card_y = card_top + index * 520
        draw.rounded_rectangle((70, card_y, 2530, card_y + 465), radius=20, fill=panel)
        start = max(0.0, float(window["release_detected"]) - 0.65)
        end = min(duration, float(window["release_detected"]) + 0.65)
        draw.text((110, card_y + 24), f"구간 {index + 1} 종료 확대", font=ui_font(31, True), fill=ink)
        zleft, ztop, zw, zh = 120, card_y + 85, 1850, 280
        canvas.paste(spectrogram_image(spectrum, freqs, times, start, end, zw, zh), (zleft, ztop))
        draw = ImageDraw.Draw(canvas)
        for cut in window["cuts"]:
            if start <= float(cut["render_time"]) <= end:
                x = zleft + int((float(cut["render_time"]) - start) / (end - start) * zw)
                draw.line((x, ztop, x, ztop + zh), fill=cut_color, width=3)
        release_x = zleft + int((float(window["release_render_time"]) - start) / (end - start) * zw)
        draw_dashed(draw, release_x, ztop, ztop + zh, release_color, width=5)
        next_candidate = next((item for item in candidates if float(item["time"]) > float(window["release_detected"])), None)
        if next_candidate and float(next_candidate["time"]) <= end:
            x = zleft + int((float(next_candidate["time"]) - start) / (end - start) * zw)
            draw_dashed(draw, x, ztop, ztop + zh, candidate_color, width=3, dash=7)
        draw.text(
            (2010, card_y + 100),
            f"검출 복귀\n{window['release_detected']:.3f}s\n\n실제 프레임\n{window['release_render_time']:.3f}s\n\n근거\n{window['release_reason']}",
            font=ui_font(25), fill=release_color, spacing=7,
        )
        draw.text((120, card_y + 382), f"탐색 힌트: {window['hint']}  ·  컷 {len(window['cuts'])}개", font=ui_font(23), fill=muted)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze music and export beat-synced edit timelines.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--ffmpeg")

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--audio", type=Path, required=True)
    analyze.add_argument("--duration", type=float)
    analyze.add_argument("--hint", action="append", default=[])
    analyze.add_argument("--fps", type=int, default=30)
    analyze.add_argument("--zoom", choices=["off", "subtle", "medium", "strong"], default="off")
    analyze.add_argument("--color", choices=["off", "cycle"], default="off")
    analyze.add_argument("--mode", choices=["fill-only", "strong-beat", "hybrid"], default="fill-only")
    analyze.add_argument("--ffmpeg")
    analyze.add_argument("--output", type=Path, required=True)

    visualize = sub.add_parser("visualize")
    visualize.add_argument("--audio", type=Path, required=True)
    visualize.add_argument("--plan", type=Path, required=True)
    visualize.add_argument("--output", type=Path, required=True)
    visualize.add_argument("--ffmpeg")

    package = sub.add_parser("render-package")
    package.add_argument("--plan", type=Path, required=True)
    package.add_argument("--audio", type=Path, required=True)
    package.add_argument("--media", nargs="+", type=Path, required=True)
    package.add_argument("--output-dir", type=Path, required=True)
    package.add_argument("--width", type=int, default=1280)
    package.add_argument("--height", type=int, default=720)
    package.add_argument("--diagnostic", type=Path)
    package.add_argument("--ffmpeg")

    capcut = sub.add_parser("export-capcut-json")
    capcut.add_argument("--package-dir", type=Path, required=True)
    capcut.add_argument("--template-draft", type=Path, required=True)
    capcut.add_argument("--output-draft", type=Path, required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--package-dir", type=Path)
    verify.add_argument("--capcut-draft", type=Path)

    validate = sub.add_parser("validate-plan")
    validate.add_argument("--plan", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        try:
            ffmpeg = locate_ffmpeg(args.ffmpeg)
            import numpy
            import PIL

            print(json.dumps({"ok": True, "ffmpeg": str(ffmpeg), "numpy": numpy.__version__, "pillow": PIL.__version__}, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1

    if args.command == "analyze":
        ffmpeg = locate_ffmpeg(args.ffmpeg)
        hints = [parse_hint(value) for value in args.hint]
        plan, _ = analyze_audio(args.audio, ffmpeg, args.duration, hints, args.fps, args.zoom, args.color, args.mode)
        write_json(args.output, plan)
        print(json.dumps({"output": str(args.output), "bpm": plan["analysis"]["estimated_bpm"], "windows": len(plan["windows"]), "cuts": len(plan["timeline"]["cuts"]), "status": plan["status"]}, ensure_ascii=False))
        return 0

    if args.command == "visualize":
        ffmpeg = locate_ffmpeg(args.ffmpeg)
        render_diagnostic(args.audio, args.plan, args.output, ffmpeg)
        print(json.dumps({"output": str(args.output)}, ensure_ascii=False))
        return 0

    if args.command == "render-package":
        ffmpeg = locate_ffmpeg(args.ffmpeg)
        output = render_package(
            args.plan,
            args.audio,
            args.media,
            args.output_dir,
            ffmpeg,
            args.width,
            args.height,
            args.diagnostic,
        )
        print(json.dumps({"output_dir": str(output)}, ensure_ascii=False))
        return 0

    if args.command == "export-capcut-json":
        output = export_capcut_json(args.package_dir, args.template_draft, args.output_draft)
        print(json.dumps({"output_draft": str(output), "verified": True, "opened_in_capcut": False}, ensure_ascii=False))
        return 0

    if args.command == "verify":
        if not args.package_dir and not args.capcut_draft:
            raise ValueError("Provide --package-dir or --capcut-draft")
        result = {}
        if args.package_dir:
            result["package"] = verify_package(args.package_dir)
        if args.capcut_draft:
            result["capcut_draft"] = validate_capcut_stage(args.capcut_draft)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(section.get("ok") for section in result.values()) else 1

    if args.command == "validate-plan":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        errors = validate_plan(plan)
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 1
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
