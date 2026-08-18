#!/usr/bin/env python3
"""Build a deterministic contact sheet from review-frame images."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
import uuid
from pathlib import Path
from typing import Iterable

from _cinema_common import commit_temporary_file, contains_name_redirecting_component, issue

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # Gracefully reported by make_contact_sheet.
    Image = ImageDraw = ImageFont = ImageOps = None


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
MAX_CANVAS_PIXELS = 64_000_000


def _layout_error(
    columns: object,
    thumb_size: object,
    padding: object,
    label_height: object,
) -> dict | None:
    def integer(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    if not integer(columns) or not 1 <= columns <= 20:
        return issue("INVALID_LAYOUT", "columns must be an integer between 1 and 20")
    if (
        not isinstance(thumb_size, (tuple, list))
        or len(thumb_size) != 2
        or not all(integer(value) for value in thumb_size)
    ):
        return issue("INVALID_LAYOUT", "thumb_size must contain two integer dimensions")
    thumb_width, thumb_height = thumb_size
    if thumb_width < 16 or thumb_height < 16:
        return issue("INVALID_LAYOUT", "Thumbnail dimensions must be at least 16px")
    if not integer(padding) or padding < 0:
        return issue("INVALID_LAYOUT", "padding must be a non-negative integer")
    if not integer(label_height) or label_height < 0:
        return issue("INVALID_LAYOUT", "label_height must be a non-negative integer")
    return None


def _discover(inputs: Iterable[str | Path]) -> tuple[list[Path], list[Path], dict | None]:
    discovered: dict[Path, None] = {}
    monitored_paths: list[Path] = []
    for raw in inputs:
        lexical = Path(raw).expanduser()
        monitored_paths.append(lexical)
        if contains_name_redirecting_component(lexical):
            return (
                [],
                monitored_paths,
                issue(
                    "UNSAFE_INPUT_PATH",
                    f"Input path must not contain a symlink or name-redirection: {lexical}",
                ),
            )
        path = lexical.resolve()
        if path.is_dir():
            for candidate in path.iterdir():
                if candidate.suffix.casefold() not in IMAGE_SUFFIXES:
                    continue
                monitored_paths.append(candidate)
                if contains_name_redirecting_component(candidate):
                    return (
                        [],
                        monitored_paths,
                        issue(
                            "UNSAFE_INPUT_PATH",
                            f"Discovered image path must not contain a symlink or name-redirection: {candidate}",
                        ),
                    )
                if candidate.is_file():
                    discovered[candidate.resolve()] = None
        elif path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES:
            discovered[path] = None
    return (
        sorted(
            discovered,
            key=lambda value: (value.name.casefold(), value.as_posix().casefold()),
        ),
        monitored_paths,
        None,
    )


def _draw_label(draw, position: tuple[int, int], text: str, fill: tuple[int, int, int], font) -> None:
    try:
        draw.text(position, text, fill=fill, font=font)
    except UnicodeEncodeError:
        draw.text(position, text.encode("ascii", "replace").decode("ascii"), fill=fill, font=font)


def _output_error(
    raw_output: Path,
    output: Path,
    images: Iterable[Path],
    *,
    force: bool,
) -> dict | None:
    if contains_name_redirecting_component(raw_output) or contains_name_redirecting_component(output):
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Output path must not contain a symlink or name-redirection: {raw_output}",
        )
    if not os.path.lexists(output):
        return None
    try:
        if not output.is_file():
            return issue(
                "UNSAFE_OUTPUT_PATH",
                f"Output target must be a regular file: {output}",
            )
        if any(os.path.samefile(output, image) for image in images):
            return issue(
                "OUTPUT_ALIASES_INPUT",
                "Output must not alias an input image, even with --force",
            )
    except OSError as exc:
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Output target could not be inspected safely: {exc}",
        )
    if not force:
        return issue("OUTPUT_EXISTS", f"Refusing to overwrite existing file: {output}")
    return None


def _temporary_output_error(temporary: Path, images: Iterable[Path]) -> dict | None:
    if contains_name_redirecting_component(temporary):
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Temporary output contains a symlink or name-redirection: {temporary}",
        )
    try:
        metadata = os.lstat(temporary)
        if not stat.S_ISREG(metadata.st_mode) or getattr(metadata, "st_nlink", 1) != 1:
            return issue(
                "UNSAFE_OUTPUT_PATH",
                f"Temporary output must be a single-link regular file: {temporary}",
            )
        if any(os.path.samefile(temporary, image) for image in images):
            return issue(
                "OUTPUT_ALIASES_INPUT",
                "Temporary output must not alias an input image",
            )
    except OSError as exc:
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Temporary output could not be inspected safely: {exc}",
        )
    return None


def make_contact_sheet(
    inputs: Iterable[str | Path],
    output_path: str | Path,
    *,
    columns: int = 4,
    thumb_size: tuple[int, int] = (320, 180),
    padding: int = 12,
    label_height: int = 24,
    labels: bool = True,
    force: bool = False,
) -> dict:
    """Create a contact sheet atomically and refuse implicit overwrites."""

    raw_inputs = [Path(raw).expanduser() for raw in inputs]
    for raw_input in raw_inputs:
        if contains_name_redirecting_component(raw_input):
            return {
                "ok": False,
                "errors": [
                    issue(
                        "UNSAFE_INPUT_PATH",
                        f"Input path must not contain a symlink or name-redirection: {raw_input}",
                    )
                ],
                "inputs": [],
            }
    raw_output = Path(output_path).expanduser()
    if contains_name_redirecting_component(raw_output):
        return {
            "ok": False,
            "errors": [
                issue(
                    "UNSAFE_OUTPUT_PATH",
                    f"Output path must not contain a symlink or name-redirection: {raw_output}",
                )
            ],
            "inputs": [],
        }
    output = raw_output.resolve()
    if Image is None:
        return {"ok": False, "errors": [issue("PILLOW_NOT_FOUND", "Install Pillow to create contact sheets")], "inputs": []}
    layout_error = _layout_error(columns, thumb_size, padding, label_height)
    if layout_error is not None:
        return {"ok": False, "errors": [layout_error], "inputs": []}
    thumb_width, thumb_height = thumb_size
    try:
        images, monitored_inputs, discovery_error = _discover(raw_inputs)
    except (OSError, UnicodeError) as exc:
        return {
            "ok": False,
            "errors": [
                issue(
                    "INPUT_DISCOVERY_FAILED",
                    f"Input images could not be discovered safely: {exc}",
                )
            ],
            "inputs": [],
        }
    if discovery_error is not None:
        return {"ok": False, "errors": [discovery_error], "inputs": []}
    if not images:
        return {"ok": False, "errors": [issue("NO_IMAGES", "No supported image files were found")], "inputs": []}
    output_error = _output_error(raw_output, output, images, force=force)
    if output_error is not None:
        return {
            "ok": False,
            "errors": [output_error],
            "inputs": [str(path) for path in images],
        }
    rows = math.ceil(len(images) / columns)
    effective_label_height = label_height if labels else 0
    canvas_width = columns * thumb_width + (columns + 1) * padding
    canvas_height = rows * (thumb_height + effective_label_height) + (rows + 1) * padding
    canvas_pixels = canvas_width * canvas_height
    if (
        canvas_width < 1
        or canvas_height < 1
        or canvas_pixels > MAX_CANVAS_PIXELS
    ):
        return {
            "ok": False,
            "errors": [
                issue(
                    "INVALID_LAYOUT",
                    f"Contact-sheet canvas exceeds the {MAX_CANVAS_PIXELS}-pixel safety limit",
                )
            ],
            "inputs": [str(path) for path in images],
        }
    try:
        sheet = Image.new("RGB", (canvas_width, canvas_height), (18, 18, 20))
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()
    except (MemoryError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "errors": [issue("INVALID_LAYOUT", f"Contact-sheet canvas could not be allocated: {exc}")],
            "inputs": [str(path) for path in images],
        }
    try:
        for index, path in enumerate(images):
            row, column = divmod(index, columns)
            x = padding + column * (thumb_width + padding)
            y = padding + row * (thumb_height + effective_label_height + padding)
            with Image.open(path) as source:
                max_pixels = getattr(Image, "MAX_IMAGE_PIXELS", None)
                if max_pixels is not None and source.width * source.height > max_pixels:
                    raise ValueError(
                        f"Image dimensions exceed the safe pixel limit: {source.width}x{source.height}"
                    )
                source = ImageOps.exif_transpose(source).convert("RGB")
                preview = ImageOps.contain(source, (thumb_width, thumb_height), Image.Resampling.LANCZOS)
            preview_x = x + (thumb_width - preview.width) // 2
            preview_y = y + (thumb_height - preview.height) // 2
            sheet.paste(preview, (preview_x, preview_y))
            if labels:
                _draw_label(draw, (x, y + thumb_height + 3), path.name, (225, 225, 228), font)
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        sheet.close()
        return {"ok": False, "errors": [issue("IMAGE_READ_FAILED", str(exc))], "inputs": [str(path) for path in images]}
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sheet.close()
        return {
            "ok": False,
            "errors": [issue("OUTPUT_WRITE_FAILED", str(exc))],
            "inputs": [str(path) for path in images],
        }
    suffix = output.suffix if output.suffix else ".png"
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp{suffix}")
    try:
        sheet.save(temporary)
        temporary_error = _temporary_output_error(temporary, images)
        if temporary_error is not None:
            return {
                "ok": False,
                "errors": [temporary_error],
                "inputs": [str(path) for path in images],
            }
        if contains_name_redirecting_component(temporary) or not temporary.is_file():
            return {
                "ok": False,
                "errors": [
                    issue(
                        "UNSAFE_OUTPUT_PATH",
                        f"Temporary output is not a safe regular file: {temporary}",
                    )
                ],
                "inputs": [str(path) for path in images],
            }
        try:
            if any(os.path.samefile(temporary, image) for image in images):
                return {
                    "ok": False,
                    "errors": [
                        issue(
                            "OUTPUT_ALIASES_INPUT",
                            "Temporary output must not alias an input image",
                        )
                    ],
                    "inputs": [str(path) for path in images],
                }
            with temporary.open("r+b") as generated:
                generated.flush()
                os.fsync(generated.fileno())
        except OSError as exc:
            return {
                "ok": False,
                "errors": [
                    issue(
                        "OUTPUT_WRITE_FAILED",
                        f"Temporary output could not be synchronized safely: {exc}",
                    )
                ],
                "inputs": [str(path) for path in images],
            }
        for monitored_input in monitored_inputs:
            if contains_name_redirecting_component(monitored_input):
                return {
                    "ok": False,
                    "errors": [
                        issue(
                            "UNSAFE_INPUT_PATH",
                            f"Input path became unsafe before publish: {monitored_input}",
                        )
                    ],
                    "inputs": [str(path) for path in images],
                }
        output_error = _output_error(raw_output, output, images, force=force)
        if output_error is not None:
            return {
                "ok": False,
                "errors": [output_error],
                "inputs": [str(path) for path in images],
            }
        temporary_error = _temporary_output_error(temporary, images)
        if temporary_error is not None:
            return {
                "ok": False,
                "errors": [temporary_error],
                "inputs": [str(path) for path in images],
            }
        if contains_name_redirecting_component(temporary) or not temporary.is_file():
            return {
                "ok": False,
                "errors": [
                    issue(
                        "UNSAFE_OUTPUT_PATH",
                        f"Temporary output is not a safe regular file: {temporary}",
                    )
                ],
                "inputs": [str(path) for path in images],
            }
        try:
            if any(os.path.samefile(temporary, image) for image in images):
                return {
                    "ok": False,
                    "errors": [
                        issue(
                            "OUTPUT_ALIASES_INPUT",
                            "Temporary output must not alias an input image",
                        )
                    ],
                    "inputs": [str(path) for path in images],
                }
        except OSError as exc:
            return {
                "ok": False,
                "errors": [
                    issue(
                        "UNSAFE_OUTPUT_PATH",
                        f"Temporary output could not be inspected safely: {exc}",
                    )
                ],
                "inputs": [str(path) for path in images],
            }
        commit_temporary_file(temporary, output, force=force)
    except (OSError, ValueError, MemoryError) as exc:
        return {"ok": False, "errors": [issue("OUTPUT_WRITE_FAILED", str(exc))], "inputs": [str(path) for path in images]}
    finally:
        temporary.unlink(missing_ok=True)
        sheet.close()
    return {
        "ok": True,
        "output": str(output),
        "inputs": [str(path) for path in images],
        "grid": {"columns": columns, "rows": rows, "width": canvas_width, "height": canvas_height},
        "errors": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--thumb-width", type=int, default=320)
    parser.add_argument("--thumb-height", type=int, default=180)
    parser.add_argument("--no-labels", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = make_contact_sheet(
        args.inputs,
        args.output,
        columns=args.columns,
        thumb_size=(args.thumb_width, args.thumb_height),
        labels=not args.no_labels,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
