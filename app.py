import os
import logging
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
import yt_dlp
from datetime import datetime
import uuid
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['DOWNLOAD_FOLDER'] = os.path.join(os.getcwd(), 'downloads')
app.config['TEMP_FOLDER'] = tempfile.gettempdir()

# Create directories if they don't exist
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Global dictionary to store download progress
download_progress = {}

def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters"""
    import re
    # Remove invalid characters for filenames
    filename = re.sub(r'[<>:"/\|?*]', '', filename)
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    return filename[:200]  # Limit filename length

def get_video_info(url):
    """Extract video information without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extractflat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Get available formats
            formats = []
            if 'formats' in info:
                seen_qualities = set()
                for fmt in info['formats']:
                    if fmt.get('vcodec') != 'none' and fmt.get('height'):  # Video formats only
                        quality = f"{fmt.get('height')}p"
                        if quality not in seen_qualities:
                            formats.append({
                                'format_id': fmt['format_id'],
                                'quality': quality,
                                'ext': fmt.get('ext', 'mp4'),
                                'filesize': fmt.get('filesize', 0)
                            })
                            seen_qualities.add(quality)

            # Sort by quality (highest first)
            formats.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)

            return {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats[:10]  # Limit to top 10 formats
            }
    except Exception as e:
        logger.error(f"Error extracting video info: {str(e)}")
        return None

def progress_hook(d, download_id):
    """Progress callback for yt-dlp"""
    global download_progress

    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)

        if total > 0:
            percent = (downloaded / total) * 100
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)

            download_progress[download_id] = {
                'status': 'downloading',
                'percent': round(percent, 1),
                'speed': speed,
                'eta': eta,
                'downloaded': downloaded,
                'total': total
            }
    elif d['status'] == 'finished':
        download_progress[download_id] = {
            'status': 'finished',
            'percent': 100,
            'filename': d.get('filename', '')
        }

def download_video(url, quality, audio_only, download_id):
    """Download video in a separate thread"""
    global download_progress

    try:
        # Sanitize filename template
        output_template = os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s.%(ext)s')

        if audio_only:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'progress_hooks': [lambda d: progress_hook(d, download_id)],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'ffmpeg_location': os.environ.get('FFMPEG_PATH', '/usr/bin/ffmpeg'),
            }
        else:
            if quality == 'best':
                format_selector = 'best[height<=1080]/best'
            else:
                height = quality.replace('p', '')
                format_selector = f'best[height<={height}]/best'

            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'progress_hooks': [lambda d: progress_hook(d, download_id)],
                'ffmpeg_location': os.environ.get('FFMPEG_PATH', '/usr/bin/ffmpeg'),
                'merge_output_format': 'mp4',
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        download_progress[download_id] = {
            'status': 'error',
            'error': str(e)
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    """Get video information endpoint"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Validate URL
        if 'youtube.com/watch' not in url and 'youtu.be/' not in url:
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400

        video_info = get_video_info(url)
        if not video_info:
            return jsonify({'error': 'Could not extract video information'}), 400

        return jsonify(video_info)

    except Exception as e:
        logger.error(f"Error in get_info: {str(e)}")
        return jsonify({'error': 'An error occurred while processing the request'}), 500

@app.route('/download', methods=['POST'])
def download():
    """Start download endpoint"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        quality = data.get('quality', 'best')
        audio_only = data.get('audio_only', False)

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Generate unique download ID
        download_id = str(uuid.uuid4())

        # Initialize progress
        download_progress[download_id] = {
            'status': 'starting',
            'percent': 0
        }

        # Start download in background thread
        thread = threading.Thread(
            target=download_video, 
            args=(url, quality, audio_only, download_id)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'download_id': download_id,
            'message': 'Download started'
        })

    except Exception as e:
        logger.error(f"Error starting download: {str(e)}")
        return jsonify({'error': 'Failed to start download'}), 500

@app.route('/progress/<download_id>')
def get_progress(download_id):
    """Get download progress endpoint"""
    progress = download_progress.get(download_id, {'status': 'not_found'})
    return jsonify(progress)

@app.route('/download_file/<download_id>')
def download_file(download_id):
    """Download completed file"""
    try:
        progress = download_progress.get(download_id)
        if not progress or progress.get('status') != 'finished':
            return jsonify({'error': 'File not ready or not found'}), 404

        filename = progress.get('filename')
        if not filename or not os.path.exists(filename):
            return jsonify({'error': 'File not found'}), 404

        return send_file(filename, as_attachment=True)

    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': 'Error downloading file'}), 500

@app.errorhandler(404)
def not_found(error):
    return render_template('index.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': 'File too large'}), 413

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
