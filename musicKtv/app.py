"""
音乐KTV — Flask 后端入口
搜索伴奏、管理歌单、人声合成
"""
import os
import json
import threading
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template

from search import (
    search_songs, download_accompaniment, download_accompaniment_async,
    search_lyrics, init_cache_dir, is_cached, get_cached_path,
)
from audio import mix_audio, get_recordings

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
RECORDING_DIR = BASE_DIR / "recordings"
DATA_DIR = BASE_DIR / "data"
PLAYLIST_FILE = DATA_DIR / "playlist.json"
SUNG_FILE = DATA_DIR / "sung.json"

DOWNLOAD_DIR.mkdir(exist_ok=True)
RECORDING_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

init_cache_dir(str(DOWNLOAD_DIR))

app = Flask(__name__)


def _load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _save_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 搜索 ───────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "请输入搜索关键词"}), 400
    try:
        results = search_songs(q)
        for r in results:
            r["cached"] = is_cached(r.get("title", ""))
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 歌词 ───────────────────────────────────────────────────

@app.route("/api/lyrics")
def api_lyrics():
    title = request.args.get("title", "").strip()
    artist = request.args.get("artist", "").strip()
    if not title:
        return jsonify({"error": "缺少歌名"}), 400
    try:
        lrc = search_lyrics(title, artist)
        return jsonify({"lyrics": lrc})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 伴奏下载 ───────────────────────────────────────────────

_download_tasks = {}  # task_id → {status, progress, speed, eta, filename, error}


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    url = data.get("url", "")
    title = data.get("title", "unknown")
    if not url:
        return jsonify({"error": "缺少下载链接"}), 400

    if is_cached(title):
        cached = get_cached_path(title)
        return jsonify({
            "path": cached,
            "filename": os.path.basename(cached),
            "cached": True,
        })

    task_id = str(_timestamp_int())
    _download_tasks[task_id] = {
        "status": "downloading",
        "progress": 0,
        "speed": "",
        "eta": "",
        "filename": None,
        "error": None,
    }

    def _run():
        try:
            def _on_progress(pct, speed, eta):
                _download_tasks[task_id]["progress"] = int(pct)
                _download_tasks[task_id]["speed"] = speed
                _download_tasks[task_id]["eta"] = eta

            path = download_accompaniment_async(
                url, title, str(DOWNLOAD_DIR), _on_progress,
            )
            _download_tasks[task_id]["status"] = "complete"
            _download_tasks[task_id]["filename"] = os.path.basename(path)
            _download_tasks[task_id]["progress"] = 100
        except Exception as e:
            _download_tasks[task_id]["status"] = "error"
            _download_tasks[task_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"task_id": task_id, "status": "downloading"})


@app.route("/api/download/status/<task_id>")
def api_download_status(task_id):
    task = _download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task)


@app.route("/downloads/<filename>")
def serve_download(filename):
    return send_file(DOWNLOAD_DIR / filename)


# ── 已点歌单 ───────────────────────────────────────────────

@app.route("/api/playlist", methods=["GET", "POST", "DELETE"])
def api_playlist():
    if request.method == "GET":
        return jsonify({"playlist": _load_json(PLAYLIST_FILE)})

    if request.method == "POST":
        song = request.get_json()
        plist = _load_json(PLAYLIST_FILE)
        song["id"] = str(_timestamp_int())
        plist.append(song)
        _save_json(PLAYLIST_FILE, plist)
        return jsonify({"playlist": plist, "added": song})

    if request.method == "DELETE":
        song_id = request.args.get("id", "")
        plist = _load_json(PLAYLIST_FILE)
        plist = [s for s in plist if s.get("id") != song_id]
        _save_json(PLAYLIST_FILE, plist)
        return jsonify({"playlist": plist})


# ── 已唱列表 ───────────────────────────────────────────────

@app.route("/api/sung", methods=["GET", "POST", "DELETE"])
def api_sung():
    if request.method == "GET":
        return jsonify({"sung": _load_json(SUNG_FILE)})

    if request.method == "POST":
        song = request.get_json()
        slist = _load_json(SUNG_FILE)
        url = song.get("url", "")
        if not any(s.get("url") == url for s in slist):
            song["id"] = str(_timestamp_int())
            slist.append(song)
            _save_json(SUNG_FILE, slist)
        return jsonify({"sung": slist})

    if request.method == "DELETE":
        _save_json(SUNG_FILE, [])
        return jsonify({"sung": []})


# ── 人声合成 ──────────────────────────────────────────────

@app.route("/api/mix", methods=["POST"])
def api_mix():
    voice = request.files.get("voice")
    accomp_filename = request.form.get("accompaniment", "")
    title = request.form.get("title", "recording")

    if not voice or not accomp_filename:
        return jsonify({"error": "缺少人声或伴奏文件"}), 400

    accomp_path = str(DOWNLOAD_DIR / accomp_filename)
    if not os.path.exists(accomp_path):
        return jsonify({"error": "伴奏文件不存在，请重新下载"}), 404

    voice_path = str(RECORDING_DIR / "_temp_voice.webm")
    voice.save(voice_path)

    try:
        out_name = f"{title}_{_timestamp()}.mp3"
        out_path = str(RECORDING_DIR / out_name)
        mix_audio(voice_path, accomp_path, out_path)
    finally:
        try:
            os.remove(voice_path)
        except Exception:
            pass

    return jsonify({"filename": out_name, "url": f"/recordings/{out_name}"})


@app.route("/recordings/<filename>")
def serve_recording(filename):
    return send_file(RECORDING_DIR / filename)


@app.route("/api/recordings", methods=["GET", "DELETE"])
def api_recordings():
    if request.method == "DELETE":
        for f in RECORDING_DIR.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                except Exception:
                    pass
        return jsonify({"ok": True})
    return jsonify({"recordings": get_recordings(str(RECORDING_DIR))})


@app.route("/api/recordings/<filename>", methods=["DELETE"])
def api_delete_recording(filename):
    filepath = RECORDING_DIR / filename
    if filepath.exists():
        try:
            filepath.unlink()
        except Exception:
            pass
    return jsonify({"ok": True})


# ── 页面 ───────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


def _timestamp():
    import time
    return time.strftime("%Y%m%d_%H%M%S")


def _timestamp_int():
    import time
    return str(int(time.time() * 1000))


if __name__ == "__main__":
    print("Music KTV starting...")
    print("   Open browser: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
