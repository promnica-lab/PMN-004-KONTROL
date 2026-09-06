import json
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.request
import urllib.error
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROMPT_PATH = APP_DIR / "kontrol_prompt.txt"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:4b"
MAX_CHARS = 2000
REQUEST_TIMEOUT = 120
SLOW_WARNING_SECONDS = 60

BG = "#090c12"
PANEL = "#111824"
PANEL_2 = "#0d131d"
CYAN = "#27d9e8"
CYAN_DARK = "#12363e"
TEXT = "#e9f7ff"
MUTED = "#91a4b7"
BORDER = "#263446"
WARN = "#f0b35a"
DANGER = "#ef6a6a"
GOOD = "#73d69a"

def clamp_score(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0

def score_color(score):
    if score >= 70:
        return DANGER
    if score >= 40:
        return WARN
    return GOOD

def risk_label(score):
    if score >= 85:
        return "CRITICAL / 高危険"
    if score >= 70:
        return "HIGH / 高"
    if score >= 40:
        return "CAUTION / 注意"
    return "LOW / 低"

def corrected_overall_score(result):
    """AI値に最低保証ルールを適用する。"""
    ai_score = clamp_score(result.get("overall_risk", {}).get("score", 0))
    humble = clamp_score(result.get("humblebrag", {}).get("score", 0))

    floor = 0
    if humble >= 85:
        floor = 45
    elif humble >= 70:
        floor = 35
    elif humble >= 40:
        floor = 25

    return max(ai_score, floor)

class KontrolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PMN-004 KONTROL")
        self.geometry("940x920")
        self.minsize(820, 760)
        self.configure(bg=BG)

        self._request_id = 0
        self._elapsed_seconds = 0
        self._analysis_running = False

        self._build_ui()

    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure(
            "Kontrol.Horizontal.TProgressbar",
            troughcolor=PANEL,
            background=CYAN,
            bordercolor=BORDER,
            lightcolor=CYAN,
            darkcolor=CYAN,
            thickness=12,
        )

    def _label(self, parent, text, size=11, color=TEXT, bold=False):
        return tk.Label(
            parent,
            text=text,
            bg=parent["bg"],
            fg=color,
            font=("Yu Gothic UI", size, "bold" if bold else "normal"),
        )

    def _button(self, parent, text, command, primary=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=CYAN if primary else PANEL_2,
            fg=BG if primary else TEXT,
            activebackground="#5ce8f2" if primary else CYAN_DARK,
            activeforeground=BG if primary else TEXT,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            font=("Yu Gothic UI", 10, "bold"),
            highlightthickness=1,
            highlightbackground=CYAN if primary else BORDER,
        )

    def _panel(self, parent, **kwargs):
        return tk.Frame(
            parent,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER,
            **kwargs,
        )

    def _build_ui(self):
        self._build_styles()

        outer = tk.Frame(self, bg=BG, padx=20, pady=18)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 14))

        tk.Label(
            header,
            text="PMN-004",
            bg=BG,
            fg=CYAN,
            font=("Consolas", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="KONTROL",
            bg=BG,
            fg=TEXT,
            font=("Consolas", 29, "bold"),
        ).pack(anchor="w", pady=(1, 0))
        tk.Label(
            header,
            text="投稿事前検問装置",
            bg=BG,
            fg=MUTED,
            font=("Yu Gothic UI", 11),
        ).pack(anchor="w")
        tk.Frame(header, bg=CYAN, height=2).pack(fill="x", pady=(10, 0))

        inp = self._panel(outer)
        inp.pack(fill="x", pady=(0, 12))

        top = tk.Frame(inp, bg=PANEL)
        top.pack(fill="x", padx=14, pady=(12, 8))
        self._label(top, "SUBMISSION / 投稿予定文", 10, CYAN, True).pack(side="left")

        self.char_count_var = tk.StringVar(value=f"0 / {MAX_CHARS}")
        tk.Label(
            top,
            textvariable=self.char_count_var,
            bg=PANEL,
            fg=MUTED,
            font=("Consolas", 9, "bold"),
        ).pack(side="right")

        self.input_text = tk.Text(
            inp,
            height=6,
            wrap="word",
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=CYAN,
            selectbackground=CYAN_DARK,
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            font=("Yu Gothic UI", 11),
            padx=12,
            pady=10,
        )
        self.input_text.pack(fill="x", padx=14, pady=(0, 10))
        self.input_text.bind("<<Modified>>", self._on_text_modified)
        self.input_text.edit_modified(False)

        btnrow = tk.Frame(inp, bg=PANEL)
        btnrow.pack(fill="x", padx=14, pady=(0, 8))

        self._button(btnrow, "CLIPBOARD", self.paste_clipboard).pack(side="left")
        self._button(
            btnrow,
            "CLEAR",
            lambda: self.input_text.delete("1.0", "end"),
        ).pack(side="left", padx=(8, 0))

        self.cancel_btn = self._button(btnrow, "中止", self.cancel_analysis)
        self.cancel_btn.pack(side="right", padx=(8, 0))
        self.cancel_btn.config(state="disabled")

        self.analyze_btn = self._button(
            btnrow,
            "検問開始",
            self.start_analysis,
            primary=True,
        )
        self.analyze_btn.pack(side="right")

        status_box = tk.Frame(
            inp,
            bg=PANEL_2,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        status_box.pack(fill="x", padx=14, pady=(0, 12))

        status_top = tk.Frame(status_box, bg=PANEL_2)
        status_top.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(
            status_top,
            text="STATUS",
            bg=PANEL_2,
            fg=CYAN,
            font=("Consolas", 10, "bold"),
        ).pack(side="left")

        self.status_detail_var = tk.StringVar(value="待機中")
        tk.Label(
            status_top,
            textvariable=self.status_detail_var,
            bg=PANEL_2,
            fg=MUTED,
            font=("Yu Gothic UI", 9),
        ).pack(side="left", padx=(12, 0))

        self.elapsed_var = tk.StringVar(value="")
        tk.Label(
            status_top,
            textvariable=self.elapsed_var,
            bg=PANEL_2,
            fg=MUTED,
            font=("Consolas", 9),
        ).pack(side="right")

        self.progress = ttk.Progressbar(
            status_box,
            mode="indeterminate",
            style="Kontrol.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", padx=10, pady=(0, 10))

        notice = tk.Frame(
            outer,
            bg=CYAN_DARK,
            highlightthickness=1,
            highlightbackground="#1d5964",
        )
        notice.pack(fill="x", pady=(0, 12))
        tk.Label(
            notice,
            text="最大2,000文字 ｜ 判定対象：炎上・攻撃・後悔などの危険信号 ｜ 面白さ・センス・バズりやすさは判定しません",
            bg=CYAN_DARK,
            fg=TEXT,
            font=("Yu Gothic UI", 9),
            anchor="w",
            padx=12,
            pady=8,
        ).pack(fill="x")

        result = self._panel(outer)
        result.pack(fill="both", expand=True)

        result_head = tk.Frame(result, bg=PANEL)
        result_head.pack(fill="x", padx=14, pady=(12, 8))
        self._label(
            result_head,
            "INSPECTION RESULT / 検問結果",
            10,
            CYAN,
            True,
        ).pack(side="left")

        self.status_var = tk.StringVar(value="STANDBY")
        tk.Label(
            result_head,
            textvariable=self.status_var,
            bg=PANEL,
            fg=MUTED,
            font=("Consolas", 9, "bold"),
        ).pack(side="right")

        holder = tk.Frame(result, bg=PANEL_2)
        holder.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.canvas = tk.Canvas(holder, bg=PANEL_2, highlightthickness=0)
        scroll = tk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)

        self.result_inner = tk.Frame(self.canvas, bg=PANEL_2)
        self.result_inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.result_inner,
            anchor="nw",
        )
        self.canvas.bind("<Configure>", self._resize_result_window)
        self.canvas.configure(yscrollcommand=scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind_all("<Button-4>", self._on_mousewheel_linux, add="+")
        self.bind_all("<Button-5>", self._on_mousewheel_linux, add="+")

        self._empty_result()

    def _on_text_modified(self, event=None):
        if not self.input_text.edit_modified():
            return

        text = self.input_text.get("1.0", "end-1c")
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", text)
            self.bell()

        count = len(text)
        self.char_count_var.set(f"{count} / {MAX_CHARS}")
        self.input_text.edit_modified(False)

    def paste_clipboard(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("KONTROL", "クリップボードにテキストがありません。")
            return

        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
            messagebox.showinfo(
                "KONTROL",
                f"入力上限は{MAX_CHARS:,}文字です。\n先頭{MAX_CHARS:,}文字を取り込みました。",
            )

        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)

    def _pointer_is_over_results(self):
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            rx = self.canvas.winfo_rootx()
            ry = self.canvas.winfo_rooty()
            rw = self.canvas.winfo_width()
            rh = self.canvas.winfo_height()
            return rx <= x <= rx + rw and ry <= y <= ry + rh
        except Exception:
            return False

    def _on_mousewheel(self, event):
        if not self._pointer_is_over_results():
            return
        delta = event.delta
        if delta == 0:
            return
        steps = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(steps * 3, "units")
        return "break"

    def _on_mousewheel_linux(self, event):
        if not self._pointer_is_over_results():
            return
        direction = -3 if event.num == 4 else 3
        self.canvas.yview_scroll(direction, "units")
        return "break"

    def _resize_result_window(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _clear_result_widgets(self):
        for widget in self.result_inner.winfo_children():
            widget.destroy()

    def _empty_result(self):
        self._clear_result_widgets()
        tk.Label(
            self.result_inner,
            text="投稿文を入力して「検問開始」を押してください。",
            bg=PANEL_2,
            fg=MUTED,
            font=("Yu Gothic UI", 11),
            padx=14,
            pady=20,
            anchor="w",
        ).pack(fill="x")

    def _set_status_detail(self, text):
        self.status_detail_var.set(text)

    def _start_progress(self):
        self._elapsed_seconds = 0
        self.elapsed_var.set("0s")
        self.progress.start(12)
        self._tick_elapsed()

    def _tick_elapsed(self):
        if not self._analysis_running:
            return

        self._elapsed_seconds += 1
        self.elapsed_var.set(f"{self._elapsed_seconds}s")

        if self._elapsed_seconds == SLOW_WARNING_SECONDS:
            self.status_detail_var.set(
                "判定に時間がかかっています。長文では処理が遅くなる場合があります。"
            )

        self.after(1000, self._tick_elapsed)

    def _stop_progress(self):
        self.progress.stop()

    def start_analysis(self):
        post = self.input_text.get("1.0", "end-1c").strip()
        if not post:
            messagebox.showwarning("KONTROL", "投稿文を入力してください。")
            return

        if len(post) > MAX_CHARS:
            messagebox.showwarning(
                "KONTROL",
                f"投稿文は{MAX_CHARS:,}文字以内にしてください。",
            )
            return

        self._request_id += 1
        request_id = self._request_id
        self._analysis_running = True

        self.analyze_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.status_var.set("INSPECTING...")
        self._set_status_detail("検問を開始しています...")
        self._start_progress()

        self._clear_result_widgets()
        tk.Label(
            self.result_inner,
            text="検問中...",
            bg=PANEL_2,
            fg=CYAN,
            font=("Consolas", 12, "bold"),
            padx=14,
            pady=20,
        ).pack(anchor="w")

        threading.Thread(
            target=self.analyze,
            args=(post, request_id),
            daemon=True,
        ).start()

    def cancel_analysis(self):
        if not self._analysis_running:
            return

        # 返ってきた古い結果を破棄するためIDを更新する。
        self._request_id += 1
        self._analysis_running = False

        self._stop_progress()
        self.status_var.set("CANCELLED")
        self.status_detail_var.set("検問を中止しました")
        self.analyze_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

        self._clear_result_widgets()
        tk.Label(
            self.result_inner,
            text="検問を中止しました。",
            bg=PANEL_2,
            fg=WARN,
            font=("Yu Gothic UI", 10, "bold"),
            padx=14,
            pady=20,
            anchor="w",
        ).pack(fill="x")

    def analyze(self, post, request_id):
        try:
            self.after(0, self._set_status_detail, "判定基準を読み込み中...")
            system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

            payload = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"投稿文:\n{post}"},
                ],
                "stream": False,
                "format": "json",
                # KONTROLは分類用途なので思考モードを使わず速度を優先する。
                "think": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 4096,
                    "num_predict": 512,
                },
            }

            self.after(0, self._set_status_detail, "ローカルAIで検問中...")

            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                raw = json.loads(res.read().decode("utf-8"))

            content = raw.get("message", {}).get("content", "")
            result = json.loads(content)

            if request_id != self._request_id:
                return

            self.after(0, self.finish_success, result, request_id)

        except urllib.error.URLError:
            if request_id != self._request_id:
                return
            self.after(
                0,
                self.finish_error,
                "Ollamaに接続できません。\n"
                "Ollamaが起動しているか、qwen3:4b が導入済みか確認してください。",
                request_id,
            )
        except Exception as exc:
            if request_id != self._request_id:
                return
            self.after(0, self.finish_error, str(exc), request_id)

    def _make_summary(self, parent, result):
        item = result.get("overall_risk", {})
        ai_score = clamp_score(item.get("score", 0))
        score = corrected_overall_score(result)
        reason = str(item.get("reason", "")).strip()
        color = score_color(score)

        box = tk.Frame(
            parent,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=color,
        )
        box.pack(fill="x", padx=7, pady=(7, 10))

        left = tk.Frame(box, bg=PANEL)
        left.pack(side="left", fill="both", expand=True, padx=16, pady=12)

        tk.Label(
            left,
            text="OVERALL / 総合投稿リスク",
            bg=PANEL,
            fg=CYAN,
            font=("Consolas", 10, "bold"),
        ).pack(anchor="w")

        tk.Label(
            left,
            text=risk_label(score),
            bg=PANEL,
            fg=color,
            font=("Yu Gothic UI", 16, "bold"),
        ).pack(anchor="w", pady=(4, 4))

        summary = reason or "理由なし"
        if score > ai_score:
            summary += "  ※KONTROL補正を適用"

        tk.Label(
            left,
            text=summary,
            bg=PANEL,
            fg=MUTED,
            font=("Yu Gothic UI", 10),
            justify="left",
            anchor="w",
            wraplength=620,
        ).pack(fill="x")

        right = tk.Frame(box, bg=PANEL)
        right.pack(side="right", padx=18, pady=10)

        tk.Label(
            right,
            text=f"{score:02d}",
            bg=PANEL,
            fg=color,
            font=("Consolas", 34, "bold"),
        ).pack()
        tk.Label(
            right,
            text="/ 100",
            bg=PANEL,
            fg=MUTED,
            font=("Consolas", 9),
        ).pack()

    def _make_card(self, parent, label, item, row, col, colspan=1):
        score = clamp_score(item.get("score", 0))
        reason = str(item.get("reason", "")).strip()

        card = tk.Frame(
            parent,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        card.grid(
            row=row,
            column=col,
            columnspan=colspan,
            sticky="nsew",
            padx=7,
            pady=7,
        )

        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x", padx=12, pady=(10, 3))

        tk.Label(
            top,
            text=label,
            bg=PANEL,
            fg=TEXT,
            font=("Yu Gothic UI", 11, "bold"),
        ).pack(side="left")

        tk.Label(
            top,
            text=f"{score:02d}",
            bg=PANEL,
            fg=score_color(score),
            font=("Consolas", 18, "bold"),
        ).pack(side="right")

        bar_bg = tk.Frame(card, bg=BORDER, height=6)
        bar_bg.pack(fill="x", padx=12, pady=(3, 7))

        fill = tk.Frame(bar_bg, bg=score_color(score), height=6)
        self.after_idle(
            lambda f=fill, s=score:
            f.place(x=0, y=0, relheight=1, relwidth=s / 100)
        )

        wrap = 680 if colspan == 2 else 330
        tk.Label(
            card,
            text=reason or "理由なし",
            bg=PANEL,
            fg=MUTED,
            font=("Yu Gothic UI", 9),
            justify="left",
            anchor="w",
            wraplength=wrap,
            padx=12,
            pady=6,
        ).pack(fill="x")

    def finish_success(self, result, request_id):
        if request_id != self._request_id:
            return

        self._analysis_running = False
        self._stop_progress()
        self._set_status_detail("検問完了")

        self._clear_result_widgets()
        self._make_summary(self.result_inner, result)

        grid = tk.Frame(self.result_inner, bg=PANEL_2)
        grid.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        grid.columnconfigure(0, weight=1, uniform="cols")
        grid.columnconfigure(1, weight=1, uniform="cols")

        self._make_card(grid, "怒り", result.get("anger", {}), 0, 0)
        self._make_card(grid, "攻撃性", result.get("aggression", {}), 0, 1)
        self._make_card(grid, "人格攻撃", result.get("personal_attack", {}), 1, 0)
        self._make_card(
            grid,
            "ハンブルブランギング",
            result.get("humblebrag", {}),
            1,
            1,
        )
        self._make_card(
            grid,
            "後悔リスク",
            result.get("regret_risk", {}),
            2,
            0,
            colspan=2,
        )

        self.status_var.set("COMPLETE")
        self.analyze_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

    def finish_error(self, text, request_id):
        if request_id != self._request_id:
            return

        self._analysis_running = False
        self._stop_progress()
        self._set_status_detail("エラー")

        self._clear_result_widgets()
        tk.Label(
            self.result_inner,
            text=text,
            bg=PANEL_2,
            fg=DANGER,
            font=("Yu Gothic UI", 10),
            justify="left",
            anchor="w",
            padx=14,
            pady=20,
        ).pack(fill="x")

        self.status_var.set("ERROR")
        self.analyze_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

if __name__ == "__main__":
    KontrolApp().mainloop()
