"""One-question-at-a-time wizard.

The student sees a single question, types the answer in their own words, and hits
Continue. What they type is mapped onto the tag vocabulary by textmatch, shown back
to them as chips so they can correct it, and only at the end does the ranking appear.

The matching engine is untouched -- this is purely a different way of collecting
the same four weighted inputs.

Colour: each of the four inputs owns a hue, and that hue follows it everywhere --
the step pill, the progress bar, the question heading, its chips, and its weight on
the results screen. Match strength and schooling length are colour-coded too, so the
results table can be read at a glance.

Layout: a centred square card on a dark page. Tk widgets can't have rounded
corners, so the card is a rounded rectangle drawn on a Canvas with the content
frame inset on top of it -- the frame's square corners sit inside the curve, in
the same colour, and the drawn radius is what you see.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List

from .dataset import dataset_meta, fields, label, load_careers
from .generator import get_generator
from .models import DIMENSION_LABELS, DIMENSIONS, StudentProfile
from .recommender import Recommender
from .report import format_recommendation, to_markdown
from .textmatch import extract, suggestions

QUESTIONS = [
    ("interests", "What do you actually enjoy?",
     "Hobbies, subjects, anything you lose track of time doing."),
    ("subjects", "Which classes do you like or do well in?",
     "List the ones you'd take again."),
    ("work_style", "How do you want to spend your workday?",
     "Think about where you are, who you're with, and how it feels."),
    ("values", "What matters most to you in a job?",
     "What would make you say yes to one job over another?"),
]

# ------------------------------------------------------------------ palette
PAGE = "#0d0f14"
CARD = "#171a21"
FIELD = "#21252e"
LINE = "#2c313c"
INK = "#eef1f6"
MUTED = "#98a1b2"
DIM = "#5d6675"

# one hue per input, reused everywhere that input appears
DIM_COLORS = {
    "interests":  "#ff8a4c",   # orange
    "subjects":   "#4f9cf9",   # blue
    "work_style": "#3ecf8e",   # green
    "values":     "#c77dff",   # violet
}
DIM_SOFT = {
    "interests":  "#3a2318",
    "subjects":   "#152a44",
    "work_style": "#12332a",
    "values":     "#2d1f3d",
}

# match strength
STRONG_C, GOOD_C, FAIR_C = "#3ecf8e", "#4f9cf9", "#e0a03a"
# schooling length
EDU_COLORS = {
    "high_school": "#3ecf8e", "certificate": "#3ecf8e",
    "associate": "#4f9cf9", "bachelor": "#4f9cf9",
    "master": "#c77dff", "doctorate": "#ff6b8a",
}

CARD_SIZE = 660
RADIUS = 24
INSET = 30


def match_color(pct: float) -> str:
    return STRONG_C if pct >= 80 else GOOD_C if pct >= 60 else FAIR_C


class Wizard:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("FutureForge")
        master.geometry("940x820")
        master.minsize(760, 740)
        master.configure(bg=PAGE)

        self.careers = load_careers()
        self.meta = dataset_meta()
        generator, self.mode_status = get_generator()
        self.recommender = Recommender(careers=self.careers, generator=generator)

        self.answers: Dict[str, str] = {d: "" for d in DIMENSIONS}
        self.picked: Dict[str, List[str]] = {d: [] for d in DIMENSIONS}
        self.name = "Student"
        self.grade = "11"
        self.years = 4
        self.pay = 3
        self.recommendations: List = []
        self._queue: "queue.Queue" = queue.Queue()

        self.step = 0
        self.total_steps = len(QUESTIONS)

        self.canvas = tk.Canvas(master, bg=PAGE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.card = tk.Frame(self.canvas, bg=CARD)
        self.card_item = self.canvas.create_window(
            0, 0, window=self.card, anchor="nw",
            width=CARD_SIZE - INSET * 2, height=CARD_SIZE - INSET * 2)
        self.canvas.bind("<Configure>", lambda e: self._place_card())

        master.bind("<Return>", lambda e: self.next())
        master.bind("<Escape>", lambda e: self.back())

        self._build_card()
        self._render()

    # ------------------------------------------------------------ card shell
    def _rounded(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _place_card(self) -> None:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        x, y = max(0, (w - CARD_SIZE) // 2), max(0, (h - CARD_SIZE) // 2)
        self.canvas.delete("cardbg")
        # a soft accent glow in the current step's colour, behind the card
        accent = self._current_color()
        self._rounded(x - 2, y - 2, x + CARD_SIZE + 2, y + CARD_SIZE + 2,
                      RADIUS + 2, fill=accent, outline="", tags="cardbg")
        self._rounded(x, y, x + CARD_SIZE, y + CARD_SIZE, RADIUS,
                      fill=CARD, outline="", tags="cardbg")
        self.canvas.coords(self.card_item, x + INSET, y + INSET)

    def _current_color(self) -> str:
        if 1 <= self.step <= self.total_steps:
            return DIM_COLORS[QUESTIONS[self.step - 1][0]]
        return "#4f9cf9" if self.step == 0 else STRONG_C

    def _build_card(self) -> None:
        head = tk.Frame(self.card, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="FutureForge", font=("Helvetica", 15, "bold"),
                 bg=CARD, fg=INK).pack(side="left")
        self.progress_lbl = tk.Label(head, text="", font=("Helvetica", 11),
                                     bg=CARD, fg=MUTED)
        self.progress_lbl.pack(side="right")

        # clickable colour-coded step pills
        self.steps_bar = tk.Frame(self.card, bg=CARD)
        self.steps_bar.pack(fill="x", pady=(12, 0))
        self.step_pills = {}
        for index, (dimension, _, _) in enumerate(QUESTIONS, start=1):
            pill = tk.Frame(self.steps_bar, bg=FIELD, height=5,
                            highlightthickness=0)
            pill.pack(side="left", fill="x", expand=True,
                      padx=(0, 5 if index < self.total_steps else 0))
            pill.bind("<Button-1>", lambda e, s=index: self.jump(s))
            self.step_pills[index] = pill

        self.legend = tk.Frame(self.card, bg=CARD)
        self.legend.pack(fill="x", pady=(6, 0))
        self.legend_labels = {}
        for index, (dimension, _, _) in enumerate(QUESTIONS, start=1):
            lbl = tk.Label(self.legend, text=DIMENSION_LABELS[dimension],
                           font=("Helvetica", 9), bg=CARD, fg=DIM, cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True)
            lbl.bind("<Button-1>", lambda e, s=index: self.jump(s))
            self.legend_labels[index] = (lbl, dimension)

        self.body = tk.Frame(self.card, bg=CARD)
        self.body.pack(fill="both", expand=True, pady=4)

        foot = tk.Frame(self.card, bg=CARD)
        foot.pack(fill="x")
        self.back_btn = ttk.Button(foot, text="←  Back", style="Ghost.TButton",
                                   command=self.back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(foot, text="Continue", style="Accent.TButton",
                                   command=self.next)
        self.next_btn.pack(side="right")
        self.status_lbl = tk.Label(foot, text="", bg=CARD, fg=MUTED,
                                   font=("Helvetica", 11))
        self.status_lbl.pack(side="right", padx=12)

    def _paint_steps(self) -> None:
        for index, pill in self.step_pills.items():
            dimension = QUESTIONS[index - 1][0]
            done = self.step > index or self.step > self.total_steps
            here = self.step == index
            pill.configure(bg=DIM_COLORS[dimension] if (done or here) else FIELD,
                           height=6 if here else 4)
            lbl, dim_name = self.legend_labels[index]
            lbl.configure(fg=DIM_COLORS[dim_name] if (done or here) else DIM,
                          font=("Helvetica", 9, "bold" if here else "normal"))

    def _clear(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

    # ----------------------------------------------------------------- steps
    def _render(self) -> None:
        self._clear()
        self.status_lbl.config(text="")
        if self.step == 0:
            self._render_intro()
        elif 1 <= self.step <= self.total_steps:
            self._render_question(self.step - 1)
        elif self.step == self.total_steps + 1:
            self._render_practical()
        else:
            self._render_results()
        self._paint_steps()
        self._place_card()

    def _title(self, text: str, size: int = 22, color: str = INK) -> None:
        tk.Label(self.body, text=text, font=("Helvetica", size, "bold"), bg=CARD,
                 fg=color, wraplength=CARD_SIZE - INSET * 2 - 8,
                 justify="left").pack(anchor="w", pady=(14, 6))

    def _sub(self, text: str) -> None:
        tk.Label(self.body, text=text, font=("Helvetica", 12), bg=CARD, fg=MUTED,
                 wraplength=CARD_SIZE - INSET * 2 - 8,
                 justify="left").pack(anchor="w", pady=(0, 12))

    def _render_intro(self) -> None:
        self.progress_lbl.config(text="%d careers  ·  %d fields" % (
            len(self.careers), len(fields(self.careers))))
        self._title("Let's find careers\nthat fit you.", 26)
        self._sub("Four questions, answered in your own words. Two minutes.")

        # colour key for the four inputs
        for dimension, question, _ in QUESTIONS:
            row = tk.Frame(self.body, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Frame(row, bg=DIM_COLORS[dimension], width=4, height=20).pack(
                side="left", padx=(0, 10))
            tk.Label(row, text=DIMENSION_LABELS[dimension], bg=CARD,
                     fg=DIM_COLORS[dimension], font=("Helvetica", 11, "bold"),
                     width=20, anchor="w").pack(side="left")
            tk.Label(row, text=question, bg=CARD, fg=MUTED,
                     font=("Helvetica", 10), anchor="w").pack(side="left")

        row = tk.Frame(self.body, bg=CARD)
        row.pack(anchor="w", pady=(18, 0))
        tk.Label(row, text="Your name", font=("Helvetica", 11), bg=CARD,
                 fg=MUTED).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.name_var = tk.StringVar(value=self.name)
        ttk.Entry(row, textvariable=self.name_var, width=24,
                  font=("Helvetica", 13)).grid(row=1, column=0, sticky="w", ipady=4)
        tk.Label(row, text="Grade", font=("Helvetica", 11), bg=CARD,
                 fg=MUTED).grid(row=0, column=1, sticky="w", padx=(16, 0), pady=(0, 4))
        self.grade_var = tk.StringVar(value=self.grade)
        ttk.Combobox(row, textvariable=self.grade_var, values=["9", "10", "11", "12"],
                     width=5, state="readonly", font=("Helvetica", 13)).grid(
            row=1, column=1, sticky="w", padx=(16, 0), ipady=3)

        tk.Label(self.body, text=self.mode_status, font=("Helvetica", 9), bg=CARD,
                 fg=DIM).pack(anchor="w", side="bottom")

        self.back_btn.state(["disabled"])
        self.next_btn.config(text="Start  →")

    def _render_question(self, index: int) -> None:
        dimension, question, hint = QUESTIONS[index]
        color = DIM_COLORS[dimension]
        self.progress_lbl.config(text="Question %d of %d" % (index + 1, self.total_steps))

        tag = tk.Frame(self.body, bg=CARD)
        tag.pack(fill="x", pady=(12, 0))
        tk.Label(tag, text="  %s  " % DIMENSION_LABELS[dimension].upper(),
                 font=("Helvetica", 9, "bold"), bg=DIM_SOFT[dimension],
                 fg=color).pack(side="left")

        self._title(question, 22, INK)
        self._sub(hint)

        wrap = tk.Frame(self.body, bg=color, padx=2, pady=2)
        wrap.pack(fill="x")
        self.entry = tk.Text(wrap, height=4, font=("Helvetica", 14), wrap="word",
                             bg=FIELD, fg=INK, relief="flat", padx=12, pady=10,
                             insertbackground=color, highlightthickness=0,
                             selectbackground=color)
        self.entry.pack(fill="x")
        self.entry.insert("1.0", self.answers[dimension])
        self.entry.focus_set()
        self.entry.bind("<KeyRelease>", lambda e: self._update_picked(dimension))

        tk.Label(self.body, text="e.g. " + ", ".join(suggestions(dimension, 4)),
                 font=("Helvetica", 10), bg=CARD, fg=DIM,
                 wraplength=CARD_SIZE - INSET * 2 - 8,
                 justify="left").pack(anchor="w", pady=(8, 10))

        self.chip_area = tk.Frame(self.body, bg=CARD)
        self.chip_area.pack(fill="both", expand=True, anchor="w")

        self.back_btn.state(["!disabled"])
        self.next_btn.config(text="Continue  →")
        self._update_picked(dimension)

    def _update_picked(self, dimension: str) -> None:
        text = self.entry.get("1.0", "end").strip()
        tags = extract(dimension, text)
        self.answers[dimension] = text
        self.picked[dimension] = tags

        for child in self.chip_area.winfo_children():
            child.destroy()
        if not tags:
            return
        color, soft = DIM_COLORS[dimension], DIM_SOFT[dimension]
        tk.Label(self.chip_area, text="Picked up", font=("Helvetica", 9, "bold"),
                 bg=CARD, fg=DIM).pack(anchor="w", pady=(0, 5))
        row = tk.Frame(self.chip_area, bg=CARD)
        row.pack(anchor="w", fill="x")
        used = 0
        for tag in tags:
            text_ = label(dimension, tag)
            width = len(text_) + 4
            if used + width > 62:
                row = tk.Frame(self.chip_area, bg=CARD)
                row.pack(anchor="w", fill="x", pady=(4, 0))
                used = 0
            tk.Label(row, text="  %s  " % text_, font=("Helvetica", 10),
                     bg=soft, fg=color).pack(side="left", padx=(0, 5), pady=1)
            used += width

    def _render_practical(self) -> None:
        self.progress_lbl.config(text="Last bit")
        self._title("Two last things.")

        tk.Label(self.body, text="How many years of school after high school?",
                 font=("Helvetica", 13), bg=CARD, fg=INK).pack(anchor="w", pady=(4, 0))
        self.years_lbl = tk.Label(self.body, text="", font=("Helvetica", 11),
                                  bg=CARD, fg=STRONG_C)
        s1 = ttk.Scale(self.body, from_=0, to=8, orient="horizontal",
                       command=lambda v: self._years_changed(float(v)))
        s1.pack(fill="x", pady=(8, 0))
        s1.set(self.years)
        self.years_lbl.pack(anchor="w", pady=(4, 20))

        tk.Label(self.body, text="How much does high pay matter to you?",
                 font=("Helvetica", 13), bg=CARD, fg=INK).pack(anchor="w")
        self.pay_lbl = tk.Label(self.body, text="", font=("Helvetica", 11),
                                bg=CARD, fg=DIM_COLORS["values"])
        s2 = ttk.Scale(self.body, from_=1, to=5, orient="horizontal",
                       command=lambda v: self._pay_changed(float(v)))
        s2.pack(fill="x", pady=(8, 0))
        s2.set(self.pay)
        self.pay_lbl.pack(anchor="w", pady=(4, 0))

        self._years_changed(self.years)
        self._pay_changed(self.pay)
        self.back_btn.state(["!disabled"])
        self.next_btn.config(text="See my matches  →")

    def _years_changed(self, value: float) -> None:
        self.years = int(round(value))
        words = {0: "straight to work", 1: "about a year", 2: "two years (associate)",
                 4: "four years (bachelor's)", 6: "six years (master's)",
                 8: "eight years (doctorate)"}
        self.years_lbl.config(text="%d — %s" % (
            self.years, words.get(self.years, "%d years" % self.years)))

    def _pay_changed(self, value: float) -> None:
        self.pay = int(round(value))
        words = {1: "barely matters", 2: "a little", 3: "somewhat", 4: "a lot",
                 5: "top priority"}
        self.pay_lbl.config(text="%d of 5 — %s" % (self.pay, words[self.pay]))

    # --------------------------------------------------------------- results
    def _render_results(self) -> None:
        self.progress_lbl.config(text="Your matches")
        self._title("%s, here's what fits you." % self.name, 20)

        weights = self.profile().normalized_weights()
        strip = tk.Frame(self.body, bg=CARD)
        strip.pack(fill="x", pady=(0, 10))
        for dimension in DIMENSIONS:
            chip = tk.Frame(strip, bg=DIM_SOFT[dimension])
            chip.pack(side="left", padx=(0, 5))
            tk.Label(chip, text=" %s %d%% " % (DIMENSION_LABELS[dimension],
                                               round(weights[dimension] * 100)),
                     font=("Helvetica", 9, "bold"), bg=DIM_SOFT[dimension],
                     fg=DIM_COLORS[dimension]).pack()

        cols = ("rank", "career", "match", "pay", "school")
        self.tree = ttk.Treeview(self.body, columns=cols, show="headings", height=5)
        for key, text, width, anchor in (("rank", "#", 28, "center"),
                                         ("career", "Career", 200, "w"),
                                         ("match", "Match", 60, "center"),
                                         ("pay", "Pay", 80, "center"),
                                         ("school", "School", 92, "center")):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor)
        for name, color in (("strong", STRONG_C), ("good", GOOD_C), ("fair", FAIR_C)):
            self.tree.tag_configure(name, foreground=color)
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        wrap = tk.Frame(self.body, bg=LINE, padx=1, pady=1)
        wrap.pack(fill="both", expand=True, pady=(10, 8))
        self.detail = tk.Text(wrap, height=7, font=("Menlo", 10), wrap="word",
                              bg=FIELD, fg=INK, relief="flat", padx=12, pady=10,
                              highlightthickness=0, selectbackground=GOOD_C)
        self.detail.pack(fill="both", expand=True)
        for dimension in DIMENSIONS:
            self.detail.tag_configure(dimension, foreground=DIM_COLORS[dimension])
        self.detail.tag_configure("head", foreground=STRONG_C,
                                  font=("Menlo", 11, "bold"))

        ttk.Button(self.body, text="Export report", style="Ghost.TButton",
                   command=self.export).pack(anchor="w")

        self.back_btn.state(["!disabled"])
        self.next_btn.config(text="Start over")

        short = {"high_school": "HS", "certificate": "Cert", "associate": "2 yr",
                 "bachelor": "4 yr", "master": "6 yr", "doctorate": "8 yr"}
        for index, rec in enumerate(self.recommendations, 1):
            m = rec.match
            pct = round(m.total * 100)
            level = "strong" if pct >= 80 else "good" if pct >= 60 else "fair"
            self.tree.insert("", "end", tags=(level,), values=(
                index, m.career.title, "%d%%" % pct,
                "${:,}k".format(m.career.salary.median // 1000),
                short.get(m.career.education, m.career.education)))
        if self.recommendations:
            self.tree.selection_set(self.tree.get_children()[0])
            self._show(0)

    def _on_select(self, _event: object) -> None:
        sel = self.tree.selection()
        if sel:
            self._show(self.tree.index(sel[0]))

    def _show(self, index: int) -> None:
        if not (0 <= index < len(self.recommendations)):
            return
        self.detail.delete("1.0", "end")
        text = format_recommendation(self.recommendations[index], index + 1)
        self.detail.insert("1.0", text)
        # tint each input's line in the breakdown with its own colour
        for dimension in DIMENSIONS:
            needle = DIMENSION_LABELS[dimension]
            start = "1.0"
            while True:
                pos = self.detail.search(needle, start, stopindex="end")
                if not pos:
                    break
                end = "%s lineend" % pos
                self.detail.tag_add(dimension, pos, end)
                start = end
        first = self.detail.search(self.recommendations[index].career.title,
                                   "1.0", stopindex="end")
        if first:
            self.detail.tag_add("head", first, "%s lineend" % first)

    # -------------------------------------------------------------- controls
    def profile(self) -> StudentProfile:
        return StudentProfile(
            name=self.name, grade=self.grade,
            interests=self.picked["interests"], subjects=self.picked["subjects"],
            work_style=self.picked["work_style"], values=self.picked["values"],
            max_education_years=self.years, salary_priority=self.pay,
        )

    def jump(self, step: int) -> None:
        """Click a step pill to go back to that question."""
        if step < self.step <= self.total_steps + 2:
            if 1 <= self.step <= self.total_steps:
                self._update_picked(QUESTIONS[self.step - 1][0])
            self.step = step
            self._render()

    def back(self) -> None:
        if self.step > 0:
            if 1 <= self.step <= self.total_steps:
                self._update_picked(QUESTIONS[self.step - 1][0])
            self.step -= 1
            self._render()

    def next(self) -> None:
        if self.step == 0:
            self.name = self.name_var.get().strip() or "Student"
            self.grade = self.grade_var.get()
        elif 1 <= self.step <= self.total_steps:
            self._update_picked(QUESTIONS[self.step - 1][0])
        elif self.step == self.total_steps + 2:
            self.restart()
            return

        if self.step == self.total_steps + 1:
            self.run_match()
            return

        self.step += 1
        self._render()

    def restart(self) -> None:
        self.answers = {d: "" for d in DIMENSIONS}
        self.picked = {d: [] for d in DIMENSIONS}
        self.recommendations = []
        self.step = 0
        self._render()

    def run_match(self) -> None:
        self.next_btn.state(["disabled"])
        self.status_lbl.config(text="Matching…")
        threading.Thread(target=self._worker, args=(self.profile(),),
                         daemon=True).start()
        self.master.after(60, self._drain)

    def _worker(self, profile: StudentProfile) -> None:
        try:
            self._queue.put(("ok", self.recommender.recommend(profile, top_n=5)))
        except Exception as exc:  # surfaced in the UI rather than the console
            self._queue.put(("error", exc))

    def _drain(self) -> None:
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.master.after(60, self._drain)
            return
        self.next_btn.state(["!disabled"])
        self.status_lbl.config(text="")
        if kind == "error":
            messagebox.showerror("Something went wrong", str(payload))
            return
        self.recommendations = payload
        self.step = self.total_steps + 2
        self._render()

    def export(self) -> None:
        if not self.recommendations:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile="futureforge-%s.md" % self.name.lower().replace(" ", "-"),
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(to_markdown(self.profile(), self.recommendations))
            messagebox.showinfo("Saved", "Report written to:\n%s" % path)


def _theme(root: tk.Tk) -> None:
    """Dark ttk styling. 'clam' is used because macOS 'aqua' ignores colours."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=CARD, foreground=INK, bordercolor=LINE,
                    darkcolor=FIELD, lightcolor=FIELD, troughcolor=FIELD,
                    focuscolor=CARD, fieldbackground=FIELD)
    style.configure("Accent.TButton", background=GOOD_C, foreground="#08131f",
                    borderwidth=0, focusthickness=0, padding=(18, 9),
                    font=("Helvetica", 12, "bold"))
    style.map("Accent.TButton",
              background=[("pressed", GOOD_C), ("active", "#6fb0ff"),
                          ("disabled", "#2a2f3a")],
              foreground=[("disabled", "#606a7b")])
    style.configure("Ghost.TButton", background=FIELD, foreground=INK,
                    borderwidth=0, focusthickness=0, padding=(16, 9),
                    font=("Helvetica", 12))
    style.map("Ghost.TButton",
              background=[("active", LINE), ("disabled", CARD)],
              foreground=[("disabled", "#4e5666")])
    style.configure("TEntry", fieldbackground=FIELD, foreground=INK,
                    insertcolor=INK, borderwidth=0, padding=6)
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD,
                    foreground=INK, arrowcolor=GOOD_C, borderwidth=0, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)],
              foreground=[("readonly", INK)])
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", GOOD_C)
    style.configure("TScale", background=CARD, troughcolor=FIELD, borderwidth=0)
    style.configure("Treeview", background=FIELD, fieldbackground=FIELD,
                    foreground=INK, borderwidth=0, rowheight=27)
    style.configure("Treeview.Heading", background=LINE, foreground=MUTED,
                    borderwidth=0, font=("Helvetica", 10, "bold"))
    style.map("Treeview", background=[("selected", LINE)],
              foreground=[("selected", INK)])


def launch() -> None:
    root = tk.Tk()
    _theme(root)
    Wizard(root)
    root.mainloop()
