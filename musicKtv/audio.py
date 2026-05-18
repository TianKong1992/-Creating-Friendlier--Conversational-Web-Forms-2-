"""
音频处理模块 — ffmpeg 混音、录音列表管理
"""
import subprocess
import os
import time


def mix_audio(voice_path: str, accomp_path: str, out_path: str) -> None:
    """将人声与伴奏混合，输出 MP3"""
    args = [
        "ffmpeg", "-y",
        "-i", voice_path,
        "-i", accomp_path,
        "-filter_complex",
        "[0:a]volume=1.8[voice];[1:a]volume=0.85[acc];[voice][acc]amix=inputs=2:duration=first[out]",
        "-map", "[out]",
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        "-shortest",
        out_path,
    ]
    subprocess.run(args, capture_output=True, text=True, timeout=120, check=True)


def get_recordings(recording_dir: str) -> list[dict]:
    """列出所有已混音录音"""
    results = []
    if not os.path.isdir(recording_dir):
        return results
    for f in sorted(os.listdir(recording_dir), reverse=True):
        if f.startswith("_temp"):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in (".mp3", ".mp4", ".webm"):
            continue
        full = os.path.join(recording_dir, f)
        size = os.path.getsize(full)
        mtime = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(full))
        )
        results.append({
            "filename": f,
            "size": _fmt_size(size),
            "time": mtime,
        })
    return results


def get_recording_path(recording_dir: str, filename: str) -> str:
    return os.path.join(recording_dir, filename)


def _fmt_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
