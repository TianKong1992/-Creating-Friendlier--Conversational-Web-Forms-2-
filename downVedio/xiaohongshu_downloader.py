"""
小红书视频下载器 — 基于 yt-dlp 的小红书提取器
小红书视频为单流 (音视频合并)，无需 ffmpeg 分离合并
部分高清视频可能需要登录 Cookie
"""
import os
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp


class XiaohongshuDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("小红书下载器")
        self.root.geometry("780x620")
        self.root.resizable(True, True)
        self.root.minsize(640, 480)

        self.formats = []
        self.video_title = ""
        self.output_dir = os.path.expanduser("~\\Downloads")
        self._has_ffmpeg = self._check_ffmpeg()

        self.checked_iid = None
        self.agree_var = tk.BooleanVar(value=False)
        self.video_author = ""
        self._cookie_file = ""

        self._build_ui()

    # ── ffmpeg 检测 ───────────────────────────────────────────────

    @staticmethod
    def _check_ffmpeg():
        try:
            subprocess.run(["ffmpeg", "-version"],
                           capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ── Cookie 配置 ───────────────────────────────────────────────

    def _load_cookie_file(self):
        path = filedialog.askopenfilename(
            title="选择 Cookies 文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path and os.path.exists(path):
            self._cookie_file = path
            self.cookie_status_var.set(f"已加载: {os.path.basename(path)}")
            self.cookie_status_label.config(foreground="green")

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        # URL 输入
        url_frame = ttk.Frame(self.root, padding="8")
        url_frame.pack(fill=tk.X)
        ttk.Label(url_frame, text="视频链接:").pack(side=tk.LEFT)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self.query_btn = ttk.Button(url_frame, text="查询", command=self._query)
        self.query_btn.pack(side=tk.LEFT)
        self.root.bind("<Return>", lambda e: self._query())

        # Cookie 加载
        cookie_frame = ttk.Frame(self.root, padding="0 0 8 0")
        cookie_frame.pack(fill=tk.X, padx=8)
        ttk.Label(cookie_frame, text="Cookie:").pack(side=tk.LEFT)
        ttk.Button(cookie_frame, text="加载 cookies.txt",
                   command=self._load_cookie_file).pack(side=tk.LEFT, padx=(6, 8))
        self.cookie_status_var = tk.StringVar(value="未加载 (公开视频无需登录)")
        self.cookie_status_label = ttk.Label(
            cookie_frame, textvariable=self.cookie_status_var, foreground="gray")
        self.cookie_status_label.pack(side=tk.LEFT)

        # 格式列表
        ff = ttk.LabelFrame(self.root, text="可用画质 (勾选一个)", padding="4")
        ff.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        cols = ("select", "id", "quality", "resolution", "codec", "bitrate", "filesize")
        self.format_tree = ttk.Treeview(ff, columns=cols, show="headings",
                                        height=8, selectmode="none")
        self.format_tree.heading("select", text="☐")
        self.format_tree.heading("id", text="格式ID")
        self.format_tree.heading("quality", text="画质")
        self.format_tree.heading("resolution", text="分辨率")
        self.format_tree.heading("codec", text="编码")
        self.format_tree.heading("bitrate", text="码率")
        self.format_tree.heading("filesize", text="文件大小")
        self.format_tree.column("select", width=36, anchor=tk.CENTER)
        self.format_tree.column("id", width=80, anchor=tk.CENTER)
        self.format_tree.column("quality", width=100, anchor=tk.CENTER)
        self.format_tree.column("resolution", width=110, anchor=tk.CENTER)
        self.format_tree.column("codec", width=140, anchor=tk.CENTER)
        self.format_tree.column("bitrate", width=90, anchor=tk.CENTER)
        self.format_tree.column("filesize", width=100, anchor=tk.CENTER)

        fs = ttk.Scrollbar(ff, orient=tk.VERTICAL, command=self.format_tree.yview)
        self.format_tree.configure(yscrollcommand=fs.set)
        self.format_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fs.pack(side=tk.RIGHT, fill=tk.Y)
        self.format_tree.bind("<ButtonRelease-1>", self._on_format_click)

        # 视频信息显示
        info_frame = ttk.LabelFrame(self.root, text="视频信息", padding="6")
        info_frame.pack(fill=tk.X, padx=8, pady=(6, 0))
        self.video_title_var = tk.StringVar(value="")
        ttk.Label(info_frame, textvariable=self.video_title_var,
                  font=("", 11, "bold"), wraplength=700).pack(anchor=tk.W)
        self.video_author_var = tk.StringVar(value="")
        ttk.Label(info_frame, textvariable=self.video_author_var,
                  foreground="#888", wraplength=700).pack(anchor=tk.W, pady=(2, 0))
        self.copy_info_btn = ttk.Button(info_frame, text="复制信息", command=self._copy_video_info)
        self.copy_info_btn.pack(anchor=tk.W, pady=(4, 0))

        # 保存目录
        dir_frame = ttk.Frame(self.root, padding="8 4 8 4")
        dir_frame.pack(fill=tk.X)
        ttk.Label(dir_frame, text="保存目录:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=self.output_dir)
        ttk.Label(dir_frame, textvariable=self.dir_var, foreground="gray").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        ttk.Button(dir_frame, text="浏览", command=self._browse_dir).pack(side=tk.LEFT)

        # 进度
        prog_frame = ttk.Frame(self.root, padding="8 4 8 4")
        prog_frame.pack(fill=tk.X)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill=tk.X)

        # 下载按钮 + 用户协议
        btn_frame = ttk.Frame(self.root, padding="8 4 8 8")
        btn_frame.pack(fill=tk.X)
        self.dl_btn = ttk.Button(btn_frame, text="下载", command=self._download)
        self.dl_btn.pack(side=tk.LEFT)

        self.agree_cb = ttk.Checkbutton(btn_frame, variable=self.agree_var)
        self.agree_cb.pack(side=tk.LEFT, padx=(12, 0))
        self._disclaimer_text = (
            "本软件仅为技术工具，提供公开网络视频资源的下载辅助功能，"
            "不存储、不托管、不分享任何视频内容，不拥有任何下载内容的版权。\n\n"
            "用户使用本软件仅限个人学习、研究、欣赏等非商业用途，"
            "且必须获得原作品权利人的合法授权。严禁用于商业盈利、二次分发、公开传播、侵权搬运。\n\n"
            "任何因未经授权下载、传播、商用导致的版权侵权、法律纠纷、赔偿责任，"
            "全部由用户自行承担，与本软件开发者无关。\n\n"
            "使用即同意：下载、安装、使用本软件，即表示您已阅读、理解并同意本声明全部条款。"
        )
        self.agree_link = ttk.Label(btn_frame, text="用户协议/免责声明",
                                    foreground="blue", cursor="hand2")
        self.agree_link.pack(side=tk.LEFT, padx=(4, 0))
        self.agree_link.bind("<Button-1>", lambda e: messagebox.showinfo(
            "免责声明 / 用户协议", self._disclaimer_text))

        # 状态栏
        self.status_var = tk.StringVar(value="就绪 — 粘贴小红书笔记链接后点击查询")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding="4 2 4 2").pack(fill=tk.X, side=tk.BOTTOM)

    # ── 格式选择 ──────────────────────────────────────────────────

    def _on_format_click(self, event):
        col = self.format_tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.format_tree.identify_row(event.y)
        if not iid:
            return
        if self.checked_iid == iid:
            self.format_tree.set(iid, "select", "☐")
            self.checked_iid = None
        else:
            if self.checked_iid:
                self.format_tree.set(self.checked_iid, "select", "☐")
            self.format_tree.set(iid, "select", "☑")
            self.checked_iid = iid

    def _browse_dir(self):
        chosen = filedialog.askdirectory(
            initialdir=self.output_dir, title="选择保存目录")
        if chosen:
            self.output_dir = chosen
            self.dir_var.set(chosen)

    def _copy_video_info(self):
        parts = []
        if self.video_title:
            parts.append(self.video_title)
        if self.video_author:
            parts.append(f"@{self.video_author}")
        if parts:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(parts))
            self.status_var.set("视频信息已复制到剪贴板")
        else:
            messagebox.showwarning("提示", "暂无视频信息，请先查询")

    # ── 查询 ──────────────────────────────────────────────────────

    def _query(self):
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
        if size_bytes >= 1024 ** 3:
            return f"{size_bytes / (1024 ** 3):.1f} GB"
        if size_bytes >= 1024 ** 2:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        return f"{size_bytes / 1024:.1f} KB"

    @staticmethod
    def _format_bitrate(kbps):
        if kbps <= 0:
            return "未知"
        if kbps >= 1000:
            return f"{kbps / 1000:.1f} Mbps"
        return f"{kbps:.0f} Kbps"

    @staticmethod
    def _deduplicate_formats(formats, key_fn):
        seen = {}
        for f in formats:
            k = key_fn(f)
            if k not in seen or f["_bytes"] > seen[k]["_bytes"]:
                seen[k] = f
        return list(seen.values())

    def _do_query(self, url):
        opts = {"quiet": True, "no_warnings": True}
        if self._cookie_file and os.path.exists(self._cookie_file):
            opts["cookiefile"] = self._cookie_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._on_query_error,
                            f"获取信息失败: {e}\n\n请确认链接有效，或尝试加载 Cookie 后重试")
            return

        self.video_title = info.get("title") or info.get("fulltitle") or "未知"
        self.video_author = info.get("uploader") or info.get("channel") or ""
        duration = info.get("duration") or 0
        raw_formats = info.get("formats", [])
        all_formats = []

        for f in raw_formats:
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"

            # 跳过纯音频格式
            if vcodec == "none" and acodec != "none":
                continue

            height = f.get("height") or 0
            width = f.get("width") or 0
            if width and height:
                resolution = f"{width}x{height}"
            elif height:
                resolution = f"{height}p"
            else:
                resolution = "未知"

            tbr = f.get("tbr") or f.get("vbr") or 0
            filesize = f.get("filesize") or f.get("filesize_approx") or 0
            if not filesize and tbr and duration:
                filesize = int(tbr * 1000 / 8 * duration)

            q = f.get("format_note") or f.get("format") or ""

            all_formats.append({
                "id": f.get("format_id", ""),
                "quality": q,
                "resolution": resolution,
                "codec": f"{vcodec}/{acodec}".replace(".", ""),
                "bitrate": self._format_bitrate(tbr),
                "filesize": self._format_bytes(filesize),
                "_height": height,
                "_tbr": tbr,
                "_bytes": filesize,
            })

        # 去重并按分辨率从高到低排序
        all_formats = self._deduplicate_formats(
            all_formats, key_fn=lambda f: (f["_height"], f["codec"]))
        all_formats.sort(key=lambda x: (x["_height"], x["_tbr"]), reverse=True)

        self.root.after(0, self._on_query_success, all_formats)

    def _on_query_error(self, msg):
        self.query_btn.config(state=tk.NORMAL)
        self.status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _on_query_success(self, formats):
        self.query_btn.config(state=tk.NORMAL)
        self.formats = formats
        self.checked_iid = None

        self.format_tree.delete(*self.format_tree.get_children())
        for f in formats:
            self.format_tree.insert("", tk.END, values=(
                "☐", f["id"], f["quality"], f["resolution"],
                f["codec"], f["bitrate"], f["filesize"]))

        self.video_title_var.set(self.video_title)
        author_text = f"@{self.video_author}" if self.video_author else ""
        self.video_author_var.set(author_text)

        if formats:
            best = formats[0]
            self.status_var.set(
                f"查询完成 — {self.video_title} — "
                f"共 {len(formats)} 个格式, "
                f"最佳: {best['quality']} {best['resolution']}")
        else:
            self.status_var.set(
                f"查询完成 — {self.video_title} — 未找到可用格式")

    # ── 下载 ──────────────────────────────────────────────────────

    def _get_checked_format(self):
        if self.checked_iid is None:
            return None
        try:
            idx = self.format_tree.index(self.checked_iid)
        except tk.TclError:
            return None
        if idx >= len(self.formats):
            return None
        return self.formats[idx]

    def _download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        fmt = self._get_checked_format()
        if fmt is None:
            if not self.formats:
                messagebox.showwarning("提示", "请先查询视频信息")
                return
            fmt = self.formats[0]
        self._start(fmt["id"])

    def _start(self, fmt_id):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.dl_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("正在下载...")
        threading.Thread(target=self._do_download,
                         args=(url, fmt_id), daemon=True).start()

    def _progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024 ** 2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, pct,
                                f"下载中... {pct}% — {speed_str}")
            else:
                speed = d.get("speed")
                speed_str = f"{speed / 1024 ** 2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, -1,
                                f"下载中... — {speed_str}")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, 100,
                            "下载完成，正在处理...")

    def _update_progress(self, pct, msg):
        if pct >= 0:
            self.progress["value"] = pct
        self.status_var.set(msg)

    def _do_download(self, url, fmt_id):
        outtmpl = os.path.join(self.output_dir, "%(title)s.%(ext)s")
        opts = {
            "format": fmt_id,
            "outtmpl": outtmpl,
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": True,
        }
        if self._cookie_file and os.path.exists(self._cookie_file):
            opts["cookiefile"] = self._cookie_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_error, f"下载失败: {e}")
            return
        self.root.after(0, self._on_success)

    def _on_error(self, msg):
        self.dl_btn.config(state=tk.NORMAL)
        self.progress["value"] = 0
        self.status_var.set("下载失败")
        messagebox.showerror("错误", msg)

    def _on_success(self):
        self.dl_btn.config(state=tk.NORMAL)
        self.progress["value"] = 100
        self.status_var.set(f"下载完成 → {self.output_dir}")
        messagebox.showinfo("完成", f"视频已保存到:\n{self.output_dir}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    XiaohongshuDownloader().run()
