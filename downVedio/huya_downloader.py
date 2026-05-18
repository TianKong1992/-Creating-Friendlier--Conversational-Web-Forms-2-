"""
虎牙视频下载器 — 基于 yt-dlp 的 huya:video 提取器
虎牙的 HLS(m3u8) 格式自带音视频，无需 ffmpeg 合并
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp


class HuyaDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("虎牙视频下载器")
        self.root.geometry("780x500")
        self.root.resizable(True, True)
        self.root.minsize(600, 400)

        self.formats = []
        self.video_title = ""
        self.output_dir = os.path.expanduser("~\\Downloads")
        self.checked_iid = None

        self._build_ui()

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

        # 格式列表
        fmt_frame = ttk.LabelFrame(self.root, text="可用格式 (勾选一个)", padding="4")
        fmt_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        columns = ("select", "quality", "resolution", "ext", "protocol", "filesize")
        self.tree = ttk.Treeview(fmt_frame, columns=columns, show="headings",
                                 height=6, selectmode="none")
        self.tree.heading("select", text="☐")
        self.tree.heading("quality", text="画质")
        self.tree.heading("resolution", text="分辨率")
        self.tree.heading("ext", text="格式")
        self.tree.heading("protocol", text="协议")
        self.tree.heading("filesize", text="文件大小")
        self.tree.column("select", width=36, anchor=tk.CENTER)
        self.tree.column("quality", width=100, anchor=tk.CENTER)
        self.tree.column("resolution", width=120, anchor=tk.CENTER)
        self.tree.column("ext", width=60, anchor=tk.CENTER)
        self.tree.column("protocol", width=100, anchor=tk.CENTER)
        self.tree.column("filesize", width=100, anchor=tk.CENTER)

        scroll = ttk.Scrollbar(fmt_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<ButtonRelease-1>", self._on_click)

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

        # 按钮 + 状态
        bottom = ttk.Frame(self.root, padding="8 4 8 8")
        bottom.pack(fill=tk.X)
        self.dl_btn = ttk.Button(bottom, text="下载选中画质", command=self._download)
        self.dl_btn.pack(side=tk.LEFT)
        self.dl_best_btn = ttk.Button(bottom, text="下载最高画质", command=self._download_best)
        self.dl_best_btn.pack(side=tk.LEFT, padx=(6, 0))

        self.status_var = tk.StringVar(value="就绪 — 请粘贴虎牙视频链接并点击查询")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding="4 2 4 2").pack(fill=tk.X, side=tk.BOTTOM)

    # ── 格式选择 ──────────────────────────────────────────────────

    def _on_click(self, event):
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if self.checked_iid == iid:
            self.tree.set(iid, "select", "☐")
            self.checked_iid = None
        else:
            if self.checked_iid:
                self.tree.set(self.checked_iid, "select", "☐")
            self.tree.set(iid, "select", "☑")
            self.checked_iid = iid

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir, title="选择保存目录")
        if chosen:
            self.output_dir = chosen
            self.dir_var.set(chosen)

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

    def _do_query(self, url):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.root.after(0, self._on_query_error, f"获取信息失败: {e}")
            return

        self.video_title = info.get("title", "未知")
        duration = info.get("duration") or 0
        raw_formats = info.get("formats", [])

        formats = []
        for f in raw_formats:
            height = f.get("height") or 0
            width = f.get("width") or 0
            if width and height:
                resolution = f"{width}x{height}"
            elif height:
                resolution = f"{height}p"
            else:
                resolution = "未知"

            filesize = f.get("filesize") or f.get("filesize_approx") or 0
            if not filesize:
                tbr = f.get("tbr") or 0
                if tbr and duration:
                    filesize = int(tbr * 1000 / 8 * duration)

            fmt_id = f.get("format_id", "")
            # 虎牙用描述性 ID 如 "1080P"; 画质列用 quality 字段或 format_note
            quality_label = f.get("format_note") or fmt_id

            formats.append({
                "id": fmt_id,
                "quality": quality_label,
                "resolution": resolution,
                "ext": f.get("ext", "未知"),
                "protocol": f.get("protocol", "未知"),
                "filesize": self._format_bytes(filesize),
                "_height": height,
                "_bytes": filesize,
            })

        formats.sort(key=lambda x: x["_height"], reverse=True)
        self.root.after(0, self._on_query_success, formats)

    def _on_query_error(self, msg):
        self.query_btn.config(state=tk.NORMAL)
        self.status_var.set("查询失败")
        messagebox.showerror("错误", msg)

    def _on_query_success(self, formats):
        self.query_btn.config(state=tk.NORMAL)
        self.formats = formats
        self.checked_iid = None
        self.tree.delete(*self.tree.get_children())

        for f in formats:
            self.tree.insert("", tk.END, values=(
                "☐", f["quality"], f["resolution"],
                f["ext"], f["protocol"], f["filesize"]))

        if formats:
            best = formats[0]
            self.status_var.set(
                f"查询完成 — {self.video_title} — "
                f"共 {len(formats)} 个格式, 最高: {best['quality']} ({best['resolution']})")
        else:
            self.status_var.set(f"查询完成 — {self.video_title} — 未找到可用格式")

    # ── 下载 ──────────────────────────────────────────────────────

    def _get_checked(self):
        if self.checked_iid is None:
            return None
        try:
            idx = self.tree.index(self.checked_iid)
        except tk.TclError:
            return None
        if idx >= len(self.formats):
            return None
        return self.formats[idx]

    def _download(self):
        fmt = self._get_checked()
        if fmt is None:
            messagebox.showwarning("提示", "请先在列表中勾选一个格式")
            return
        self._start(fmt["id"])

    def _download_best(self):
        if not self.formats:
            messagebox.showwarning("提示", "请先查询视频信息")
            return
        self._start(self.formats[0]["id"])

    def _start(self, fmt_id):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.dl_btn.config(state=tk.DISABLED)
        self.dl_best_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("正在下载...")
        print(f"下载格式: {fmt_id}")
        threading.Thread(target=self._do_download, args=(url, fmt_id), daemon=True).start()

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

    def _update_progress(self, pct, msg):
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
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            self.root.after(0, self._on_error, f"下载失败: {e}")
            return
        self.root.after(0, self._on_success)

    def _on_error(self, msg):
        self.dl_btn.config(state=tk.NORMAL)
        self.dl_best_btn.config(state=tk.NORMAL)
        self.progress["value"] = 0
        self.status_var.set("下载失败")
        messagebox.showerror("错误", msg)

    def _on_success(self):
        self.dl_btn.config(state=tk.NORMAL)
        self.dl_best_btn.config(state=tk.NORMAL)
        self.progress["value"] = 100
        self.status_var.set(f"下载完成 → {self.output_dir}")
        messagebox.showinfo("完成", f"视频已保存到:\n{self.output_dir}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    HuyaDownloader().run()
