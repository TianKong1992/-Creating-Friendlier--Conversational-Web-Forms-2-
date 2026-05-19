"""
抖音视频下载器 — 基于 Playwright 提取视频信息
通过浏览器 Cookie 认证身份，直接下载视频文件
仅限个人学习使用，请勿分发下载内容
Chrome/Edge 因 App-Bound Encryption 可能无法解密 Cookie，推荐使用 Firefox
"""
import json
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
from playwright.sync_api import sync_playwright


QUALITY_LABELS = {
    0: "4K", 1: "1080p", 2: "720p", 3: "540p", 4: "480p",
    10: "1080p+", 20: "720p+", 25: "540p HDR",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

MAX_FILE_SIZE = 2 * 1024 ** 3  # 2 GB 下载上限


class DouyinDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("抖音下载器")
        self.root.geometry("800x620")
        self.root.resizable(True, True)
        self.root.minsize(680, 500)

        self.formats = []
        self.video_title = ""
        self.video_author = ""
        self.output_dir = os.path.expanduser("~\\Downloads")

        self.checked_iid = None
        self.agree_var = tk.BooleanVar(value=False)
        self._playwright_cookies = []
        self._cookies_browser = "firefox"
        self._lock = threading.Lock()

        self._build_ui()

    # ── 工具方法 ──────────────────────────────────────────────────

    @staticmethod
    def _sanitize_filename(name):
        name = name.replace("\r", " ").replace("\n", " ")
        name = re.sub(r'[\\/:*?"<>|]', '_', name)
        return re.sub(r'\s+', ' ', name).strip()

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
    def _format_bitrate(bps):
        if bps <= 0:
            return "未知"
        if bps >= 1_000_000:
            return f"{bps / 1_000_000:.1f} Mbps"
        if bps >= 1000:
            return f"{bps / 1000:.0f} Kbps"
        return f"{bps:.0f} bps"

    @staticmethod
    def _normalize_url(url):
        """将各种抖音视频链接统一转为 /video/{id} 格式"""
        m = re.search(r'modal_id=(\d+)', url)
        if m:
            return f"https://www.douyin.com/video/{m.group(1)}"
        if re.search(r'/video/\d+', url):
            return url
        return url

    @staticmethod
    def _extract_video_id(url):
        m = re.search(r'/video/(\d+)', url)
        return m.group(1) if m else None

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

        # 登录区域
        login_frame = ttk.LabelFrame(self.root, text="抖音登录 (获取Cookie)", padding="6")
        login_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        row1 = ttk.Frame(login_frame)
        row1.pack(fill=tk.X, pady=(0, 4))

        self.login_btn = ttk.Button(row1, text="获取登录状态",
                                    command=self._browser_login)
        self.login_btn.pack(side=tk.LEFT)

        self.login_status_var = tk.StringVar(
            value="未登录 — 推荐使用 Firefox 登录 douyin.com，Chrome/Edge 可能无法解密 Cookie")
        self.login_status_label = ttk.Label(login_frame, textvariable=self.login_status_var,
                                            foreground="gray")
        self.login_status_label.pack(anchor=tk.W, pady=(4, 0))

        ttk.Label(login_frame,
                  text="步骤: ① 用 Firefox 打开并登录 douyin.com → ② 点击「获取登录状态」",
                  foreground="#0066cc").pack(anchor=tk.W, pady=(2, 0))

        # 视频格式列表
        ff = ttk.LabelFrame(self.root, text="视频格式 (勾选一个)", padding="4")
        ff.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        cols = ("fselect", "id", "quality", "resolution", "codec", "filesize", "note")
        self.fmt_tree = ttk.Treeview(ff, columns=cols, show="headings",
                                     height=8, selectmode="none")
        self.fmt_tree.heading("fselect", text="☐")
        self.fmt_tree.heading("id", text="序号")
        self.fmt_tree.heading("quality", text="画质")
        self.fmt_tree.heading("resolution", text="分辨率")
        self.fmt_tree.heading("codec", text="编码")
        self.fmt_tree.heading("filesize", text="预估大小")
        self.fmt_tree.heading("note", text="码率")
        self.fmt_tree.column("fselect", width=36, anchor=tk.CENTER)
        self.fmt_tree.column("id", width=50, anchor=tk.CENTER)
        self.fmt_tree.column("quality", width=100, anchor=tk.CENTER)
        self.fmt_tree.column("resolution", width=110, anchor=tk.CENTER)
        self.fmt_tree.column("codec", width=100, anchor=tk.CENTER)
        self.fmt_tree.column("filesize", width=100, anchor=tk.CENTER)
        self.fmt_tree.column("note", width=100, anchor=tk.CENTER)

        fs = ttk.Scrollbar(ff, orient=tk.VERTICAL, command=self.fmt_tree.yview)
        self.fmt_tree.configure(yscrollcommand=fs.set)
        self.fmt_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fs.pack(side=tk.RIGHT, fill=tk.Y)
        self.fmt_tree.bind("<ButtonRelease-1>", self._on_format_click)

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

        # 进度条
        prog_frame = ttk.Frame(self.root, padding="8 4 8 4")
        prog_frame.pack(fill=tk.X)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill=tk.X)

        # 下载按钮 + 用户协议
        btn_frame = ttk.Frame(self.root, padding="8 4 8 8")
        btn_frame.pack(fill=tk.X)
        self.dl_btn = ttk.Button(btn_frame, text="下载选中格式", command=self._download)
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
        self.status_var = tk.StringVar(value="就绪 — 粘贴抖音视频链接，点击查询")
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

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir, title="选择保存目录")
        if chosen:
            self.output_dir = chosen
            self.dir_var.set(chosen)

    # ── 登录 ──────────────────────────────────────────────────────

    def _browser_login(self):
        self.login_btn.config(state=tk.DISABLED)
        self.login_status_var.set("正在读取 Firefox 中的抖音 Cookie...")
        threading.Thread(target=self._do_browser_login, args=("firefox",), daemon=True).start()

    def _do_browser_login(self, browser):
        from yt_dlp.cookies import extract_cookies_from_browser

        try:
            browser_cj = extract_cookies_from_browser(browser)
        except PermissionError:
            self.root.after(0, self._on_login_error,
                          f"读取 {browser.title()} Cookie 失败，请关闭浏览器后重试")
            return
        except FileNotFoundError:
            self.root.after(0, self._on_login_error,
                          f"未找到 {browser.title()} 浏览器数据，请确认已安装该浏览器")
            return
        except Exception as e:
            err = str(e).lower()
            if "decrypt" in err or "dpapi" in err or "keyring" in err:
                self.root.after(0, self._on_login_error,
                              f"{browser.title()} Cookie 解密失败（App-Bound Encryption）。\n"
                              f"Chrome/Edge 新版不再支持外部工具读取 Cookie。\n"
                              f"请改用 Firefox 浏览器登录抖音后重试。")
            else:
                self.root.after(0, self._on_login_error,
                              f"提取 {browser.title()} Cookie 失败: {str(e)[:250]}")
            return

        douyin_cookies = [c for c in browser_cj if "douyin.com" in c.domain]
        if not douyin_cookies:
            self.root.after(0, self._on_login_error,
                          f"未在 {browser.title()} 中找到 douyin.com 的 Cookie。\n"
                          f"请先在浏览器中打开并登录 douyin.com 后重试。")
            return

        # 转换为 Playwright 格式
        pw_cookies = []
        for c in browser_cj:
            if "douyin.com" not in c.domain:
                continue
            expires = c.expires
            if expires is None or expires == 0:
                expires = 2147483647
            http_only = False
            if hasattr(c, 'has_nonstandard_attr'):
                try:
                    http_only = c.has_nonstandard_attr('HttpOnly')
                except Exception:
                    pass
            pw_cookies.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain.lstrip("."),
                "path": c.path or "/",
                "expires": expires,
                "secure": True if c.secure else False,
                "httpOnly": http_only,
                "sameSite": "Lax",
            })

        with self._lock:
            self._playwright_cookies = pw_cookies
            self._cookies_browser = browser
        self.root.after(0, self._on_login_success, browser, len(pw_cookies))

    def _on_login_success(self, _browser, _count):
        self.login_btn.config(state=tk.NORMAL)
        self.login_status_var.set("已登录")
        self.login_status_label.config(foreground="green")

    def _on_login_error(self, msg):
        self.login_btn.config(state=tk.NORMAL)
        self.login_status_var.set("未登录")
        messagebox.showerror("获取失败", msg)

    # ── 查询 ──────────────────────────────────────────────────────

    def _query(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self.query_btn.config(state=tk.DISABLED)
        self.status_var.set("正在获取视频信息...")
        threading.Thread(target=self._do_query, args=(url,), daemon=True).start()

    def _do_query(self, url):
        url = self._normalize_url(url)
        video_id = self._extract_video_id(url)
        if not video_id:
            self.root.after(0, self._on_query_error, "无法从链接中提取视频 ID")
            return

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=UA,
                    viewport={"width": 1920, "height": 1080},
                )
                with self._lock:
                    cookies_snapshot = list(self._playwright_cookies)
                if cookies_snapshot:
                    context.add_cookies(cookies_snapshot)
                page = context.new_page()

                captured = []

                def on_response(resp):
                    if "aweme" in resp.url:
                        captured.append(resp)

                page.on("response", on_response)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                page.wait_for_timeout(12000)

                aweme_data = None
                for resp in captured:
                    try:
                        if "detail" in resp.url and resp.status == 200:
                            body = resp.body()
                            data = json.loads(body)
                            if data.get("aweme_detail"):
                                aweme_data = data
                                break
                    except Exception:
                        continue

                browser.close()

                if not aweme_data:
                    self.root.after(0, self._on_query_error,
                                  "未捕获到视频数据，请确认已登录抖音并获取 Cookie")
                    return

        except Exception as e:
            self.root.after(0, self._on_query_error, f"Playwright 错误: {e}")
            return

        detail = aweme_data["aweme_detail"]
        self.video_title = detail.get("desc", "未知")
        author_info = detail.get("author", {})
        self.video_author = author_info.get("nickname", "")
        stats = detail.get("statistics", {})
        digg = stats.get("digg_count", 0)
        comment = stats.get("comment_count", 0)
        share = stats.get("share_count", 0)
        duration_ms = detail.get("duration", 0) or 0
        video = detail.get("video", {})
        bit_rates = video.get("bit_rate", [])

        if not bit_rates:
            bit_rates = [{
                "bit_rate": video.get("bit_rate", 0),
                "quality_type": 0,
                "play_addr": video.get("play_addr", {}),
            }]

        formats = []
        for i, br in enumerate(bit_rates):
            quality_type = br.get("quality_type", 0)
            bitrate = br.get("bit_rate", 0)
            play_addr = br.get("play_addr", {})
            url_list = play_addr.get("url_list", [])

            width = play_addr.get("width", 0) or br.get("width", 0) or video.get("width", 0)
            height = play_addr.get("height", 0) or br.get("height", 0) or video.get("height", 0)

            if width and height:
                resolution = f"{width}x{height}"
            elif height:
                resolution = f"{height}p"
            else:
                resolution = "未知"

            is_h265 = br.get("is_h265", 0) or br.get("is_bytevc1", 0)
            codec = "H.265" if is_h265 else "H.264"
            fmt_type = br.get("format", "")

            # 过滤掉无音频的 DASH 分离流
            if fmt_type == "dash":
                continue

            # 用 video_extra 中的 definition 作为画质标签
            extra_str = br.get("video_extra", "")
            definition = ""
            if extra_str:
                try:
                    extra = json.loads(extra_str)
                    definition = extra.get("definition", "")
                except (json.JSONDecodeError, TypeError):
                    pass
            quality_label = definition.upper() if definition else QUALITY_LABELS.get(
                quality_type, f"Q{quality_type}")

            # 文件大小: 优先使用 data_size
            data_size = play_addr.get("data_size", 0)
            if data_size > 0:
                filesize = data_size
            elif duration_ms > 0 and bitrate > 0:
                filesize = int(bitrate / 8 * duration_ms / 1000)
            else:
                filesize = 0

            note_parts = [self._format_bitrate(bitrate)]

            formats.append({
                "idx": i,
                "quality": quality_label,
                "resolution": resolution,
                "codec": codec,
                "filesize": self._format_bytes(filesize),
                "note": " ".join(note_parts),
                "_height": height,
                "_bitrate": bitrate,
                "_quality_type": quality_type,
                "_urls": url_list,
            })

        formats.sort(key=lambda x: (-x["_height"], -x["_bitrate"]))
        self.root.after(0, self._on_query_success, formats)

    def _on_query_error(self, msg):
        self.query_btn.config(state=tk.NORMAL)
        self.status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _on_query_success(self, formats):
        self.query_btn.config(state=tk.NORMAL)
        self.formats = formats
        self.checked_iid = None

        self.fmt_tree.delete(*self.fmt_tree.get_children())

        for f in formats:
            self.fmt_tree.insert("", tk.END, values=(
                "☐", str(f["idx"] + 1), f["quality"], f["resolution"],
                f["codec"], f["filesize"], f["note"]))

        # 更新视频信息显示
        self.video_title_var.set(self.video_title)
        author_text = f"@{self.video_author}" if self.video_author else ""
        self.video_author_var.set(author_text)

        if formats:
            best = formats[0]
            self.status_var.set(
                f"查询完成 — {self.video_title} — "
                f"共 {len(formats)} 个格式, "
                f"最佳: {best['quality']} {best['resolution']} {best['note']}")
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
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        f = self._get_checked_format()
        if f is None:
            messagebox.showwarning("提示", "请在视频格式列表中勾选一个格式")
            return

        self.dl_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("正在获取下载地址...")
        threading.Thread(target=self._do_download, args=(f,), daemon=True).start()

    def _do_download(self, fmt):
        urls = fmt.get("_urls", [])
        if not urls:
            self.root.after(0, self._on_error, "没有可用的下载地址")
            return

        # 先尝试直接下载缓存中的 URL
        self.root.after(0, self._update_progress, 0, "正在下载...")
        success = self._download_file(urls)
        if success:
            self.root.after(0, self._on_success)
            return

        # URL 过期，重新通过 Playwright 获取
        self.root.after(0, self._update_progress, 0, "地址过期，重新获取...")
        fresh_urls = self._refresh_urls(fmt)
        if not fresh_urls:
            self.root.after(0, self._on_error, "获取下载地址失败，请重新查询")
            return

        self.root.after(0, self._update_progress, 0, "正在下载...")
        success = self._download_file(fresh_urls)
        if success:
            self.root.after(0, self._on_success)
        else:
            self.root.after(0, self._on_error, "下载失败，所有地址不可用")

    def _download_file(self, url_list):
        """从 URL 列表中尝试下载，返回是否成功"""
        safe_title = self._sanitize_filename(self.video_title)
        ext = ".mp4"

        for url in url_list:
            # 跳过非 HTTP(S) 的 URL（可能是其他协议）
            if not url.startswith("http"):
                continue
            try:
                resp = requests.get(url, stream=True, timeout=30,
                                   headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
                if resp.status_code == 403 or resp.status_code == 410:
                    continue  # URL 过期，尝试下一个
                resp.raise_for_status()

                total = int(resp.headers.get("Content-Length", 0))
                if total == 0:
                    total = int(resp.headers.get("content-length", 0))

                out_path = os.path.join(self.output_dir, f"{safe_title}{ext}")
                downloaded = 0
                too_large = False
                with open(out_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            downloaded += len(chunk)
                            if downloaded > MAX_FILE_SIZE:
                                too_large = True
                                break
                            f.write(chunk)
                            pct = int(downloaded / total * 100) if total > 0 else 0
                            speed = f"{downloaded / (1024 ** 2):.1f} MB" if total == 0 else ""
                            self.root.after(0, self._update_progress, min(pct, 100),
                                          f"下载中... {min(pct, 100)}% {speed}")
                if too_large:
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                    self.root.after(0, self._update_progress, 0,
                                  f"文件过大 ({downloaded/(1024**2):.0f} MB)，超过 2GB 上限，已取消")
                    return False

                self.root.after(0, self._update_progress, 100, "下载完成")
                return True

            except (requests.RequestException, IOError):
                continue

        return False

    def _refresh_urls(self, fmt):
        """用 Playwright 重新访问视频页获取新鲜 URL"""
        video_id = self._extract_video_id(self._normalize_url(self.url_entry.get().strip()))
        if not video_id:
            return []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=UA,
                    viewport={"width": 1920, "height": 1080},
                )
                with self._lock:
                    cookies_snapshot = list(self._playwright_cookies)
                if cookies_snapshot:
                    context.add_cookies(cookies_snapshot)
                page = context.new_page()

                captured = []

                def on_response(resp):
                    if "aweme" in resp.url:
                        captured.append(resp)

                page.on("response", on_response)

                try:
                    page.goto(f"https://www.douyin.com/video/{video_id}",
                            wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                page.wait_for_timeout(12000)

                for resp in captured:
                    try:
                        if "detail" in resp.url and resp.status == 200:
                            data = json.loads(resp.body())
                            detail = data.get("aweme_detail", {})
                            bit_rates = detail.get("video", {}).get("bit_rate", [])
                            if bit_rates:
                                # 按 quality_type 和 bitrate 匹配
                                qt = fmt["_quality_type"]
                                br_match = fmt["_bitrate"]
                                for br_item in bit_rates:
                                    if (br_item.get("quality_type") == qt and
                                        br_item.get("bit_rate") == br_match):
                                        urls = br_item.get("play_addr", {}).get("url_list", [])
                                        if urls:
                                            browser.close()
                                            return urls
                                # 也可以用索引匹配
                                if fmt["idx"] < len(bit_rates):
                                    br_item = bit_rates[fmt["idx"]]
                                    urls = br_item.get("play_addr", {}).get("url_list", [])
                                    browser.close()
                                    return urls
                    except Exception:
                        continue

                browser.close()
        except Exception:
            pass

        return []

    def _update_progress(self, pct, msg):
        self.progress["value"] = pct
        self.status_var.set(msg)

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
    DouyinDownloader().run()
