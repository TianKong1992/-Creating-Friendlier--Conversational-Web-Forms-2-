"""
多功能视频下载器 — 合并版
支持: 哔哩哔哩 / 抖音 / 虎牙 / YouTube / 小红书
使用标签页切换平台，共用底层工具函数
"""

# ── 通用导入 ────────────────────────────────────────────────────────
import json
import os
import re
import sys
import threading
import subprocess
import tempfile
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp
import requests

# ── 常量 ────────────────────────────────────────────────────────────

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

MAX_FILE_SIZE = 2 * 1024 ** 3  # 2 GB

DISCLAIMER_TEXT = (
    "本软件仅为技术工具，提供公开网络视频资源的下载辅助功能，"
    "不存储、不托管、不分享任何视频内容，不拥有任何下载内容的版权。\n\n"
    "用户使用本软件仅限个人学习、研究、欣赏等非商业用途，"
    "且必须获得原作品权利人的合法授权。严禁用于商业盈利、二次分发、公开传播、侵权搬运。\n\n"
    "任何因未经授权下载、传播、商用导致的版权侵权、法律纠纷、赔偿责任，"
    "全部由用户自行承担，与本软件开发者无关。\n\n"
    "使用即同意：下载、安装、使用本软件，即表示您已阅读、理解并同意本声明全部条款。"
)

DOUYIN_QUALITY_LABELS = {
    0: "4K", 1: "1080p", 2: "720p", 3: "540p", 4: "480p",
    10: "1080p+", 20: "720p+", 25: "540p HDR",
}


# ══════════════════════════════════════════════════════════════════════
# 主应用
# ══════════════════════════════════════════════════════════════════════

class VideoDownloader:
    """多平台视频下载器 — 标签页切换"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("多功能视频下载器")
        self.root.geometry("920x760")
        self.root.resizable(True, True)
        self.root.minsize(740, 560)

        self.output_dir = os.path.expanduser("~\\Downloads")
        self._has_ffmpeg = self._check_ffmpeg()

        # 各平台的格式/状态数据 — 由对应标签页管理
        self._init_platform_state()

        self._build_notebook()
        self._build_bilibili_tab()
        self._build_douyin_tab()
        self._build_huya_tab()
        self._build_youtube_tab()
        self._build_xiaohongshu_tab()

    # ── 平台状态初始化 ──────────────────────────────────────────────

    def _init_platform_state(self):
        # 共享的用户协议勾选
        self.agree_var = tk.BooleanVar(value=False)

        # B站
        self.bili_formats = []
        self.bili_audio_formats = []
        self.bili_title = ""
        self.bili_author = ""
        self.bili_v_checked = None
        self.bili_cookie_mode = "none"
        self.bili_cookie_file = ""

        # 抖音
        self.dy_formats = []
        self.dy_title = ""
        self.dy_author = ""
        self.dy_checked = None
        self.dy_cookies = []
        self.dy_lock = threading.Lock()

        # 虎牙
        self.huya_formats = []
        self.huya_title = ""
        self.huya_author = ""
        self.huya_checked = None

        # YouTube
        self.yt_formats = []
        self.yt_audio_formats = []
        self.yt_title = ""
        self.yt_author = ""
        self.yt_v_checked = None
        self.yt_use_cookies = False
        self.yt_cookies_browser = "firefox"

        # 小红书
        self.xhs_formats = []
        self.xhs_title = ""
        self.xhs_author = ""
        self.xhs_checked = None

    # ═══════════════════════════════════════════════════════════════
    # 通用工具方法
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _check_ffmpeg():
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

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

    def _show_disclaimer(self):
        messagebox.showinfo("免责声明 / 用户协议", DISCLAIMER_TEXT)

    # ═══════════════════════════════════════════════════════════════
    # 标签页框架
    # ═══════════════════════════════════════════════════════════════

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.bili_frame = ttk.Frame(self.notebook)
        self.douyin_frame = ttk.Frame(self.notebook)
        self.huya_frame = ttk.Frame(self.notebook)
        self.yt_frame = ttk.Frame(self.notebook)
        self.xhs_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.bili_frame, text="哔哩哔哩")
        self.notebook.add(self.douyin_frame, text="抖音")
        self.notebook.add(self.huya_frame, text="虎牙")
        self.notebook.add(self.yt_frame, text="YouTube")
        self.notebook.add(self.xhs_frame, text="小红书")

    # ═══════════════════════════════════════════════════════════════
    # 通用 UI 构建助手
    # ═══════════════════════════════════════════════════════════════

    def _make_url_row(self, parent, query_cmd):
        """创建 URL 输入行，返回 (url_entry, query_btn)"""
        f = ttk.Frame(parent, padding="8")
        f.pack(fill=tk.X)
        ttk.Label(f, text="视频链接:").pack(side=tk.LEFT)
        entry = ttk.Entry(f)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        btn = ttk.Button(f, text="查询", command=query_cmd)
        btn.pack(side=tk.LEFT)
        return entry, btn, f

    def _make_dir_row(self, parent):
        """创建保存目录选择行"""
        f = ttk.Frame(parent, padding="8 4 8 4")
        f.pack(fill=tk.X)
        ttk.Label(f, text="保存目录:").pack(side=tk.LEFT)
        var = tk.StringVar(value=self.output_dir)
        ttk.Label(f, textvariable=var, foreground="gray").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        ttk.Button(f, text="浏览",
                   command=lambda: self._browse_dir(var)).pack(side=tk.LEFT)
        return var

    def _make_progress_bar(self, parent):
        """创建进度条，返回 progressbar"""
        f = ttk.Frame(parent, padding="8 4 8 4")
        f.pack(fill=tk.X)
        p = ttk.Progressbar(f, mode="determinate")
        p.pack(fill=tk.X)
        return p

    def _make_bottom_row(self, parent, dl_text, dl_cmd):
        """创建下载按钮 + 协议复选框 + 状态栏"""
        btn_frame = ttk.Frame(parent, padding="8 4 8 8")
        btn_frame.pack(fill=tk.X)
        dl_btn = ttk.Button(btn_frame, text=dl_text, command=dl_cmd)
        dl_btn.pack(side=tk.LEFT)

        ttk.Checkbutton(btn_frame, variable=self.agree_var).pack(side=tk.LEFT, padx=(12, 0))
        link = ttk.Label(btn_frame, text="用户协议/免责声明",
                        foreground="blue", cursor="hand2")
        link.pack(side=tk.LEFT, padx=(4, 0))
        link.bind("<Button-1>", lambda e: self._show_disclaimer())

        status_var = tk.StringVar(value="就绪")
        ttk.Label(parent, textvariable=status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding="4 2 4 2").pack(fill=tk.X, side=tk.BOTTOM)
        return dl_btn, status_var

    def _make_info_frame(self, parent):
        """创建视频信息显示区域"""
        f = ttk.LabelFrame(parent, text="视频信息", padding="6")
        f.pack(fill=tk.X, padx=8, pady=(6, 0))
        title_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=title_var,
                  font=("", 11, "bold"), wraplength=700).pack(anchor=tk.W)
        author_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=author_var,
                  foreground="#888", wraplength=700).pack(anchor=tk.W, pady=(2, 0))
        btn = ttk.Button(f, text="复制信息",
                         command=lambda: self._copy_info(title_var.get(), author_var.get()))
        btn.pack(anchor=tk.W, pady=(4, 0))
        return title_var, author_var

    def _copy_info(self, title, author):
        parts = [p for p in [title, f"@{author}" if author else ""] if p]
        if parts:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(parts))
        else:
            messagebox.showwarning("提示", "暂无视频信息，请先查询")

    def _browse_dir(self, var):
        chosen = filedialog.askdirectory(initialdir=self.output_dir, title="选择保存目录")
        if chosen:
            self.output_dir = chosen
            var.set(chosen)

    # ── Treeview 单选逻辑 ──────────────────────────────────────────

    @staticmethod
    def _on_tree_select(tree, checked_ref, col_name, select_col="#1"):
        """返回一个点击回调，col_name 即 ☐/☑ 列的标识"""
        def handler(event):
            col = tree.identify_column(event.x)
            if col != select_col:
                return
            iid = tree.identify_row(event.y)
            if not iid:
                return
            if checked_ref[0] == iid:
                tree.set(iid, col_name, "☐")
                checked_ref[0] = None
            else:
                if checked_ref[0]:
                    tree.set(checked_ref[0], col_name, "☐")
                tree.set(iid, col_name, "☑")
                checked_ref[0] = iid
        return handler

    @staticmethod
    def _get_checked(tree, checked_ref, formats):
        if checked_ref[0] is None:
            return None
        try:
            idx = tree.index(checked_ref[0])
        except tk.TclError:
            return None
        if idx >= len(formats):
            return None
        return formats[idx]

    # ═══════════════════════════════════════════════════════════════
    # 哔哩哔哩 标签页
    # ═══════════════════════════════════════════════════════════════

    def _build_bilibili_tab(self):
        p = self.bili_frame

        self.bili_url_entry, self.bili_query_btn, _ = self._make_url_row(p, self._bili_query)

        # 登录
        lf = ttk.Frame(p, padding="0 0 8 0")
        lf.pack(fill=tk.X, padx=8)
        ttk.Label(lf, text="登录:").pack(side=tk.LEFT)
        ttk.Button(lf, text="扫码登录", command=self._bili_qr_login).pack(side=tk.LEFT, padx=(6, 8))
        self.bili_cookie_var = tk.StringVar(value="未登录")
        ttk.Label(lf, textvariable=self.bili_cookie_var, foreground="gray").pack(side=tk.LEFT)

        # 视频格式列表
        vf = ttk.LabelFrame(p, text="视频格式 (勾选一个)", padding="4")
        vf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        v_cols = ("vselect", "id", "quality", "resolution", "codec", "vbr", "filesize")
        self.bili_video_tree = ttk.Treeview(vf, columns=v_cols, show="headings", height=6, selectmode="none")
        for col, txt, w in zip(v_cols, ["☐", "格式ID", "画质", "分辨率", "编码", "码率", "文件大小"],
                               [36, 70, 100, 110, 130, 85, 100]):
            self.bili_video_tree.heading(col, text=txt)
            self.bili_video_tree.column(col, width=w, anchor=tk.CENTER)
        vs = ttk.Scrollbar(vf, orient=tk.VERTICAL, command=self.bili_video_tree.yview)
        self.bili_video_tree.configure(yscrollcommand=vs.set)
        self.bili_video_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        self._bili_v_ref = [None]
        self.bili_video_tree.bind("<ButtonRelease-1>",
            self._on_tree_select(self.bili_video_tree, self._bili_v_ref, "vselect"))

        # 视频信息
        self.bili_title_var, self.bili_author_var = self._make_info_frame(p)

        # 目录 & 进度 & 按钮
        self.bili_dir_var = self._make_dir_row(p)
        self.bili_progress = self._make_progress_bar(p)
        self.bili_dl_btn, self.bili_status_var = self._make_bottom_row(
            p, "下载", self._bili_download)
        self.bili_status_var.set("就绪 — 请先扫码登录，再粘贴B站视频链接")
        p.bind("<Return>", lambda e: self._bili_query())

    # ── B站 二维码登录 ─────────────────────────────────────────────

    def _bili_qr_login(self):
        win = tk.Toplevel(self.root)
        win.title("B站APP扫码登录")
        win.geometry("300x320")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        self._bili_qr_label = ttk.Label(win)
        self._bili_qr_label.pack(pady=(12, 4))
        self._bili_qr_status_var = tk.StringVar(value="正在生成二维码...")
        ttk.Label(win, textvariable=self._bili_qr_status_var,
                  font=("", 10, "bold")).pack(pady=(0, 6))

        scan_frame = ttk.LabelFrame(win, text="扫码方式", padding="6")
        scan_frame.pack(fill=tk.X, padx=20, pady=(0, 6))
        row = ttk.Frame(scan_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="📱  B站APP", font=("", 10), width=10).pack(side=tk.LEFT)
        ttk.Label(row, text="打开B站APP → 扫一扫", foreground="gray").pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(win, text="扫描后请在手机上确认登录", foreground="gray").pack()

        self._bili_qr_win = win
        self._bili_qr_key = None
        self._bili_qr_running = True
        win.protocol("WM_DELETE_WINDOW", self._bili_close_qr)
        threading.Thread(target=self._bili_qr_flow, daemon=True).start()

    def _bili_close_qr(self):
        self._bili_qr_running = False
        self._bili_qr_win.destroy()

    def _bili_qr_flow(self):
        sess = requests.Session()
        sess.headers["User-Agent"] = UA
        try:
            resp = sess.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                self.root.after(0, self._bili_qr_error, f"生成二维码失败: {data.get('message', '')}")
                return
            qr_url = data["data"]["url"]
            self._bili_qr_key = data["data"]["qrcode_key"]
        except Exception as e:
            self.root.after(0, self._bili_qr_error, f"请求失败: {e}")
            return

        try:
            import qrcode
            from PIL import Image, ImageTk
            img = qrcode.make(qr_url, border=1, box_size=4)
            img_tk = ImageTk.PhotoImage(img)
        except Exception as e:
            self.root.after(0, self._bili_qr_error, f"生成二维码图片失败: {e}")
            return

        self.root.after(0, self._bili_show_qr, img_tk)
        self.root.after(0, lambda: self._bili_qr_status_var.set("请使用B站APP扫描二维码"))

        poll_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        for _ in range(90):
            if not self._bili_qr_running:
                return
            time.sleep(2)
            try:
                resp = sess.get(poll_url, params={"qrcode_key": self._bili_qr_key}, timeout=10)
                result = resp.json()
                if result.get("code") != 0:
                    continue
                status = result["data"]["code"]
            except Exception:
                continue
            if status == 0:
                self._bili_save_qr_cookies(resp.cookies)
                self.root.after(0, self._bili_qr_success)
                return
            elif status == 86038:
                self.root.after(0, self._bili_qr_error, "二维码已过期，请重新获取")
                return
            elif status == 86090:
                self.root.after(0, lambda: self._bili_qr_status_var.set("已扫描，请在手机上确认登录..."))
        self.root.after(0, self._bili_qr_error, "登录超时，请重新获取二维码")

    def _bili_show_qr(self, img_tk):
        self._bili_qr_label.configure(image=img_tk)
        self._bili_qr_label.image = img_tk

    def _bili_save_qr_cookies(self, cookies):
        lines = ["# Netscape HTTP Cookie File", "# B站二维码登录"]
        for c in cookies:
            domain = c.domain if c.domain.startswith(".") else f".{c.domain}"
            secure = "TRUE" if c.secure else "FALSE"
            expires = str(c.expires) if c.expires else "0"
            lines.append(f"{domain}\tTRUE\t{c.path}\t{secure}\t{expires}\t{c.name}\t{c.value}")
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="bilibili_cookies_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.bili_cookie_file = path
        self.bili_cookie_mode = "file"

    def _bili_qr_success(self):
        self._bili_qr_running = False
        self.bili_cookie_var.set("已登录 ✓ (扫码)")
        self._bili_qr_win.destroy()
        messagebox.showinfo("登录成功", "已通过扫码登录，现在可以下载高清视频了！")

    def _bili_qr_error(self, msg):
        self._bili_qr_running = False
        self._bili_qr_status_var.set(msg)
        self.bili_cookie_var.set("未登录")

    # ── B站 查询 & 下载 ─────────────────────────────────────────────

    def _bili_query(self):
        url = self.bili_url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self.bili_query_btn.config(state=tk.DISABLED)
        self.bili_status_var.set("正在获取视频信息...")
        threading.Thread(target=self._bili_do_query, args=(url,), daemon=True).start()

    def _bili_do_query(self, url):
        opts = {"quiet": True, "no_warnings": True}
        if self.bili_cookie_mode == "file" and self.bili_cookie_file:
            opts["cookiefile"] = self.bili_cookie_file
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._bili_query_error, f"获取信息失败: {e}")
            return

        self.bili_title = info.get("title", "未知")
        self.bili_author = info.get("uploader") or info.get("channel") or ""
        duration = info.get("duration") or 0
        raw = info.get("formats", [])

        vf, af = [], []
        for f in raw:
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"

            if vcodec == "none" and acodec != "none":
                abr = f.get("abr") or f.get("tbr") or 0
                fs = f.get("filesize") or f.get("filesize_approx") or 0
                if not fs and abr and duration:
                    fs = int(abr * 1000 / 8 * duration)
                quality = "高音质" if abr >= 160 else ("标准音质" if abr >= 80 else (f.get("format_note") or "低音质"))
                af.append({"id": f.get("format_id", ""), "quality": quality,
                           "codec": acodec.split(".")[0] if acodec else "未知",
                           "abr": self._format_bitrate(abr), "filesize": self._format_bytes(fs),
                           "_abr": abr, "_bytes": fs})
                continue

            if vcodec == "none":
                continue

            height = f.get("height") or 0
            width = f.get("width") or 0
            resolution = f"{width}x{height}" if width and height else (f"{height}p" if height else "未知")
            vbr = f.get("vbr") or f.get("tbr") or 0
            fs = f.get("filesize") or f.get("filesize_approx") or 0
            if not fs and vbr and duration:
                fs = int(vbr * 1000 / 8 * duration)
            vf.append({"id": f.get("format_id", ""), "quality": f.get("format_note") or f.get("format", ""),
                       "resolution": resolution, "codec": vcodec.split(".")[0] if vcodec else "未知",
                       "vbr": self._format_bitrate(vbr), "filesize": self._format_bytes(fs),
                       "_height": height, "_vbr": vbr, "_bytes": fs, "_has_audio": acodec != "none"})

        vf = self._deduplicate_formats(vf, lambda x: (x["_height"], x["codec"]))
        af = self._deduplicate_formats(af, lambda x: (x["_abr"], x["codec"]))
        vf.sort(key=lambda x: (x["_height"], x["_vbr"]), reverse=True)
        af.sort(key=lambda x: x["_abr"], reverse=True)
        self.root.after(0, self._bili_query_ok, vf, af)

    def _bili_query_error(self, msg):
        self.bili_query_btn.config(state=tk.NORMAL)
        self.bili_status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _bili_query_ok(self, vf, af):
        self.bili_query_btn.config(state=tk.NORMAL)
        self.bili_formats, self.bili_audio_formats = vf, af
        self._bili_v_ref[0] = None
        self.bili_video_tree.delete(*self.bili_video_tree.get_children())
        self.bili_title_var.set(self.bili_title)
        self.bili_author_var.set(f"@{self.bili_author}" if self.bili_author else "")
        for f in vf:
            self.bili_video_tree.insert("", tk.END, values=("☐", f["id"], f["quality"], f["resolution"], f["codec"], f["vbr"], f["filesize"]))
        if vf:
            b = vf[0]
            self.bili_status_var.set(f"查询完成 — {self.bili_title} — 视频: {len(vf)} 个, 音频: {len(af)} 个, 最佳: {b['quality']} {b['resolution']}")
        else:
            self.bili_status_var.set(f"查询完成 — {self.bili_title} — 未找到可用格式")

    def _bili_download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        if not self.bili_formats:
            messagebox.showwarning("提示", "请先查询视频信息")
            return
        v = self._get_checked(self.bili_video_tree, self._bili_v_ref, self.bili_formats)
        if v is None:
            v = self.bili_formats[0]
        if v["_has_audio"]:
            fmt_str = v["id"]
        elif self.bili_audio_formats:
            if not self._has_ffmpeg:
                messagebox.showwarning("缺少 ffmpeg", "未检测到 ffmpeg，B站视频音视频分离，需要 ffmpeg 合并。\n\n下载地址: https://ffmpeg.org/download.html")
                return
            a = self.bili_audio_formats[0]
            fmt_str = f"{v['id']}+{a['id']}"
            print(f"视频不含音频，自动选择最佳音频: {a['id']}")
        else:
            messagebox.showwarning("提示", "该视频格式不含音频且无可用的独立音频流")
            return
        print(f"下载格式: {fmt_str}")
        self._bili_start(fmt_str)

    def _bili_start(self, fmt_str):
        url = self.bili_url_entry.get().strip()
        if not url:
            return
        self.bili_dl_btn.config(state=tk.DISABLED)
        self.bili_progress["value"] = 0
        self.bili_status_var.set("正在下载...")
        threading.Thread(target=self._bili_do_dl, args=(url, fmt_str), daemon=True).start()

    def _bili_progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024**2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, self.bili_progress, self.bili_status_var, pct,
                                f"下载中... {pct}% — {speed_str}")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, self.bili_progress, self.bili_status_var, 100, "下载完成，正在合并音视频...")

    def _bili_do_dl(self, url, fmt_str):
        opts = {
            "format": fmt_str, "outtmpl": os.path.join(self.output_dir, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4", "progress_hooks": [self._bili_progress_hook],
            "quiet": True, "no_warnings": True,
        }
        if self.bili_cookie_mode == "file" and self.bili_cookie_file:
            opts["cookiefile"] = self.bili_cookie_file
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_dl_error, self.bili_dl_btn, self.bili_progress, self.bili_status_var, f"下载失败: {e}")
            return
        self.root.after(0, self._on_dl_success, self.bili_dl_btn, self.bili_progress, self.bili_status_var)

    # ═══════════════════════════════════════════════════════════════
    # 抖音 标签页
    # ═══════════════════════════════════════════════════════════════

    def _build_douyin_tab(self):
        p = self.douyin_frame

        self.dy_url_entry, self.dy_query_btn, _ = self._make_url_row(p, self._dy_query)

        # 格式列表
        ff = ttk.LabelFrame(p, text="视频格式 (勾选一个)", padding="4")
        ff.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        cols = ("fselect", "id", "quality", "resolution", "codec", "filesize", "note")
        self.dy_tree = ttk.Treeview(ff, columns=cols, show="headings", height=8, selectmode="none")
        for col, txt, w in zip(cols, ["☐", "序号", "画质", "分辨率", "编码", "预估大小", "码率"],
                               [36, 50, 100, 110, 100, 100, 100]):
            self.dy_tree.heading(col, text=txt)
            self.dy_tree.column(col, width=w, anchor=tk.CENTER)
        fs = ttk.Scrollbar(ff, orient=tk.VERTICAL, command=self.dy_tree.yview)
        self.dy_tree.configure(yscrollcommand=fs.set)
        self.dy_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fs.pack(side=tk.RIGHT, fill=tk.Y)
        self._dy_ref = [None]
        self.dy_tree.bind("<ButtonRelease-1>",
            self._on_tree_select(self.dy_tree, self._dy_ref, "fselect"))

        self.dy_title_var, self.dy_author_var = self._make_info_frame(p)
        self.dy_dir_var = self._make_dir_row(p)
        self.dy_progress = self._make_progress_bar(p)
        self.dy_dl_btn, self.dy_status_var = self._make_bottom_row(
            p, "下载", self._dy_download)
        self.dy_status_var.set("就绪 — 粘贴抖音视频链接，点击查询")
        p.bind("<Return>", lambda e: self._dy_query())

    @staticmethod
    def _dy_sanitize(name):
        name = name.replace("\r", " ").replace("\n", " ")
        name = re.sub(r'[\\/:*?"<>|]', '_', name)
        return re.sub(r'\s+', ' ', name).strip()

    @staticmethod
    def _dy_norm_url(url):
        m = re.search(r'modal_id=(\d+)', url)
        if m:
            return f"https://www.douyin.com/video/{m.group(1)}"
        if re.search(r'/video/\d+', url):
            return url
        return url

    @staticmethod
    def _dy_extract_id(url):
        m = re.search(r'/video/(\d+)', url)
        return m.group(1) if m else None

    # ── 抖音 查询 ─────────────────────────────────────────────────

    def _dy_query(self):
        url = self.dy_url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self.dy_query_btn.config(state=tk.DISABLED)
        self.dy_status_var.set("正在获取视频信息...")
        threading.Thread(target=self._dy_do_query, args=(url,), daemon=True).start()

    def _dy_do_query(self, url):
        from playwright.sync_api import sync_playwright

        url = self._dy_norm_url(url)
        vid = self._dy_extract_id(url)
        if not vid:
            self.root.after(0, self._dy_query_err, "无法从链接中提取视频 ID")
            return

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=UA, viewport={"width": 1920, "height": 1080})
                with self.dy_lock:
                    cs = list(self.dy_cookies)
                if cs:
                    ctx.add_cookies(cs)
                page = ctx.new_page()
                captured = []

                def on_resp(resp):
                    if "aweme" in resp.url:
                        captured.append(resp)
                page.on("response", on_resp)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                page.wait_for_timeout(12000)

                aweme = None
                for resp in captured:
                    try:
                        if "detail" in resp.url and resp.status == 200:
                            data = json.loads(resp.body())
                            if data.get("aweme_detail"):
                                aweme = data
                                break
                    except Exception:
                        continue
                browser.close()

                if not aweme:
                    self.root.after(0, self._dy_query_err, "未捕获到视频数据，请确认已登录抖音并获取 Cookie")
                    return
        except Exception as e:
            self.root.after(0, self._dy_query_err, f"Playwright 错误: {e}")
            return

        detail = aweme["aweme_detail"]
        self.dy_title = detail.get("desc", "未知")
        self.dy_author = (detail.get("author", {}) or {}).get("nickname", "")
        video = detail.get("video", {}) or {}
        dur_ms = detail.get("duration", 0) or 0
        bit_rates = video.get("bit_rate", [])
        if not bit_rates:
            bit_rates = [{"bit_rate": video.get("bit_rate", 0), "quality_type": 0, "play_addr": video.get("play_addr", {})}]

        formats = []
        for i, br in enumerate(bit_rates):
            if br.get("format", "") == "dash":
                continue
            play_addr = br.get("play_addr", {}) or {}
            urls = play_addr.get("url_list", [])
            w = play_addr.get("width", 0) or br.get("width", 0) or video.get("width", 0)
            h = play_addr.get("height", 0) or br.get("height", 0) or video.get("height", 0)
            resolution = f"{w}x{h}" if w and h else (f"{h}p" if h else "未知")
            bitrate = br.get("bit_rate", 0)
            qt = br.get("quality_type", 0)
            is_h265 = br.get("is_h265", 0) or br.get("is_bytevc1", 0)
            codec = "H.265" if is_h265 else "H.264"
            extra_str = br.get("video_extra", "")
            definition = ""
            if extra_str:
                try:
                    definition = json.loads(extra_str).get("definition", "")
                except (json.JSONDecodeError, TypeError):
                    pass
            qlabel = definition.upper() if definition else DOUYIN_QUALITY_LABELS.get(qt, f"Q{qt}")
            data_size = play_addr.get("data_size", 0)
            fs = data_size if data_size > 0 else (int(bitrate / 8 * dur_ms / 1000) if dur_ms > 0 and bitrate > 0 else 0)
            note_parts = [self._format_bitrate(bitrate)]
            formats.append({"idx": i, "quality": qlabel, "resolution": resolution, "codec": codec,
                           "filesize": self._format_bytes(fs), "note": " ".join(note_parts),
                           "_height": h, "_bitrate": bitrate, "_quality_type": qt, "_urls": urls})

        formats.sort(key=lambda x: (-x["_height"], -x["_bitrate"]))
        self.root.after(0, self._dy_query_ok, formats)

    def _dy_query_err(self, msg):
        self.dy_query_btn.config(state=tk.NORMAL)
        self.dy_status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _dy_query_ok(self, formats):
        self.dy_query_btn.config(state=tk.NORMAL)
        self.dy_formats = formats
        self._dy_ref[0] = None
        self.dy_tree.delete(*self.dy_tree.get_children())
        self.dy_title_var.set(self.dy_title)
        self.dy_author_var.set(f"@{self.dy_author}" if self.dy_author else "")
        for f in formats:
            self.dy_tree.insert("", tk.END, values=("☐", str(f["idx"] + 1), f["quality"], f["resolution"], f["codec"], f["filesize"], f["note"]))
        if formats:
            b = formats[0]
            self.dy_status_var.set(f"查询完成 — {self.dy_title} — 共 {len(formats)} 个格式, 最佳: {b['quality']} {b['resolution']} {b['note']}")
        else:
            self.dy_status_var.set(f"查询完成 — {self.dy_title} — 未找到可用格式")

    # ── 抖音 下载 ─────────────────────────────────────────────────

    def _dy_download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        if not self.dy_formats:
            messagebox.showwarning("提示", "请先查询视频信息")
            return
        f = self._get_checked(self.dy_tree, self._dy_ref, self.dy_formats)
        if f is None:
            f = self.dy_formats[0]
        self.dy_dl_btn.config(state=tk.DISABLED)
        self.dy_progress["value"] = 0
        self.dy_status_var.set("正在获取下载地址...")
        threading.Thread(target=self._dy_do_dl, args=(f,), daemon=True).start()

    def _dy_do_dl(self, fmt):
        urls = fmt.get("_urls", [])
        if not urls:
            self.root.after(0, self._on_dl_error, self.dy_dl_btn, self.dy_progress, self.dy_status_var, "没有可用的下载地址")
            return
        success = self._dy_dl_file(urls)
        if success:
            self.root.after(0, self._on_dl_success, self.dy_dl_btn, self.dy_progress, self.dy_status_var)
            return
        # 刷新 URL
        fresh = self._dy_refresh_urls(fmt)
        if not fresh:
            self.root.after(0, self._on_dl_error, self.dy_dl_btn, self.dy_progress, self.dy_status_var, "获取下载地址失败，请重新查询")
            return
        success = self._dy_dl_file(fresh)
        if success:
            self.root.after(0, self._on_dl_success, self.dy_dl_btn, self.dy_progress, self.dy_status_var)
        else:
            self.root.after(0, self._on_dl_error, self.dy_dl_btn, self.dy_progress, self.dy_status_var, "下载失败，所有地址不可用")

    def _dy_dl_file(self, url_list):
        safe = self._dy_sanitize(self.dy_title)
        for url in url_list:
            if not url.startswith("http"):
                continue
            try:
                resp = requests.get(url, stream=True, timeout=30,
                                   headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
                if resp.status_code in (403, 410):
                    continue
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0) or 0)
                out = os.path.join(self.output_dir, f"{safe}.mp4")
                downloaded = 0
                too_large = False
                with open(out, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            downloaded += len(chunk)
                            if downloaded > MAX_FILE_SIZE:
                                too_large = True
                                break
                            f.write(chunk)
                            pct = int(downloaded / total * 100) if total > 0 else 0
                            self.root.after(0, self._update_progress, self.dy_progress, self.dy_status_var,
                                          min(pct, 100), f"下载中... {min(pct, 100)}%")
                if too_large:
                    try:
                        os.remove(out)
                    except OSError:
                        pass
                    return False
                return True
            except (requests.RequestException, IOError):
                continue
        return False

    def _dy_refresh_urls(self, fmt):
        from playwright.sync_api import sync_playwright

        vid = self._dy_extract_id(self._dy_norm_url(self.dy_url_entry.get().strip()))
        if not vid:
            return []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=UA, viewport={"width": 1920, "height": 1080})
                with self.dy_lock:
                    cs = list(self.dy_cookies)
                if cs:
                    ctx.add_cookies(cs)
                page = ctx.new_page()
                captured = []

                def on_resp(resp):
                    if "aweme" in resp.url:
                        captured.append(resp)
                page.on("response", on_resp)
                try:
                    page.goto(f"https://www.douyin.com/video/{vid}", wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                page.wait_for_timeout(12000)
                for resp in captured:
                    try:
                        if "detail" in resp.url and resp.status == 200:
                            data = json.loads(resp.body())
                            bit_rates = (data.get("aweme_detail", {}) or {}).get("video", {}).get("bit_rate", [])
                            qt = fmt["_quality_type"]
                            br_match = fmt["_bitrate"]
                            for br_item in bit_rates:
                                if br_item.get("quality_type") == qt and br_item.get("bit_rate") == br_match:
                                    urls = (br_item.get("play_addr", {}) or {}).get("url_list", [])
                                    if urls:
                                        browser.close()
                                        return urls
                            if fmt["idx"] < len(bit_rates):
                                urls = (bit_rates[fmt["idx"]].get("play_addr", {}) or {}).get("url_list", [])
                                browser.close()
                                return urls
                    except Exception:
                        continue
                browser.close()
        except Exception:
            pass
        return []

    # ═══════════════════════════════════════════════════════════════
    # 虎牙 标签页
    # ═══════════════════════════════════════════════════════════════

    def _build_huya_tab(self):
        p = self.huya_frame

        self.huya_url_entry, self.huya_query_btn, _ = self._make_url_row(p, self._huya_query)

        ff = ttk.LabelFrame(p, text="可用格式 (勾选一个)", padding="4")
        ff.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        cols = ("select", "quality", "resolution", "ext", "protocol", "filesize")
        self.huya_tree = ttk.Treeview(ff, columns=cols, show="headings", height=6, selectmode="none")
        for col, txt, w in zip(cols, ["☐", "画质", "分辨率", "格式", "协议", "文件大小"],
                               [36, 100, 120, 60, 100, 100]):
            self.huya_tree.heading(col, text=txt)
            self.huya_tree.column(col, width=w, anchor=tk.CENTER)
        sc = ttk.Scrollbar(ff, orient=tk.VERTICAL, command=self.huya_tree.yview)
        self.huya_tree.configure(yscrollcommand=sc.set)
        self.huya_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self._huya_ref = [None]
        self.huya_tree.bind("<ButtonRelease-1>",
            self._on_tree_select(self.huya_tree, self._huya_ref, "select"))

        self.huya_title_var, self.huya_author_var = self._make_info_frame(p)
        self.huya_dir_var = self._make_dir_row(p)
        self.huya_progress = self._make_progress_bar(p)
        self.huya_dl_btn, self.huya_status_var = self._make_bottom_row(
            p, "下载", self._huya_download)
        self.huya_status_var.set("就绪 — 请粘贴虎牙视频链接并点击查询")
        p.bind("<Return>", lambda e: self._huya_query())

    def _huya_query(self):
        url = self.huya_url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self.huya_query_btn.config(state=tk.DISABLED)
        self.huya_status_var.set("正在获取视频信息...")
        threading.Thread(target=self._huya_do_query, args=(url,), daemon=True).start()

    def _huya_do_query(self, url):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._huya_query_err, f"获取信息失败: {e}")
            return

        self.huya_title = info.get("title", "未知")
        self.huya_author = info.get("uploader") or info.get("channel") or ""
        dur = info.get("duration") or 0
        raw = info.get("formats", [])
        formats = []
        for f in raw:
            h = f.get("height") or 0
            w = f.get("width") or 0
            resolution = f"{w}x{h}" if w and h else (f"{h}p" if h else "未知")
            fs = f.get("filesize") or f.get("filesize_approx") or 0
            if not fs:
                tbr = f.get("tbr") or 0
                if tbr and dur:
                    fs = int(tbr * 1000 / 8 * dur)
            fid = f.get("format_id", "")
            qlabel = f.get("format_note") or fid
            formats.append({"id": fid, "quality": qlabel, "resolution": resolution,
                           "ext": f.get("ext", "未知"), "protocol": f.get("protocol", "未知"),
                           "filesize": self._format_bytes(fs), "_height": h, "_bytes": fs})
        formats.sort(key=lambda x: x["_height"], reverse=True)
        self.root.after(0, self._huya_query_ok, formats)

    def _huya_query_err(self, msg):
        self.huya_query_btn.config(state=tk.NORMAL)
        self.huya_status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _huya_query_ok(self, formats):
        self.huya_query_btn.config(state=tk.NORMAL)
        self.huya_formats = formats
        self._huya_ref[0] = None
        self.huya_tree.delete(*self.huya_tree.get_children())
        self.huya_title_var.set(self.huya_title)
        self.huya_author_var.set(f"@{self.huya_author}" if self.huya_author else "")
        for f in formats:
            self.huya_tree.insert("", tk.END, values=("☐", f["quality"], f["resolution"], f["ext"], f["protocol"], f["filesize"]))
        if formats:
            b = formats[0]
            self.huya_status_var.set(f"查询完成 — {self.huya_title} — 共 {len(formats)} 个格式, 最高: {b['quality']} ({b['resolution']})")
        else:
            self.huya_status_var.set(f"查询完成 — {self.huya_title} — 未找到可用格式")

    def _huya_download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        if not self.huya_formats:
            messagebox.showwarning("提示", "请先查询视频信息")
            return
        f = self._get_checked(self.huya_tree, self._huya_ref, self.huya_formats)
        if f is None:
            f = self.huya_formats[0]
        print(f"下载格式: {f['id']}")
        self._huya_start(f["id"])

    def _huya_start(self, fmt_id):
        url = self.huya_url_entry.get().strip()
        if not url:
            return
        self.huya_dl_btn.config(state=tk.DISABLED)
        self.huya_progress["value"] = 0
        self.huya_status_var.set("正在下载...")
        threading.Thread(target=self._huya_do_dl, args=(url, fmt_id), daemon=True).start()

    def _huya_progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024**2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, self.huya_progress, self.huya_status_var, pct,
                                f"下载中... {pct}% — {speed_str}")

    def _huya_do_dl(self, url, fmt_id):
        opts = {
            "format": fmt_id, "outtmpl": os.path.join(self.output_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [self._huya_progress_hook], "quiet": True, "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_dl_error, self.huya_dl_btn, self.huya_progress, self.huya_status_var, f"下载失败: {e}")
            return
        self.root.after(0, self._on_dl_success, self.huya_dl_btn, self.huya_progress, self.huya_status_var)

    # ═══════════════════════════════════════════════════════════════
    # YouTube 标签页
    # ═══════════════════════════════════════════════════════════════

    def _build_youtube_tab(self):
        p = self.yt_frame

        self.yt_url_entry, self.yt_query_btn, _ = self._make_url_row(p, self._yt_query)

        # 登录
        lf = ttk.LabelFrame(p, text="Google 账户登录", padding="6")
        lf.pack(fill=tk.X, padx=8, pady=(4, 0))
        r1 = ttk.Frame(lf)
        r1.pack(fill=tk.X, pady=(0, 4))
        self.yt_login_btn = ttk.Button(r1, text="获取登录状态", command=self._yt_login)
        self.yt_login_btn.pack(side=tk.LEFT)
        self.yt_login_var = tk.StringVar(value="未登录 — 推荐 Firefox 登录 YouTube")
        ttk.Label(lf, textvariable=self.yt_login_var, foreground="gray").pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(lf, text="步骤: ① 用 Firefox 登录 youtube.com → ② 点击「获取登录状态」",
                  foreground="#0066cc").pack(anchor=tk.W, pady=(2, 0))

        # 视频格式
        vf = ttk.LabelFrame(p, text="视频格式 (勾选一个)", padding="4")
        vf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        v_cols = ("vselect", "id", "quality", "resolution", "codec", "vbr", "filesize")
        self.yt_video_tree = ttk.Treeview(vf, columns=v_cols, show="headings", height=5, selectmode="none")
        for col, txt, w in zip(v_cols, ["☐", "格式ID", "画质", "分辨率", "编码", "码率", "文件大小"],
                               [36, 70, 100, 110, 130, 85, 100]):
            self.yt_video_tree.heading(col, text=txt)
            self.yt_video_tree.column(col, width=w, anchor=tk.CENTER)
        vs = ttk.Scrollbar(vf, orient=tk.VERTICAL, command=self.yt_video_tree.yview)
        self.yt_video_tree.configure(yscrollcommand=vs.set)
        self.yt_video_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        self._yt_v_ref = [None]
        self.yt_video_tree.bind("<ButtonRelease-1>",
            self._on_tree_select(self.yt_video_tree, self._yt_v_ref, "vselect"))

        self.yt_title_var, self.yt_author_var = self._make_info_frame(p)
        self.yt_dir_var = self._make_dir_row(p)
        self.yt_progress = self._make_progress_bar(p)
        self.yt_dl_btn, self.yt_status_var = self._make_bottom_row(
            p, "下载", self._yt_download)
        self.yt_status_var.set("就绪 — 粘贴YouTube链接，点击查询")
        p.bind("<Return>", lambda _: self._yt_query())

    # ── YouTube 登录 ──────────────────────────────────────────────

    def _yt_login(self):
        self.yt_login_btn.config(state=tk.DISABLED)
        self.yt_login_var.set("正在检测 Firefox 中的 YouTube 登录状态...")
        threading.Thread(target=self._yt_do_login, args=("firefox",), daemon=True).start()

    def _yt_do_login(self, browser):
        opts = {"cookiesfrombrowser": (browser,), "quiet": True, "no_warnings": True,
                "playlistend": 0, "js_runtimes": {"node": {}}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info("https://www.youtube.com/watch?v=jNQXAC9IVRw", download=False)
            self.yt_cookies_browser = browser
            self.yt_use_cookies = True
            self.root.after(0, self._yt_login_ok)
        except Exception as e:
            err = str(e).lower()
            if any(kw in err for kw in ("permission", "sharing violation", "being used", "lock", "另一个程序正在使用", "进程无法访问")):
                msg = f"读取 {browser.title()} Cookie 失败，请关闭浏览器后重试"
            elif any(kw in err for kw in ("could not find", "no such file")):
                msg = f"未找到 {browser.title()} 浏览器数据"
            elif any(kw in err for kw in ("decrypt", "dpapi", "keyring")):
                msg = f"{browser.title()} Cookie 解密失败（App-Bound Encryption）。请改用 Firefox。"
            elif "incomplete login" in err or "you must be logged in" in err:
                msg = f"未检测到 {browser.title()} 中的 YouTube 登录信息"
            elif "cookies" in err and "not find" in err:
                msg = f"未检测到 {browser.title()} 中的 YouTube 登录信息"
            else:
                msg = f"检测失败: {str(e)[:250]}"
            self.root.after(0, self._yt_login_err, msg)

    def _yt_login_ok(self):
        self.yt_login_btn.config(state=tk.NORMAL)
        self.yt_login_var.set("已登录")
        self.yt_login_btn.config(foreground="green")

    def _yt_login_err(self, msg):
        self.yt_login_btn.config(state=tk.NORMAL)
        self.yt_use_cookies = False
        self.yt_login_var.set("未登录")
        messagebox.showerror("登录失败", msg)

    # ── YouTube 查询 ──────────────────────────────────────────────

    def _yt_query(self):
        if not self.yt_use_cookies:
            messagebox.showwarning("未登录", "请先点击「获取登录状态」登录 YouTube 后再查询")
            return
        url = self.yt_url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self.yt_query_btn.config(state=tk.DISABLED)
        self.yt_status_var.set("正在获取视频信息...")
        threading.Thread(target=self._yt_do_query, args=(url,), daemon=True).start()

    def _yt_do_query(self, url):
        opts = {"quiet": True, "no_warnings": True, "js_runtimes": {"node": {}}}
        if self.yt_use_cookies:
            opts["cookiesfrombrowser"] = (self.yt_cookies_browser,)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._yt_query_err, f"获取信息失败: {e}")
            return

        self.yt_title = info.get("title", "未知")
        self.yt_author = info.get("uploader") or info.get("channel") or ""
        dur = info.get("duration") or 0
        raw = info.get("formats", [])

        vf, af = [], []
        for f in raw:
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"

            if vcodec == "none" and acodec != "none":
                abr = f.get("abr") or f.get("tbr") or 0
                fs = f.get("filesize") or f.get("filesize_approx") or 0
                if not fs and abr and dur:
                    fs = int(abr * 1000 / 8 * dur)
                quality = "高音质" if abr >= 160 else ("标准音质" if abr >= 80 else (f.get("format_note") or "低音质"))
                af.append({"id": f.get("format_id", ""), "quality": quality,
                           "codec": acodec.split(".")[0] if acodec else "未知",
                           "abr": self._format_bitrate(abr), "filesize": self._format_bytes(fs),
                           "_abr": abr, "_bytes": fs})
                continue
            if vcodec == "none":
                continue

            h = f.get("height") or 0
            w = f.get("width") or 0
            resolution = f"{w}x{h}" if w and h else (f"{h}p" if h else "未知")
            vbr = f.get("vbr") or f.get("tbr") or 0
            fs = f.get("filesize") or f.get("filesize_approx") or 0
            if not fs and vbr and dur:
                fs = int(vbr * 1000 / 8 * dur)
            qlabel = f.get("format_note") or f.get("format", "")
            vf.append({"id": f.get("format_id", ""), "quality": qlabel, "resolution": resolution,
                       "codec": vcodec.split(".")[0] if vcodec else "未知",
                       "vbr": self._format_bitrate(vbr), "filesize": self._format_bytes(fs),
                       "_height": h, "_vbr": vbr, "_bytes": fs, "_has_audio": acodec != "none"})

        vf = self._deduplicate_formats(vf, lambda x: (x["_height"], x["codec"]))
        af = self._deduplicate_formats(af, lambda x: (x["_abr"], x["codec"]))
        vf.sort(key=lambda x: (x["_height"], x["_vbr"]), reverse=True)
        af.sort(key=lambda x: x["_abr"], reverse=True)
        self.root.after(0, self._yt_query_ok, vf, af)

    def _yt_query_err(self, msg):
        self.yt_query_btn.config(state=tk.NORMAL)
        self.yt_status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _yt_query_ok(self, vf, af):
        self.yt_query_btn.config(state=tk.NORMAL)
        self.yt_formats, self.yt_audio_formats = vf, af
        self._yt_v_ref[0] = None
        self.yt_video_tree.delete(*self.yt_video_tree.get_children())
        self.yt_title_var.set(self.yt_title)
        self.yt_author_var.set(f"@{self.yt_author}" if self.yt_author else "")
        for f in vf:
            self.yt_video_tree.insert("", tk.END, values=("☐", f["id"], f["quality"], f["resolution"], f["codec"], f["vbr"], f["filesize"]))
        if vf:
            b = vf[0]
            self.yt_status_var.set(f"查询完成 — {self.yt_title} — 视频: {len(vf)} 个, 音频: {len(af)} 个, 最佳: {b['quality']} {b['resolution']}")
        else:
            self.yt_status_var.set(f"查询完成 — {self.yt_title} — 未找到可用格式")

    # ── YouTube 下载 ──────────────────────────────────────────────

    def _yt_download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        if not self.yt_formats:
            messagebox.showwarning("提示", "请先查询视频信息")
            return
        v = self._get_checked(self.yt_video_tree, self._yt_v_ref, self.yt_formats)
        if v is None:
            v = self.yt_formats[0]
        if v["_has_audio"]:
            fmt_str = v["id"]
        elif self.yt_audio_formats:
            if not self._has_ffmpeg:
                messagebox.showwarning("缺少 ffmpeg", "未检测到 ffmpeg，需要安装 ffmpeg。\n下载地址: https://ffmpeg.org/download.html")
                return
            a = self.yt_audio_formats[0]
            fmt_str = f"{v['id']}+{a['id']}"
            print(f"视频不含音频，自动选择最佳音频: {a['id']}")
        else:
            messagebox.showwarning("提示", "该视频格式不含音频且无可用的独立音频流")
            return
        print(f"下载格式: {fmt_str}")
        self._yt_start(fmt_str)

    def _yt_start(self, fmt_str):
        url = self.yt_url_entry.get().strip()
        if not url:
            return
        self.yt_dl_btn.config(state=tk.DISABLED)
        self.yt_progress["value"] = 0
        self.yt_status_var.set("正在下载...")
        threading.Thread(target=self._yt_do_dl, args=(url, fmt_str), daemon=True).start()

    def _yt_progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024**2:.1f} MB/s" if speed else "--"
                info = d.get("info_dict", {}) or {}
                fmt_note = info.get("format_note", "") or info.get("format", "") or ""
                self.root.after(0, self._update_progress, self.yt_progress, self.yt_status_var, pct,
                                f"下载中... {pct}% — {speed_str} [{fmt_note}]")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, self.yt_progress, self.yt_status_var, 100, "下载完成，正在合并...")

    class _YTLogger:
        @staticmethod
        def debug(msg): print(f"[yt-dlp] {msg}") if msg.strip() else None
        @staticmethod
        def info(msg): print(f"[yt-dlp] {msg}") if msg.strip() else None
        @staticmethod
        def warning(msg): print(f"[yt-dlp WARN] {msg}") if msg.strip() else None
        @staticmethod
        def error(msg): print(f"[yt-dlp ERROR] {msg}") if msg.strip() else None

    def _yt_do_dl(self, url, fmt_str):
        opts = {
            "format": fmt_str, "outtmpl": os.path.join(self.output_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [self._yt_progress_hook], "logger": self._YTLogger(),
            "verbose": True, "js_runtimes": {"node": {}},
        }
        if self.yt_use_cookies:
            opts["cookiesfrombrowser"] = (self.yt_cookies_browser,)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_dl_error, self.yt_dl_btn, self.yt_progress, self.yt_status_var, f"下载失败: {e}")
            return
        self.root.after(0, self._on_dl_success, self.yt_dl_btn, self.yt_progress, self.yt_status_var)

    # ═══════════════════════════════════════════════════════════════
    # 小红书 标签页
    # ═══════════════════════════════════════════════════════════════

    def _build_xiaohongshu_tab(self):
        p = self.xhs_frame

        self.xhs_url_entry, self.xhs_query_btn, _ = self._make_url_row(p, self._xhs_query)

        # 格式列表
        ff = ttk.LabelFrame(p, text="可用画质 (勾选一个)", padding="4")
        ff.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        cols = ("select", "id", "quality", "resolution", "codec", "bitrate", "filesize")
        self.xhs_tree = ttk.Treeview(ff, columns=cols, show="headings", height=8, selectmode="none")
        for col, txt, w in zip(cols, ["☐", "格式ID", "画质", "分辨率", "编码", "码率", "文件大小"],
                               [36, 80, 100, 110, 140, 90, 100]):
            self.xhs_tree.heading(col, text=txt)
            self.xhs_tree.column(col, width=w, anchor=tk.CENTER)
        fs = ttk.Scrollbar(ff, orient=tk.VERTICAL, command=self.xhs_tree.yview)
        self.xhs_tree.configure(yscrollcommand=fs.set)
        self.xhs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fs.pack(side=tk.RIGHT, fill=tk.Y)
        self._xhs_ref = [None]
        self.xhs_tree.bind("<ButtonRelease-1>",
            self._on_tree_select(self.xhs_tree, self._xhs_ref, "select"))

        self.xhs_title_var, self.xhs_author_var = self._make_info_frame(p)
        self.xhs_dir_var = self._make_dir_row(p)
        self.xhs_progress = self._make_progress_bar(p)
        self.xhs_dl_btn, self.xhs_status_var = self._make_bottom_row(
            p, "下载", self._xhs_download)
        self.xhs_status_var.set("就绪 — 粘贴小红书笔记链接后点击查询")
        p.bind("<Return>", lambda e: self._xhs_query())

    def _xhs_query(self):
        url = self.xhs_url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频链接")
            return
        self.xhs_query_btn.config(state=tk.DISABLED)
        self.xhs_status_var.set("正在获取视频信息...")
        threading.Thread(target=self._xhs_do_query, args=(url,), daemon=True).start()

    def _xhs_do_query(self, url):
        opts = {"quiet": True, "no_warnings": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._xhs_query_err, f"获取信息失败: {e}")
            return

        self.xhs_title = info.get("title") or info.get("fulltitle") or "未知"
        self.xhs_author = info.get("uploader") or info.get("channel") or ""
        dur = info.get("duration") or 0
        raw = info.get("formats", [])
        formats = []
        for f in raw:
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"
            if vcodec == "none" and acodec != "none":
                continue
            h = f.get("height") or 0
            w = f.get("width") or 0
            resolution = f"{w}x{h}" if w and h else (f"{h}p" if h else "未知")
            tbr = f.get("tbr") or f.get("vbr") or 0
            fs = f.get("filesize") or f.get("filesize_approx") or 0
            if not fs and tbr and dur:
                fs = int(tbr * 1000 / 8 * dur)
            q = f.get("format_note") or f.get("format") or ""
            formats.append({"id": f.get("format_id", ""), "quality": q, "resolution": resolution,
                           "codec": f"{vcodec}/{acodec}".replace(".", ""),
                           "bitrate": self._format_bitrate(tbr), "filesize": self._format_bytes(fs),
                           "_height": h, "_tbr": tbr, "_bytes": fs})
        formats = self._deduplicate_formats(formats, lambda x: (x["_height"], x["codec"]))
        formats.sort(key=lambda x: (x["_height"], x["_tbr"]), reverse=True)
        self.root.after(0, self._xhs_query_ok, formats)

    def _xhs_query_err(self, msg):
        self.xhs_query_btn.config(state=tk.NORMAL)
        self.xhs_status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _xhs_query_ok(self, formats):
        self.xhs_query_btn.config(state=tk.NORMAL)
        self.xhs_formats = formats
        self._xhs_ref[0] = None
        self.xhs_tree.delete(*self.xhs_tree.get_children())
        self.xhs_title_var.set(self.xhs_title)
        self.xhs_author_var.set(f"@{self.xhs_author}" if self.xhs_author else "")
        for f in formats:
            self.xhs_tree.insert("", tk.END, values=("☐", f["id"], f["quality"], f["resolution"], f["codec"], f["bitrate"], f["filesize"]))
        if formats:
            b = formats[0]
            self.xhs_status_var.set(f"查询完成 — {self.xhs_title} — 共 {len(formats)} 个格式, 最佳: {b['quality']} {b['resolution']}")
        else:
            self.xhs_status_var.set(f"查询完成 — {self.xhs_title} — 未找到可用格式")

    def _xhs_download(self):
        if not self.agree_var.get():
            messagebox.showwarning("提示", "请先勾选同意「用户协议/免责声明」")
            return
        if not self.xhs_formats:
            messagebox.showwarning("提示", "请先查询视频信息")
            return
        f = self._get_checked(self.xhs_tree, self._xhs_ref, self.xhs_formats)
        if f is None:
            f = self.xhs_formats[0]
        self._xhs_start(f["id"])

    def _xhs_start(self, fmt_id):
        url = self.xhs_url_entry.get().strip()
        if not url:
            return
        self.xhs_dl_btn.config(state=tk.DISABLED)
        self.xhs_progress["value"] = 0
        self.xhs_status_var.set("正在下载...")
        threading.Thread(target=self._xhs_do_dl, args=(url, fmt_id), daemon=True).start()

    def _xhs_progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                speed = d.get("speed")
                speed_str = f"{speed / 1024**2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, self.xhs_progress, self.xhs_status_var, pct,
                                f"下载中... {pct}% — {speed_str}")
            else:
                speed = d.get("speed")
                speed_str = f"{speed / 1024**2:.1f} MB/s" if speed else "--"
                self.root.after(0, self._update_progress, self.xhs_progress, self.xhs_status_var, -1,
                                f"下载中... — {speed_str}")
        elif d["status"] == "finished":
            self.root.after(0, self._update_progress, self.xhs_progress, self.xhs_status_var, 100, "下载完成，正在处理...")

    def _xhs_do_dl(self, url, fmt_id):
        opts = {
            "format": fmt_id, "outtmpl": os.path.join(self.output_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [self._xhs_progress_hook], "quiet": True, "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_dl_error, self.xhs_dl_btn, self.xhs_progress, self.xhs_status_var, f"下载失败: {e}")
            return
        self.root.after(0, self._on_dl_success, self.xhs_dl_btn, self.xhs_progress, self.xhs_status_var)

    # ═══════════════════════════════════════════════════════════════
    # 通用回调
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _update_progress(bar, status_var, pct, msg):
        if pct >= 0:
            bar["value"] = pct
        status_var.set(msg)

    def _on_dl_error(self, btn, bar, status_var, msg):
        btn.config(state=tk.NORMAL)
        bar["value"] = 0
        status_var.set("下载失败")
        messagebox.showerror("错误", msg)

    def _on_dl_success(self, btn, bar, status_var):
        btn.config(state=tk.NORMAL)
        bar["value"] = 100
        status_var.set(f"下载完成 → {self.output_dir}")
        messagebox.showinfo("完成", f"视频已保存到:\n{self.output_dir}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    VideoDownloader().run()
