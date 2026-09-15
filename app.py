from flask import Flask, request, Response, jsonify
import subprocess
import os
import sys
import time
import threading
import urllib.request
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

current_track = {"title": "Chưa phát bài nào", "status": "idle", "source": "none"}

def search_stream(query):
    # Try 1: YouTube with android client
    cmd_yt = [
        sys.executable, "-m", "yt_dlp",
        f"ytsearch1:{query}",
        "--extractor-args", "youtube:player_client=android",
        "--get-title", "--get-url",
        "-f", "bestaudio/ba",
        "--no-warnings"
    ]
    try:
        res = subprocess.run(cmd_yt, capture_output=True, text=True, timeout=12)
        if res.returncode == 0:
            lines = res.stdout.strip().split("\n")
            if len(lines) >= 2 and lines[1].strip().startswith("http"):
                return lines[0].strip(), lines[1].strip(), "youtube"
    except Exception as e:
        app.logger.warning(f"YouTube search error: {e}")

    # Try 2: SoundCloud search (extremely reliable on cloud datacenter IPs)
    cmd_sc = [
        sys.executable, "-m", "yt_dlp",
        f"scsearch1:{query}",
        "--get-title", "--get-url",
        "-f", "bestaudio",
        "--no-warnings"
    ]
    try:
        res = subprocess.run(cmd_sc, capture_output=True, text=True, timeout=12)
        if res.returncode == 0:
            lines = res.stdout.strip().split("\n")
            if len(lines) >= 2 and lines[1].strip().startswith("http"):
                return lines[0].strip(), lines[1].strip(), "soundcloud"
    except Exception as e:
        app.logger.warning(f"SoundCloud search error: {e}")

    return None, None, None

@app.route("/")
def index():
    return "🎵 Xiaozhi AI Music Cloud Server is Running 24/7!"

@app.route("/status")
def status():
    return jsonify(current_track)

@app.route("/stream")
def stream_music():
    q = request.args.get("q", "").strip()
    if not q:
        return "Thiếu tên bài hát (?q=...)", 400

    app.logger.info(f"Search request: {q}")
    title, audio_url, source = search_stream(q)
    if not audio_url:
        return f"Không tìm thấy bài hát: {q}", 404

    current_track["title"] = title
    current_track["status"] = "playing"
    current_track["source"] = source
    app.logger.info(f"Playing [{source}]: {title} | URL: {audio_url[:80]}...")

    ffmpeg_cmd = [
        "ffmpeg",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", audio_url,
        "-vn",
        "-f", "mp3",
        "-ab", "96k",
        "-ar", "24000",
        "-ac", "1",
        "pipe:1"
    ]

    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=2048)

    def generate():
        try:
            while True:
                chunk = process.stdout.read(2048)
                if not chunk:
                    break
                yield chunk
        except Exception as err:
            app.logger.error(f"Stream exception: {err}")
        finally:
            try:
                process.kill()
            except Exception:
                pass
            current_track["status"] = "idle"

    # NOTE: DO NOT set Transfer-Encoding header manually in WSGI; Werkzeug handles chunked transfer automatically
    resp = Response(generate(), mimetype="audio/mpeg")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Song-Title"] = title.encode("ascii", "ignore").decode("ascii")
    resp.headers["X-Song-Source"] = source
    return resp

def keep_alive_worker():
    time.sleep(60)
    my_url = os.environ.get("RENDER_EXTERNAL_URL", "https://esp32-music-server-9not.onrender.com")
    while True:
        try:
            time.sleep(600)
            urllib.request.urlopen(my_url, timeout=10)
            app.logger.info("Keep-alive ping sent successfully")
        except Exception as e:
            app.logger.warning(f"Keep-alive ping failed: {e}")

threading.Thread(target=keep_alive_worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
