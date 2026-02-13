# -*- coding: utf-8 -*-
"""
IPE-CGA Auto-Enhancement Watcher v1.0
======================================
Drop any photo into the 'pic/' folder and it will be
automatically enhanced and saved to 'enhanced/' folder.

Usage:  python auto_enhance.py
Stop:   Press Ctrl+C

Supported formats: JPG, JPEG, PNG, BMP, TIFF, WEBP
"""

import os
import sys
import io
import time
import math
import json
import hashlib
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter, ImageStat, ImageDraw

# Force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Paths ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "pic")
OUTPUT_DIR = os.path.join(BASE_DIR, "enhanced")
TRACKER_FILE = os.path.join(BASE_DIR, ".processed_tracker.json")

SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
POLL_INTERVAL = 2  # Check every 2 seconds


# ═══════════════════════════════════════════════════════
#  ENHANCEMENT ENGINE (same professional pipeline)
# ═══════════════════════════════════════════════════════

def analyze_image(img):
    stat = ImageStat.Stat(img)
    r_mean, g_mean, b_mean = stat.mean[:3]
    r_std, g_std, b_std = stat.stddev[:3]
    overall_brightness = (r_mean + g_mean + b_mean) / 3.0
    overall_contrast = (r_std + g_std + b_std) / 3.0
    green_dominance = g_mean - ((r_mean + b_mean) / 2.0)
    return {
        "r_mean": round(r_mean, 2),
        "g_mean": round(g_mean, 2),
        "b_mean": round(b_mean, 2),
        "overall_brightness": round(overall_brightness, 2),
        "overall_contrast": round(overall_contrast, 2),
        "green_dominance": round(green_dominance, 2),
        "has_green_cast": green_dominance > 15,
        "is_underexposed": overall_brightness < 100,
        "is_overexposed": overall_brightness > 180,
    }


def correct_exposure(img, analysis):
    brightness = analysis["overall_brightness"]
    if analysis["is_underexposed"]:
        factor = min(1.0 + (128 - brightness) / 256.0, 1.35)
    elif analysis["is_overexposed"]:
        factor = max(1.0 - (brightness - 128) / 384.0, 0.85)
    else:
        factor = 1.05
    return ImageEnhance.Brightness(img).enhance(factor)


def enhance_contrast(img, analysis):
    c = analysis["overall_contrast"]
    factor = 1.30 if c < 50 else (1.18 if c < 65 else 1.08)
    return ImageEnhance.Contrast(img).enhance(factor)


def remove_green_cast(img, analysis):
    if not analysis["has_green_cast"]:
        return img
    pixels = img.load()
    w, h = img.size
    correction = min(analysis["green_dominance"] * 0.4, 25)
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y][:3]
            if g > 150 and g > r * 1.5 and g > b * 1.5:
                continue
            pixels[x, y] = (
                min(255, int(r + correction * 0.2)),
                max(0, int(g - correction * 0.6)),
                min(255, int(b + correction * 0.15))
            )
    return img


def apply_color_grading(img, analysis):
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y][:3]
            lum = r * 0.299 + g * 0.587 + b * 0.114
            if lum < 60:
                nr, ng, nb = r, min(255, g + 2), min(255, b + 5)
            elif lum < 180:
                nr, ng, nb = min(255, r + 4), min(255, g + 1), max(0, b - 3)
            else:
                nr, ng, nb = min(255, r + 3), min(255, g + 1), max(0, b - 2)
            pixels[x, y] = (nr, ng, nb)
    return img


def optimize_saturation(img, analysis):
    if analysis["has_green_cast"]:
        f = 1.10
    elif analysis["overall_brightness"] < 100:
        f = 1.20
    elif analysis["overall_brightness"] > 170:
        f = 1.05
    else:
        f = 1.15
    return ImageEnhance.Color(img).enhance(f)


def apply_sharpening(img):
    return img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=3))


def apply_vignette(img):
    w, h = img.size
    vignette = Image.new('L', (w, h), 0)
    cx, cy = w // 2, h // 2
    max_r = math.sqrt(cx**2 + cy**2)
    for y in range(h):
        for x in range(w):
            dist = math.sqrt((x - cx)**2 + (y - cy)**2)
            ratio = dist / max_r
            darkness = int(255 - (ratio - 0.6) * 160) if ratio > 0.6 else 255
            darkness = max(darkness, 140)
            vignette.putpixel((x, y), darkness)
    r, g, b = img.split()[:3]
    zero = Image.new('L', (w, h), 0)
    r = Image.composite(r, zero, vignette)
    g = Image.composite(g, zero, vignette)
    b = Image.composite(b, zero, vignette)
    return Image.merge('RGB', (r, g, b))


def apply_gradient_adjustment(img):
    def s_curve(x):
        t = x / 255.0
        return int(max(0, min(255, 0.5 * (1 + math.tanh(2.5 * (t - 0.5))) * 255)))
    lut = [s_curve(i) for i in range(256)]
    if img.mode == 'RGB':
        return img.point(lut * 3)
    elif img.mode == 'RGBA':
        r, g, b, a = img.split()
        return Image.merge('RGBA', (r.point(lut), g.point(lut), b.point(lut), a))
    return img


def enhance_single_photo(filepath, output_dir):
    """Run the full 8-step enhancement pipeline on one photo."""
    filename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(filename)[0]
    output_path = os.path.join(output_dir, f"{name_no_ext}_enhanced.png")

    img = Image.open(filepath)
    original_size = img.size
    if img.mode != 'RGB':
        img = img.convert('RGB')

    analysis = analyze_image(img)

    # 8-step pipeline
    img = correct_exposure(img, analysis)
    img = enhance_contrast(img, analysis)
    img = apply_gradient_adjustment(img)
    if analysis["has_green_cast"]:
        img = remove_green_cast(img, analysis)
    img = apply_color_grading(img, analysis)
    img = optimize_saturation(img, analysis)
    img = apply_sharpening(img)
    if not analysis["has_green_cast"]:
        img = apply_vignette(img)

    analysis_after = analyze_image(img)
    img.save(output_path, "PNG", optimize=True)
    file_kb = round(os.path.getsize(output_path) / 1024, 1)

    return {
        "input": filename,
        "output": f"{name_no_ext}_enhanced.png",
        "size": f"{original_size[0]}x{original_size[1]}",
        "file_kb": file_kb,
        "brightness": f"{analysis['overall_brightness']} -> {analysis_after['overall_brightness']}",
        "contrast": f"{analysis['overall_contrast']} -> {analysis_after['overall_contrast']}",
        "green_cast_removed": analysis["has_green_cast"],
    }


# ═══════════════════════════════════════════════════════
#  FILE WATCHER & AUTO-PROCESSOR
# ═══════════════════════════════════════════════════════

def load_tracker():
    """Load list of already-processed file hashes."""
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_tracker(tracker):
    """Save processed file tracker."""
    with open(TRACKER_FILE, 'w') as f:
        json.dump(tracker, f, indent=2)


def get_file_hash(filepath):
    """Get modification-based hash for a file."""
    stat = os.stat(filepath)
    key = f"{filepath}|{stat.st_size}|{stat.st_mtime}"
    return hashlib.md5(key.encode()).hexdigest()


def get_image_files():
    """Get all image files in the input directory."""
    if not os.path.exists(INPUT_DIR):
        os.makedirs(INPUT_DIR, exist_ok=True)
        return []
    return [
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXT
    ]


def is_file_ready(filepath):
    """Check if a file is fully written (not still being copied)."""
    try:
        size1 = os.path.getsize(filepath)
        time.sleep(0.5)
        size2 = os.path.getsize(filepath)
        return size1 == size2 and size1 > 0
    except OSError:
        return False


def process_new_files(tracker):
    """Check for new/modified files and process them."""
    images = get_image_files()
    new_count = 0

    for filepath in images:
        file_hash = get_file_hash(filepath)
        filename = os.path.basename(filepath)

        # Skip already processed files
        if filename in tracker and tracker[filename] == file_hash:
            continue

        # Wait for file to be fully written
        if not is_file_ready(filepath):
            continue

        # New or modified file found!
        action = "Modified" if filename in tracker else "New"
        print(f"\n  [{action}] {filename} detected!")
        print(f"  Enhancing...", end="", flush=True)

        try:
            start = time.time()
            result = enhance_single_photo(filepath, OUTPUT_DIR)
            elapsed = round(time.time() - start, 1)

            print(f" DONE! ({elapsed}s)")
            print(f"    -> {result['output']} ({result['file_kb']} KB)")
            print(f"    Brightness: {result['brightness']}")
            print(f"    Contrast:   {result['contrast']}")
            if result['green_cast_removed']:
                print(f"    Green Cast: Removed")

            # Mark as processed
            tracker[filename] = file_hash
            save_tracker(tracker)
            new_count += 1

        except Exception as e:
            print(f" ERROR: {e}")

    return new_count


def main():
    print("=" * 55)
    print("  IPE-CGA Auto-Enhancement Watcher v1.0")
    print("=" * 55)
    print()
    print(f"  Watching:  {INPUT_DIR}")
    print(f"  Output:    {OUTPUT_DIR}")
    print(f"  Formats:   JPG, PNG, BMP, TIFF, WEBP")
    print(f"  Interval:  {POLL_INTERVAL}s")
    print()
    print("  Drop any photo into the 'pic/' folder")
    print("  and it will be auto-enhanced instantly!")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 55)

    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    tracker = load_tracker()

    # Initial scan - process any unprocessed files
    print("\n  Scanning for unprocessed photos...")
    initial = process_new_files(tracker)
    if initial == 0:
        print("  All existing photos are already enhanced.")
    else:
        print(f"\n  Processed {initial} photo(s) on startup.")

    # Watch loop
    print(f"\n  [WATCHING] Waiting for new photos...\n")
    try:
        while True:
            new = process_new_files(tracker)
            if new > 0:
                print(f"\n  [WATCHING] Waiting for new photos...\n")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print(f"\n\n  Watcher stopped. {len(tracker)} photos tracked.")
        print(f"  Enhanced photos are in: {OUTPUT_DIR}")
        print("=" * 55)


if __name__ == "__main__":
    main()
