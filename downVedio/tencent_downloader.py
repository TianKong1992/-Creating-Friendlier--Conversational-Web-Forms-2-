"""
腾讯视频下载器 — 基于 yt-dlp 的 VQQ 提取器
通过浏览器 Cookie 登录，支持 VIP 内容下载
HLS (m3u8) 流媒体，需要 ffmpeg 转换为 mp4
"""
import os
import json
import shutil
import tempfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

import yt_dlp
import requests


class TencentDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("腾讯视频下载器")
        self.root.geometry("800x620")
        self.root.resizable(True, True)
        self.root.minsize(680, 500)

        self.formats = []
        self.video_title = ""
        self.output_dir = os.path.expanduser("~\\Downloads")
        self._has_ffmpeg = self._check_ffmpeg()

        self.checked_iid = None
        self._cookie_file = ""
        self._cookies_browser = "firefox"
        self._cancel_flag = threading.Event()

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
        if self._cookie_file:
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
        self.cancel_btn = ttk.Button(url_frame, text="取消", command=self._cancel_operation)
        self.root.bind("<Return>", lambda e: self._query())

        # 登录区域
        login_frame = ttk.LabelFrame(self.root, text="腾讯视频登录 (VIP内容需要)", padding="6")
        login_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        row1 = ttk.Frame(login_frame)
        row1.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(row1, text="浏览器:").pack(side=tk.LEFT)
        self.browser_var = tk.StringVar(value="Firefox")
        self.browser_combo = ttk.Combobox(
            row1, textvariable=self.browser_var,
            values=["Firefox (推荐)", "Chrome", "Edge", "Brave", "Opera"],
            state="readonly", width=14)
        self.browser_combo.pack(side=tk.LEFT, padx=(4, 8))

        self.login_btn = ttk.Button(row1, text="获取登录状态",
                                    command=self._browser_login)
        self.login_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.open_web_btn = ttk.Button(row1, text="打开登录页",
                                       command=self._open_login_page)
        self.open_web_btn.pack(side=tk.LEFT)

        self.login_status_var = tk.StringVar(
            value="未登录 — 免费视频无需登录，VIP内容请在浏览器登录 v.qq.com")
        ttk.Label(login_frame, textvariable=self.login_status_var,
                  foreground="gray").pack(anchor=tk.W, pady=(4, 0))

        ttk.Label(login_frame,
                  text="步骤: ① 用 Firefox 打开并登录 v.qq.com → ② 点击「获取登录状态」",
                  foreground="#0066cc").pack(anchor=tk.W, pady=(2, 0))

        # 视频格式列表
        ff = ttk.LabelFrame(self.root, text="视频格式 (HLS 流，勾选一个)", padding="4")
        ff.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        cols = ("fselect", "id", "quality", "resolution", "codec", "vbr", "note")
        self.fmt_tree = ttk.Treeview(ff, columns=cols, show="headings",
                                     height=8, selectmode="none")
        self.fmt_tree.heading("fselect", text="☐")
        self.fmt_tree.heading("id", text="格式ID")
        self.fmt_tree.heading("quality", text="画质")
        self.fmt_tree.heading("resolution", text="分辨率")
        self.fmt_tree.heading("codec", text="编码")
        self.fmt_tree.heading("vbr", text="码率")
        self.fmt_tree.heading("note", text="备注")
        self.fmt_tree.column("fselect", width=36, anchor=tk.CENTER)
        self.fmt_tree.column("id", width=70, anchor=tk.CENTER)
        self.fmt_tree.column("quality", width=110, anchor=tk.CENTER)
        self.fmt_tree.column("resolution", width=110, anchor=tk.CENTER)
        self.fmt_tree.column("codec", width=100, anchor=tk.CENTER)
        self.fmt_tree.column("vbr", width=85, anchor=tk.CENTER)
        self.fmt_tree.column("note", width=100, anchor=tk.CENTER)

        fs = ttk.Scrollbar(ff, orient=tk.VERTICAL, command=self.fmt_tree.yview)
        self.fmt_tree.configure(yscrollcommand=fs.set)
        self.fmt_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fs.pack(side=tk.RIGHT, fill=tk.Y)
        self.fmt_tree.bind("<ButtonRelease-1>", self._on_format_click)

        # ffmpeg 提示
        if not self._has_ffmpeg:
            ttk.Label(ff, text="⚠ 未检测到 ffmpeg，HLS 流下载后需要 ffmpeg 合并转换",
                      foreground="red").pack(anchor=tk.W, pady=(2, 0))

        # 保存目录
        dir_frame = ttk.Frame(self.root, padding="8 4 8 4")
        dir_frame.pack(fill=tk.X)
        ttk.Label(dir_frame, text="保存目录:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=self.output_dir)
        ttk.Label(dir_frame, textvariable=self.dir_var, foreground="gray").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        ttk.Button(dir_frame, text="浏览", command=self._browse_dir).pack(side=tk.LEFT)

        # 进度条
        prog_frame = ttk.Frame(self.root, padding="8 4 8 4")
        prog_frame.pack(fill=tk.X)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill=tk.X)

        # 下载按钮
        btn_frame = ttk.Frame(self.root, padding="8 4 8 8")
        btn_frame.pack(fill=tk.X)
        self.dl_btn = ttk.Button(btn_frame, text="下载选中格式", command=self._download)
        self.dl_btn.pack(side=tk.LEFT)

        # 免责声明
        disclaimer_frame = ttk.Frame(self.root, padding="2 4 2 2")
        disclaimer_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(disclaimer_frame,
                  text="免责声明：本工具仅供个人学习使用。下载内容请勿二次分发，版权归原作者及平台所有。",
                  foreground="gray", font=("", 8)).pack()

        # 状态栏
        self.status_var = tk.StringVar(value="就绪 — 粘贴腾讯视频链接，点击查询")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding="4 2 4 2").pack(fill=tk.X, side=tk.BOTTOM)

    # ── 格式选择 ──────────────────────────────────────────────────

    def _on_format_click(self, event):
        col = self.fmt_tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.fmt_tree.identify_row(event.y)
        if not iid:
            return
        if self.checked_iid == iid:
            self.fmt_tree.set(iid, "fselect", "☐")
            self.checked_iid = None
        else:
            if self.checked_iid:
                self.fmt_tree.set(self.checked_iid, "fselect", "☐")
            self.fmt_tree.set(iid, "fselect", "☑")
            self.checked_iid = iid

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir, title="选择保存目录")
        if chosen:
            self.output_dir = chosen
            self.dir_var.set(chosen)

    # ── 登录 ──────────────────────────────────────────────────────

    def _open_login_page(self):
        webbrowser.open("https://v.qq.com/")

    def _browser_login(self):
        browser = self.browser_var.get().replace(" (推荐)", "").lower()
        self._cancel_flag.clear()
        self.login_btn.config(state=tk.DISABLED)
        self.login_status_var.set(f"正在读取 {browser.title()} 中的腾讯视频 Cookie...")
        threading.Thread(target=self._do_browser_login, args=(browser,), daemon=True).start()

    def _do_browser_login(self, browser):
        from yt_dlp.cookies import extract_cookies_from_browser

        try:
            browser_cj = extract_cookies_from_browser(browser)
        except PermissionError:
            if not self._cancel_flag.is_set():
                self.root.after(0, self._on_login_error,
                              f"读取 {browser.title()} Cookie 失败，请关闭浏览器后重试")
            return
        except FileNotFoundError:
            if not self._cancel_flag.is_set():
                self.root.after(0, self._on_login_error,
                              f"未找到 {browser.title()} 浏览器数据，请确认已安装该浏览器")
            return
        except Exception as e:
            if not self._cancel_flag.is_set():
                err = str(e).lower()
                if "decrypt" in err or "dpapi" in err or "keyring" in err:
                    self.root.after(0, self._on_login_error,
                                  f"{browser.title()} Cookie 解密失败（App-Bound Encryption）。\n"
                                  f"Chrome/Edge 新版不再支持外部工具读取 Cookie。\n"
                                  f"请改用 Firefox 浏览器登录后重试。")
                else:
                    self.root.after(0, self._on_login_error,
                                  f"提取 {browser.title()} Cookie 失败: {str(e)[:250]}")
            return

        if self._cancel_flag.is_set():
            return

        # 检查是否有腾讯视频相关 Cookie
        tencent_domains = ["qq.com", "v.qq.com", "video.qq.com"]
        has_tencent = any(
            any(d in c.domain for d in tencent_domains)
            for c in browser_cj
        )
        if not has_tencent:
            if not self._cancel_flag.is_set():
                self.root.after(0, self._on_login_error,
                              f"未在 {browser.title()} 中找到腾讯视频相关 Cookie。\n"
                              f"请先在浏览器中打开并登录 v.qq.com 后重试。")
            return

        # 获取新鲜访客 Cookie
        sess = requests.Session()
        sess.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        )
        try:
            sess.get("https://v.qq.com/", timeout=15)
        except Exception:
            pass

        # 合并写入 Netscape 文件
        lines = [
            "# Netscape HTTP Cookie File",
            "# 腾讯视频 — 浏览器登录 Cookie + 新鲜访客 Cookie",
        ]
        seen = set()

        for c in browser_cj:
            key = (c.domain, c.path, c.name)
            if key in seen:
                continue
            seen.add(key)
            domain = c.domain if c.domain.startswith(".") else f".{c.domain}"
            secure = "TRUE" if c.secure else "FALSE"
            expires = str(c.expires) if c.expires else "0"
            lines.append(
                f"{domain}\tTRUE\t{c.path}\t{secure}\t{expires}"
                f"\t{c.name}\t{c.value}"
            )

        for c in sess.cookies:
            key = (c.domain, c.path, c.name)
            if key in seen:
                continue
            seen.add(key)
            domain = c.domain if c.domain.startswith(".") else f".{c.domain}"
            secure = "TRUE" if c.secure else "FALSE"
            expires = str(c.expires) if c.expires else "0"
            lines.append(
                f"{domain}\tTRUE\t{c.path}\t{secure}\t{expires}"
                f"\t{c.name}\t{c.value}"
            )

        fd, path = tempfile.mkstemp(suffix=".txt", prefix="tencent_cookies_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._cookie_file = path
        self._cookies_browser = browser
        if not self._cancel_flag.is_set():
            self.root.after(0, self._on_login_success, browser)

    def _on_login_success(self, browser):
        self.login_btn.config(state=tk.NORMAL)
        self.login_status_var.set(f"已获取 ✓ ({browser}) — VIP 内容也可下载")
        messagebox.showinfo(
            "获取成功",
            f"已读取 {browser.title()} 中的腾讯视频登录状态！\n\n"
            f"合并了浏览器登录 Cookie 与新鲜访客 Cookie。\n"
            f"现在可以下载 VIP 内容了。"
        )

    def _on_login_error(self, msg):
        self.login_btn.config(state=tk.NORMAL)
        self.login_status_var.set("未登录")
        messagebox.showerror("获取失败", msg)

    # ── 工具方法 ──────────────────────────────────────────────────

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
        """按 key_fn 去重，保留第一个"""
        seen = set()
        result = []
        for f in formats:
            k = key_fn(f)
            if k not in seen:
                seen.add(k)
                result.append(f)
        return result

    # ── 查询 ──────────────────────────────────────────────────────

    def _query(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self._cancel_flag.clear()
        self.query_btn.pack_forget()
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 0))
        self.status_var.set("正在获取视频信息...")
        threading.Thread(target=self._do_query, args=(url,), daemon=True).start()

    def _cancel_operation(self):
        self._cancel_flag.set()
        self._reset_query_ui()
        self._reset_download_ui()
        self.status_var.set("已取消")

    def _reset_query_ui(self):
        self.cancel_btn.pack_forget()
        self.query_btn.config(state=tk.NORMAL)
        self.query_btn.pack(side=tk.LEFT)
        self.fmt_tree.delete(*self.fmt_tree.get_children())

    def _do_query(self, url):
        opts = {"quiet": True, "no_warnings": True, "socket_timeout": 30}
        opts.update(self._build_cookie_opts())

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            if not self._cancel_flag.is_set():
                self.root.after(0, self._on_query_error, f"获取信息失败: {e}")
            else:
                self.root.after(0, self._reset_query_ui)
            return

        self.video_title = info.get("title", "未知")
        duration = info.get("duration") or 0
        raw_formats = info.get("formats", [])

        video_formats = []
        for f in raw_formats:
            if f.get("has_drm"):
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

            vcodec = f.get("vcodec")
            if vcodec and vcodec != "none":
                codec = vcodec.split(".")[0] if "." in vcodec else vcodec
            else:
                codec = "H.264"

            protocol = f.get("protocol", "")
            note = "HLS" if "m3u8" in protocol else protocol

            video_formats.append({
                "id": f.get("format_id", ""),
                "quality": quality_label,
                "resolution": resolution,
                "codec": codec,
                "vbr": self._format_bitrate(vbr),
                "note": note,
                "_height": height,
                "_vbr": vbr,
                "_bytes": filesize,
                "_url": f.get("url", ""),
            })

        # 去重：腾讯视频同一画质有多条 CDN 镜像
        video_formats = self._deduplicate_formats(
            video_formats,
            key_fn=lambda f: (f["_height"], f["quality"]))
        video_formats.sort(key=lambda x: (x["_height"], x["_vbr"]), reverse=True)

        self.root.after(0, self._on_query_success, video_formats)

    def _on_query_error(self, msg):
        self._reset_query_ui()
        self.status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _on_query_success(self, video_formats):
        self._reset_query_ui()
        self.formats = video_formats
        self.checked_iid = None

        self.fmt_tree.delete(*self.fmt_tree.get_children())

        for f in video_formats:
            self.fmt_tree.insert("", tk.END, values=(
                "☐", f["id"], f["quality"], f["resolution"],
                f["codec"], f["vbr"], f["note"]))

        if video_formats:
            best = video_formats[0]
            note = f" — 需要 ffmpeg 合并 HLS" if not self._has_ffmpeg else ""
            self.status_var.set(
                f"查询完成 — {self.video_title} — "
                f"共 {len(video_formats)} 个格式, "
                f"最佳: {best['quality']} {best['resolution']}{note}")
        else:
            self.status_var.set(f"查询完成 — {self.video_title} — 未找到可用格式")

    # ── 下载 ──────────────────────────────────────────────────────

    def _get_checked_format(self):
        if self.checked_iid is None:
            return None
        try:
            idx = self.fmt_tree.index(self.checked_iid)
        except tk.TclError:
            return None
        if idx >= len(self.formats):
            return None
        return self.formats[idx]

    def _download(self):
        f = self._get_checked_format()
        if f is None:
            messagebox.showwarning("提示", "请在视频格式列表中勾选一个格式")
            return

        if not self._has_ffmpeg:
            messagebox.showwarning(
                "缺少 ffmpeg",
                "腾讯视频使用 HLS (m3u8) 流媒体，需要 ffmpeg 下载并合并为 mp4。\n\n"
                "请安装 ffmpeg 并添加到系统 PATH。\n"
                "下载地址: https://ffmpeg.org/download.html")
            return

        self._start(f["id"])

    def _start(self, fmt_id):
        url = self.url_entry.get().strip()
        if not url:
            return

        # 在主线程安全获取 m3u8 URL
        f = self._get_checked_format()
        m3u8_url = f.get("_url", "") if f else ""

        self._cancel_flag.clear()
        self.dl_btn.pack_forget()
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 0))
        self.progress["value"] = 0
        self.status_var.set("正在下载...")
        threading.Thread(target=self._do_download,
                         args=(url, fmt_id, m3u8_url), daemon=True).start()

    def _reset_download_ui(self):
        self.cancel_btn.pack_forget()
        self.dl_btn.config(state=tk.NORMAL)
        self.dl_btn.pack(side=tk.LEFT)

    def _progress_hook(self, d):
        if self._cancel_flag.is_set():
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024 ** 2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, pct,
                                f"下载中... {pct}% — {speed_str}")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, 100, "下载完成，正在处理...")

    def _update_progress(self, pct, msg):
        self.progress["value"] = pct
        self.status_var.set(msg)

    def _do_download(self, url, fmt_id, m3u8_url):
        if not m3u8_url:
            # 重新提取以获取新鲜 URL
            opts = {"quiet": True, "no_warnings": True, "socket_timeout": 30}
            opts.update(self._build_cookie_opts())
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    for fmt in info.get("formats", []):
                        if fmt.get("format_id") == fmt_id:
                            m3u8_url = fmt["url"]
                            break
            except Exception:
                pass

        if not m3u8_url:
            self.root.after(0, self._on_error, "无法获取下载链接，请重新查询后重试")
            self.root.after(0, self._reset_download_ui)
            return

        self._do_download_pw(m3u8_url)

    def _do_download_pw(self, m3u8_url):
        """通过 Playwright 浏览器下载 HLS 流，绕过 CDN 对非浏览器客户端的限速"""
        CHROME_UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        )

        temp_dir = tempfile.mkdtemp()
        segments = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.root.after(0, self._on_error,
                          "需要安装 Playwright:\npip install playwright\nplaywright install chromium")
            self.root.after(0, self._reset_download_ui)
            return

        try:
            self.root.after(0, self._update_progress, 0, "启动浏览器引擎...")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=CHROME_UA)
                page = context.new_page()

                # 访问 v.qq.com 设置必要的 Cookie
                try:
                    page.goto("https://v.qq.com/", wait_until="domcontentloaded",
                             timeout=15000)
                except Exception:
                    pass  # Cookie 设置尽力而为

                if self._cancel_flag.is_set():
                    browser.close()
                    self.root.after(0, self._reset_download_ui)
                    return

                # 通过浏览器 fetch 获取 m3u8 playlist
                self.root.after(0, self._update_progress, 0, "解析视频分片列表...")
                m3u8_safe = json.dumps(m3u8_url)
                m3u8_text = page.evaluate(f"""
                async () => {{
                    const resp = await fetch({m3u8_safe}, {{
                        headers: {{'Referer': 'https://v.qq.com/'}}
                    }});
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    return await resp.text();
                }}
                """)

                # 解析 ts 分片 URL
                ts_urls = []
                for line in m3u8_text.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if not line.startswith('http'):
                            line = m3u8_url.rsplit('/', 1)[0] + '/' + line
                        ts_urls.append(line)

                total = len(ts_urls)
                if total == 0:
                    browser.close()
                    self.root.after(0, self._on_error, "m3u8 中未找到视频分片")
                    self.root.after(0, self._reset_download_ui)
                    return

                # 路由拦截：所有 .ts 请求通过浏览器的 HTTP 栈下载并保存到磁盘
                def handle_route(route):
                    if self._cancel_flag.is_set():
                        route.abort()
                        return
                    idx = len(segments)
                    seg_path = os.path.join(temp_dir, f"seg_{idx:05d}.ts")
                    try:
                        response = route.fetch()
                        body = response.body()
                        with open(seg_path, 'wb') as fh:
                            fh.write(body)
                        segments.append(seg_path)
                        route.fulfill(response=response)

                        pct = min(int(len(segments) / total * 100), 99)
                        self.root.after(0, self._update_progress, pct,
                                      f"下载中... {len(segments)}/{total} 片段")
                    except Exception:
                        route.abort()

                page.route("**/*.ts*", handle_route)

                # 分批触发下载：JS 发起并行 fetch，路由处理器串行保存
                BATCH = 64
                for i in range(0, total, BATCH):
                    if self._cancel_flag.is_set():
                        break
                    batch = ts_urls[i:i + BATCH]
                    try:
                        page.evaluate(f"""
                        async () => {{
                            const urls = {json.dumps(batch)};
                            await Promise.all(urls.map(url =>
                                fetch(url, {{
                                    headers: {{'Referer': 'https://v.qq.com/'}}
                                }}).catch(() => {{}})
                            ));
                        }}
                        """)
                    except Exception:
                        # 路由处理器可能因为取消或错误而 abort
                        pass

                browser.close()

            if self._cancel_flag.is_set():
                self.root.after(0, self._reset_download_ui)
                return

            if not segments:
                self.root.after(0, self._on_error, "没有下载到任何视频分片")
                self.root.after(0, self._reset_download_ui)
                return

            # 用 ffmpeg 合并分片
            self.root.after(0, self._update_progress, 99, "正在合并视频...")

            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as fh:
                for seg in sorted(segments):
                    fh.write(f"file '{seg}'\n")

            out_name = self.video_title if self.video_title else "tencent_video"
            out_name = "".join(c for c in out_name if c not in r'\/:*?"<>|')
            output_path = os.path.join(self.output_dir, f"{out_name}.mp4")

            result = subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file, "-c", "copy", output_path
            ], capture_output=True, text=True)

            if result.returncode == 0:
                self.root.after(0, self._on_success)
            else:
                err = result.stderr[-300:] if result.stderr else "未知错误"
                self.root.after(0, self._on_error, f"合并视频失败: {err}")
                self.root.after(0, self._reset_download_ui)

        except Exception as e:
            if not self._cancel_flag.is_set():
                self.root.after(0, self._on_error, f"下载失败: {e}")
                self.root.after(0, self._reset_download_ui)
            else:
                self.root.after(0, self._reset_download_ui)
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def _on_error(self, msg):
        self._reset_download_ui()
        self.progress["value"] = 0
        self.status_var.set("下载失败")
        messagebox.showerror("错误", msg)

    def _on_success(self):
        self._reset_download_ui()
        self.progress["value"] = 100
        self.status_var.set(f"下载完成 → {self.output_dir}")
        messagebox.showinfo("完成", f"视频已保存到:\n{self.output_dir}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    TencentDownloader().run()
