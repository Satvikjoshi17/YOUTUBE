// YouTube Downloader JavaScript
class YouTubeDownloader {
    constructor() {
        this.currentDownloadId = null;
        this.progressInterval = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.setupFormValidation();
    }

    bindEvents() {
        // Get info button
        document.getElementById('getInfoBtn').addEventListener('click', () => {
            this.getVideoInfo();
        });

        // Download button
        document.getElementById('downloadBtn').addEventListener('click', () => {
            this.startDownload();
        });

        // Download type radio buttons
        document.querySelectorAll('input[name="downloadType"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.toggleQualitySection();
            });
        });

        // URL input enter key
        document.getElementById('videoUrl').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.getVideoInfo();
            }
        });

        // Download file button
        document.getElementById('downloadFileBtn').addEventListener('click', () => {
            this.downloadFile();
        });

        // Download another button
        document.getElementById('downloadAnotherBtn').addEventListener('click', () => {
            this.resetForm();
        });

        // Retry button
        document.getElementById('retryBtn').addEventListener('click', () => {
            this.resetToInfo();
        });
    }

    setupFormValidation() {
        const urlInput = document.getElementById('videoUrl');
        urlInput.addEventListener('input', () => {
            this.validateUrl();
        });
    }

    validateUrl() {
        const url = document.getElementById('videoUrl').value.trim();
        const errorDiv = document.getElementById('urlError');

        if (url && !this.isValidYouTubeUrl(url)) {
            this.showError(errorDiv, 'Please enter a valid YouTube URL');
            return false;
        } else {
            this.hideError(errorDiv);
            return true;
        }
    }

    isValidYouTubeUrl(url) {
        const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)([\w-]{11})(&.*)?$/;
        return youtubeRegex.test(url);
    }

    async getVideoInfo() {
        const url = document.getElementById('videoUrl').value.trim();
        const getInfoBtn = document.getElementById('getInfoBtn');

        if (!url) {
            this.showError(document.getElementById('urlError'), 'Please enter a YouTube URL');
            return;
        }

        if (!this.validateUrl()) {
            return;
        }

        // Show loading
        this.hideAllSections();
        this.showSection('loadingInfo');
        this.setButtonLoading(getInfoBtn, true);

        try {
            const response = await fetch('/get_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (response.ok) {
                this.displayVideoInfo(data);
            } else {
                throw new Error(data.error || 'Failed to get video information');
            }
        } catch (error) {
            console.error('Error getting video info:', error);
            this.showError(document.getElementById('urlError'), error.message);
            this.hideSection('loadingInfo');
        } finally {
            this.setButtonLoading(getInfoBtn, false);
        }
    }

    displayVideoInfo(info) {
        // Hide loading and show video info
        this.hideSection('loadingInfo');
        this.showSection('videoInfo');

        // Set video details
        document.getElementById('thumbnail').src = info.thumbnail;
        document.getElementById('videoTitle').textContent = info.title;
        document.getElementById('uploader').innerHTML = `<i class="fas fa-user"></i> ${info.uploader}`;
        document.getElementById('viewCount').innerHTML = `<i class="fas fa-eye"></i> ${this.formatNumber(info.view_count)} views`;
        document.getElementById('duration').textContent = this.formatDuration(info.duration);

        // Populate quality options
        const qualitySelect = document.getElementById('qualitySelect');
        qualitySelect.innerHTML = '<option value="best">Best Quality</option>';

        info.formats.forEach(format => {
            const option = document.createElement('option');
            option.value = format.quality;
            option.textContent = `${format.quality} (${format.ext.toUpperCase()})`;
            qualitySelect.appendChild(option);
        });

        // Reset download type to video
        document.querySelector('input[name="downloadType"][value="video"]').checked = true;
        this.toggleQualitySection();
    }

    toggleQualitySection() {
        const downloadType = document.querySelector('input[name="downloadType"]:checked').value;
        const qualitySection = document.getElementById('qualitySection');

        if (downloadType === 'audio') {
            qualitySection.style.display = 'none';
        } else {
            qualitySection.style.display = 'block';
        }
    }

    async startDownload() {
        const url = document.getElementById('videoUrl').value.trim();
        const downloadType = document.querySelector('input[name="downloadType"]:checked').value;
        const quality = document.getElementById('qualitySelect').value;
        const downloadBtn = document.getElementById('downloadBtn');

        this.setButtonLoading(downloadBtn, true);

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    quality: quality,
                    audio_only: downloadType === 'audio'
                })
            });

            const data = await response.json();

            if (response.ok) {
                this.currentDownloadId = data.download_id;
                this.showDownloadProgress();
                this.startProgressTracking();
            } else {
                throw new Error(data.error || 'Failed to start download');
            }
        } catch (error) {
            console.error('Error starting download:', error);
            this.showErrorSection(error.message);
        } finally {
            this.setButtonLoading(downloadBtn, false);
        }
    }

    showDownloadProgress() {
        this.hideAllSections();
        this.showSection('downloadProgress');

        // Reset progress
        document.getElementById('progressFill').style.width = '0%';
        document.getElementById('progressText').textContent = '0%';
        document.getElementById('downloadSpeed').textContent = '';
        document.getElementById('progressDetails').textContent = 'Initializing download...';
    }

    startProgressTracking() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }

        this.progressInterval = setInterval(() => {
            this.checkProgress();
        }, 1000);
    }

    async checkProgress() {
        if (!this.currentDownloadId) return;

        try {
            const response = await fetch(`/progress/${this.currentDownloadId}`);
            const progress = await response.json();

            if (progress.status === 'downloading') {
                this.updateProgress(progress);
            } else if (progress.status === 'finished') {
                this.showDownloadComplete();
                this.stopProgressTracking();
            } else if (progress.status === 'error') {
                this.showErrorSection(progress.error || 'Download failed');
                this.stopProgressTracking();
            }
        } catch (error) {
            console.error('Error checking progress:', error);
            this.showErrorSection('Connection error while tracking progress');
            this.stopProgressTracking();
        }
    }

    updateProgress(progress) {
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const downloadSpeed = document.getElementById('downloadSpeed');
        const progressDetails = document.getElementById('progressDetails');

        progressFill.style.width = `${progress.percent}%`;
        progressText.textContent = `${progress.percent}%`;

        if (progress.speed) {
            downloadSpeed.textContent = `${this.formatBytes(progress.speed)}/s`;
        }

        if (progress.eta) {
            progressDetails.textContent = `ETA: ${this.formatTime(progress.eta)}`;
        } else if (progress.downloaded && progress.total) {
            progressDetails.textContent = `${this.formatBytes(progress.downloaded)} / ${this.formatBytes(progress.total)}`;
        }
    }

    showDownloadComplete() {
        this.hideAllSections();
        this.showSection('downloadComplete');
    }

    showErrorSection(message) {
        this.hideAllSections();
        this.showSection('errorSection');
        document.getElementById('errorMessage').textContent = message;
    }

    stopProgressTracking() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    }

    downloadFile() {
        if (this.currentDownloadId) {
            window.open(`/download_file/${this.currentDownloadId}`, '_blank');
        }
    }

    resetForm() {
        this.hideAllSections();
        this.currentDownloadId = null;
        this.stopProgressTracking();
        document.getElementById('videoUrl').value = '';
        this.hideError(document.getElementById('urlError'));
    }

    resetToInfo() {
        this.hideAllSections();
        this.showSection('videoInfo');
        this.stopProgressTracking();
    }

    // Helper methods
    hideAllSections() {
        const sections = [
            'loadingInfo', 'videoInfo', 'downloadProgress', 
            'downloadComplete', 'errorSection'
        ];
        sections.forEach(sectionId => this.hideSection(sectionId));
    }

    showSection(sectionId) {
        document.getElementById(sectionId).classList.remove('hidden');
    }

    hideSection(sectionId) {
        document.getElementById(sectionId).classList.add('hidden');
    }

    showError(element, message) {
        element.textContent = message;
        element.style.display = 'block';
    }

    hideError(element) {
        element.textContent = '';
        element.style.display = 'none';
    }

    setButtonLoading(button, loading) {
        if (loading) {
            button.disabled = true;
            const originalText = button.innerHTML;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
            button.setAttribute('data-original-text', originalText);
        } else {
            button.disabled = false;
            const originalText = button.getAttribute('data-original-text');
            if (originalText) {
                button.innerHTML = originalText;
            }
        }
    }

    formatDuration(seconds) {
        if (!seconds) return '0:00';
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    formatNumber(num) {
        if (!num) return '0';
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }

    formatBytes(bytes) {
        if (!bytes) return '0 B';
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
    }

    formatTime(seconds) {
        if (!seconds) return 'Unknown';
        if (seconds < 60) return `${seconds}s`;
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}m ${remainingSeconds}s`;
    }
}

// Initialize the downloader when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new YouTubeDownloader();
});