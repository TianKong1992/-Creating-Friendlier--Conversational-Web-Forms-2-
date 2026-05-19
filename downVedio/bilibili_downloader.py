"""
哔哩哔哩视频下载器 — 基于 yt-dlp 的 BiliBili 提取器
B站使用 DASH 分离流，音视频分开存储，需要 ffmpeg 合并
高清视频 (720P+) 需要登录，支持B站APP扫码登录
"""
import os
import tempfile
import threading
import subprocess
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp
import requests


class BilibiliDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("哔哩哔哩下载器")
        self.root.geometry("860x665")
        self.root.resizable(True, True)
        self.root.minsize(720, 540)

        self.formats = []
        self.audio_formats = []
        self.video_title = ""
        self.output_dir = os.path.expanduser("~\\Downloads")
        self._has_ffmpeg = self._check_ffmpeg()

        self.video_checked_iid = None
        self.audio_checked_iid = None
        self.agree_var = tk.BooleanVar(value=False)
        self.video_author = ""

        self._cookie_mode = "none"          # "none" | "file"
        self._cookie_file = ""              # cookies.txt 路径

        self._build_ui()

    # ── ffmpeg 检测 ───────────────────────────────────────────────

    @staticmethod
    def _check_ffmpeg():
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

    # ── Cookie 配置 ───────────────────────────────────────────────

    def _build_cookie_opts(self):
        if self._cookie_mode == "file" and self._cookie_file:
            return {"cookiefile": self._cookie_file}
        return {}

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

        # 登录方式
        login_frame = ttk.Frame(self.root, padding="0 0 8 0")
        login_frame.pack(fill=tk.X, padx=8)
        ttk.Label(login_frame, text="登录:").pack(side=tk.LEFT)

        self.qr_btn = ttk.Button(login_frame, text="扫码登录",
                                 command=self._qr_login)
        self.qr_btn.pack(side=tk.LEFT, padx=(6, 8))

        self.cookie_status_var = tk.StringVar(value="未登录")
        self.cookie_status_label = ttk.Label(
            login_frame, textvariable=self.cookie_status_var, foreground="gray")
        self.cookie_status_label.pack(side=tk.LEFT)

        # 视频格式列表
        vf = ttk.LabelFrame(self.root, text="视频格式 (勾选一个)", padding="4")
        vf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        v_cols = ("vselect", "id", "quality", "resolution", "codec", "vbr", "filesize")
        self.video_tree = ttk.Treeview(vf, columns=v_cols, show="headings",
                                       height=6, selectmode="none")
        self.video_tree.heading("vselect", text="☐")
        self.video_tree.heading("id", text="格式ID")
        self.video_tree.heading("quality", text="画质")
        self.video_tree.heading("resolution", text="分辨率")
        self.video_tree.heading("codec", text="编码")
        self.video_tree.heading("vbr", text="码率")
        self.video_tree.heading("filesize", text="文件大小")
        self.video_tree.column("vselect", width=36, anchor=tk.CENTER)
        self.video_tree.column("id", width=70, anchor=tk.CENTER)
        self.video_tree.column("quality", width=100, anchor=tk.CENTER)
        self.video_tree.column("resolution", width=110, anchor=tk.CENTER)
        self.video_tree.column("codec", width=130, anchor=tk.CENTER)
        self.video_tree.column("vbr", width=85, anchor=tk.CENTER)
        self.video_tree.column("filesize", width=100, anchor=tk.CENTER)

        vs = ttk.Scrollbar(vf, orient=tk.VERTICAL, command=self.video_tree.yview)
        self.video_tree.configure(yscrollcommand=vs.set)
        self.video_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        self.video_tree.bind("<ButtonRelease-1>", self._on_video_click)

        # 音频格式列表
        af = ttk.LabelFrame(self.root, text="音频格式 (勾选一个)", padding="4")
        af.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 0))

        a_cols = ("aselect", "aid", "quality", "codec", "abr", "filesize")
        self.audio_tree = ttk.Treeview(af, columns=a_cols, show="headings",
                                       height=3, selectmode="none")
        self.audio_tree.heading("aselect", text="☐")
        self.audio_tree.heading("aid", text="格式ID")
        self.audio_tree.heading("quality", text="音质")
        self.audio_tree.heading("codec", text="编码")
        self.audio_tree.heading("abr", text="码率")
        self.audio_tree.heading("filesize", text="文件大小")
        self.audio_tree.column("aselect", width=36, anchor=tk.CENTER)
        self.audio_tree.column("aid", width=70, anchor=tk.CENTER)
        self.audio_tree.column("quality", width=100, anchor=tk.CENTER)
        self.audio_tree.column("codec", width=130, anchor=tk.CENTER)
        self.audio_tree.column("abr", width=85, anchor=tk.CENTER)
        self.audio_tree.column("filesize", width=100, anchor=tk.CENTER)

        as_ = ttk.Scrollbar(af, orient=tk.VERTICAL, command=self.audio_tree.yview)
        self.audio_tree.configure(yscrollcommand=as_.set)
        self.audio_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        as_.pack(side=tk.RIGHT, fill=tk.Y)
        self.audio_tree.bind("<ButtonRelease-1>", self._on_audio_click)

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
        self.dl_btn = ttk.Button(btn_frame, text="下载选中画质", command=self._download)
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
        self.status_var = tk.StringVar(value="就绪 — 请先扫码登录，再粘贴B站视频链接")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding="4 2 4 2").pack(fill=tk.X, side=tk.BOTTOM)

    # ── 二维码登录 ────────────────────────────────────────────────

    def _qr_login(self):
        """B站APP扫码登录"""
        win = tk.Toplevel(self.root)
        win.title("B站APP扫码登录")
        win.geometry("300x320")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        self.qr_image_label = ttk.Label(win)
        self.qr_image_label.pack(pady=(12, 4))

        self.qr_status_var = tk.StringVar(value="正在生成二维码...")
        ttk.Label(win, textvariable=self.qr_status_var,
                  font=("", 10, "bold")).pack(pady=(0, 6))

        scan_frame = ttk.LabelFrame(win, text="扫码方式", padding="6")
        scan_frame.pack(fill=tk.X, padx=20, pady=(0, 6))
        row = ttk.Frame(scan_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="📱  B站APP", font=("", 10), width=10).pack(side=tk.LEFT)
        ttk.Label(row, text="打开B站APP → 扫一扫", foreground="gray").pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(win, text="扫描后请在手机上确认登录",
                  foreground="gray").pack()

        self._qr_win = win
        self._qr_key = None
        self._qr_running = True

        win.protocol("WM_DELETE_WINDOW", self._close_qr_win)
        threading.Thread(target=self._qr_login_flow, daemon=True).start()

    def _close_qr_win(self):
        self._qr_running = False
        self._qr_win.destroy()

    def _qr_login_flow(self):
        """二维码登录主流程: 生成二维码 → 轮询状态"""
        sess = requests.Session()
        sess.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        )

        # 1. 生成二维码
        try:
            resp = sess.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                self.root.after(0, self._on_qr_error,
                                f"生成二维码失败: {data.get('message', '')}")
                return
            qr_url = data["data"]["url"]
            self._qr_key = data["data"]["qrcode_key"]
        except Exception as e:
            self.root.after(0, self._on_qr_error, f"请求失败: {e}")
            return

        # 2. 生成二维码图片
        try:
            import qrcode
            from PIL import Image, ImageTk
            img = qrcode.make(qr_url, border=1, box_size=4)
            img_tk = ImageTk.PhotoImage(img)
        except Exception as e:
            self.root.after(0, self._on_qr_error, f"生成二维码图片失败: {e}")
            return

        self.root.after(0, self._show_qr_image, img_tk)
        self.root.after(0, self._set_qr_status, "请使用B站APP扫描二维码")

        # 3. 轮询登录状态
        poll_url = ("https://passport.bilibili.com/x/passport-login/web/"
                    "qrcode/poll")
        for _ in range(90):  # 最多 3 分钟
            if not self._qr_running:
                return
            time.sleep(2)
            try:
                resp = sess.get(poll_url, params={"qrcode_key": self._qr_key},
                                timeout=10)
                result = resp.json()
                if result.get("code") != 0:
                    continue
                status = result["data"]["code"]
            except Exception:
                continue

            if status == 0:
                # 登录成功 — 保存 cookies
                cookies = resp.cookies
                self._save_qr_cookies(cookies)
                self.root.after(0, self._on_qr_success)
                return
            elif status == 86038:
                self.root.after(0, self._on_qr_error, "二维码已过期，请重新获取")
                return
            elif status == 86090:
                self.root.after(0, self._set_qr_status, "已扫描，请在手机上确认登录...")
            # 86101: 未扫描，继续等待

        self.root.after(0, self._on_qr_error, "登录超时，请重新获取二维码")

    def _show_qr_image(self, img_tk):
        self.qr_image_label.configure(image=img_tk)
        self.qr_image_label.image = img_tk  # 保持引用

    def _set_qr_status(self, msg):
        self.qr_status_var.set(msg)

    def _save_qr_cookies(self, cookies):
        """将登录 Cookie 保存为 Netscape 格式的临时文件"""
        lines = [
            "# Netscape HTTP Cookie File",
            "# B站二维码登录",
        ]
        for c in cookies:
            domain = c.domain if c.domain.startswith(".") else f".{c.domain}"
            secure = "TRUE" if c.secure else "FALSE"
            expires = str(c.expires) if c.expires else "0"
            lines.append(
                f"{domain}\tTRUE\t{c.path}\t{secure}\t{expires}"
                f"\t{c.name}\t{c.value}"
            )

        fd, path = tempfile.mkstemp(suffix=".txt", prefix="bilibili_cookies_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._cookie_file = path
        self._cookie_mode = "file"

    def _on_qr_success(self):
        self._qr_running = False
        self.cookie_status_var.set("已登录 ✓ (扫码)")
        self.cookie_status_label.config(foreground="green")
        self._qr_win.destroy()
        messagebox.showinfo("登录成功", "已通过扫码登录，现在可以下载高清视频了！")

    def _on_qr_error(self, msg):
        self._qr_running = False
        self._set_qr_status(msg)
        self.cookie_status_label.config(foreground="red")
        self.cookie_status_var.set("未登录")

    # ── 格式选择 ──────────────────────────────────────────────────

    def _on_video_click(self, event):
        col = self.video_tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.video_tree.identify_row(event.y)
        if not iid:
            return
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
        if size_bytes >= 1024**3:
            return f"{size_bytes / (1024**3):.1f} GB"
        if size_bytes >= 1024**2:
            return f"{size_bytes / (1024**2):.1f} MB"
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
        """按 key_fn 去重，保留文件最大的一项"""
        seen = {}
        for f in formats:
            k = key_fn(f)
            if k not in seen or f["_bytes"] > seen[k]["_bytes"]:
                seen[k] = f
        return list(seen.values())

    def _do_query(self, url):
        opts = {"quiet": True, "no_warnings": True}
        opts.update(self._build_cookie_opts())

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._on_query_error, f"获取信息失败: {e}")
            return

        self.video_title = info.get("title", "未知")
        self.video_author = info.get("uploader") or info.get("channel") or ""
        duration = info.get("duration") or 0
        raw_formats = info.get("formats", [])

        video_formats = []
        audio_formats = []

        for f in raw_formats:
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"

            # 音频格式
            if vcodec == "none" and acodec != "none":
                abr = f.get("abr") or f.get("tbr") or 0
                filesize = f.get("filesize") or f.get("filesize_approx") or 0
                if not filesize and abr and duration:
                    filesize = int(abr * 1000 / 8 * duration)

                if abr >= 160:
                    quality = "高音质"
                elif abr >= 80:
                    quality = "标准音质"
                else:
                    quality = f.get("format_note") or "低音质"

                audio_formats.append({
                    "id": f.get("format_id", ""),
                    "quality": quality,
                    "codec": acodec.split(".")[0] if acodec else "未知",
                    "abr": self._format_bitrate(abr),
                    "filesize": self._format_bytes(filesize),
                    "_abr": abr,
                    "_bytes": filesize,
                })
                continue

            # 视频格式
            if vcodec == "none":
                continue

            height = f.get("height") or 0
            width = f.get("width") or 0
            if width and height:
                resolution = f"{width}x{height}"
            elif height:
                resolution = f"{height}p"
            else:
                resolution = "未知"

            vbr = f.get("vbr") or f.get("tbr") or 0
            filesize = f.get("filesize") or f.get("filesize_approx") or 0
            if not filesize and vbr and duration:
                filesize = int(vbr * 1000 / 8 * duration)

            quality_label = f.get("format_note") or f.get("format", "")

            video_formats.append({
                "id": f.get("format_id", ""),
                "quality": quality_label,
                "resolution": resolution,
                "codec": vcodec.split(".")[0] if vcodec else "未知",
                "vbr": self._format_bitrate(vbr),
                "filesize": self._format_bytes(filesize),
                "_height": height,
                "_vbr": vbr,
                "_bytes": filesize,
            })

        video_formats = self._deduplicate_formats(
            video_formats, key_fn=lambda f: (f["_height"], f["codec"]))
        audio_formats = self._deduplicate_formats(
            audio_formats, key_fn=lambda f: (f["_abr"], f["codec"]))

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

        self.video_tree.delete(*self.video_tree.get_children())
        self.audio_tree.delete(*self.audio_tree.get_children())

        self.video_title_var.set(self.video_title)
        author_text = f"@{self.video_author}" if self.video_author else ""
        self.video_author_var.set(author_text)

        for f in video_formats:
            self.video_tree.insert("", tk.END, values=(
                "☐", f["id"], f["quality"], f["resolution"],
                f["codec"], f["vbr"], f["filesize"]))

        for f in audio_formats:
            self.audio_tree.insert("", tk.END, values=(
                "☐", f["id"], f["quality"], f["codec"],
                f["abr"], f["filesize"]))

        if video_formats:
            best = video_formats[0]
            self.status_var.set(
                f"查询完成 — {self.video_title} — "
                f"视频: {len(video_formats)} 个, 音频: {len(audio_formats)} 个, "
                f"最佳: {best['quality']} {best['resolution']}")
        else:
            self.status_var.set(f"查询完成 — {self.video_title} — 未找到可用格式")

    # ── 下载 ──────────────────────────────────────────────────────

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

    def _download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        v = self._get_checked_video()
        if v is None:
            messagebox.showwarning("提示", "请在视频列表中勾选一个格式")
            return
        a = self._get_checked_audio()
        if a is None:
            messagebox.showwarning("提示", "请在音频列表中勾选一个格式")
            return
        if not self._has_ffmpeg:
            messagebox.showwarning(
                "缺少 ffmpeg",
                "未检测到 ffmpeg，B站视频音视频分离，需要 ffmpeg 合并。\n\n"
                "请安装 ffmpeg 并添加到系统 PATH。\n"
                "下载地址: https://ffmpeg.org/download.html")
            return

        fmt_str = f"{v['id']}+{a['id']}"
        print(f"下载格式: {fmt_str}")
        self._start(fmt_str)

    def _start(self, fmt_str):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.dl_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("正在下载...")
        threading.Thread(target=self._do_download, args=(url, fmt_str), daemon=True).start()

    def _progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024**2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, pct,
                                f"下载中... {pct}% — {speed_str}")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, 100, "下载完成，正在合并音视频...")

    def _update_progress(self, pct, msg):
        self.progress["value"] = pct
        self.status_var.set(msg)

    def _do_download(self, url, fmt_str):
        outtmpl = os.path.join(self.output_dir, "%(title)s.%(ext)s")
        opts = {
            "format": fmt_str,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": True,
        }
        opts.update(self._build_cookie_opts())

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
    BilibiliDownloader().run()
