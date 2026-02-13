/* ═══════════════════════════════════════════════════════
   IPE-CGA Photo Enhancement — Frontend Logic
   ═══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

    // ─── DOM Elements ───
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const processingCard = document.getElementById('processing-card');
    const resultSection = document.getElementById('result-section');
    const errorCard = document.getElementById('error-card');

    const processingSteps = document.getElementById('processing-steps');
    const errorMessage = document.getElementById('error-message');

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

    // ─── New Photo ───
    newPhotoBtn.addEventListener('click', () => {
        resultSection.classList.remove('active');
        errorCard.classList.remove('active');
        uploadZone.style.display = '';
        fileInput.value = '';
    });

    // ─── File Handler ───
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

        // Show processing
        showProcessing();

        // Upload
        const formData = new FormData();
        formData.append('photo', file);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                showError(data.error || 'Enhancement failed. Please try again.');
                return;
            }

            showResult(data, file);

        } catch (err) {
            showError('Connection error. Make sure the server is running.');
        }
    }

    // ─── Show States ───
    function showProcessing() {
        uploadZone.style.display = 'none';
        resultSection.classList.remove('active');
        errorCard.classList.remove('active');
        processingCard.classList.add('active');
        processingSteps.innerHTML = '';

        const steps = [
            'Analyzing image properties',
            'Correcting exposure & brightness',
            'Enhancing contrast',
            'Applying S-curve tone mapping',
            'Removing color casts',
            'Cinematic color grading',
            'Optimizing saturation',
            'Professional sharpening',
            'Finalizing & saving PNG'
        ];

        steps.forEach((text, i) => {
            setTimeout(() => {
                const step = document.createElement('div');
                step.className = 'step';
                step.style.animationDelay = '0s';
                step.innerHTML = `<span class="check">✓</span> ${text}`;
                processingSteps.appendChild(step);
            }, i * 400);
        });
    }

    function showResult(data, file) {
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
            const w = sliderAfterImg.naturalWidth;
            sliderBeforeImg.style.width = sliderAfterImg.offsetWidth + 'px';
        };

        // Stats
        const before = data.analysis_before;
        const after = data.analysis_after;

        statResolution.textContent = data.original_size;
        statBrightness.innerHTML = `${before.overall_brightness} <span class="arrow">→</span> ${after.overall_brightness}`;
        statContrast.innerHTML = `${before.overall_contrast} <span class="arrow">→</span> ${after.overall_contrast}`;
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

    function showError(message) {
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
