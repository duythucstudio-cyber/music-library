from flask import Flask, request, Response, jsonify
import subprocess
import os
import sys

app = Flask(__name__)

current_track = {"title": "Chưa phát bài nào", "status": "idle"}

def get_youtube_stream_info(query):
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            f"ytsearch1:{query}",
            "--get-title",
            "--get-url",
            "-f", "bestaudio/ba",
            "--no-warnings"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if res.returncode == 0:
            lines = res.stdout.strip().split("\n")
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()
    except Exception as e:
        print(f"Lỗi tìm kiếm: {e}")
    return None, None

@app.route("/")
def index():
    return "🎵 Xiaozhi AI YouTube Music Cloud Server 24/7 is Running!"

@app.route("/stream")
def stream_music():
    q = request.args.get("q", "").strip()
    if not q:
        return "Thiếu tên bài hát (?q=...)", 400

    title, audio_url = get_youtube_stream_info(q)
    if not audio_url:
        return "Không tìm thấy bài hát", 404

    print(f"[*] Đang phát: {title}")
    current_track["title"] = title
    current_track["status"] = "playing"

    # Transcode audio to 24000Hz mono MP3 128kbps matching ESP32 AudioCodec exactly
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

@app.route("/play")
def play():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Thiếu query"}), 400
    title, url = get_youtube_stream_info(q)
    if not url:
        return jsonify({"error": "Không tìm thấy bài hát"}), 404
    return jsonify({"title": title, "stream_url": f"/stream?q={q}"})

@app.route("/status")
def status():
    return jsonify(current_track)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
