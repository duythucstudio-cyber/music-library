from flask import Flask, request, Response, jsonify
import subprocess
import os
import sys
import traceback
import yt_dlp

app = Flask(__name__)

current_track = {"title": "Chua phat", "status": "idle"}

@app.route("/")
def index():
    return "Xiaozhi AI YouTube Music Cloud Server 24/7 is Running!"

@app.route("/debug")
def debug():
    q = request.args.get("q", "son tung").strip()
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{q}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                return jsonify({
                    'status': 'ok',
                    'title': entry.get('title'),
                    'url': entry.get('url'),
                    'formats_count': len(entry.get('formats', []))
                })
            else:
                return jsonify({'status': 'no_entries', 'info': str(info)[:300]})
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route("/play")
def play():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Thieu query"}), 400
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{q}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                title = entry.get('title', q)
                return jsonify({"title": title, "stream_url": f"/stream?q={q}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"error": "Khong tim thay"}), 404

@app.route("/stream")
def stream_music():
    q = request.args.get("q", "").strip()
    if not q:
        return "Thieu ten bai hat", 400

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
    }
    audio_url = None
    title = q
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{q}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                title = entry.get('title', q)
                audio_url = entry.get('url')
    except Exception as e:
        return f"Loi tim kiem: {e}", 500

    if not audio_url:
        return "Khong tim thay audio stream", 404

    current_track["title"] = title
    current_track["status"] = "playing"

    ffmpeg_cmd = [
        "ffmpeg",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", audio_url,
        "-vn",
        "-f", "mp3",
        "-ab", "128k",
        "-ar", "24000",
        "-ac", "1",
        "pipe:1"
    ]

    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=4096)

    def generate():
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()
            current_track["status"] = "idle"

    headers = {
        "Content-Type": "audio/mpeg",
        "Transfer-Encoding": "chunked",
        "X-Song-Title": title.encode("ascii", "ignore").decode("ascii")
    }
    return Response(generate(), headers=headers)

@app.route("/status")
def status():
    return jsonify(current_track)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
