import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess
import yt_dlp
import os


class VideoDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("视频下载器")
        self.root.geometry("820x620")
        self.root.resizable(True, True)
        self.root.minsize(700, 520)

        self.formats = []
        self.audio_formats = []
        self.video_title = ""
        self.output_dir = os.path.expanduser("~\\Downloads")
        self._has_ffmpeg = self._check_ffmpeg()

        self.video_checked_iid = None
        self.audio_checked_iid = None

        self._build_ui()

    @staticmethod
    def _check_ffmpeg():
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

    def _build_ui(self):
        # URL 输入区
        url_frame = ttk.Frame(self.root, padding="8")
        url_frame.pack(fill=tk.X)
        ttk.Label(url_frame, text="视频链接:").pack(side=tk.LEFT)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self.query_btn = ttk.Button(url_frame, text="查询", command=self._query_formats)
        self.query_btn.pack(side=tk.LEFT)
        self.root.bind("<Return>", lambda e: self._query_formats())

        # 视频格式列表
        video_frame = ttk.LabelFrame(self.root, text="视频格式 (勾选一个)", padding="4")
        video_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        v_columns = ("vselect", "id", "resolution", "vbr", "ext", "codec", "filesize", "note")
        self.video_tree = ttk.Treeview(video_frame, columns=v_columns, show="headings",
                                       height=6, selectmode="none")
        self.video_tree.heading("vselect", text="☐")
        self.video_tree.heading("id", text="格式ID")
        self.video_tree.heading("resolution", text="分辨率")
        self.video_tree.heading("vbr", text="码率")
        self.video_tree.heading("ext", text="扩展名")
        self.video_tree.heading("codec", text="编码")
        self.video_tree.heading("filesize", text="文件大小")
        self.video_tree.heading("note", text="备注")
        self.video_tree.column("vselect", width=36, anchor=tk.CENTER)
        self.video_tree.column("id", width=70, anchor=tk.CENTER)
        self.video_tree.column("resolution", width=100, anchor=tk.CENTER)
        self.video_tree.column("vbr", width=85, anchor=tk.CENTER)
        self.video_tree.column("ext", width=60, anchor=tk.CENTER)
        self.video_tree.column("codec", width=150, anchor=tk.CENTER)
        self.video_tree.column("filesize", width=90, anchor=tk.CENTER)
        self.video_tree.column("note", width=180, anchor=tk.CENTER)

        v_scroll = ttk.Scrollbar(video_frame, orient=tk.VERTICAL, command=self.video_tree.yview)
        self.video_tree.configure(yscrollcommand=v_scroll.set)
        self.video_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.video_tree.bind("<ButtonRelease-1>", self._on_video_click)

        # 音频格式列表
        audio_frame = ttk.LabelFrame(self.root, text="音频格式 (勾选一个)", padding="4")
        audio_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 0))

        a_columns = ("aselect", "aid", "bitrate", "aext", "acodec", "afilesize", "alang")
        self.audio_tree = ttk.Treeview(audio_frame, columns=a_columns, show="headings",
                                       height=4, selectmode="none")
        self.audio_tree.heading("aselect", text="☐")
        self.audio_tree.heading("aid", text="格式ID")
        self.audio_tree.heading("bitrate", text="码率/音质")
        self.audio_tree.heading("aext", text="扩展名")
        self.audio_tree.heading("acodec", text="编码")
        self.audio_tree.heading("afilesize", text="文件大小")
        self.audio_tree.heading("alang", text="语言/备注")
        self.audio_tree.column("aselect", width=36, anchor=tk.CENTER)
        self.audio_tree.column("aid", width=80, anchor=tk.CENTER)
        self.audio_tree.column("bitrate", width=120, anchor=tk.CENTER)
        self.audio_tree.column("aext", width=70, anchor=tk.CENTER)
        self.audio_tree.column("acodec", width=140, anchor=tk.CENTER)
        self.audio_tree.column("afilesize", width=100, anchor=tk.CENTER)
        self.audio_tree.column("alang", width=120, anchor=tk.CENTER)

        a_scroll = ttk.Scrollbar(audio_frame, orient=tk.VERTICAL, command=self.audio_tree.yview)
        self.audio_tree.configure(yscrollcommand=a_scroll.set)
        self.audio_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        a_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.audio_tree.bind("<ButtonRelease-1>", self._on_audio_click)

        # 输出目录
        dir_frame = ttk.Frame(self.root, padding="8 4 8 4")
        dir_frame.pack(fill=tk.X)
        ttk.Label(dir_frame, text="保存目录:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=self.output_dir)
        self.dir_label = ttk.Label(dir_frame, textvariable=self.dir_var, foreground="gray")
        self.dir_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self.browse_btn = ttk.Button(dir_frame, text="浏览", command=self._browse_dir)
        self.browse_btn.pack(side=tk.LEFT)

        # 进度条
        prog_frame = ttk.Frame(self.root, padding="8 4 8 4")
        prog_frame.pack(fill=tk.X)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill=tk.X)

        # 下载按钮
        btn_frame = ttk.Frame(self.root, padding="8 4 8 8")
        btn_frame.pack(fill=tk.X)
        self.dl_btn = ttk.Button(btn_frame, text="下载选中视频", command=self._download_selected)
        self.dl_btn.pack(side=tk.LEFT)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪 — 请粘贴视频链接并点击查询")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                               anchor=tk.W, padding="4 2 4 2")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _on_video_click(self, event):
        col = self.video_tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.video_tree.identify_row(event.y)
        if not iid:
            return
        self._toggle_video_check(iid)

    def _toggle_video_check(self, iid):
        if self.video_checked_iid == iid:
            self.video_tree.set(iid, "vselect", "☐")
            self.video_checked_iid = None
        else:
            if self.video_checked_iid:
                self.video_tree.set(self.video_checked_iid, "vselect", "☐")
            self.video_tree.set(iid, "vselect", "☑")
            self.video_checked_iid = iid

    def _on_audio_click(self, event):
        col = self.audio_tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.audio_tree.identify_row(event.y)
        if not iid:
            return
        self._toggle_audio_check(iid)

    def _toggle_audio_check(self, iid):
        if self.audio_checked_iid == iid:
            self.audio_tree.set(iid, "aselect", "☐")
            self.audio_checked_iid = None
        else:
            if self.audio_checked_iid:
                self.audio_tree.set(self.audio_checked_iid, "aselect", "☐")
            self.audio_tree.set(iid, "aselect", "☑")
            self.audio_checked_iid = iid

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir, title="选择保存目录")
        if chosen:
            self.output_dir = chosen
            self.dir_var.set(chosen)

    def _query_formats(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return

        self.query_btn.config(state=tk.DISABLED)
        self.status_var.set("正在获取视频信息...")
        threading.Thread(target=self._do_query, args=(url,), daemon=True).start()

    @staticmethod
    def _format_bytes(size_bytes):
        if size_bytes <= 0:
            return "未知"
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024**3):.1f} GB"
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024**2):.1f} MB"
        return f"{size_bytes / 1024:.1f} KB"

    @staticmethod
    def _format_bitrate(kbps):
        if kbps <= 0:
            return "未知"
        if kbps >= 1000:
            return f"{kbps / 1000:.1f} Mbps"
        return f"{kbps:.0f} Kbps"

    def _do_query(self, url):
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._on_query_error, f"获取信息失败: {e}")
            return

        self.video_title = info.get("title", "未知")
        duration = info.get("duration") or 0
        raw_formats = info.get("formats", [])

        video_formats = []
        audio_formats = []

        for f in raw_formats:
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")

            # 音频格式 (无视频轨道)
            if vcodec == "none" and acodec != "none":
                abr = f.get("abr") or f.get("tbr") or 0
                if abr:
                    abr_str = f"{abr:.0f} kbps"
                else:
                    asr = f.get("asr")
                    abr_str = f"{asr} Hz" if asr else "未知"

                filesize = f.get("filesize") or f.get("filesize_approx") or 0
                if not filesize and abr and duration:
                    filesize = int(abr * 1000 / 8 * duration)

                audio_formats.append({
                    "id": f.get("format_id", ""),
                    "bitrate": abr_str,
                    "ext": f.get("ext", "未知"),
                    "codec": acodec.split(".")[0] if acodec else "未知",
                    "filesize": self._format_bytes(filesize),
                    "lang": f.get("language") or "",
                    "note": f.get("format_note", ""),
                    "_abr": abr,
                    "_bytes": filesize,
                })
                continue

            # 视频格式 (有视频轨道)
            if vcodec == "none":
                continue

            height = f.get("height")
            width = f.get("width")
            if height and width:
                res = f"{width}x{height}"
            elif height:
                res = f"{height}p"
            else:
                res = "未知"

            filesize = f.get("filesize") or f.get("filesize_approx") or 0
            if not filesize:
                tbr = f.get("tbr") or 0
                if tbr and duration:
                    filesize = int(tbr * 1000 / 8 * duration)

            note = f.get("format_note", "")
            fmt_id = f.get("format_id", "")

            codec_parts = []
            if vcodec and vcodec != "none":
                codec_parts.append(vcodec.split(".")[0])
            if acodec and acodec != "none":
                codec_parts.append(acodec.split(".")[0])
            codec = "+".join(codec_parts) if codec_parts else "未知"

            has_audio = acodec != "none"
            if not has_audio:
                note = (note + " ").rstrip() + " 无音频"

            # 码率: 优先用 vbr，否则用 tbr
            vbr = f.get("vbr") or f.get("tbr") or 0

            video_formats.append({
                "id": fmt_id,
                "resolution": res,
                "vbr": self._format_bitrate(vbr),
                "ext": f.get("ext", "未知"),
                "codec": codec,
                "filesize": self._format_bytes(filesize),
                "note": note,
                "_height": height or 0,
                "_vbr": vbr,
                "_has_audio": has_audio,
                "_bytes": filesize,
            })

        # 按分辨率降序，同分辨率按码率降序
        video_formats.sort(key=lambda x: (x["_height"], x["_vbr"]), reverse=True)
        audio_formats.sort(key=lambda x: x["_abr"], reverse=True)

        self.root.after(0, self._on_query_success, video_formats, audio_formats)

    def _on_query_error(self, msg):
        self.query_btn.config(state=tk.NORMAL)
        self.status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _on_query_success(self, video_formats, audio_formats):
        self.query_btn.config(state=tk.NORMAL)
        self.formats = video_formats
        self.audio_formats = audio_formats
        self.video_checked_iid = None
        self.audio_checked_iid = None

        for row in self.video_tree.get_children():
            self.video_tree.delete(row)
        for row in self.audio_tree.get_children():
            self.audio_tree.delete(row)

        for f in video_formats:
            self.video_tree.insert("", tk.END,
                                   values=("☐", f["id"], f["resolution"], f["vbr"],
                                           f["ext"], f["codec"], f["filesize"], f["note"]))

        for f in audio_formats:
            lang_note = f["lang"]
            if f["note"]:
                lang_note = f"{lang_note} {f['note']}".strip()
            self.audio_tree.insert("", tk.END,
                                   values=("☐", f["id"], f["bitrate"], f["ext"],
                                           f["codec"], f["filesize"], lang_note))

        if video_formats:
            best = video_formats[0]
            self.status_var.set(
                f"查询完成 — {self.video_title} — "
                f"视频: {len(video_formats)} 个, 音频: {len(audio_formats)} 个, "
                f"最佳: {best['resolution']} {best['vbr']} ({best['id']})"
            )
        else:
            self.status_var.set(f"查询完成 — {self.video_title} — 未找到可用视频格式")

    def _get_checked_video(self):
        if self.video_checked_iid is None:
            return None
        try:
            idx = self.video_tree.index(self.video_checked_iid)
        except tk.TclError:
            return None
        if idx >= len(self.formats):
            return None
        return self.formats[idx]

    def _get_checked_audio(self):
        if self.audio_checked_iid is None:
            return None
        try:
            idx = self.audio_tree.index(self.audio_checked_iid)
        except tk.TclError:
            return None
        if idx >= len(self.audio_formats):
            return None
        return self.audio_formats[idx]

    def _download_selected(self):
        video_fmt = self._get_checked_video()
        if video_fmt is None:
            messagebox.showwarning("提示", "请在视频列表中勾选一个视频格式")
            return
        audio_fmt = self._get_checked_audio()
        if audio_fmt is None:
            messagebox.showwarning("提示", "请在音频列表中勾选一个音频格式")
            return
        if not self._has_ffmpeg:
            self._warn_no_ffmpeg()
            return

        fmt_str = f"{video_fmt['id']}+{audio_fmt['id']}"
        print(f"下载格式: {fmt_str}")
        self._start_download(fmt_str)

    def _start_download(self, fmt_str):
        url = self.url_entry.get().strip()
        if not url:
            return

        self.dl_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("正在下载...")

        threading.Thread(target=self._do_download, args=(url, fmt_str), daemon=True).start()

    def _warn_no_ffmpeg(self):
        messagebox.showwarning(
            "缺少 ffmpeg",
            "未检测到 ffmpeg，无法合并视频和音频。\n\n"
            "请安装 ffmpeg 并将其添加到系统 PATH。\n"
            "下载地址: https://ffmpeg.org/download.html\n\n"
            "或者勾选本身包含音频的视频格式下载。"
        )

    def _progress_hook(self, d):
        if d["status"] == "downloading":
            # 诊断日志: 打印实际下载的格式信息
            fmt_id = d.get("info_dict", {}).get("format_id", "?")
            resolution = d.get("info_dict", {}).get("resolution") or ""
            tbr = d.get("info_dict", {}).get("tbr") or ""
            print(f"[下载中] format_id={fmt_id}  resolution={resolution}  tbr={tbr}")

            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = self._format_speed(speed) if speed else "--"
                self.root.after(0, self._update_progress, pct, f"下载中... {pct}% — {speed_str}")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, 100, "下载完成，正在合并音视频...")

    @staticmethod
    def _format_speed(speed):
        if speed is None:
            return "--"
        if speed >= 1024 * 1024:
            return f"{speed / (1024**2):.1f} MB/s"
        if speed >= 1024:
            return f"{speed / 1024:.1f} KB/s"
        return f"{speed:.0f} B/s"

    def _update_progress(self, pct, msg):
        self.progress["value"] = pct
        self.status_var.set(msg)

    def _do_download(self, url, fmt_str):
        outtmpl = os.path.join(self.output_dir, "%(title)s.%(ext)s")
        opts = {
            "format": fmt_str,
            "outtmpl": outtmpl,
            "merge_output_format": "mkv",
            "progress_hooks": [self._progress_hook],
            # 模拟 Android 客户端，YouTube 通常会返回更高码率的流
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            # 当有多个匹配时，优先码率高的
            "format_sort": ["vbr", "tbr", "res"],
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_download_error, f"下载失败: {e}")
            return

        self.root.after(0, self._on_download_success)

    def _on_download_error(self, msg):
        self.dl_btn.config(state=tk.NORMAL)
        self.progress["value"] = 0
        self.status_var.set("下载失败")
        messagebox.showerror("错误", msg)

    def _on_download_success(self):
        self.dl_btn.config(state=tk.NORMAL)
        self.progress["value"] = 100
        self.status_var.set(f"下载完成！保存在: {self.output_dir}")
        messagebox.showinfo("完成", f"视频已保存到:\n{self.output_dir}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    VideoDownloader().run()
