"""
音乐搜索模块 — Bilibili 搜索 API + yt-dlp 伴奏下载
"""
import os
import re
import json
import subprocess
import urllib.request
import urllib.parse

YT_DLP = "yt-dlp"

BILIBILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

CACHE_DIR = ""


def init_cache_dir(path: str):
    global CACHE_DIR
    CACHE_DIR = path


def _get_cache_path(title: str) -> str:
    safe = "".join(c for c in title if c not in r'\/:*?"<>|')[:60]
    return os.path.join(CACHE_DIR, f"{safe}.mp3")


def is_cached(title: str) -> bool:
    return os.path.exists(_get_cache_path(title))


def get_cached_path(title: str) -> str:
    return _get_cache_path(title)


# ── 搜索 ───────────────────────────────────────────────────

def search_songs(query: str, source: str = "") -> list[dict]:
    """Bilibili 搜索伴奏"""
    results = _search_bilibili_api(query + " 伴奏")
    results.sort(key=lambda r: r.get("play_count", 0), reverse=True)
    return results[:20]


def _search_bilibili_api(query: str) -> list[dict]:
    """通过 Bilibili 搜索 API 获取结果"""
    results = []
    params = urllib.parse.urlencode({"keyword": query, "page": 1})
    api_url = f"https://api.bilibili.com/x/web-interface/search/all/v2?{params}"

    try:
        req = urllib.request.Request(api_url, headers=BILIBILI_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return _search_bilibili_fallback(query)

    if data.get("code") != 0:
        return _search_bilibili_fallback(query)

    for item in data.get("data", {}).get("result", []):
        if item.get("result_type") != "video":
            continue
        for v in item.get("data", []):
            title = re.sub(r'<.*?>', '', v.get("title", "")).strip()
            title = title.replace("&nbsp;", " ")
            if not title:
                continue

            duration_str = v.get("duration", "") or ""
            duration = _parse_bili_duration(duration_str)

            bvid = v.get("bvid", "")
            aid = v.get("aid", "")
            url = v.get("arcurl", "") or f"https://www.bilibili.com/video/{bvid}"

            results.append({
                "id": bvid or str(aid),
                "title": title,
                "artist": v.get("author", ""),
                "duration": duration,
                "url": url,
                "thumbnail": v.get("pic", ""),
                "source": "bilibili",
                "play_count": v.get("play", 0),
                "bvid": bvid,
                "aid": str(aid) if aid else "",
            })

    return results


def _search_bilibili_fallback(query: str) -> list[dict]:
    """备用: yt-dlp bilisearch"""
    results = []
    search_query = f"bilisearch15:{query}"

    args = [
        YT_DLP, search_query,
        "--dump-json", "--no-warnings",
        "--ignore-errors", "--socket-timeout", "15",
        "--extractor-retries", "2",
    ]

    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return results

    for line in proc.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            info = json.loads(line)
        except json.JSONDecodeError:
            continue

        dur = info.get("duration")
        if dur and dur > 1200:
            continue

        title = info.get("title") or info.get("fulltitle") or ""
        title = re.sub(r'\s*[\[【].*?[\]】]\s*', ' ', title).strip()

        results.append({
            "id": info.get("id", ""),
            "title": title,
            "artist": info.get("uploader") or info.get("channel") or "",
            "duration": _fmt_duration(dur),
            "url": info.get("webpage_url") or info.get("url") or "",
            "thumbnail": info.get("thumbnail") or "",
            "source": "bilibili",
            "play_count": info.get("view_count") or 0,
        })

    return results


# ── 伴奏下载 (音频) ─────────────────────────────────────────

def download_accompaniment(url: str, title: str, download_dir: str) -> str:
    """下载B站伴奏音频为 MP3，返回缓存路径"""
    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')[:60]
    out_path = os.path.join(download_dir, f"{safe_title}.mp3")

    if os.path.exists(out_path):
        return out_path

    out_tmpl = os.path.join(download_dir, f"{safe_title}.%(ext)s")

    args = [
        YT_DLP, url,
        "-f", "bestaudio/best",
        "-o", out_tmpl,
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "192K",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout", "30",
        "--retries", "3",
    ]

    cookie_file = os.path.join(os.path.dirname(download_dir), "cookies.txt")
    if os.path.exists(cookie_file):
        args += ["--cookies", cookie_file]

    subprocess.run(args, capture_output=True, text=True, timeout=300)

    if os.path.exists(out_path):
        return out_path

    for ext in ("mp3", "m4a", "webm", "opus"):
        candidate = os.path.join(download_dir, f"{safe_title}.{ext}")
        if os.path.exists(candidate):
            return candidate

    for f in os.listdir(download_dir):
        if safe_title[:20] in f and not f.endswith(".part") and not f.endswith(".ytdl"):
            return os.path.join(download_dir, f)

    raise RuntimeError(f"下载失败: {title}")


def download_accompaniment_async(url: str, title: str, download_dir: str, progress_callback=None) -> str:
    """下载伴奏并报告进度。progress_callback(percentage, speed, eta)"""
    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')[:60]
    out_path = os.path.join(download_dir, f"{safe_title}.mp3")

    if os.path.exists(out_path):
        if progress_callback:
            progress_callback(100, "", "")
        return out_path

    out_tmpl = os.path.join(download_dir, f"{safe_title}.%(ext)s")

    args = [
        YT_DLP, url,
        "-f", "bestaudio/best",
        "-o", out_tmpl,
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "192K",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout", "30",
        "--retries", "3",
        "--newline",
    ]

    cookie_file = os.path.join(os.path.dirname(download_dir), "cookies.txt")
    if os.path.exists(cookie_file):
        args += ["--cookies", cookie_file]

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    for line in proc.stderr:
        if progress_callback:
            m = re.search(r'\[download\]\s+([\d.]+)%', line)
            if m:
                pct = float(m.group(1))
                speed_m = re.search(r'at\s+(\S+)', line)
                eta_m = re.search(r'ETA\s+(\S+)', line)
                speed = speed_m.group(1) if speed_m else ""
                eta = eta_m.group(1) if eta_m else ""
                progress_callback(pct, speed, eta)

    proc.wait()

    if os.path.exists(out_path):
        return out_path

    for ext in ("mp3", "m4a", "webm", "opus"):
        candidate = os.path.join(download_dir, f"{safe_title}.{ext}")
        if os.path.exists(candidate):
            return candidate

    for f in os.listdir(download_dir):
        if safe_title[:20] in f and not f.endswith(".part") and not f.endswith(".ytdl"):
            return os.path.join(download_dir, f)

    raise RuntimeError(f"下载失败: {title}")


# ── 歌词 ───────────────────────────────────────────────

def search_lyrics(title: str, artist: str = "") -> str:
    """获取歌词 (网易云 API)"""
    try:
        params = urllib.parse.urlencode({"s": f"{title} {artist}", "type": 1, "limit": 1})
        api_url = f"https://music.163.com/api/search/get?{params}"
        req = urllib.request.Request(api_url, headers={
            **BILIBILI_HEADERS,
            "Referer": "https://music.163.com/",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        songs = data.get("result", {}).get("songs", [])
        if songs:
            song_id = songs[0]["id"]
            lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1"
            req2 = urllib.request.Request(lyric_url, headers={
                **BILIBILI_HEADERS,
                "Referer": "https://music.163.com/",
            })
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                lyric_data = json.loads(resp2.read().decode("utf-8"))
            return lyric_data.get("lrc", {}).get("lyric", "")
    except Exception:
        pass
    return ""


def _parse_bili_duration(s: str) -> str:
    if not s:
        return ""
    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{h * 60 + m}:{sec:02d}"
    elif len(parts) == 2:
        return s
    return s


def _fmt_duration(seconds) -> str:
    if not seconds:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"
