"""Tkinter GUI -- the surface you walk a student through.

Left pane: the four weighted inputs as checkbox groups plus two sliders.
Right pane: ranked career cards with pay, degree requirement, and a plain-language
breakdown of why each one matched. Weight sliders in the Advanced panel re-rank
live, which is the thing to show off in a demo: change what you value, watch the
list reorder.

Generation runs on a worker thread so the window never freezes -- instant offline,
a second or two per career when OPENAI_API_KEY is set.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .dataset import VOCABULARIES, dataset_meta, fields, load_careers
from .generator import get_generator
from .models import DEFAULT_WEIGHTS, DIMENSION_LABELS, DIMENSIONS, StudentProfile
from .recommender import Recommender
from .report import format_recommendation, to_json, to_markdown

GROUP_PROMPTS = {
    "interests": "1. Check everything you actually enjoy",
    "subjects": "2. Which classes do you do well in or like?",
    "work_style": "3. How do you want to spend your workday?",
    "values": "4. What matters most in a job?",
}

EXAMPLE_PROFILE = StudentProfile(
    name="Maya Chen",
    grade="11",
    interests=["health", "helping_people", "science"],
    subjects=["biology", "chemistry", "psychology"],
    work_style=["team", "hands_on", "fast_paced"],
    values=["helping_others", "job_security", "stay_local"],
    max_education_years=4,
    salary_priority=3,
)


class FutureForgeApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=0)
        self.master.title("FutureForge - Career Guidance")
        self.master.geometry("1180x820")
        self.master.minsize(980, 680)
        self.pack(fill="both", expand=True)

        self.careers = load_careers()
        self.meta = dataset_meta()
        generator, self.mode_status = get_generator()
        self.recommender = Recommender(careers=self.careers, generator=generator)

        self.vars: Dict[str, Dict[str, tk.BooleanVar]] = {d: {} for d in DIMENSIONS}
        self.weight_vars: Dict[str, tk.DoubleVar] = {}
        self.recommendations: List = []
        self.profile: Optional[StudentProfile] = None
        self._queue: "queue.Queue" = queue.Queue()

        self._build_header()
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        body.add(self._build_form(body), weight=3)
        body.add(self._build_results(body), weight=4)
        self._build_statusbar()
        self.load_example()

    # ---------------------------------------------------------------- header
    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 6))
        header.pack(fill="x")
        ttk.Label(header, text="FutureForge", font=("Helvetica", 22, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Answer four questions. Get careers matched to you, with real pay ranges "
            "and exactly how much school each one takes.",
            foreground="#555",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="{} careers across {} fields   |   {}".format(
                len(self.careers), len(fields(self.careers)), self.mode_status
            ),
            foreground="#777",
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(4, 0))
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(8, 8))

    # ------------------------------------------------------------------ form
    def _build_form(self, parent: ttk.PanedWindow) -> ttk.Frame:
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0, width=430)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=(2, 2, 12, 2))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 3)), "units"))

        who = ttk.LabelFrame(inner, text="About you", padding=10)
        who.pack(fill="x", pady=(0, 8))
        self.name_var = tk.StringVar(value="Student")
        self.grade_var = tk.StringVar(value="11")
        ttk.Label(who, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(who, textvariable=self.name_var, width=24).grid(row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Label(who, text="Grade").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            who, textvariable=self.grade_var, values=["9", "10", "11", "12"], width=4, state="readonly"
        ).grid(row=0, column=3, sticky="w", padx=(8, 0))

        for dimension in DIMENSIONS:
            self._build_checkgroup(inner, dimension)

        sliders = ttk.LabelFrame(inner, text="Two more things", padding=10)
        sliders.pack(fill="x", pady=(0, 8))
        self.years_var = tk.IntVar(value=4)
        self.pay_var = tk.IntVar(value=3)
        self.years_label = ttk.Label(sliders, text="")
        self.pay_label = ttk.Label(sliders, text="")

        ttk.Label(sliders, text="How many years of school after high school?").pack(anchor="w")
        self._years_scale = ttk.Scale(
            sliders, from_=0, to=8, orient="horizontal",
            command=lambda v: self._on_years(float(v)),
        )
        self._years_scale.pack(fill="x")
        self.years_label.pack(anchor="w", pady=(0, 8))

        ttk.Label(sliders, text="How much does high pay matter to you?").pack(anchor="w")
        self._pay_scale = ttk.Scale(
            sliders, from_=1, to=5, orient="horizontal",
            command=lambda v: self._on_pay(float(v)),
        )
        self._pay_scale.pack(fill="x")
        self.pay_label.pack(anchor="w")
        self._years_scale.set(4)
        self._pay_scale.set(3)

        advanced = ttk.LabelFrame(inner, text="Advanced: how much each answer counts", padding=10)
        advanced.pack(fill="x", pady=(0, 8))
        ttk.Label(
            advanced, text="Drag to re-weight the four inputs, then match again.", foreground="#666"
        ).pack(anchor="w", pady=(0, 6))
        self.weight_labels: Dict[str, ttk.Label] = {}
        for dimension in DIMENSIONS:
            var = tk.DoubleVar(value=DEFAULT_WEIGHTS[dimension])
            self.weight_vars[dimension] = var
            row = ttk.Frame(advanced)
            row.pack(fill="x")
            lbl = ttk.Label(row, text="", width=26)
            lbl.pack(side="left")
            self.weight_labels[dimension] = lbl
            ttk.Scale(
                row, from_=0.0, to=1.0, orient="horizontal", variable=var,
                command=lambda v, d=dimension: self._on_weight(d),
            ).pack(side="left", fill="x", expand=True)
            self._on_weight(dimension)
        ttk.Button(advanced, text="Reset weights", command=self.reset_weights).pack(anchor="e", pady=(6, 0))

        buttons = ttk.Frame(inner)
        buttons.pack(fill="x", pady=(4, 12))
        ttk.Button(buttons, text="Get my matches", command=self.run_match).pack(side="left")
        ttk.Button(buttons, text="Load example student", command=self.load_example).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear", command=self.clear_form).pack(side="left")
        return outer

    def _build_checkgroup(self, parent: ttk.Frame, dimension: str) -> None:
        group = ttk.LabelFrame(parent, text=GROUP_PROMPTS[dimension], padding=10)
        group.pack(fill="x", pady=(0, 8))
        vocab = VOCABULARIES[dimension]
        for index, (tag, text) in enumerate(vocab.items()):
            var = tk.BooleanVar(value=False)
            self.vars[dimension][tag] = var
            ttk.Checkbutton(group, text=text, variable=var).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 10), pady=1
            )
        group.columnconfigure(0, weight=1)
        group.columnconfigure(1, weight=1)

    # --------------------------------------------------------------- results
    def _build_results(self, parent: ttk.PanedWindow) -> ttk.Frame:
        outer = ttk.Frame(parent, padding=(10, 0, 0, 0))

        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="Your matches", font=("Helvetica", 14, "bold")).pack(side="left")
        ttk.Label(top, text="  how many:").pack(side="left", padx=(12, 2))
        self.topn_var = tk.IntVar(value=5)
        ttk.Combobox(
            top, textvariable=self.topn_var, values=[3, 5, 8, 10], width=3, state="readonly"
        ).pack(side="left")
        ttk.Button(top, text="Export report...", command=self.export_report).pack(side="right")

        columns = ("rank", "career", "match", "pay", "school")
        self.tree = ttk.Treeview(outer, columns=columns, show="headings", height=9)
        for col, heading, width, anchor in (
            ("rank", "#", 34, "center"),
            ("career", "Career", 200, "w"),
            ("match", "Match", 60, "center"),
            ("pay", "Typical pay (median)", 165, "w"),
            ("school", "School needed", 150, "w"),
        ):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "career"))
        tree_scroll = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(fill="x", pady=(8, 0), side="top")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_frame = ttk.LabelFrame(outer, text="Details", padding=6)
        detail_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.detail = tk.Text(detail_frame, wrap="word", height=18, borderwidth=0, font=("Menlo", 11))
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set, state="disabled")
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        self._set_detail(
            "Pick your answers on the left and press \"Get my matches\".\n\n"
            "Every result shows the pay range, exactly how much school it takes, and which of "
            "your own answers put it on the list."
        )
        return outer

    def _build_statusbar(self) -> None:
        self.status_var = tk.StringVar(value="Ready. {}".format(self.mode_status))
        bar = ttk.Frame(self, relief="groove", padding=(12, 4))
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, textvariable=self.status_var, foreground="#444").pack(anchor="w")

    # ------------------------------------------------------------- callbacks
    def _on_years(self, value: float) -> None:
        years = int(round(value))
        self.years_var.set(years)
        wording = {0: "None - start working right after high school", 1: "About a year (certificate or trade program)",
                   2: "Two years (associate degree)", 4: "Four years (bachelor's degree)",
                   6: "Six years (master's degree)", 8: "Eight+ years (doctorate or professional degree)"}
        self.years_label.configure(text="  {} -> {}".format(years, wording.get(years, "{} years".format(years))))

    def _on_pay(self, value: float) -> None:
        pay = int(round(value))
        self.pay_var.set(pay)
        wording = {1: "barely matters", 2: "a little", 3: "somewhat", 4: "a lot", 5: "top priority"}
        self.pay_label.configure(text="  {}/5 - {}".format(pay, wording[pay]))

    def _on_weight(self, _dimension: Optional[str] = None) -> None:
        """Moving one slider changes every share, so relabel them all."""
        total = sum(max(0.0, v.get()) for v in self.weight_vars.values()) or 1.0
        for name, var in self.weight_vars.items():
            share = max(0.0, var.get()) / total
            self.weight_labels[name].configure(
                text="{:<20} {:>3}%".format(DIMENSION_LABELS[name], int(round(share * 100)))
            )

    def reset_weights(self) -> None:
        for dimension, value in DEFAULT_WEIGHTS.items():
            self.weight_vars[dimension].set(value)
        self._on_weight("interests")

    def clear_form(self) -> None:
        for dimension in DIMENSIONS:
            for var in self.vars[dimension].values():
                var.set(False)
        self.name_var.set("Student")
        self.grade_var.set("11")
        self._years_scale.set(4)
        self._pay_scale.set(3)
        self.reset_weights()
        self.tree.delete(*self.tree.get_children())
        self._set_detail("Cleared. Pick your answers and press \"Get my matches\".")

    def load_example(self) -> None:
        p = EXAMPLE_PROFILE
        self.name_var.set(p.name)
        self.grade_var.set(p.grade)
        for dimension in DIMENSIONS:
            selected = set(p.tags(dimension))
            for tag, var in self.vars[dimension].items():
                var.set(tag in selected)
        self._years_scale.set(p.max_education_years)
        self._pay_scale.set(p.salary_priority)
        self.status_var.set("Loaded example student ({}). Press \"Get my matches\".".format(p.name))

    def current_profile(self) -> StudentProfile:
        return StudentProfile(
            name=self.name_var.get().strip() or "Student",
            grade=self.grade_var.get(),
            interests=[t for t, v in self.vars["interests"].items() if v.get()],
            subjects=[t for t, v in self.vars["subjects"].items() if v.get()],
            work_style=[t for t, v in self.vars["work_style"].items() if v.get()],
            values=[t for t, v in self.vars["values"].items() if v.get()],
            max_education_years=self.years_var.get(),
            salary_priority=self.pay_var.get(),
            weights={d: max(0.0, v.get()) for d, v in self.weight_vars.items()},
        )

    # ----------------------------------------------------------------- match
    def run_match(self) -> None:
        profile = self.current_profile()
        answered = sum(len(profile.tags(d)) for d in DIMENSIONS)
        if answered < 3:
            messagebox.showinfo(
                "A few more answers",
                "Check at least three boxes so there is something to match on.\n\n"
                "Tip: \"Load example student\" fills the form in for you.",
            )
            return

        self.profile = profile
        self.status_var.set("Matching {} against {} careers...".format(profile.name, len(self.careers)))
        self.tree.delete(*self.tree.get_children())
        self._set_detail("Working...")
        top_n = int(self.topn_var.get())
        threading.Thread(target=self._worker, args=(profile, top_n), daemon=True).start()
        self.after(80, self._drain_queue)

    def _worker(self, profile: StudentProfile, top_n: int) -> None:
        try:
            self._queue.put(("done", self.recommender.recommend(profile, top_n=top_n)))
        except Exception as exc:  # noqa: BLE001 -- surface it in the UI, never crash the demo
            self._queue.put(("error", exc))

    def _drain_queue(self) -> None:
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.after(80, self._drain_queue)
            return
        if kind == "error":
            self.status_var.set("Something went wrong.")
            messagebox.showerror("Matching failed", str(payload))
            return
        self.recommendations = payload
        self._render(payload)

    def _render(self, recs: List) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, rec in enumerate(recs, start=1):
            c = rec.career
            self.tree.insert(
                "", "end", iid=str(index - 1),
                values=(index, c.title, "{}%".format(rec.match.percent),
                        "${:,}".format(c.salary.median), c.education_label),
            )
        if recs:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._show(0)
        sources = {r.source for r in recs}
        self.status_var.set(
            "{} matches for {} | guidance: {}".format(len(recs), self.profile.name, ", ".join(sorted(sources)))
        )

    def _on_select(self, _event: object) -> None:
        selection = self.tree.selection()
        if selection:
            self._show(int(selection[0]))

    def _show(self, index: int) -> None:
        if 0 <= index < len(self.recommendations):
            self._set_detail(format_recommendation(self.recommendations[index], index + 1))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    # ---------------------------------------------------------------- export
    def export_report(self) -> None:
        if not self.recommendations or not self.profile:
            messagebox.showinfo("Nothing to export", "Run a match first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save report",
            defaultextension=".md",
            initialfile="{}_career_report.md".format(self.profile.name.replace(" ", "_").lower()),
            filetypes=[("Markdown", "*.md"), ("JSON", "*.json"), ("Text", "*.txt")],
        )
        if not path:
            return
        if path.endswith(".json"):
            content = to_json(self.profile, self.recommendations)
        elif path.endswith(".txt"):
            from .report import format_report
            content = format_report(self.profile, self.recommendations)
        else:
            content = to_markdown(self.profile, self.recommendations)
        try:
            with open(path, "w") as handle:
                handle.write(content)
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc))
            return
        self.status_var.set("Saved report to {}".format(path))


def launch() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("aqua")  # macOS native look; falls back below elsewhere
    except tk.TclError:
        pass
    FutureForgeApp(root)
    root.mainloop()
