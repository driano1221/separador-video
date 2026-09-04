"""Phase 4 filled cut-and-divide screen."""

from __future__ import annotations

import argparse
import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox

from app.ui_shell_preview import SECTIONS, ShellPreview
from app.ui_theme import validate_tokens
from app.video_splitter_core import VIDEO_EXTENSIONS, ffprobe_video, format_clock


@dataclass
class MediaInfo:
    path: Path
    duration: float
    resolution: str
    codec: str
    size_text: str


def parse_clock(value: str) -> float:
    fields = value.strip().split(":")
    if len(fields) != 3:
        raise ValueError("Use HH:MM:SS")
    try:
        hours, minutes, seconds = (int(field) for field in fields)
    except ValueError as error:
        raise ValueError("Use HH:MM:SS") from error
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("Horario invalido")
    return float(hours * 3600 + minutes * 60 + seconds)


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class MainScreenPreview(ShellPreview):
    def __init__(self, root: tk.Tk, theme_override: str | None = None) -> None:
        self.media = MediaInfo(
            path=Path(r"C:\Users\drian\Videos\2026-08-27 10-07-40.mp4"),
            duration=4328.0,
            resolution="1920 x 1080",
            codec="H.264 / AAC",
            size_text="36.0 MB",
        )
        self.interval_start = 480.0
        self.interval_end = 4320.0
        self.parts = 2
        self.interval_error = ""
        self.start_var = tk.StringVar(root, format_clock(self.interval_start))
        self.end_var = tk.StringVar(root, format_clock(self.interval_end))
        self.quality_var = tk.StringVar(root, "Equilibrada")
        self.encoder_var = tk.StringVar(root, "Automatico")
        self.open_folder_var = tk.BooleanVar(root, True)
        self.segment_list: tk.Listbox | None = None
        self.timeline: tk.Canvas | None = None
        super().__init__(root, theme_override)
        self.root.title("SeparadorVideo | Cortar e dividir")
        self.root.bind("<Control-o>", lambda _event: self.open_media())
        self.root.bind("<Control-Return>", lambda _event: self.preview_process_action())

    def build_sidebar(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.rail"))
        self.sidebar_heading(panel, "FERRAMENTAS")
        for section in SECTIONS:
            self.navigation_button(panel, section)

        self.divider(panel, "top")
        self.sidebar_heading(panel, "MIDIA RECENTE")
        recent = (
            self.media.path.name,
            "2026-08-19 14-41-36.mp4",
            "2026-07-14 09-01-52.mp4",
        )
        for index, filename in enumerate(recent):
            selected = index == 0 and self.state["section"] == SECTIONS[0]
            tk.Button(
                panel,
                text=filename,
                command=lambda: None,
                anchor="w",
                padx=self.value("space.4"),
                pady=self.value("space.2"),
                background=self.value("surface.selected" if selected else "surface.rail"),
                foreground=self.value("text.primary" if selected else "text.secondary"),
                activebackground=self.value("surface.hover"),
                activeforeground=self.value("text.primary"),
                font=self.font("font.size.2"),
                relief="flat",
                borderwidth=0,
                highlightthickness=self.value("line.1"),
                highlightbackground=self.value("surface.rail"),
                highlightcolor=self.value("border.focus"),
                takefocus=True,
            ).pack(fill="x")

        tk.Frame(panel, background=self.value("surface.rail")).pack(fill="both", expand=True)
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

    def sidebar_heading(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.rail"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.semibold"),
        ).pack(fill="x", pady=(self.value("space.5"), self.value("space.3")))

    def navigation_button(self, parent: tk.Widget, section: str) -> None:
        selected = section == self.state["section"]
        tk.Button(
            parent,
            text=f">  {section}" if selected else f"   {section}",
            command=lambda value=section: self.select_section(value),
            anchor="w",
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
        ).pack(fill="x")

    def build_workspace(self, parent: tk.Widget) -> tk.Frame:
        if self.state["section"] != SECTIONS[0]:
            return super().build_workspace(parent)

        panel = tk.Frame(parent, background=self.value("surface.workspace"))
        self.build_workspace_toolbar(panel)
        self.divider(panel, "top")
        self.build_media_header(panel)
        self.divider(panel, "top")
        self.build_timeline(panel)
        self.divider(panel, "top")
        self.build_segment_list(panel)
        return panel

    def build_workspace_toolbar(self, parent: tk.Widget) -> None:
        toolbar = tk.Frame(
            parent,
            height=self.value("workspace.toolbar-height"),
            background=self.value("surface.panel"),
        )
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Label(
            toolbar,
            text="CORTAR E DIVIDIR",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(side="left", fill="y")
        self.tool_button(toolbar, "ABRIR   Ctrl+O", self.open_media).pack(
            side="right",
            padx=self.value("space.3"),
            pady=self.value("space.2"),
        )

    def build_media_header(self, parent: tk.Widget) -> None:
        header = tk.Frame(
            parent,
            height=self.value("media.header-height"),
            background=self.value("surface.workspace"),
        )
        header.pack(fill="x")
        header.pack_propagate(False)
        title = tk.Frame(header, background=self.value("surface.workspace"))
        title.pack(side="left", fill="both", expand=True, padx=self.value("space.4"))
        tk.Label(
            title,
            text=self.media.path.name,
            anchor="w",
            background=self.value("surface.workspace"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.3", "font.weight.semibold"),
        ).pack(fill="x", pady=(self.value("space.3"), 0))
        tk.Label(
            title,
            text=str(self.media.path.parent),
            anchor="w",
            background=self.value("surface.workspace"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1"),
        ).pack(fill="x")
        tk.Label(
            header,
            text=f"{self.media.resolution}   |   {self.media.codec}   |   {self.media.size_text}   |   {format_clock(self.media.duration)}",
            padx=self.value("space.4"),
            background=self.value("surface.workspace"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="right", fill="y")

    def build_timeline(self, parent: tk.Widget) -> None:
        frame = tk.Frame(
            parent,
            height=self.value("timeline.height"),
            background=self.value("timeline.background"),
        )
        frame.pack(fill="x")
        frame.pack_propagate(False)
        self.timeline = tk.Canvas(
            frame,
            background=self.value("timeline.background"),
            borderwidth=0,
            highlightthickness=0,
            takefocus=True,
        )
        self.timeline.pack(fill="both", expand=True)
        self.timeline.bind("<Configure>", lambda event: self.draw_timeline(event.width, event.height))
        self.timeline.bind("<Button-3>", self.show_timeline_menu)

    def draw_timeline(self, width: int, height: int) -> None:
        if self.timeline is None or width <= 1:
            return
        canvas = self.timeline
        canvas.delete("all")
        padding = self.value("space.9")
        ruler_y = self.value("space.8")
        wave_top = self.value("space.8") * 2
        wave_bottom = height - self.value("space.8") * 2
        usable_width = width - padding * 2
        duration = max(1.0, self.media.duration)
        start_x = padding + usable_width * (self.interval_start / duration)
        end_x = padding + usable_width * (self.interval_end / duration)

        canvas.create_rectangle(
            start_x,
            wave_top - self.value("space.3"),
            end_x,
            wave_bottom + self.value("space.3"),
            fill=self.value("selection.fill"),
            outline="",
        )

        ticks = 6
        for index in range(ticks + 1):
            x = padding + usable_width * index / ticks
            seconds = duration * index / ticks
            canvas.create_line(x, ruler_y, x, ruler_y + self.value("space.3"), fill=self.value("timeline.ruler"), width=self.value("line.1"))
            canvas.create_text(
                x,
                ruler_y - self.value("space.2"),
                text=format_clock(seconds),
                anchor="s",
                fill=self.value("text.muted"),
                font=self.font("font.size.1", mono=True),
            )

        center_y = (wave_top + wave_bottom) / 2
        amplitude = (wave_bottom - wave_top) * 0.42
        bars = max(80, usable_width // self.value("space.3"))
        for index in range(int(bars)):
            x = padding + usable_width * index / max(1, bars - 1)
            variation = 0.22 + 0.58 * abs(math.sin(index * 0.37) * math.cos(index * 0.11))
            color = self.value("text.secondary" if start_x <= x <= end_x else "text.muted")
            canvas.create_line(x, center_y - amplitude * variation, x, center_y + amplitude * variation, fill=color, width=self.value("line.1"))

        for x, seconds, anchor in (
            (start_x, self.interval_start, "sw"),
            (end_x, self.interval_end, "se"),
        ):
            canvas.create_line(x, wave_top - self.value("space.5"), x, wave_bottom + self.value("space.5"), fill=self.value("selection.edge"), width=self.value("line.1"))
            canvas.create_text(
                x,
                wave_bottom + self.value("space.7"),
                text=format_clock(seconds),
                anchor=anchor,
                fill=self.value("accent.primary"),
                font=self.font("font.size.1", "font.weight.bold", mono=True),
            )

    def build_segment_list(self, parent: tk.Widget) -> None:
        frame = tk.Frame(
            parent,
            height=self.value("segment-list.height"),
            background=self.value("surface.panel"),
        )
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, height=self.value("control.height"), background=self.value("surface.panel"))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="SEGMENTOS GERADOS",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(side="left", fill="y")
        tk.Label(
            header,
            text=f"{self.parts} ITENS",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="right", fill="y")

        columns = tk.Label(
            frame,
            text=" #    INICIO       FIM          DURACAO      SAIDA",
            anchor="w",
            padx=self.value("space.3"),
            background=self.value("surface.workspace"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.semibold", mono=True),
        )
        columns.pack(fill="x")

        list_area = tk.Frame(frame, background=self.value("surface.workspace"))
        list_area.pack(fill="both", expand=True)
        self.segment_list = tk.Listbox(
            list_area,
            selectmode=tk.EXTENDED,
            activestyle="none",
            background=self.value("list.background"),
            foreground=self.value("list.item.text.rest"),
            selectbackground=self.value("selection.fill"),
            selectforeground=self.value("text.primary"),
            disabledforeground=self.value("text.disabled"),
            font=self.font("font.size.2", mono=True),
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("border.subtle"),
            highlightcolor=self.value("border.focus"),
            exportselection=False,
        )
        self.segment_list.pack(side="left", fill="both", expand=True)
        self.segment_list.bind("<Button-3>", self.show_segment_menu)
        self.refresh_segments()

    def build_inspector(self, parent: tk.Widget) -> tk.Frame:
        if self.state["section"] != SECTIONS[0]:
            return super().build_inspector(parent)

        panel = tk.Frame(parent, background=self.value("surface.panel"))
        self.inspector_heading(panel, "PROPRIEDADES")
        self.inspector_section(panel, "INTERVALO")
        self.field_row(panel, "Inicio", self.start_var)
        self.field_row(panel, "Fim", self.end_var)
        if self.interval_error:
            tk.Label(
                panel,
                text=f"!  {self.interval_error}",
                anchor="w",
                padx=self.value("space.4"),
                background=self.value("surface.panel"),
                foreground=self.value("status.error"),
                font=self.font("font.size.1", "font.weight.semibold"),
            ).pack(fill="x")

        self.inspector_section(panel, "DIVISAO")
        segmented = tk.Frame(panel, background=self.value("surface.panel"))
        segmented.pack(fill="x", padx=self.value("space.4"), pady=(0, self.value("space.4")))
        for parts in range(1, 5):
            selected = parts == self.parts
            tk.Button(
                segmented,
                text=str(parts),
                command=lambda value=parts: self.set_parts(value),
                background=self.value("accent.primary" if selected else "surface.control"),
                foreground=self.value("text.on-accent" if selected else "text.primary"),
                activebackground=self.value("accent.primary-hover" if selected else "surface.hover"),
                activeforeground=self.value("text.on-accent" if selected else "text.primary"),
                font=self.font("font.size.2", "font.weight.semibold"),
                relief="flat",
                borderwidth=0,
                highlightthickness=self.value("line.1"),
                highlightbackground=self.value("border.control"),
                highlightcolor=self.value("border.focus"),
                takefocus=True,
            ).pack(side="left", fill="x", expand=True, padx=(0, self.value("line.1")))

        self.inspector_section(panel, "PROCESSAMENTO")
        self.menu_row(panel, "Qualidade", self.quality_var, ("Alta qualidade", "Equilibrada", "Arquivo menor"))
        self.menu_row(panel, "Encoder", self.encoder_var, ("Automatico", "NVIDIA NVENC", "Software x264"))

        self.inspector_section(panel, "RESUMO")
        duration = max(0.0, self.interval_end - self.interval_start)
        self.info_row(panel, "Trecho", format_clock(duration))
        self.info_row(panel, "Partes", str(self.parts))
        self.info_row(panel, "Por parte", format_clock(duration / max(1, self.parts)))
        self.info_row(panel, "Destino", f"{self.parts}_partes")

        tk.Frame(panel, background=self.value("surface.panel")).pack(fill="both", expand=True)
        self.divider(panel, "bottom")
        tk.Checkbutton(
            panel,
            text="Abrir pasta ao terminar",
            variable=self.open_folder_var,
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            activebackground=self.value("surface.panel"),
            activeforeground=self.value("text.primary"),
            selectcolor=self.value("surface.control"),
            font=self.font("font.size.2"),
            relief="flat",
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("surface.panel"),
            highlightcolor=self.value("border.focus"),
            takefocus=True,
        ).pack(fill="x", pady=self.value("space.2"))
        self.primary_button(panel, f"GERAR {self.parts} ARQUIVOS   Ctrl+Enter", self.preview_process_action).pack(
            fill="x",
            padx=self.value("space.4"),
            pady=(0, self.value("space.4")),
        )
        return panel

    def inspector_heading(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            anchor="w",
            padx=self.value("space.4"),
            pady=self.value("space.3"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(fill="x")
        self.divider(parent, "top")

    def inspector_section(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            anchor="w",
            padx=self.value("space.4"),
            pady=self.value("space.3"),
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.semibold"),
        ).pack(fill="x")

    def field_row(self, parent: tk.Widget, label: str, variable: tk.StringVar) -> None:
        row = tk.Frame(parent, background=self.value("surface.panel"))
        row.pack(fill="x", padx=self.value("space.4"), pady=(0, self.value("space.3")))
        tk.Label(
            row,
            text=label,
            width=7,
            anchor="w",
            background=self.value("surface.panel"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.2"),
        ).pack(side="left")
        entry = tk.Entry(
            row,
            textvariable=variable,
            background=self.value("field.background.rest"),
            foreground=self.value("field.text.rest"),
            insertbackground=self.value("text.primary"),
            selectbackground=self.value("selection.fill"),
            selectforeground=self.value("text.primary"),
            font=self.font("font.size.2", mono=True),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("field.border.rest"),
            highlightcolor=self.value("field.border.focus"),
        )
        entry.pack(side="left", fill="x", expand=True, ipady=self.value("space.2"))
        entry.bind("<Return>", lambda _event: self.apply_interval())
        entry.bind("<FocusOut>", lambda _event: self.apply_interval())

    def menu_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, values: tuple[str, ...]) -> None:
        row = tk.Frame(parent, background=self.value("surface.panel"))
        row.pack(fill="x", padx=self.value("space.4"), pady=(0, self.value("space.3")))
        tk.Label(
            row,
            text=label,
            width=9,
            anchor="w",
            background=self.value("surface.panel"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.2"),
        ).pack(side="left")
        button = tk.Menubutton(
            row,
            textvariable=variable,
            anchor="w",
            background=self.value("field.background.rest"),
            foreground=self.value("field.text.rest"),
            activebackground=self.value("field.background.hover"),
            activeforeground=self.value("field.text.rest"),
            font=self.font("font.size.2"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("field.border.rest"),
            highlightcolor=self.value("field.border.focus"),
            indicatoron=True,
            takefocus=True,
        )
        menu = tk.Menu(
            button,
            tearoff=False,
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            activebackground=self.value("surface.hover"),
            activeforeground=self.value("text.primary"),
            font=self.font("font.size.2"),
        )
        for value in values:
            menu.add_radiobutton(label=value, value=value, variable=variable)
        button.configure(menu=menu)
        button.pack(side="left", fill="x", expand=True, ipady=self.value("space.2"))

    def info_row(self, parent: tk.Widget, label: str, value: str) -> None:
        row = tk.Frame(parent, background=self.value("surface.panel"))
        row.pack(fill="x", padx=self.value("space.4"), pady=self.value("space.1"))
        tk.Label(
            row,
            text=label,
            anchor="w",
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1"),
        ).pack(side="left")
        tk.Label(
            row,
            text=value,
            anchor="e",
            background=self.value("surface.panel"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="right")

    def tool_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            background=self.value("button.background.rest"),
            foreground=self.value("button.text.rest"),
            activebackground=self.value("button.background.hover"),
            activeforeground=self.value("button.text.rest"),
            font=self.font("font.size.1", "font.weight.semibold"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("button.border.rest"),
            highlightcolor=self.value("button.border.focus"),
            padx=self.value("space.4"),
            takefocus=True,
        )

    def primary_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            background=self.value("accent.primary"),
            foreground=self.value("text.on-accent"),
            activebackground=self.value("accent.primary-hover"),
            activeforeground=self.value("text.on-accent"),
            font=self.font("font.size.2", "font.weight.bold"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("accent.primary"),
            highlightcolor=self.value("border.focus"),
            pady=self.value("space.3"),
            takefocus=True,
        )

    def set_parts(self, parts: int) -> None:
        self.capture_panel_widths()
        self.parts = parts
        self.render()
        self.root.after_idle(self.restore_panel_widths)

    def apply_interval(self) -> None:
        try:
            start = parse_clock(self.start_var.get())
            end = parse_clock(self.end_var.get())
            if start >= end or end > self.media.duration:
                raise ValueError("O intervalo precisa estar dentro do video")
        except ValueError as error:
            self.interval_error = str(error)
        else:
            self.interval_start = start
            self.interval_end = end
            self.interval_error = ""
        self.capture_panel_widths()
        self.render()
        self.root.after_idle(self.restore_panel_widths)

    def refresh_segments(self) -> None:
        if self.segment_list is None:
            return
        self.segment_list.delete(0, tk.END)
        total = max(0.0, self.interval_end - self.interval_start)
        part_duration = total / max(1, self.parts)
        for index in range(self.parts):
            start = self.interval_start + part_duration * index
            end = self.interval_start + part_duration * (index + 1)
            output = f"parte_{index + 1:02d}.mp4"
            self.segment_list.insert(
                tk.END,
                f" {index + 1:02d}   {format_clock(start)}   {format_clock(end)}   {format_clock(end - start)}   {output}",
            )
        if self.parts:
            self.segment_list.selection_set(0)

    def build_statusbar(self) -> None:
        self.divider(self.root, "top")
        bar = tk.Frame(self.root, height=self.value("statusbar.height"), background=self.value("statusbar.background"))
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
            text=f"{self.parts} segmentos  |  trecho {format_clock(self.interval_end - self.interval_start)}",
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="left", fill="y")
        tk.Label(
            bar,
            text="NVENC  |  LOCAL",
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.bold", mono=True),
        ).pack(side="right", fill="y")

    def open_media(self) -> None:
        patterns = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        selected = filedialog.askopenfilename(
            title="Abrir video",
            filetypes=(("Videos", patterns), ("Todos os arquivos", "*.*")),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            metadata = ffprobe_video(path)
            video_stream = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"), {})
            duration = float(metadata.get("format", {}).get("duration") or 0.0)
            if duration <= 0:
                raise RuntimeError("Duracao do video nao encontrada")
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Nao foi possivel abrir", str(error), parent=self.root)
            return
        self.media = MediaInfo(
            path=path,
            duration=duration,
            resolution=f"{video_stream.get('width', '?')} x {video_stream.get('height', '?')}",
            codec=str(video_stream.get("codec_name", "desconhecido")).upper(),
            size_text=format_size(path.stat().st_size),
        )
        self.interval_start = 0.0
        self.interval_end = duration
        self.start_var.set(format_clock(0.0))
        self.end_var.set(format_clock(duration))
        self.capture_panel_widths()
        self.render()
        self.root.after_idle(self.restore_panel_widths)

    def show_timeline_menu(self, event: tk.Event) -> None:
        menu = self.context_menu()
        menu.add_command(label="Definir inicio aqui", command=lambda: None)
        menu.add_command(label="Definir fim aqui", command=lambda: None)
        menu.add_separator()
        menu.add_command(label="Selecionar tudo     Ctrl+A", command=lambda: None)
        menu.tk_popup(event.x_root, event.y_root)

    def show_segment_menu(self, event: tk.Event) -> None:
        if self.segment_list is not None:
            index = self.segment_list.nearest(event.y)
            if index not in self.segment_list.curselection():
                self.segment_list.selection_clear(0, tk.END)
                self.segment_list.selection_set(index)
        menu = self.context_menu()
        menu.add_command(label="Revelar saida", command=lambda: None)
        menu.add_command(label="Copiar intervalo     Ctrl+C", command=lambda: None)
        menu.add_separator()
        menu.add_command(label="Remover da divisao   Del", command=lambda: None)
        menu.tk_popup(event.x_root, event.y_root)

    def context_menu(self) -> tk.Menu:
        return tk.Menu(
            self.root,
            tearoff=False,
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            activebackground=self.value("surface.hover"),
            activeforeground=self.value("text.primary"),
            font=self.font("font.size.2"),
        )

    def preview_process_action(self) -> None:
        self.root.bell()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualiza a tela principal preenchida.")
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_tokens()
    if args.self_test:
        assert parse_clock("01:12:30") == 4350.0
        print("MAIN_SCREEN_OK")
        return
    root = tk.Tk()
    MainScreenPreview(root, args.theme)
    root.mainloop()


if __name__ == "__main__":
    main()
