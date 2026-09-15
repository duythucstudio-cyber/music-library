from flask import Flask, request, Response, jsonify
import subprocess
import os
import sys
import time
import yt_dlp

app = Flask(__name__)

# Search cache: { query_string: (timestamp, title, audio_url) }
search_cache = {}
CACHE_TTL = 3600  # 1 hour cache

def get_youtube_audio(q):
    now = time.time()
    q_key = q.lower().strip()
    
    if q_key in search_cache:
        ts, title, url = search_cache[q_key]
        if now - ts < CACHE_TTL:
            print(f"[CACHE HIT] {q} -> {title}")
            return title, url

    ydl_opts = {
        'format': 'ba/b',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
        'skip_download': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{q}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                title = entry.get('title', q)
                audio_url = entry.get('url')
                if audio_url:
                    search_cache[q_key] = (now, title, audio_url)
                    return title, audio_url
    except Exception as e:
        print(f"[ERROR] yt-dlp search failed for {q}: {e}")
        
    return None, None

@app.route("/")
def index():
    return "Xiaozhi AI YouTube Music Cloud Server 24/7 is Running!"

@app.route("/stream")
def stream_music():
    q = request.args.get("q", "").strip()
    if not q:
        return "Missing query ?q=", 400

    t0 = time.time()
    title, audio_url = get_youtube_audio(q)
    if not audio_url:
        return f"Audio not found for {q}", 404

    print(f"[*] Stream ready for: {title} (Search took {time.time()-t0:.2f}s)")

    # Ultra-optimized ffmpeg flags for INSTANT streaming:
    # -probesize 32768 & -analyzeduration 0 prevent ffmpeg from stalling to analyze headers
    ffmpeg_cmd = [
        "ffmpeg",
        "-probesize", "32768",
        "-analyzeduration", "0",
        "-fflags", "+nobuffer+fastseek",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "3",
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
        finally:
            process.kill()

    headers = {
        "Content-Type": "audio/mpeg",
        "Transfer-Encoding": "chunked",
        "X-Song-Title": title.encode("ascii", "ignore").decode("ascii")
    }
    return Response(generate(), headers=headers)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
