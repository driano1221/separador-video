"""Phase 3 application shell with empty, persistent regions."""

from __future__ import annotations

import argparse
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from typing import Any

from app.ui_theme import TokenTheme, validate_tokens


SECTIONS = ("Cortar e dividir", "Transcrever", "Fila", "Historico")
DEFAULT_SHELL_STATE = {
    "theme": "dark",
    "section": SECTIONS[0],
    "sidebar_width": 236,
    "inspector_width": 300,
    "history_filter": "",
    "history_sort": "recent",
    "history_scroll": 0.0,
}


def normalize_shell_state(raw: Any) -> dict[str, Any]:
    state = dict(DEFAULT_SHELL_STATE)
    if not isinstance(raw, dict):
        return state
    if raw.get("theme") in {"dark", "light"}:
        state["theme"] = raw["theme"]
    if raw.get("section") in SECTIONS:
        state["section"] = raw["section"]
    if isinstance(raw.get("history_filter"), str):
        state["history_filter"] = raw["history_filter"][:200]
    if raw.get("history_sort") in {"recent", "name", "size"}:
        state["history_sort"] = raw["history_sort"]
    if isinstance(raw.get("history_scroll"), (int, float)):
        state["history_scroll"] = min(1.0, max(0.0, float(raw["history_scroll"])))
    for key, minimum, maximum in (
        ("sidebar_width", 200, 280),
        ("inspector_width", 240, 360),
    ):
        value = raw.get(key)
        if isinstance(value, int):
            state[key] = min(maximum, max(minimum, value))
    return state


def shell_state_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SeparadorVideo"
    return base / "ui_shell_preview.json"


def load_shell_state() -> dict[str, Any]:
    path = shell_state_path()
    try:
        return normalize_shell_state(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SHELL_STATE)


class ShellPreview:
    def __init__(self, root: tk.Tk, theme_override: str | None = None) -> None:
        self.root = root
        self.state = load_shell_state()
        if theme_override:
            self.state["theme"] = theme_override
        self.theme = TokenTheme(self.state["theme"])
        self.fonts: dict[tuple[str, str], tkfont.Font] = {}
        self.paned: tk.PanedWindow | None = None

        self.root.title("SeparadorVideo | Shell")
        self.root.minsize(self.value("shell.min-width"), self.value("shell.min-height"))
        self.root.configure(background=self.value("window.background"))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Control-Shift-L>", lambda _event: self.toggle_theme())
        self.root.bind("<Escape>", lambda _event: self.close())
        self.render()
        self.root.after_idle(self.maximize_and_restore_panels)

    def value(self, token: str):
        return self.theme.get(token)

    def font(self, size_token: str, weight_token: str = "font.weight.regular", mono: bool = False) -> tkfont.Font:
        cache_key = (size_token, f"{weight_token}:{mono}")
        if cache_key not in self.fonts:
            self.fonts[cache_key] = tkfont.Font(
                family=self.value("font.family.mono" if mono else "font.family.ui"),
                size=self.value(size_token),
                weight="bold" if self.value(weight_token) >= 600 else "normal",
            )
        return self.fonts[cache_key]

    def render(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.root.configure(background=self.value("window.background"))
        self.build_titlebar()
        self.build_content()
        self.build_statusbar()

    def divider(self, parent: tk.Widget, side: str) -> tk.Frame:
        line = tk.Frame(
            parent,
            background=self.value("border.subtle"),
            width=self.value("line.1") if side in {"left", "right"} else 1,
            height=self.value("line.1") if side in {"top", "bottom"} else 1,
        )
        line.pack(side=side, fill="y" if side in {"left", "right"} else "x")
        return line

    def build_titlebar(self) -> None:
        bar = tk.Frame(
            self.root,
            height=self.value("titlebar.height"),
            background=self.value("titlebar.background"),
        )
        bar.pack(fill="x")
        bar.pack_propagate(False)

        brand = tk.Label(
            bar,
            text="SEPARADOR VIDEO",
            anchor="w",
            width=18,
            padx=self.value("space.4"),
            background=self.value("titlebar.background"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.3", "font.weight.bold"),
        )
        brand.pack(side="left", fill="y")
        self.divider(bar, "left")

        tk.Label(
            bar,
            text=f"Mesa local  /  {self.state['section']}",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("titlebar.background"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.2"),
        ).pack(side="left", fill="both", expand=True)

        theme_label = "CLARO" if self.state["theme"] == "dark" else "ESCURO"
        theme_button = tk.Button(
            bar,
            text=theme_label,
            command=self.toggle_theme,
            background=self.value("surface.control"),
            foreground=self.value("text.primary"),
            activebackground=self.value("surface.hover"),
            activeforeground=self.value("text.primary"),
            font=self.font("font.size.1", "font.weight.semibold"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("border.control"),
            highlightcolor=self.value("border.focus"),
            padx=self.value("space.4"),
            takefocus=True,
        )
        theme_button.pack(side="right", fill="y", padx=self.value("space.2"), pady=self.value("space.2"))
        self.divider(self.root, "top")

    def build_content(self) -> None:
        self.paned = tk.PanedWindow(
            self.root,
            orient="horizontal",
            background=self.value("border.subtle"),
            borderwidth=0,
            relief="flat",
            sashwidth=self.value("splitter.width"),
            sashrelief="flat",
            showhandle=False,
        )
        self.paned.pack(fill="both", expand=True)
        self.paned.bind("<ButtonRelease-1>", lambda _event: self.capture_panel_widths())

        sidebar = self.build_sidebar(self.paned)
        workspace = self.build_workspace(self.paned)
        inspector = self.build_inspector(self.paned)
        self.paned.add(sidebar, minsize=self.value("sidebar.min-width"), stretch="never")
        self.paned.add(workspace, minsize=self.value("workspace.min-width"), stretch="always")
        self.paned.add(inspector, minsize=self.value("inspector.min-width"), stretch="never")

    def build_sidebar(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.rail"))
        tk.Label(
            panel,
            text="FERRAMENTAS",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.rail"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.semibold"),
        ).pack(fill="x", pady=(self.value("space.5"), self.value("space.3")))

        for section in SECTIONS:
            selected = section == self.state["section"]
            button = tk.Button(
                panel,
                text=f">  {section}" if selected else f"   {section}",
                command=lambda value=section: self.select_section(value),
                anchor="w",
                height=1,
                padx=self.value("space.4"),
                pady=self.value("space.2"),
                background=self.value("surface.selected" if selected else "surface.rail"),
                foreground=self.value("accent.primary" if selected else "text.primary"),
                activebackground=self.value("surface.hover"),
                activeforeground=self.value("text.primary"),
                font=self.font("font.size.3", "font.weight.semibold" if selected else "font.weight.regular"),
                relief="flat",
                borderwidth=0,
                highlightthickness=self.value("line.1"),
                highlightbackground=self.value("surface.rail"),
                highlightcolor=self.value("border.focus"),
                takefocus=True,
            )
            button.pack(fill="x")

        spacer = tk.Frame(panel, background=self.value("surface.rail"))
        spacer.pack(fill="both", expand=True)
        self.divider(panel, "bottom")
        tk.Label(
            panel,
            text="PROCESSAMENTO LOCAL",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.rail"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.semibold"),
        ).pack(fill="x", pady=self.value("space.4"))
        return panel

    def build_workspace(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.workspace"))
        toolbar = tk.Frame(panel, height=self.value("control.height"), background=self.value("surface.panel"))
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Label(
            toolbar,
            text=self.state["section"].upper(),
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(side="left", fill="y")
        tk.Label(
            toolbar,
            text="0 ITENS",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="right", fill="y")
        self.divider(panel, "top")

        empty = tk.Frame(panel, background=self.value("surface.workspace"))
        empty.pack(fill="both", expand=True)
        center = tk.Frame(empty, background=self.value("surface.workspace"))
        center.place(relx=0.5, rely=0.46, anchor="center")
        tk.Label(
            center,
            text="Nenhum video aberto",
            background=self.value("surface.workspace"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.4", "font.weight.semibold"),
        ).pack()
        tk.Label(
            center,
            text="Ctrl+O para adicionar midia",
            background=self.value("surface.workspace"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.2"),
        ).pack(pady=(self.value("space.2"), 0))
        return panel

    def build_inspector(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.panel"))
        header = tk.Label(
            panel,
            text="PROPRIEDADES",
            anchor="w",
            height=1,
            padx=self.value("space.4"),
            pady=self.value("space.3"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        )
        header.pack(fill="x")
        self.divider(panel, "top")
        tk.Label(
            panel,
            text="Nenhuma selecao",
            anchor="nw",
            padx=self.value("space.4"),
            pady=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.2"),
        ).pack(fill="both", expand=True)
        return panel

    def build_statusbar(self) -> None:
        self.divider(self.root, "top")
        bar = tk.Frame(
            self.root,
            height=self.value("statusbar.height"),
            background=self.value("statusbar.background"),
        )
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(
            bar,
            text="PRONTO",
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("status.ready"),
            font=self.font("font.size.1", "font.weight.bold", mono=True),
        ).pack(side="left", fill="y")
        tk.Label(
            bar,
            text="0 tarefas  |  nenhuma selecao",
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="left", fill="y")
        tk.Label(
            bar,
            text="LOCAL",
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.bold", mono=True),
        ).pack(side="right", fill="y")

    def maximize_and_restore_panels(self) -> None:
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass
        self.root.after(100, self.restore_panel_widths)

    def restore_panel_widths(self) -> None:
        if self.paned is None or self.paned.winfo_width() <= 1:
            return
        sidebar_width = self.state["sidebar_width"]
        inspector_width = self.state["inspector_width"]
        self.paned.sash_place(0, sidebar_width, 0)
        self.paned.sash_place(1, self.paned.winfo_width() - inspector_width, 0)

    def capture_panel_widths(self) -> None:
        if self.paned is None or self.paned.winfo_width() <= 1:
            return
        first_x = self.paned.sash_coord(0)[0]
        second_x = self.paned.sash_coord(1)[0]
        self.state["sidebar_width"] = min(280, max(200, first_x))
        self.state["inspector_width"] = min(360, max(240, self.paned.winfo_width() - second_x))

    def select_section(self, section: str) -> None:
        self.capture_panel_widths()
        self.state["section"] = section
        self.render()
        self.root.after_idle(self.restore_panel_widths)

    def toggle_theme(self) -> None:
        self.capture_panel_widths()
        self.state["theme"] = "light" if self.state["theme"] == "dark" else "dark"
        self.theme = TokenTheme(self.state["theme"])
        self.fonts.clear()
        self.render()
        self.root.after_idle(self.restore_panel_widths)

    def save_state(self) -> None:
        self.capture_panel_widths()
        path = shell_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self) -> None:
        self.save_state()
        self.root.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualiza o shell vazio da interface.")
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_tokens()
    if args.self_test:
        normalize_shell_state({"theme": "invalid", "sidebar_width": 999})
        print("SHELL_OK")
        return
    root = tk.Tk()
    ShellPreview(root, args.theme)
    root.mainloop()


if __name__ == "__main__":
    main()
