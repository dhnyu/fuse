#!/usr/bin/env python3
"""Prototype fixed semantic Street View panorama crops.

This script intentionally treats each Google Street View panorama as a canonical
2D image layout. It performs direct rectangular extraction only: no spherical
projection, no cubemap conversion, no road-bearing alignment, and no horizontal
wraparound.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "fuse_paths.py").exists():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO_ROOT / "src"))

from fuse_paths import data_dir, relative_to_repo_or_data  # noqa: E402


VIEW_ORDER = ("left", "front", "right", "rear")
VIEW_COLORS = {
    "left": (43, 131, 186),
    "front": (26, 152, 80),
    "right": (245, 131, 32),
    "rear": (215, 48, 39),
}
DEFAULT_LIMIT = 3
JPEG_QUALITY = 92


@dataclass(frozen=True)
class CropWindow:
    label: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float


SEMANTIC_WINDOWS = (
    CropWindow("left", 0.05, 0.35, 0.30, 0.90),
    CropWindow("front", 0.25, 0.55, 0.30, 0.90),
    CropWindow("right", 0.45, 0.75, 0.30, 0.90),
    CropWindow("rear", 0.65, 0.95, 0.30, 0.90),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=data_dir("streetview_panoramas_raw"))
    parser.add_argument("--output-dir", type=Path, default=data_dir("streetview_debug", create=True) / "semantic_crops")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of sorted toy panoramas to process.")
    parser.add_argument("--pano-id", action="append", default=[], help="Specific pano_id stem to process. May be repeated.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing debug outputs.")
    return parser.parse_args()


def image_paths(input_dir: Path, limit: int, pano_ids: list[str]) -> list[Path]:
    if pano_ids:
        paths = [input_dir / f"{pano_id}.jpg" for pano_id in pano_ids]
        missing = [path for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing requested panorama(s): " + ", ".join(str(path) for path in missing))
        return paths
    paths = sorted([*input_dir.glob("*.jpg"), *input_dir.glob("*.jpeg")])
    if limit > 0:
        paths = paths[:limit]
    return paths


def normalized_to_pixel_box(window: CropWindow, width: int, height: int) -> tuple[int, int, int, int]:
    left = round(window.x_min * width)
    right = round(window.x_max * width)
    top = round((1.0 - window.y_max) * height)
    bottom = round((1.0 - window.y_min) * height)
    return left, top, right, bottom


def load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, fill: tuple[int, int, int]) -> None:
    padding = 5
    bbox = draw.textbbox(xy, text, font=font)
    background = (bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding)
    draw.rectangle(background, fill=(255, 255, 255), outline=fill, width=2)
    draw.text(xy, text, fill=(20, 20, 20), font=font)


def save_crop_overlay(panorama: Image.Image, output_path: Path) -> None:
    overlay = panorama.copy()
    draw = ImageDraw.Draw(overlay)
    font = load_font(max(14, panorama.width // 95))
    for window in SEMANTIC_WINDOWS:
        color = VIEW_COLORS[window.label]
        box = normalized_to_pixel_box(window, *panorama.size)
        draw.rectangle(box, outline=color, width=max(4, panorama.width // 400))
        label_xy = (box[0] + 8, box[1] + 8)
        draw_label(draw, label_xy, window.label, font, color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, format="JPEG", quality=JPEG_QUALITY)


def paste_labeled_image(
    sheet: Image.Image,
    image: Image.Image,
    xy: tuple[int, int],
    label: str,
    cell_size: tuple[int, int],
    font: ImageFont.ImageFont,
) -> None:
    cell_w, cell_h = cell_size
    fitted = image.copy()
    fitted.thumbnail((cell_w, cell_h - 34), Image.Resampling.LANCZOS)
    x = xy[0] + (cell_w - fitted.width) // 2
    y = xy[1] + 30 + (cell_h - 34 - fitted.height) // 2
    sheet.paste(fitted, (x, y))
    draw = ImageDraw.Draw(sheet)
    draw.text((xy[0] + 8, xy[1] + 6), label, fill=(25, 25, 25), font=font)


def save_contact_sheet(pano_id: str, panorama: Image.Image, crop_paths: dict[str, Path], output_path: Path) -> None:
    cell_w = 360
    crop_cell_h = 300
    pano_h = 260
    margin = 16
    sheet_w = cell_w * 4 + margin * 2
    sheet_h = pano_h + crop_cell_h + margin * 3
    sheet = Image.new("RGB", (sheet_w, sheet_h), (245, 245, 245))
    font = load_font(18)

    pano_preview = panorama.copy()
    pano_preview.thumbnail((sheet_w - margin * 2, pano_h - 34), Image.Resampling.LANCZOS)
    paste_labeled_image(
        sheet,
        pano_preview,
        (margin, margin),
        f"original panorama: {pano_id}",
        (sheet_w - margin * 2, pano_h),
        font,
    )

    for i, label in enumerate(VIEW_ORDER):
        crop = Image.open(crop_paths[label]).convert("RGB")
        paste_labeled_image(
            sheet,
            crop,
            (margin + i * cell_w, margin * 2 + pano_h),
            label,
            (cell_w, crop_cell_h),
            font,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=JPEG_QUALITY)


def generate_for_panorama(path: Path, output_dir: Path, overwrite: bool) -> dict[str, object]:
    pano_id = path.stem
    crop_dir = output_dir / "crops"
    overlay_dir = output_dir / "overlays"
    sheet_dir = output_dir / "contact_sheets"
    crop_paths = {label: crop_dir / f"{pano_id}_{label}.jpg" for label in VIEW_ORDER}
    overlay_path = overlay_dir / f"{pano_id}_semantic_crop_overlay.jpg"
    sheet_path = sheet_dir / f"{pano_id}_semantic_crop_contact_sheet.jpg"

    required_outputs = [*crop_paths.values(), overlay_path, sheet_path]
    if not overwrite and all(out.exists() and out.stat().st_size > 0 for out in required_outputs):
        return {
            "pano_id": pano_id,
            "source_path": str(path),
            "outputs_reused": True,
            "crop_paths": {label: str(crop_paths[label]) for label in VIEW_ORDER},
            "overlay_path": str(overlay_path),
            "contact_sheet_path": str(sheet_path),
        }

    panorama = Image.open(path).convert("RGB")
    crop_dir.mkdir(parents=True, exist_ok=True)
    for window in SEMANTIC_WINDOWS:
        crop = panorama.crop(normalized_to_pixel_box(window, *panorama.size))
        crop.save(crop_paths[window.label], format="JPEG", quality=JPEG_QUALITY)
    save_crop_overlay(panorama, overlay_path)
    save_contact_sheet(pano_id, panorama, crop_paths, sheet_path)
    return {
        "pano_id": pano_id,
        "source_path": str(path),
        "outputs_reused": False,
        "panorama_size": list(panorama.size),
        "crop_size": list(Image.open(crop_paths["front"]).size),
        "crop_paths": {label: str(crop_paths[label]) for label in VIEW_ORDER},
        "overlay_path": str(overlay_path),
        "contact_sheet_path": str(sheet_path),
    }


def write_layout_manifest(records: list[dict[str, object]], output_dir: Path) -> Path:
    manifest = {
        "description": "Fixed rectangular semantic crop-window prototype. No spherical projection or wraparound.",
        "coordinate_system": {
            "x_axis": "left edge = 0, right edge = 1",
            "y_axis": "bottom edge = 0, top edge = 1",
        },
        "windows": [asdict(window) for window in SEMANTIC_WINDOWS],
        "records": records,
    }
    path = output_dir / "semantic_crop_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    paths = image_paths(args.input_dir.expanduser(), args.limit, args.pano_id)
    if not paths:
        print(f"No panorama JPGs found in {args.input_dir}", file=sys.stderr)
        return 1

    records = [generate_for_panorama(path, args.output_dir.expanduser(), args.overwrite) for path in paths]
    manifest_path = write_layout_manifest(records, args.output_dir.expanduser())

    print("GSV semantic crop prototype complete")
    print(f"panoramas_processed: {len(records)}")
    print(f"output_dir: {relative_to_repo_or_data(args.output_dir.expanduser())}")
    print(f"manifest: {relative_to_repo_or_data(manifest_path)}")
    for record in records:
        print(f"pano_id: {record['pano_id']}")
        print(f"  overlay: {relative_to_repo_or_data(Path(str(record['overlay_path'])))}")
        print(f"  contact_sheet: {relative_to_repo_or_data(Path(str(record['contact_sheet_path'])))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
