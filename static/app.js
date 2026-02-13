/* ═══════════════════════════════════════════════════════
   IPE-CGA Photo Enhancement v2.0 — Auto-Analyze & Smart Enhancement
   Flow: Upload → Analyze → Show Report → Enhance → Result
   ═══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

    // ─── DOM Elements ───
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const analyzingCard = document.getElementById('analyzing-card');
    const analysisCard = document.getElementById('analysis-card');
    const processingCard = document.getElementById('processing-card');
    const resultSection = document.getElementById('result-section');
    const errorCard = document.getElementById('error-card');

    const processingSteps = document.getElementById('processing-steps');
    const errorMessage = document.getElementById('error-message');

    // Analysis elements
    const analysisPreview = document.getElementById('analysis-preview');
    const scoreFill = document.getElementById('score-fill');
    const scoreNumber = document.getElementById('score-number');
    const scoreSummary = document.getElementById('score-summary');
    const scoreDetail = document.getElementById('score-detail');
    const metricsGrid = document.getElementById('metrics-grid');
    const recList = document.getElementById('rec-list');
    const enhanceBtn = document.getElementById('enhance-btn');
    const cancelBtn = document.getElementById('cancel-btn');

    // Result elements
    const originalImg = document.getElementById('original-img');
    const enhancedImg = document.getElementById('enhanced-img');
    const sliderBefore = document.getElementById('slider-before');
    const sliderBeforeImg = document.getElementById('slider-before-img');
    const sliderAfterImg = document.getElementById('slider-after-img');
    const sliderHandle = document.getElementById('slider-handle');
    const downloadBtn = document.getElementById('download-btn');
    const newPhotoBtn = document.getElementById('new-photo-btn');

    // Stats
    const statResolution = document.getElementById('stat-resolution');
    const statBrightness = document.getElementById('stat-brightness');
    const statContrast = document.getElementById('stat-contrast');
    const statFileSize = document.getElementById('stat-file-size');
    const statTime = document.getElementById('stat-time');
    const enhancementsList = document.getElementById('enhancements-list');

    // Tabs
    const tabs = document.querySelectorAll('.comparison-header .tab');
    const views = document.querySelectorAll('.comparison-view');

    // ─── State ───
    let currentDownloadUrl = '';
    let currentAnalysis = null;

    // ─── Drag & Drop ───
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFile(e.target.files[0]);
    });

    ['dragenter', 'dragover'].forEach(evt => {
        uploadZone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(evt => {
        uploadZone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.classList.remove('drag-over');
        });
    });

    uploadZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFile(files[0]);
    });

    // ─── Tab Switching ───
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const view = tab.dataset.view;
            tabs.forEach(t => t.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`view-${view}`).classList.add('active');
        });
    });

    // ─── New Photo / Cancel ───
    newPhotoBtn.addEventListener('click', resetToUpload);
    cancelBtn.addEventListener('click', resetToUpload);

    function resetToUpload() {
        resultSection.classList.remove('active');
        errorCard.classList.remove('active');
        analysisCard.classList.remove('active');
        analyzingCard.classList.remove('active');
        processingCard.classList.remove('active');
        uploadZone.style.display = '';
        fileInput.value = '';
        currentAnalysis = null;
    }

    // ═══════════════════════════════════════════════════════
    //  PHASE 1: Upload → Analyze
    // ═══════════════════════════════════════════════════════

    async function handleFile(file) {
        // Validate
        const ext = file.name.split('.').pop().toLowerCase();
        const allowed = ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'webp'];
        if (!allowed.includes(ext)) {
            showError(`Unsupported format: .${ext}. Please use JPG, PNG, BMP, TIFF, or WEBP.`);
            return;
        }
        if (file.size > 50 * 1024 * 1024) {
            showError('File is too large. Maximum size is 50 MB.');
            return;
        }

        // Show analyzing state
        showAnalyzing();

        // Upload for analysis
        const formData = new FormData();
        formData.append('photo', file);

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                showError(data.error || 'Analysis failed. Please try again.');
                return;
            }

            currentAnalysis = data;
            showAnalysisReport(data);

        } catch (err) {
            showError('Connection error. Make sure the server is running.');
        }
    }

    // ═══════════════════════════════════════════════════════
    //  PHASE 2: Show Analysis Report
    // ═══════════════════════════════════════════════════════

    function showAnalyzing() {
        uploadZone.style.display = 'none';
        resultSection.classList.remove('active');
        errorCard.classList.remove('active');
        analysisCard.classList.remove('active');
        processingCard.classList.remove('active');
        analyzingCard.classList.add('active');
    }

    function showAnalysisReport(data) {
        analyzingCard.classList.remove('active');
        analysisCard.classList.add('active');

        // Preview image
        analysisPreview.src = data.preview_url;

        // Animate score ring
        const score = data.overall_score;
        const circumference = 2 * Math.PI * 52; // r=52
        const offset = circumference - (score / 100) * circumference;

        // Set score color
        let scoreColor;
        if (score >= 80) scoreColor = '#4ade80';
        else if (score >= 60) scoreColor = '#facc15';
        else if (score >= 40) scoreColor = '#fb923c';
        else scoreColor = '#f87171';

        scoreFill.style.stroke = scoreColor;

        // Animate
        setTimeout(() => {
            scoreFill.style.strokeDashoffset = offset;
            animateNumber(scoreNumber, 0, score, 1200);
        }, 200);

        // Score summary
        if (score >= 85) {
            scoreSummary.textContent = '✨ Great photo! Only minor tweaks needed.';
        } else if (score >= 65) {
            scoreSummary.textContent = '👍 Good photo with some areas to improve.';
        } else if (score >= 45) {
            scoreSummary.textContent = '🔧 Several issues detected — enhancement recommended.';
        } else {
            scoreSummary.textContent = '⚠️ Significant issues found — enhancement strongly recommended.';
        }

        scoreDetail.textContent = `${data.issues_found} issue${data.issues_found !== 1 ? 's' : ''} detected across ${data.total_metrics} metrics • ${data.resolution} • ${data.file_size_kb} KB`;

        // Metrics grid
        metricsGrid.innerHTML = '';
        const metricOrder = ['brightness', 'contrast', 'color_cast', 'saturation', 'sharpness', 'dynamic_range'];

        metricOrder.forEach((key, i) => {
            const m = data.metrics[key];
            if (!m) return;

            const card = document.createElement('div');
            card.className = 'metric-card';
            card.style.animationDelay = `${i * 0.1}s`;

            const severityClass = `severity-${m.severity}`;
            const barPercent = m.severity === 'good' ? 100
                : m.severity === 'mild' ? 70
                    : m.severity === 'moderate' ? 45
                        : 20;

            card.innerHTML = `
                <div class="metric-header">
                    <span class="metric-icon">${m.icon}</span>
                    <span class="metric-label">${m.label}</span>
                    <span class="metric-badge ${severityClass}">${m.severity === 'good' ? '✓ Good' : m.severity}</span>
                </div>
                <div class="metric-bar-track">
                    <div class="metric-bar-fill ${severityClass}" style="width: 0%;" data-width="${barPercent}%"></div>
                </div>
                <div class="metric-detail">${m.issue || 'No issues detected'} — ${m.detail}</div>
            `;
            metricsGrid.appendChild(card);
        });

        // Animate bars after a delay
        setTimeout(() => {
            document.querySelectorAll('.metric-bar-fill').forEach(bar => {
                bar.style.width = bar.dataset.width;
            });
        }, 400);

        // Recommendations
        recList.innerHTML = '';
        data.recommendations.forEach((rec, i) => {
            const item = document.createElement('div');
            item.className = 'rec-item';
            item.style.animationDelay = `${i * 0.08}s`;
            item.innerHTML = `
                <span class="rec-icon">${rec.icon}</span>
                <div class="rec-text">
                    <strong>${rec.action}</strong>
                    <span>${rec.reason}</span>
                </div>
            `;
            recList.appendChild(item);
        });

        // Update enhance button text
        enhanceBtn.innerHTML = `<span class="icon">✨</span> Apply ${data.recommendations.length} Smart Enhancements`;
    }

    function animateNumber(el, from, to, duration) {
        const start = performance.now();
        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            el.textContent = Math.round(from + (to - from) * eased);
            if (progress < 1) requestAnimationFrame(update);
        }
        requestAnimationFrame(update);
    }

    // ═══════════════════════════════════════════════════════
    //  PHASE 3: Enhance → Result
    // ═══════════════════════════════════════════════════════

    enhanceBtn.addEventListener('click', async () => {
        if (!currentAnalysis) return;

        // Show processing
        showProcessing(currentAnalysis.recommendations);

        try {
            const response = await fetch('/enhance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: currentAnalysis.filename })
            });

            const data = await response.json();

            if (!response.ok) {
                showError(data.error || 'Enhancement failed. Please try again.');
                return;
            }

            showResult(data);

        } catch (err) {
            showError('Connection error. Make sure the server is running.');
        }
    });

    function showProcessing(recommendations) {
        analysisCard.classList.remove('active');
        resultSection.classList.remove('active');
        errorCard.classList.remove('active');
        processingCard.classList.add('active');
        processingSteps.innerHTML = '';

        const steps = recommendations
            ? recommendations.map(r => r.action)
            : ['Processing...'];

        steps.forEach((text, i) => {
            setTimeout(() => {
                const step = document.createElement('div');
                step.className = 'step';
                step.style.animationDelay = '0s';
                step.innerHTML = `<span class="check">✓</span> ${text}`;
                processingSteps.appendChild(step);
            }, i * 500);
        });
    }

    function showResult(data) {
        processingCard.classList.remove('active');
        resultSection.classList.add('active');

        // Load images
        const originalUrl = data.original_preview_url;
        const enhancedUrl = data.preview_url;

        originalImg.src = originalUrl;
        enhancedImg.src = enhancedUrl;
        sliderBeforeImg.src = originalUrl;
        sliderAfterImg.src = enhancedUrl;

        // Make slider images have same dimensions
        sliderAfterImg.onload = () => {
            sliderBeforeImg.style.width = sliderAfterImg.offsetWidth + 'px';
        };

        // Before/After score comparison
        const scBefore = document.getElementById('sc-before');
        const scAfter = document.getElementById('sc-after');
        if (data.analysis_before && data.analysis_after) {
            scBefore.textContent = data.analysis_before.overall_score;
            scAfter.textContent = data.analysis_after.overall_score;

            // Color the scores
            scBefore.className = 'sc-value ' + getScoreClass(data.analysis_before.overall_score);
            scAfter.className = 'sc-value ' + getScoreClass(data.analysis_after.overall_score);
        }

        // Stats
        const beforeMetrics = data.analysis_before?.metrics || data.analysis_before?._raw || {};
        const afterMetrics = data.analysis_after?.metrics || {};

        statResolution.textContent = data.original_size;

        const bBefore = beforeMetrics.brightness?.value ?? data.analysis_before?._raw?.overall_brightness ?? '—';
        const bAfter = afterMetrics.brightness?.value ?? '—';
        statBrightness.innerHTML = `${typeof bBefore === 'number' ? bBefore.toFixed(1) : bBefore} <span class="arrow">→</span> ${typeof bAfter === 'number' ? bAfter.toFixed(1) : bAfter}`;

        const cBefore = beforeMetrics.contrast?.value ?? data.analysis_before?._raw?.overall_contrast ?? '—';
        const cAfter = afterMetrics.contrast?.value ?? '—';
        statContrast.innerHTML = `${typeof cBefore === 'number' ? cBefore.toFixed(1) : cBefore} <span class="arrow">→</span> ${typeof cAfter === 'number' ? cAfter.toFixed(1) : cAfter}`;

        statFileSize.innerHTML = `${data.input_size_kb} KB <span class="arrow">→</span> ${data.output_size_kb} KB`;
        statTime.textContent = `${data.processing_time}s`;

        // Enhancements
        enhancementsList.innerHTML = data.enhancements.map(e =>
            `<span class="tag">${e}</span>`
        ).join('');

        // Download
        currentDownloadUrl = data.download_url;
        downloadBtn.onclick = (e) => {
            e.preventDefault();
            const a = document.createElement('a');
            a.href = currentDownloadUrl;
            a.download = data.output_filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        };
    }

    function getScoreClass(score) {
        if (score >= 80) return 'score-great';
        if (score >= 60) return 'score-good';
        if (score >= 40) return 'score-fair';
        return 'score-poor';
    }

    function showError(message) {
        analyzingCard.classList.remove('active');
        analysisCard.classList.remove('active');
        processingCard.classList.remove('active');
        resultSection.classList.remove('active');
        uploadZone.style.display = 'none';
        errorCard.classList.add('active');
        errorMessage.textContent = message;
    }

    // ─── Image Comparison Slider ───
    const sliderWrapper = document.getElementById('slider-wrapper');
    let isDragging = false;

    function updateSlider(x) {
        const rect = sliderWrapper.getBoundingClientRect();
        let percent = ((x - rect.left) / rect.width) * 100;
        percent = Math.max(0, Math.min(100, percent));
        sliderBefore.style.width = percent + '%';
        sliderHandle.style.left = percent + '%';
    }

    sliderWrapper.addEventListener('mousedown', (e) => {
        isDragging = true;
        updateSlider(e.clientX);
    });

    document.addEventListener('mousemove', (e) => {
        if (isDragging) {
            e.preventDefault();
            updateSlider(e.clientX);
        }
    });

    document.addEventListener('mouseup', () => {
        isDragging = false;
    });

    // Touch support
    sliderWrapper.addEventListener('touchstart', (e) => {
        isDragging = true;
        updateSlider(e.touches[0].clientX);
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
        if (isDragging) updateSlider(e.touches[0].clientX);
    }, { passive: true });

    document.addEventListener('touchend', () => {
        isDragging = false;
    });

    // ─── Error retry ───
    document.getElementById('error-retry')?.addEventListener('click', () => {
        errorCard.classList.remove('active');
        uploadZone.style.display = '';
    });

});
