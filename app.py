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

# In-memory lottery cache: {station: (timestamp, text_result)}
lottery_cache = {}
CACHE_TTL = 300  # 5 minutes

STATIONS = [
    "mien-bac-xsmb", "mien-nam-xsmn", "mien-trung-xsmt",
    "ho-chi-minh-xshcm", "da-nang-xsdng", "can-tho-xsct",
    "dong-nai-xsdn", "vung-tau-xsvt", "ben-tre-xsbt",
    "an-giang-xsag", "tay-ninh-xstn", "tien-giang-xstg",
    "kien-giang-xskg", "khanh-hoa-xskh", "thua-thien-hue-xstth"
]

def fetch_lottery_from_xskt(station):
    url = f"https://xskt.com.vn/rss-feed/{station}.rss"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=6) as r:
            xml = r.read(4096).decode("utf-8", errors="ignore")
            item_pos = xml.find("<item>")
            if item_pos != -1:
                t_s = xml.find("<title>", item_pos)
                t_e = xml.find("</title>", item_pos)
                d_s = xml.find("<description>", item_pos)
                d_e = xml.find("</description>", item_pos)
                if t_s != -1 and t_e != -1 and d_s != -1 and d_e != -1:
                    title = xml[t_s+7:t_e].strip()
                    desc = xml[d_s+13:d_e].strip().replace("\n", ". ")
                    res = f"[KẾT QUẢ XỔ SỐ CHÍNH XÁC]: {title}\nChi tiết giải thưởng: {desc}\n(Hãy đọc rõ ràng chi tiết con số trúng thưởng từng giải: Đặc Biệt, giải Nhất, giải Nhì, giải Ba... cho người dùng nghe)"
                    return res
    except Exception as e:
        app.logger.warning(f"Error fetching {station}: {e}")
    return None

def lottery_background_updater():
    """Background worker: keeps Render awake and refreshes top lottery results every 4 minutes"""
    time.sleep(3)
    while True:
        try:
            for s in ["mien-bac-xsmb", "mien-nam-xsmn", "mien-trung-xsmt"]:
                res = fetch_lottery_from_xskt(s)
                if res:
                    lottery_cache[s] = (time.time(), res)
                    app.logger.info(f"[CACHE UPDATED] {s}")
                time.sleep(2)
        except Exception as e:
            app.logger.error(f"Updater error: {e}")
        time.sleep(240)  # Refresh every 4 minutes (prevents Render idle sleep!)

# Start background daemon thread
updater_thread = threading.Thread(target=lottery_background_updater, daemon=True)
updater_thread.start()

def search_stream(query):
    # Try 1: YouTube with android player client
    cmd_yt = [
        sys.executable, "-m", "yt_dlp",
        f"ytsearch1:{query}",
        "--extractor-args", "youtube:player_client=android",
        "--get-title", "--get-url",
        "-f", "bestaudio/ba",
        "--no-warnings"
    ]
    try:
        res = subprocess.run(cmd_yt, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            lines = res.stdout.strip().split("\n")
            if len(lines) >= 2 and lines[1].strip().startswith("http"):
                return lines[0].strip(), lines[1].strip(), "youtube"
    except Exception as e:
        app.logger.warning(f"YouTube search error: {e}")

    # Try 2: SoundCloud search
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
    return "🎵 Xiaozhi AI Music & Instant Lottery Cloud Server 24/7 is Running!"

@app.route("/status")
def status():
    return jsonify(current_track)

@app.route("/lottery")
def get_lottery():
    station = request.args.get("station", "mien-bac-xsmb").strip()
    if not station:
        station = "mien-bac-xsmb"
    
    # Check cache first for 0.001s instant response!
    if station in lottery_cache:
        t, cached_text = lottery_cache[station]
        if time.time() - t < CACHE_TTL:
            return cached_text
    
    # If not in cache or expired, fetch live
    res = fetch_lottery_from_xskt(station)
    if res:
        lottery_cache[station] = (time.time(), res)
        return res
    
    # Fallback to cached if available
    if station in lottery_cache:
        return lottery_cache[station][1]

    return "Chưa cập nhật được kết quả xổ số", 404

@app.route("/stream")
def stream_music():
    q = request.args.get("q", "").strip()
    if not q:
        return "Thiếu tên bài hát (?q=...)", 400

    title, audio_url, source = search_stream(q)
    if not audio_url:
        return "Không tìm thấy bài hát trên YouTube/SoundCloud", 404

    current_track["title"] = title
    current_track["status"] = "playing"
    current_track["source"] = source

    app.logger.info(f"[*] Streaming: {title} ({source})")

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
                data = process.stdout.read(2048)
                if not data:
                    break
                yield data
        finally:
            process.kill()
            current_track["status"] = "idle"

    headers = {
        "Content-Type": "audio/mpeg",
        "Transfer-Encoding": "chunked",
        "X-Song-Title": title.encode("ascii", "ignore").decode("ascii")
    }
    return Response(generate(), headers=headers)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
