# -*- coding: utf-8 -*-
"""
IPE-CGA Web Frontend v2.0 — Auto-Analyze & Smart Enhancement
Flask server wrapping the photo enhancement pipeline.
Upload → Auto-Analyze → Smart Enhance → Download (lossless PNG)
"""

import os
import uuid
import time
import math
import threading
import numpy as np
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
#  ANALYSIS ENGINE — Detailed Photo Diagnostics
# ═══════════════════════════════════════════════════════════

def classify_severity(value, thresholds):
    """Classify a metric into severity levels.
    thresholds = [(limit, 'severity'), ...] evaluated in order.
    """
    for limit, severity in thresholds:
        if value <= limit:
            return severity
    return thresholds[-1][1]


def analyze_image_detailed(img):
    """Run deep analysis on the image and return rich diagnostics."""
    stat = ImageStat.Stat(img)
    r_mean, g_mean, b_mean = stat.mean[:3]
    r_std, g_std, b_std = stat.stddev[:3]

    overall_brightness = (r_mean + g_mean + b_mean) / 3.0
    overall_contrast = (r_std + g_std + b_std) / 3.0
    green_dominance = g_mean - ((r_mean + b_mean) / 2.0)

    # Sharpness estimation via Laplacian variance
    gray = img.convert('L')
    arr = np.array(gray, dtype=np.float64)
    laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
    from scipy.signal import convolve2d
    lap = convolve2d(arr, laplacian, mode='valid')
    sharpness_score = float(np.var(lap))

    # Saturation estimation via HSV
    hsv = img.convert('HSV')
    s_channel = np.array(hsv)[:, :, 1]
    avg_saturation = float(np.mean(s_channel))

    # Dynamic range
    gray_arr = np.array(gray)
    dynamic_range = int(np.max(gray_arr)) - int(np.min(gray_arr))

    # Noise estimation (std of high-pass filtered image)
    hp = arr - convolve2d(arr, np.ones((3, 3)) / 9, mode='same', boundary='symm')
    noise_level = float(np.std(hp))

    # ── Severity classification ──
    # Brightness
    if overall_brightness < 70:
        br_sev, br_issue = "severe", "Very underexposed"
    elif overall_brightness < 100:
        br_sev, br_issue = "moderate", "Underexposed"
    elif overall_brightness > 200:
        br_sev, br_issue = "severe", "Very overexposed"
    elif overall_brightness > 180:
        br_sev, br_issue = "moderate", "Overexposed"
    elif overall_brightness > 160:
        br_sev, br_issue = "mild", "Slightly bright"
    else:
        br_sev, br_issue = "good", None

    # Contrast
    if overall_contrast < 35:
        ct_sev, ct_issue = "severe", "Very flat / low contrast"
    elif overall_contrast < 50:
        ct_sev, ct_issue = "moderate", "Low contrast"
    elif overall_contrast < 65:
        ct_sev, ct_issue = "mild", "Slightly low contrast"
    else:
        ct_sev, ct_issue = "good", None

    # Color cast
    if green_dominance > 25:
        cc_sev, cc_issue = "severe", "Strong green cast"
    elif green_dominance > 15:
        cc_sev, cc_issue = "moderate", "Green cast detected"
    elif green_dominance > 8:
        cc_sev, cc_issue = "mild", "Slight green tint"
    else:
        cc_sev, cc_issue = "good", None

    # Saturation
    if avg_saturation < 40:
        sat_sev, sat_issue = "severe", "Very desaturated"
    elif avg_saturation < 70:
        sat_sev, sat_issue = "moderate", "Undersaturated"
    elif avg_saturation < 90:
        sat_sev, sat_issue = "mild", "Slightly dull colors"
    elif avg_saturation > 200:
        sat_sev, sat_issue = "moderate", "Oversaturated"
    else:
        sat_sev, sat_issue = "good", None

    # Sharpness
    if sharpness_score < 100:
        sh_sev, sh_issue = "severe", "Very soft / blurry"
    elif sharpness_score < 300:
        sh_sev, sh_issue = "moderate", "Soft image"
    elif sharpness_score < 800:
        sh_sev, sh_issue = "mild", "Could be sharper"
    else:
        sh_sev, sh_issue = "good", None

    # Dynamic Range
    if dynamic_range < 100:
        dr_sev, dr_issue = "moderate", "Limited dynamic range"
    elif dynamic_range < 150:
        dr_sev, dr_issue = "mild", "Slightly compressed range"
    else:
        dr_sev, dr_issue = "good", None

    # Build metrics
    metrics = {
        "brightness": {
            "value": round(overall_brightness, 1),
            "severity": br_sev,
            "issue": br_issue,
            "icon": "☀️",
            "label": "Exposure",
            "detail": f"Mean brightness: {overall_brightness:.0f}/255"
        },
        "contrast": {
            "value": round(overall_contrast, 1),
            "severity": ct_sev,
            "issue": ct_issue,
            "icon": "🎚️",
            "label": "Contrast",
            "detail": f"Std deviation: {overall_contrast:.0f}"
        },
        "color_cast": {
            "value": round(green_dominance, 1),
            "severity": cc_sev,
            "issue": cc_issue,
            "icon": "🎨",
            "label": "Color Balance",
            "detail": f"G dominance: {green_dominance:.1f}"
        },
        "saturation": {
            "value": round(avg_saturation, 1),
            "severity": sat_sev,
            "issue": sat_issue,
            "icon": "💧",
            "label": "Saturation",
            "detail": f"Avg saturation: {avg_saturation:.0f}/255"
        },
        "sharpness": {
            "value": round(sharpness_score, 1),
            "severity": sh_sev,
            "issue": sh_issue,
            "icon": "🔍",
            "label": "Sharpness",
            "detail": f"Laplacian var: {sharpness_score:.0f}"
        },
        "dynamic_range": {
            "value": dynamic_range,
            "severity": dr_sev,
            "issue": dr_issue,
            "icon": "📊",
            "label": "Dynamic Range",
            "detail": f"Range: {dynamic_range}/255"
        }
    }

    # Recommendations
    recommendations = []
    severity_scores = {"good": 0, "mild": 1, "moderate": 2, "severe": 3}
    total_issues = 0

    for key, m in metrics.items():
        if m["severity"] != "good":
            total_issues += 1
            if key == "brightness":
                recommendations.append({"action": "Adaptive Exposure Correction", "reason": m["issue"], "icon": "☀️"})
            elif key == "contrast":
                recommendations.append({"action": "Contrast Enhancement + S-Curve", "reason": m["issue"], "icon": "🎚️"})
            elif key == "color_cast":
                recommendations.append({"action": "Green Cast Removal", "reason": m["issue"], "icon": "🎨"})
            elif key == "saturation":
                recommendations.append({"action": "Saturation Optimization", "reason": m["issue"], "icon": "💧"})
            elif key == "sharpness":
                recommendations.append({"action": "Professional Sharpening", "reason": m["issue"], "icon": "🔍"})
            elif key == "dynamic_range":
                recommendations.append({"action": "Tone Mapping & Gradient Adjustment", "reason": m["issue"], "icon": "📊"})

    # Always recommend color grading & vignette for cinematic look
    recommendations.append({"action": "Cinematic Color Grading", "reason": "Professional look", "icon": "🎬"})
    if cc_sev == "good":
        recommendations.append({"action": "Cinematic Vignette", "reason": "Focus enhancement", "icon": "🔘"})

    # Overall Quality Score (0-100)
    score = 100
    for m in metrics.values():
        penalty = {"good": 0, "mild": 5, "moderate": 12, "severe": 20}
        score -= penalty.get(m["severity"], 0)
    score = max(0, min(100, score))

    return {
        "metrics": metrics,
        "recommendations": recommendations,
        "overall_score": score,
        "issues_found": total_issues,
        "total_metrics": len(metrics),
        # Keep raw values for the pipeline
        "_raw": {
            "r_mean": r_mean, "g_mean": g_mean, "b_mean": b_mean,
            "overall_brightness": overall_brightness,
            "overall_contrast": overall_contrast,
            "green_dominance": green_dominance,
            "has_green_cast": green_dominance > 15,
            "is_underexposed": overall_brightness < 100,
            "is_overexposed": overall_brightness > 180,
            "avg_saturation": avg_saturation,
            "sharpness_score": sharpness_score,
            "dynamic_range": dynamic_range,
        }
    }


# ═══════════════════════════════════════════════════════════
#  ENHANCEMENT ENGINE — Adaptive Pipeline
# ═══════════════════════════════════════════════════════════

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
    """Run the adaptive enhancement pipeline based on analysis. Returns stats dict."""
    img = Image.open(input_path)
    original_size = img.size
    original_mode = img.mode

    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Run detailed analysis
    full_analysis = analyze_image_detailed(img)
    raw = full_analysis["_raw"]
    metrics = full_analysis["metrics"]

    enhancements = []
    steps_applied = []

    # Step 1: Exposure correction (adaptive)
    if metrics["brightness"]["severity"] != "good":
        img = correct_exposure(img, raw)
        enhancements.append("Adaptive Exposure Correction")
        steps_applied.append("exposure")
    else:
        # Light touch-up even if good
        img = ImageEnhance.Brightness(img).enhance(1.02)
        enhancements.append("Fine Exposure Tuning")
        steps_applied.append("exposure_fine")

    # Step 2: Contrast enhancement (adaptive)
    if metrics["contrast"]["severity"] != "good":
        img = enhance_contrast(img, raw)
        enhancements.append("Contrast Enhancement")
        steps_applied.append("contrast")
    else:
        img = ImageEnhance.Contrast(img).enhance(1.05)
        enhancements.append("Fine Contrast Tuning")
        steps_applied.append("contrast_fine")

    # Step 3: S-curve / tone mapping (adaptive based on dynamic range)
    if metrics["dynamic_range"]["severity"] != "good":
        img = apply_gradient_adjustment(img)
        enhancements.append("S-Curve Tone Mapping")
        steps_applied.append("tone_mapping")

    # Step 4: Green cast removal (only if detected)
    if raw["has_green_cast"]:
        img = remove_green_cast(img, raw)
        enhancements.append("Green Cast Removal")
        steps_applied.append("green_cast")

    # Step 5: Cinematic color grading (always — for professional look)
    img = apply_color_grading(img, raw)
    enhancements.append("Cinematic Color Grading")
    steps_applied.append("color_grading")

    # Step 6: Saturation optimization (adaptive)
    if metrics["saturation"]["severity"] != "good":
        img = optimize_saturation(img, raw)
        enhancements.append("Saturation Optimization")
        steps_applied.append("saturation")

    # Step 7: Sharpening (adaptive based on sharpness)
    if metrics["sharpness"]["severity"] != "good":
        img = apply_sharpening(img)
        enhancements.append("Professional Sharpening")
        steps_applied.append("sharpening")
    else:
        # Gentle sharpen for already sharp images
        img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=4))
        enhancements.append("Gentle Sharpening")
        steps_applied.append("sharpening_gentle")

    # Step 8: Vignette (only if no green cast — same logic as before)
    if not raw["has_green_cast"]:
        img = apply_vignette(img)
        enhancements.append("Cinematic Vignette")
        steps_applied.append("vignette")

    # Analyze result
    after_analysis = analyze_image_detailed(img)

    # Save as lossless PNG
    img.save(output_path, "PNG", optimize=True)
    output_size_kb = round(os.path.getsize(output_path) / 1024, 1)
    input_size_kb = round(os.path.getsize(input_path) / 1024, 1)

    return {
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "original_mode": original_mode,
        "input_size_kb": input_size_kb,
        "output_size_kb": output_size_kb,
        "analysis_before": full_analysis,
        "analysis_after": {
            "metrics": after_analysis["metrics"],
            "overall_score": after_analysis["overall_score"],
        },
        "enhancements": enhancements,
        "steps_applied": steps_applied,
    }


# ═══════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    """Upload & analyze photo — returns detailed diagnostics without enhancing."""
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
    input_filename = f"{uid}_{safe_name}"
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    file.save(input_path)

    try:
        img = Image.open(input_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        w, h = img.size

        start = time.time()
        analysis = analyze_image_detailed(img)
        elapsed = round(time.time() - start, 2)

        return jsonify({
            "filename": input_filename,
            "original_name": safe_name,
            "resolution": f"{w}x{h}",
            "file_size_kb": round(os.path.getsize(input_path) / 1024, 1),
            "analysis_time": elapsed,
            "preview_url": url_for('preview_original', filename=input_filename),
            **analysis,
        })

    except Exception as e:
        try:
            os.remove(input_path)
        except OSError:
            pass
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


@app.route('/enhance', methods=['POST'])
def enhance():
    """Enhance a previously analyzed photo."""
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "No filename provided"}), 400

    input_filename = secure_filename(data['filename'])
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)

    if not os.path.exists(input_path):
        return jsonify({"error": "File not found. Please re-upload."}), 404

    name_no_ext = os.path.splitext(input_filename)[0]
    # Remove the uid prefix for the output name
    parts = name_no_ext.split('_', 1)
    clean_name = parts[1] if len(parts) > 1 else name_no_ext
    uid = parts[0] if len(parts) > 1 else uuid.uuid4().hex[:12]

    output_filename = f"{uid}_{clean_name}_enhanced.png"
    output_path = os.path.join(app.config['ENHANCED_FOLDER'], output_filename)

    try:
        start = time.time()
        stats = run_enhancement_pipeline(input_path, output_path)
        elapsed = round(time.time() - start, 1)
        stats["processing_time"] = elapsed
        stats["download_url"] = url_for('download', filename=output_filename)
        stats["preview_url"] = url_for('preview', filename=output_filename)
        stats["original_preview_url"] = url_for('preview_original', filename=input_filename)

        # Clean download name
        download_name = f"{clean_name}_enhanced.png"
        # Remove file extension duplication
        download_name = download_name.replace('.jpg_enhanced', '_enhanced').replace('.jpeg_enhanced', '_enhanced')
        download_name = download_name.replace('.png_enhanced', '_enhanced').replace('.bmp_enhanced', '_enhanced')
        stats["output_filename"] = download_name

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
    print("  IPE-CGA Photo Enhancement Web App v2.0")
    print("  Auto-Analyze & Smart Enhancement")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 55)
    app.run(debug=True, port=5000)
