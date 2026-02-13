# -*- coding: utf-8 -*-
"""
IPE-CGA Web Frontend
Flask server wrapping the photo enhancement pipeline.
Upload → Enhance → Download (lossless PNG)
"""

import os
import uuid
import time
import math
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, url_for
from PIL import Image, ImageEnhance, ImageFilter, ImageStat
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload

# Use /tmp on cloud (Render uses ephemeral filesystem), local folders otherwise
IS_PRODUCTION = os.environ.get('RENDER') or os.environ.get('PORT')
if IS_PRODUCTION:
    app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
    app.config['ENHANCED_FOLDER'] = '/tmp/enhanced_web'
else:
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    app.config['ENHANCED_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'enhanced_web')

SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ENHANCED_FOLDER'], exist_ok=True)


# ═══════════════════════════════════════════════════════════
#  ENHANCEMENT ENGINE (from enhance_photos.py)
# ═══════════════════════════════════════════════════════════

def analyze_image(img):
    """Analyze image statistics for adaptive enhancement."""
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
    max_r = math.sqrt(cx ** 2 + cy ** 2)
    for y in range(h):
        for x in range(w):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
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


def run_enhancement_pipeline(input_path, output_path):
    """Run the full 8-step enhancement pipeline. Returns stats dict."""
    img = Image.open(input_path)
    original_size = img.size
    original_mode = img.mode

    if img.mode != 'RGB':
        img = img.convert('RGB')

    analysis_before = analyze_image(img)

    # 8-step pipeline
    img = correct_exposure(img, analysis_before)
    img = enhance_contrast(img, analysis_before)
    img = apply_gradient_adjustment(img)
    if analysis_before["has_green_cast"]:
        img = remove_green_cast(img, analysis_before)
    img = apply_color_grading(img, analysis_before)
    img = optimize_saturation(img, analysis_before)
    img = apply_sharpening(img)
    if not analysis_before["has_green_cast"]:
        img = apply_vignette(img)

    analysis_after = analyze_image(img)

    # Save as lossless PNG
    img.save(output_path, "PNG", optimize=True)
    output_size_kb = round(os.path.getsize(output_path) / 1024, 1)
    input_size_kb = round(os.path.getsize(input_path) / 1024, 1)

    enhancements = [
        "Adaptive Exposure Correction",
        "Contrast Enhancement",
        "S-Curve Tone Mapping",
    ]
    if analysis_before["has_green_cast"]:
        enhancements.append("Green Cast Removal")
    enhancements.extend([
        "Cinematic Color Grading",
        "Saturation Optimization",
        "Professional Sharpening",
    ])
    if not analysis_before["has_green_cast"]:
        enhancements.append("Cinematic Vignette")

    return {
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "original_mode": original_mode,
        "input_size_kb": input_size_kb,
        "output_size_kb": output_size_kb,
        "analysis_before": analysis_before,
        "analysis_after": analysis_after,
        "enhancements": enhancements,
    }


# ═══════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'photo' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXT:
        return jsonify({"error": f"Unsupported format: {ext}. Use JPG, PNG, BMP, TIFF, or WEBP."}), 400

    # Save uploaded file with unique name
    uid = uuid.uuid4().hex[:12]
    safe_name = secure_filename(file.filename)
    name_no_ext = os.path.splitext(safe_name)[0]
    input_filename = f"{uid}_{safe_name}"
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    file.save(input_path)

    # Output path
    output_filename = f"{uid}_{name_no_ext}_enhanced.png"
    output_path = os.path.join(app.config['ENHANCED_FOLDER'], output_filename)

    try:
        start = time.time()
        stats = run_enhancement_pipeline(input_path, output_path)
        elapsed = round(time.time() - start, 1)
        stats["processing_time"] = elapsed
        stats["download_url"] = url_for('download', filename=output_filename)
        stats["preview_url"] = url_for('preview', filename=output_filename)
        stats["original_preview_url"] = url_for('preview_original', filename=input_filename)
        stats["output_filename"] = f"{name_no_ext}_enhanced.png"

        # Schedule cleanup of uploaded original after 30 minutes
        def cleanup():
            time.sleep(1800)
            try:
                os.remove(input_path)
            except OSError:
                pass
        threading.Thread(target=cleanup, daemon=True).start()

        return jsonify(stats)

    except Exception as e:
        # Cleanup on error
        try:
            os.remove(input_path)
        except OSError:
            pass
        return jsonify({"error": f"Enhancement failed: {str(e)}"}), 500


@app.route('/download/<filename>')
def download(filename):
    filepath = os.path.join(app.config['ENHANCED_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    # Extract a clean download name (remove the uid prefix)
    parts = filename.split('_', 1)
    download_name = parts[1] if len(parts) > 1 else filename
    return send_file(filepath, as_attachment=True, download_name=download_name, mimetype='image/png')


@app.route('/preview/<filename>')
def preview(filename):
    filepath = os.path.join(app.config['ENHANCED_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, mimetype='image/png')


@app.route('/preview-original/<filename>')
def preview_original(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath)


if __name__ == '__main__':
    print("=" * 55)
    print("  IPE-CGA Photo Enhancement Web App")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 55)
    app.run(debug=True, port=5000)
