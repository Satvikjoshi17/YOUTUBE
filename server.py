import os
import uuid
import shutil
import tempfile
import threading
from flask import Flask, request, jsonify, send_file, Response
from flask import Flask, render_template, send_from_directory


from yt_dlp import YoutubeDL

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

TEMP_DIR = os.path.join(tempfile.gettempdir(), "youtube-downloader")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

JOBS = {}

def format_duration(seconds):
    if not seconds or seconds <= 0:
        return "0:00"
    h, m = divmod(int(seconds), 3600)
    m, s = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

@app.route("/api/youtube/info")
def get_info():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "YouTube URL is required"}), 400

    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        response = {
            "success": True,
            "data": {
                "id": info.get("id"),
                "title": info.get("title"),
                "description": (info.get("description", "")[:300]),
                "thumbnail": info.get("thumbnail"),
                "duration": format_duration(info.get("duration")),
                "durationSeconds": info.get("duration"),
                "channel": {
                    "name": info.get("uploader"),
                    "id": info.get("channel_id"),
                    "url": info.get("channel_url"),
                    "verified": info.get("channel_follower_count") is not None,
                    "subscriberCount": info.get("channel_follower_count"),
                },
                "stats": {
                    "viewCount": f"{info.get('view_count', 0):,}",
                    "likeCount": info.get("like_count", "N/A"),
                    "uploadDate": info.get("upload_date", "Unknown"),
                    "isLive": info.get("is_live", False),
                    "isPrivate": info.get("is_private", False),
                },
                "availableFormats": ["mp4", "webm", "mp3"],
                "tags": info.get("tags", [])[:5]
            }
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/youtube/download", methods=["POST"])
def api_download():
    # Parse request parameters
    url = request.json.get("url")
    fmt = request.json.get("format", "mp4")
    quality = request.json.get("quality", "best")
    if not url or fmt not in ("mp4", "webm", "mp3"):
        return jsonify({"success": False, "error": "Invalid input"}), 400

    job_id = str(uuid.uuid4())
    filename = f"{job_id}.{fmt}"
    output_path = os.path.join(TEMP_DIR, filename)
    JOBS[job_id] = {"status": "queued", "file": output_path}

    # Start download in background thread
    t = threading.Thread(target=download_job, args=(job_id, url, fmt, output_path, quality))
    t.daemon = True
    t.start()

    return jsonify({"success": True, "jobId": job_id})

def download_job(job_id, url, fmt, output_path, quality):
    JOBS[job_id]["status"] = "downloading"
    opts = {
        "outtmpl": output_path,
        "format": f"{quality if fmt != 'mp3' else 'bestaudio'}",
        "quiet": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
    }
    if fmt == "mp3":
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        JOBS[job_id]["status"] = "completed"
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)

@app.route('/api/progress/<job_id>')
def progress(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "Job not found"}), 404
    return jsonify({"status": job["status"], "error": job.get("error")})

@app.route("/api/download/<job_id>")
def file_download(job_id):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "completed":
        return jsonify({"success": False, "error": "File not ready"}), 400
    return send_file(job["file"], as_attachment=True, download_name=os.path.basename(job["file"]))

@app.route("/api/health")
def health():
    return jsonify({"success": True, "health": "ok", "jobCount": len(JOBS)})

@app.route('/')
def index():
    return render_template('index.html') 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
    app.run(ssl_context="adhoc")
