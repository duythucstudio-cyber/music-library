from flask import Flask, request, Response, jsonify
import subprocess
import os
import sys
import time
import threading
import urllib.request
import logging
import traceback

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route("/")
def index():
    return "OK 200"

@app.route("/debug_search")
def debug_search():
    q = request.args.get("q", "lac troi").strip()
    cmd = [
        sys.executable, "-m", "yt_dlp",
        f"scsearch1:{q}",
        "--get-title", "--get-url",
        "-f", "bestaudio",
        "--no-warnings"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return jsonify({
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr
        })
    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

@app.route("/test_stream")
def test_stream():
    def gen():
        for i in range(10):
            yield b"1234567890"
            time.sleep(0.1)
    return Response(gen(), mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
