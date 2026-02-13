# -*- coding: utf-8 -*-
"""
IPE-CGA: Intelligent Photo Enhancement & Color Grading Agent
Professional Photo Enhancement Pipeline v1.0

Enhancements Applied Per Image:
  1. Adaptive Brightness & Exposure Correction
  2. Contrast Enhancement
  3. S-Curve Gradient Tone Mapping
  4. Green Screen Color Cast Removal
  5. Cinematic Color Grading
  6. Saturation Optimization
  7. Professional Sharpening
  8. Cinematic Vignette

Output: High-quality PNG (lossless) in 'enhanced/' subfolder
"""

import os
import sys
import io
import json
import math
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter, ImageStat, ImageDraw

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

INPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pic")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enhanced")
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enhancement_report.json")


def analyze_image(img):
    """Analyze image statistics for adaptive enhancement."""
    stat = ImageStat.Stat(img)
    r_mean, g_mean, b_mean = stat.mean[:3]
    r_std, g_std, b_std = stat.stddev[:3]
    overall_brightness = (r_mean + g_mean + b_mean) / 3.0
    overall_contrast = (r_std + g_std + b_std) / 3.0
    green_dominance = g_mean - ((r_mean + b_mean) / 2.0)
    has_green_cast = green_dominance > 15
    is_underexposed = overall_brightness < 100
    is_overexposed = overall_brightness > 180

    return {
        "r_mean": round(r_mean, 2),
        "g_mean": round(g_mean, 2),
        "b_mean": round(b_mean, 2),
        "overall_brightness": round(overall_brightness, 2),
        "overall_contrast": round(overall_contrast, 2),
        "green_dominance": round(green_dominance, 2),
        "has_green_cast": has_green_cast,
        "is_underexposed": is_underexposed,
        "is_overexposed": is_overexposed,
    }


def correct_exposure(img, analysis):
    """Adaptive brightness and exposure correction."""
    brightness = analysis["overall_brightness"]
    if analysis["is_underexposed"]:
        factor = min(1.0 + (128 - brightness) / 256.0, 1.35)
    elif analysis["is_overexposed"]:
        factor = max(1.0 - (brightness - 128) / 384.0, 0.85)
    else:
        factor = 1.05
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(factor)


def enhance_contrast(img, analysis):
    """Adaptive contrast enhancement."""
    contrast = analysis["overall_contrast"]
    if contrast < 50:
        factor = 1.30
    elif contrast < 65:
        factor = 1.18
    else:
        factor = 1.08
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(factor)


def remove_green_cast(img, analysis):
    """Remove green screen color cast from skin tones and subject."""
    if not analysis["has_green_cast"]:
        return img

    pixels = img.load()
    width, height = img.size
    green_dom = analysis["green_dominance"]
    correction = min(green_dom * 0.4, 25)

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            # Skip pure green screen areas
            if g > 150 and g > r * 1.5 and g > b * 1.5:
                continue
            new_g = max(0, int(g - correction * 0.6))
            new_r = min(255, int(r + correction * 0.2))
            new_b = min(255, int(b + correction * 0.15))
            pixels[x, y] = (new_r, new_g, new_b)

    return img


def apply_color_grading(img, analysis):
    """Apply professional cinematic color grading."""
    pixels = img.load()
    width, height = img.size

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            luminance = r * 0.299 + g * 0.587 + b * 0.114

            if luminance < 60:
                new_r, new_g, new_b = r, min(255, g + 2), min(255, b + 5)
            elif luminance < 180:
                new_r, new_g, new_b = min(255, r + 4), min(255, g + 1), max(0, b - 3)
            else:
                new_r, new_g, new_b = min(255, r + 3), min(255, g + 1), max(0, b - 2)

            pixels[x, y] = (new_r, new_g, new_b)

    return img


def optimize_saturation(img, analysis):
    """Optimize color saturation."""
    if analysis["has_green_cast"]:
        factor = 1.10
    elif analysis["overall_brightness"] < 100:
        factor = 1.20
    elif analysis["overall_brightness"] > 170:
        factor = 1.05
    else:
        factor = 1.15
    enhancer = ImageEnhance.Color(img)
    return enhancer.enhance(factor)


def apply_sharpening(img):
    """Professional-grade sharpening."""
    return img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=3))


def apply_vignette(img):
    """Apply subtle cinematic vignette."""
    width, height = img.size
    vignette = Image.new('L', (width, height), 0)
    cx, cy = width // 2, height // 2
    max_radius = math.sqrt(cx ** 2 + cy ** 2)

    for y in range(height):
        for x in range(width):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            ratio = dist / max_radius
            if ratio > 0.6:
                darkness = int(255 - (ratio - 0.6) * 160)
                darkness = max(darkness, 140)
            else:
                darkness = 255
            vignette.putpixel((x, y), darkness)

    r, g, b = img.split()[:3]
    r = Image.composite(r, Image.new('L', (width, height), 0), vignette)
    g = Image.composite(g, Image.new('L', (width, height), 0), vignette)
    b = Image.composite(b, Image.new('L', (width, height), 0), vignette)
    return Image.merge('RGB', (r, g, b))


def apply_gradient_adjustment(img):
    """Apply S-curve gradient tone mapping for smooth tonal transitions."""
    def s_curve(x):
        t = x / 255.0
        result = 0.5 * (1 + math.tanh(2.5 * (t - 0.5)))
        return int(max(0, min(255, result * 255)))

    lut = [s_curve(i) for i in range(256)]

    if img.mode == 'RGB':
        img = img.point(lut * 3)
    elif img.mode == 'RGBA':
        r, g, b, a = img.split()
        r = r.point(lut)
        g = g.point(lut)
        b = b.point(lut)
        img = Image.merge('RGBA', (r, g, b, a))
    return img


def process_image(filepath, output_dir):
    """Full enhancement pipeline for a single image."""
    filename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(filename)[0]
    output_path = os.path.join(output_dir, f"{name_no_ext}_enhanced.png")

    print(f"\n{'='*60}")
    print(f"  Processing: {filename}")
    print(f"{'='*60}")

    img = Image.open(filepath)
    original_size = img.size
    original_mode = img.mode

    # Convert to RGB
    if img.mode != 'RGB':
        img_rgb = img.convert('RGB')
    else:
        img_rgb = img.copy()

    # Step 1: Analyze
    print("  [1/8] Analyzing image properties...")
    analysis_before = analyze_image(img_rgb)
    print(f"        Brightness: {analysis_before['overall_brightness']}")
    print(f"        Contrast:   {analysis_before['overall_contrast']}")
    print(f"        Green Cast: {'YES' if analysis_before['has_green_cast'] else 'No'}")
    expo = 'Under' if analysis_before['is_underexposed'] else ('Over' if analysis_before['is_overexposed'] else 'Normal')
    print(f"        Exposure:   {expo}")

    # Step 2: Exposure correction
    print("  [2/8] Correcting exposure & brightness...")
    img_rgb = correct_exposure(img_rgb, analysis_before)

    # Step 3: Contrast enhancement
    print("  [3/8] Enhancing contrast...")
    img_rgb = enhance_contrast(img_rgb, analysis_before)

    # Step 4: Gradient adjustment
    print("  [4/8] Applying gradient tone mapping...")
    img_rgb = apply_gradient_adjustment(img_rgb)

    # Step 5: Green cast removal
    if analysis_before["has_green_cast"]:
        print("  [5/8] Removing green screen color cast...")
        img_rgb = remove_green_cast(img_rgb, analysis_before)
    else:
        print("  [5/8] Green cast removal - not needed")

    # Step 6: Color grading
    print("  [6/8] Applying cinematic color grading...")
    img_rgb = apply_color_grading(img_rgb, analysis_before)

    # Step 7: Saturation optimization
    print("  [7/8] Optimizing saturation...")
    img_rgb = optimize_saturation(img_rgb, analysis_before)

    # Step 8: Sharpening
    print("  [8/8] Applying professional sharpening...")
    img_rgb = apply_sharpening(img_rgb)

    # Optional: Vignette (skip for green screen shots)
    if not analysis_before["has_green_cast"]:
        print("  [BONUS] Adding subtle cinematic vignette...")
        img_rgb = apply_vignette(img_rgb)

    # Final analysis
    analysis_after = analyze_image(img_rgb)

    # Save as high-quality PNG
    print(f"  Saving enhanced image as PNG...")
    img_rgb.save(output_path, "PNG", optimize=True)
    output_size = os.path.getsize(output_path)

    print(f"  DONE: {output_path}")
    print(f"  Output size: {output_size / 1024:.1f} KB")

    return {
        "filename": filename,
        "output_filename": f"{name_no_ext}_enhanced.png",
        "output_path": output_path,
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "original_mode": original_mode,
        "file_size_kb": round(output_size / 1024, 1),
        "analysis_before": analysis_before,
        "analysis_after": analysis_after,
        "enhancements_applied": [
            "Adaptive Exposure Correction",
            "Contrast Enhancement",
            "S-Curve Gradient Tone Mapping",
            *(["Green Cast Removal"] if analysis_before["has_green_cast"] else []),
            "Cinematic Color Grading",
            "Saturation Optimization",
            "Professional Sharpening (UnsharpMask)",
            *([] if analysis_before["has_green_cast"] else ["Cinematic Vignette"]),
        ],
    }


def main():
    print("=" * 60)
    print("  IPE-CGA: Photo Enhancement & Color Grading Agent v1.0")
    print("=" * 60)
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    supported_ext = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
    images = [
        os.path.join(INPUT_DIR, f)
        for f in sorted(os.listdir(INPUT_DIR))
        if os.path.splitext(f)[1].lower() in supported_ext
    ]

    if not images:
        print("ERROR: No images found in the 'pic' directory!")
        sys.exit(1)

    print(f"Found {len(images)} images to enhance")
    print(f"Output directory: {OUTPUT_DIR}")

    results = []
    for i, filepath in enumerate(images, 1):
        print(f"\n>>> Image {i}/{len(images)}")
        result = process_image(filepath, OUTPUT_DIR)
        results.append(result)

    # Generate report
    report = {
        "agent": "IPE-CGA v1.0",
        "timestamp": datetime.now().isoformat(),
        "total_images": len(results),
        "output_format": "PNG (lossless, optimized)",
        "output_directory": OUTPUT_DIR,
        "images": results,
    }

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  ENHANCEMENT SUMMARY")
    print(f"{'='*60}")
    print(f"  Total images processed: {len(results)}")
    print(f"  Output format: PNG (lossless)")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Report saved: {REPORT_FILE}")
    print()

    for r in results:
        gc = " [Green Cast Removed]" if r["analysis_before"]["has_green_cast"] else ""
        print(f"  {r['filename']}")
        print(f"     -> {r['output_filename']} ({r['file_size_kb']} KB)")
        print(f"     Brightness: {r['analysis_before']['overall_brightness']} -> {r['analysis_after']['overall_brightness']}")
        print(f"     Contrast:   {r['analysis_before']['overall_contrast']} -> {r['analysis_after']['overall_contrast']}")
        if gc:
            print(f"     {gc}")
        print()

    print(f"{'='*60}")
    print(f"  All {len(results)} images enhanced successfully!")
    print(f"  Find your enhanced photos in: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
