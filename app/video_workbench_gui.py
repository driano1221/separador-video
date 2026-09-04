"""Production desktop workbench built on the approved application shell."""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable

from app.transcription_core import (
    TRANSCRIPTION_LANGUAGES,
    TRANSCRIPTION_MODELS,
    TranscriptionOptions,
    TranscriptionResult,
    get_ctranslate2,
    get_faster_whisper_model_class,
    process_transcription,
)
from app.ui_main_preview import MainScreenPreview, parse_clock
from app.ui_shell_preview import SECTIONS
from app.ui_theme import validate_tokens
from app.video_splitter_core import (
    OperationCancelled,
    ProcessingOptions,
    ProcessingResult,
    default_output_root,
    ensure_basic_tools,
    ffprobe_video,
    format_clock,
    process_video,
)


QUALITY_KEYS = {
    "Alta qualidade": "alta",
    "Equilibrada": "equilibrada",
    "Arquivo menor": "leve",
}
ENCODER_KEYS = {
    "Automatico": "auto",
    "NVIDIA NVENC": "h264_nvenc",
    "Software x264": "libx264",
}
MODEL_LABELS = {
    "Rapida": "rapida",
    "Equilibrada": "equilibrada",
    "Maxima qualidade": "maxima",
}
LANGUAGE_LABELS = {language["label"]: key for key, language in TRANSCRIPTION_LANGUAGES.items()}


@dataclass
class Job:
    identifier: int
    kind: str
    input_path: Path
    status: str = "Aguardando"
    progress: float = 0.0
    detail: str = ""
    output_dir: Path | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    logs: list[str] = field(default_factory=list)
    options: ProcessingOptions | TranscriptionOptions | None = None


@dataclass
class HistoryItem:
    path: Path
    modified_at: float
    size: int


class WorkbenchApp(MainScreenPreview):
    def __init__(self, root: tk.Tk, theme_override: str | None = None) -> None:
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.jobs: list[Job] = []
        self.active_job: Job | None = None
        self.next_job_id = 1
        self.history_items: list[HistoryItem] = []
        self.last_transcription: TranscriptionResult | None = None
        self.queue_list: tk.Listbox | None = None
        self.history_list: tk.Listbox | None = None
        self.transcript_box: tk.Text | None = None
        self.progress_canvas: tk.Canvas | None = None
        self.status_label: tk.Label | None = None
        self.cancel_button: tk.Button | None = None
        self.command_window: tk.Toplevel | None = None

        self.status_var = tk.StringVar(root, "PRONTO")
        self.status_detail_var = tk.StringVar(root, "Nenhuma tarefa em execucao")
        self.model_var = tk.StringVar(root, "Equilibrada")
        self.language_var = tk.StringVar(root, TRANSCRIPTION_LANGUAGES["pt"]["label"])
        self.history_filter_var = tk.StringVar(root, "")
        self.history_sort_var = tk.StringVar(root, "recent")

        super().__init__(root, theme_override)
        self.root.title("SeparadorVideo")
        self.history_filter_var.set(str(self.state.get("history_filter", "")))
        self.history_sort_var.set(str(self.state.get("history_sort", "recent")))
        self.root.bind("<Control-k>", lambda _event: self.show_command_palette())
        self.root.bind("<Control-K>", lambda _event: self.show_command_palette())
        self.root.bind("<Control-1>", lambda _event: self.select_section(SECTIONS[0]))
        self.root.bind("<Control-2>", lambda _event: self.select_section(SECTIONS[1]))
        self.root.bind("<Control-3>", lambda _event: self.select_section(SECTIONS[2]))
        self.root.bind("<Control-4>", lambda _event: self.select_section(SECTIONS[3]))
        self.scan_history()
        self.render()
        self.root.after_idle(self.restore_panel_widths)
        self.root.after(100, self.poll_events)

    def render(self) -> None:
        self.queue_list = None
        self.history_list = None
        self.transcript_box = None
        self.progress_canvas = None
        self.status_label = None
        self.cancel_button = None
        super().render()

    def build_workspace(self, parent: tk.Widget) -> tk.Frame:
        section = self.state["section"]
        if section == SECTIONS[0]:
            return super().build_workspace(parent)
        if section == SECTIONS[1]:
            return self.build_transcription_workspace(parent)
        if section == SECTIONS[2]:
            return self.build_queue_workspace(parent)
        return self.build_history_workspace(parent)

    def build_inspector(self, parent: tk.Widget) -> tk.Frame:
        section = self.state["section"]
        if section == SECTIONS[0]:
            return super().build_inspector(parent)
        if section == SECTIONS[1]:
            return self.build_transcription_inspector(parent)
        if section == SECTIONS[2]:
            return self.build_queue_inspector(parent)
        return self.build_history_inspector(parent)

    def preview_process_action(self) -> None:
        if self.state["section"] == SECTIONS[0]:
            self.start_video_job()
        elif self.state["section"] == SECTIONS[1]:
            self.start_transcription_job()

    def workspace_toolbar(self, parent: tk.Widget, title: str, count: str, command=None) -> None:
        toolbar = tk.Frame(parent, height=self.value("workspace.toolbar-height"), background=self.value("surface.panel"))
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Label(
            toolbar,
            text=title,
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(side="left", fill="y")
        if command:
            self.tool_button(toolbar, "ABRIR   Ctrl+O", command).pack(
                side="right", padx=self.value("space.3"), pady=self.value("space.2")
            )
        tk.Label(
            toolbar,
            text=count,
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="right", fill="y")

    def empty_state(self, parent: tk.Widget, title: str, action: str) -> None:
        center = tk.Frame(parent, background=self.value("surface.workspace"))
        center.place(relx=0.5, rely=0.46, anchor="center")
        tk.Label(
            center,
            text=title,
            background=self.value("surface.workspace"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.4", "font.weight.semibold"),
        ).pack()
        tk.Label(
            center,
            text=action,
            background=self.value("surface.workspace"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.2"),
        ).pack(pady=(self.value("space.2"), 0))

    def build_transcription_workspace(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.workspace"))
        self.workspace_toolbar(panel, "TRANSCRICAO", "TXT  SRT  VTT  JSON", self.open_media)
        self.divider(panel, "top")
        self.build_media_header(panel)
        self.divider(panel, "top")

        body = tk.Frame(panel, background=self.value("surface.workspace"))
        body.pack(fill="both", expand=True)
        self.transcript_box = tk.Text(
            body,
            wrap="word",
            background=self.value("surface.workspace"),
            foreground=self.value("text.primary"),
            insertbackground=self.value("text.primary"),
            selectbackground=self.value("selection.fill"),
            selectforeground=self.value("text.primary"),
            font=self.font("font.size.3"),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=self.value("space.6"),
            pady=self.value("space.5"),
        )
        scrollbar = self.scrollbar(body, self.transcript_box.yview)
        self.transcript_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.transcript_box.pack(side="left", fill="both", expand=True)
        self.transcript_box.bind("<Button-3>", self.show_transcript_menu)

        text = ""
        if self.last_transcription and self.last_transcription.transcript_txt.exists():
            try:
                text = self.last_transcription.transcript_txt.read_text(encoding="utf-8")
            except OSError:
                text = "Nao foi possivel ler a transcricao gerada."
        if not text:
            text = (
                "Nenhuma transcricao nesta sessao.\n\n"
                "Abra um video, escolha o intervalo e pressione Ctrl+Enter. "
                "O texto aparece aqui quando o processamento terminar."
            )
        self.transcript_box.insert("1.0", text)
        self.transcript_box.configure(state="disabled")
        return panel

    def build_transcription_inspector(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.panel"))
        self.inspector_heading(panel, "TRANSCRICAO")
        self.inspector_section(panel, "INTERVALO")
        self.field_row(panel, "Inicio", self.start_var)
        self.field_row(panel, "Fim", self.end_var)
        self.inspector_section(panel, "RECONHECIMENTO")
        self.menu_row(panel, "Modelo", self.model_var, tuple(MODEL_LABELS))
        self.menu_row(panel, "Idioma", self.language_var, tuple(LANGUAGE_LABELS))
        self.inspector_section(panel, "SAIDA")
        self.info_row(panel, "Formatos", "TXT / SRT / VTT / JSON")
        self.info_row(panel, "Trecho", format_clock(max(0.0, self.interval_end - self.interval_start)))
        self.info_row(panel, "Execucao", "GPU quando disponivel")
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
        self.primary_button(panel, "TRANSCREVER   Ctrl+Enter", self.start_transcription_job).pack(
            fill="x", padx=self.value("space.4"), pady=(0, self.value("space.4"))
        )
        return panel

    def build_queue_workspace(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.workspace"))
        self.workspace_toolbar(panel, "FILA", f"{len(self.jobs)} TAREFAS")
        self.divider(panel, "top")
        if not self.jobs:
            self.empty_state(panel, "Nenhuma tarefa nesta sessao", "Inicie um corte ou uma transcricao")
            return panel
        frame = tk.Frame(panel, background=self.value("surface.workspace"))
        frame.pack(fill="both", expand=True)
        self.queue_list = self.listbox(frame)
        scrollbar = self.scrollbar(frame, self.queue_list.yview)
        self.queue_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.queue_list.pack(side="left", fill="both", expand=True)
        self.queue_list.bind("<Button-3>", self.show_queue_menu)
        self.refresh_queue_list()
        return panel

    def build_queue_inspector(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.panel"))
        self.inspector_heading(panel, "TAREFA")
        job = self.active_job or (self.jobs[0] if self.jobs else None)
        if job:
            self.inspector_section(panel, "ESTADO")
            self.info_row(panel, "Tipo", job.kind)
            self.info_row(panel, "Status", job.status)
            self.info_row(panel, "Progresso", f"{job.progress:05.1f}%")
            self.inspector_section(panel, "ARQUIVO")
            self.info_row(panel, "Entrada", job.input_path.name[:28])
            self.info_row(panel, "Detalhe", job.detail[:28] or "-")
        else:
            tk.Label(
                panel,
                text="Nenhuma tarefa selecionada",
                anchor="nw",
                padx=self.value("space.4"),
                pady=self.value("space.4"),
                background=self.value("surface.panel"),
                foreground=self.value("text.muted"),
                font=self.font("font.size.2"),
            ).pack(fill="both", expand=True)
        tk.Frame(panel, background=self.value("surface.panel")).pack(fill="both", expand=True)
        self.divider(panel, "bottom")
        self.tool_button(panel, "LIMPAR CONCLUIDAS", self.clear_finished_jobs).pack(
            fill="x", padx=self.value("space.4"), pady=self.value("space.2")
        )
        button = self.primary_button(panel, "CANCELAR TAREFA", self.cancel_active_job)
        if self.active_job:
            button.configure(state="normal")
        else:
            button.configure(
                state="disabled",
                background=self.value("surface.disabled"),
                foreground=self.value("text.disabled"),
                disabledforeground=self.value("text.disabled"),
                highlightbackground=self.value("border.control"),
            )
        button.pack(fill="x", padx=self.value("space.4"), pady=(0, self.value("space.4")))
        return panel

    def build_history_workspace(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.workspace"))
        toolbar = tk.Frame(panel, height=self.value("workspace.toolbar-height"), background=self.value("surface.panel"))
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Label(
            toolbar,
            text="HISTORICO",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(side="left", fill="y")
        search = tk.Entry(
            toolbar,
            textvariable=self.history_filter_var,
            background=self.value("field.background.rest"),
            foreground=self.value("field.text.rest"),
            insertbackground=self.value("text.primary"),
            selectbackground=self.value("selection.fill"),
            font=self.font("font.size.2"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("field.border.rest"),
            highlightcolor=self.value("field.border.focus"),
        )
        search.pack(side="left", fill="y", padx=self.value("space.3"), pady=self.value("space.2"))
        search.bind("<KeyRelease>", lambda _event: self.refresh_history_list())
        sort = tk.Menubutton(
            toolbar,
            text="ORDENAR",
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
            takefocus=True,
        )
        menu = self.context_menu()
        for label, value in (("Mais recentes", "recent"), ("Nome", "name"), ("Tamanho", "size")):
            menu.add_radiobutton(label=label, value=value, variable=self.history_sort_var, command=self.refresh_history_list)
        sort.configure(menu=menu)
        sort.pack(side="right", fill="y", padx=self.value("space.3"), pady=self.value("space.2"))
        self.divider(panel, "top")

        frame = tk.Frame(panel, background=self.value("surface.workspace"))
        frame.pack(fill="both", expand=True)
        self.history_list = self.listbox(frame)
        scrollbar = self.scrollbar(frame, self.history_list.yview)
        self.history_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.history_list.pack(side="left", fill="both", expand=True)
        self.history_list.bind("<Button-3>", self.show_history_menu)
        self.history_list.bind("<Double-Button-1>", lambda _event: self.open_selected_history())
        self.refresh_history_list()
        return panel

    def build_history_inspector(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, background=self.value("surface.panel"))
        self.inspector_heading(panel, "ARQUIVO")
        items = self.filtered_history()
        item = items[0] if items else None
        if item:
            self.inspector_section(panel, "SELECAO")
            short_name = item.path.name if len(item.path.name) <= 18 else f"{item.path.name[:17]}..."
            self.info_row(panel, "Nome", short_name)
            self.info_row(panel, "Tipo", item.path.suffix.upper().lstrip("."))
            self.info_row(panel, "Tamanho", self.format_bytes(item.size))
            self.info_row(panel, "Alterado", datetime.fromtimestamp(item.modified_at).strftime("%d/%m/%Y %H:%M"))
            self.inspector_section(panel, "LOCAL")
            tk.Label(
                panel,
                text=str(item.path.parent),
                anchor="nw",
                justify="left",
                wraplength=max(180, int(self.state["inspector_width"]) - self.value("space.8")),
                padx=self.value("space.4"),
                background=self.value("surface.panel"),
                foreground=self.value("text.secondary"),
                font=self.font("font.size.1", mono=True),
            ).pack(fill="x")
        else:
            message = "Nenhum resultado para o filtro" if self.history_filter_var.get().strip() else "Nenhum arquivo gerado"
            tk.Label(
                panel,
                text=message,
                anchor="nw",
                padx=self.value("space.4"),
                pady=self.value("space.4"),
                background=self.value("surface.panel"),
                foreground=self.value("text.muted"),
                font=self.font("font.size.2"),
            ).pack(fill="both", expand=True)
        tk.Frame(panel, background=self.value("surface.panel")).pack(fill="both", expand=True)
        self.divider(panel, "bottom")
        self.tool_button(panel, "COPIAR CAMINHO   Ctrl+C", self.copy_selected_history).pack(
            fill="x", padx=self.value("space.4"), pady=self.value("space.2")
        )
        self.primary_button(panel, "ABRIR LOCAL", self.open_selected_history).pack(
            fill="x", padx=self.value("space.4"), pady=(0, self.value("space.4"))
        )
        return panel

    def listbox(self, parent: tk.Widget) -> tk.Listbox:
        return tk.Listbox(
            parent,
            selectmode=tk.EXTENDED,
            activestyle="none",
            background=self.value("list.background"),
            foreground=self.value("list.item.text.rest"),
            selectbackground=self.value("list.item.background.selected"),
            selectforeground=self.value("text.primary"),
            font=self.font("font.size.2", mono=True),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("border.subtle"),
            highlightcolor=self.value("border.focus"),
        )

    def scrollbar(self, parent: tk.Widget, command) -> tk.Scrollbar:
        return tk.Scrollbar(
            parent,
            orient="vertical",
            command=command,
            width=self.value("scrollbar.width"),
            background=self.value("scrollbar.thumb"),
            troughcolor=self.value("scrollbar.track"),
            activebackground=self.value("accent.primary"),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )

    def build_statusbar(self) -> None:
        self.divider(self.root, "top")
        bar = tk.Frame(self.root, height=self.value("statusbar.height"), background=self.value("statusbar.background"))
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.status_label = tk.Label(
            bar,
            textvariable=self.status_var,
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("status.error") if self.status_var.get() == "ERRO" else self.value("status.ready"),
            font=self.font("font.size.1", "font.weight.bold", mono=True),
        )
        self.status_label.pack(side="left", fill="y")
        tk.Label(
            bar,
            textvariable=self.status_detail_var,
            padx=self.value("space.4"),
            background=self.value("statusbar.background"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.1", mono=True),
        ).pack(side="left", fill="y")
        self.cancel_button = tk.Button(
            bar,
            text="CANCELAR",
            command=self.cancel_active_job,
            state="normal" if self.active_job else "disabled",
            background=self.value("surface.control"),
            foreground=self.value("text.primary"),
            disabledforeground=self.value("text.disabled"),
            activebackground=self.value("surface.hover"),
            activeforeground=self.value("text.primary"),
            font=self.font("font.size.1", "font.weight.semibold"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("border.control"),
            highlightcolor=self.value("border.focus"),
            takefocus=True,
        )
        self.cancel_button.pack(side="right", fill="y", padx=self.value("space.2"))
        self.progress_canvas = tk.Canvas(
            bar,
            width=self.value("space.9") * 3,
            background=self.value("surface.control"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.progress_canvas.pack(side="right", fill="y", pady=self.value("space.3"))
        self.progress_canvas.bind("<Configure>", lambda _event: self.update_progress_visual())
        self.update_progress_visual()

    def update_progress_visual(self) -> None:
        if not self.progress_canvas or not self.progress_canvas.winfo_exists():
            return
        self.progress_canvas.delete("all")
        width = max(1, self.progress_canvas.winfo_width())
        height = max(1, self.progress_canvas.winfo_height())
        progress = self.active_job.progress if self.active_job else (100.0 if self.status_var.get() == "CONCLUIDO" else 0.0)
        self.progress_canvas.create_rectangle(0, 0, width * progress / 100.0, height, fill=self.value("accent.primary"), outline="")

    @staticmethod
    def format_bytes(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def refresh_queue_list(self) -> None:
        if not self.queue_list or not self.queue_list.winfo_exists():
            return
        self.queue_list.delete(0, tk.END)
        for job in self.jobs:
            self.queue_list.insert(
                tk.END,
                f" {job.identifier:03d}   {job.status:<11}   {job.progress:05.1f}%   {job.kind:<11}   {job.input_path.name}",
            )
        if self.jobs:
            self.queue_list.selection_set(0)

    def refresh_history_list(self) -> None:
        if not self.history_list or not self.history_list.winfo_exists():
            return
        self.history_list.delete(0, tk.END)
        items = self.filtered_history()
        if not items:
            message = " Nenhum resultado para o filtro" if self.history_filter_var.get().strip() else " Nenhum arquivo gerado"
            self.history_list.insert(tk.END, message)
            return
        for item in items:
            modified = datetime.fromtimestamp(item.modified_at).strftime("%d/%m/%Y %H:%M")
            self.history_list.insert(
                tk.END,
                f" {modified}   {item.path.suffix.upper().lstrip('.'):<4}   {self.format_bytes(item.size):>10}   {item.path.name}",
            )
        self.history_list.selection_set(0)
        self.history_list.yview_moveto(float(self.state.get("history_scroll", 0.0)))

    def selected_history_items(self) -> list[HistoryItem]:
        items = self.filtered_history()
        if not self.history_list or not items:
            return items[:1]
        indexes = self.history_list.curselection()
        return [items[index] for index in indexes if index < len(items)] or items[:1]

    def open_selected_history(self) -> None:
        selected = self.selected_history_items()
        target = selected[0].path.parent if selected else default_output_root()
        if hasattr(os, "startfile"):
            os.startfile(target)  # type: ignore[attr-defined]

    def copy_selected_history(self) -> None:
        selected = self.selected_history_items()
        if not selected:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(str(item.path) for item in selected))
        self.status_detail_var.set(f"{len(selected)} caminho(s) copiado(s)")

    def clear_finished_jobs(self) -> None:
        self.jobs = [job for job in self.jobs if job.status in {"Executando", "Cancelando"}]
        self.refresh_job_views()
        if self.state["section"] == SECTIONS[2]:
            self.render_and_restore()

    def retry_selected_job(self) -> None:
        job = self.jobs[0] if self.jobs else None
        if self.queue_list and self.queue_list.curselection():
            index = self.queue_list.curselection()[0]
            if index < len(self.jobs):
                job = self.jobs[index]
        if job and job.options and self.ensure_idle():
            self.start_job(job.kind, job.options)

    def show_transcript_menu(self, event: tk.Event) -> None:
        menu = self.context_menu()
        menu.add_command(label="Copiar selecao     Ctrl+C", command=lambda: self.transcript_box and self.transcript_box.event_generate("<<Copy>>"))
        menu.add_command(label="Selecionar tudo    Ctrl+A", command=self.select_all_transcript)
        menu.add_separator()
        menu.add_command(label="Abrir pasta de saida", command=self.open_selected_history)
        menu.tk_popup(event.x_root, event.y_root)

    def select_all_transcript(self) -> None:
        if not self.transcript_box:
            return
        self.transcript_box.configure(state="normal")
        self.transcript_box.tag_add("sel", "1.0", "end-1c")
        self.transcript_box.configure(state="disabled")

    def show_queue_menu(self, event: tk.Event) -> None:
        if self.queue_list:
            index = self.queue_list.nearest(event.y)
            if index not in self.queue_list.curselection():
                self.queue_list.selection_clear(0, tk.END)
                self.queue_list.selection_set(index)
        menu = self.context_menu()
        menu.add_command(label="Cancelar tarefa", command=self.cancel_active_job)
        menu.add_command(label="Executar novamente", command=self.retry_selected_job)
        menu.add_separator()
        menu.add_command(label="Limpar concluidas", command=self.clear_finished_jobs)
        menu.tk_popup(event.x_root, event.y_root)

    def show_history_menu(self, event: tk.Event) -> None:
        if self.history_list:
            index = self.history_list.nearest(event.y)
            if index not in self.history_list.curselection():
                self.history_list.selection_clear(0, tk.END)
                self.history_list.selection_set(index)
        menu = self.context_menu()
        menu.add_command(label="Abrir local", command=self.open_selected_history)
        menu.add_command(label="Copiar caminho     Ctrl+C", command=self.copy_selected_history)
        menu.add_separator()
        menu.add_command(label="Atualizar", command=self.rescan_history)
        menu.tk_popup(event.x_root, event.y_root)

    def rescan_history(self) -> None:
        self.scan_history()
        self.refresh_history_list()

    def show_command_palette(self) -> None:
        if self.command_window and self.command_window.winfo_exists():
            self.command_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.command_window = window
        window.title("Comandos")
        window.transient(self.root)
        window.configure(background=self.value("surface.panel"))
        width = self.value("space.9") * 14
        height = self.value("space.9") * 10
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + self.value("space.9") * 2
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.resizable(False, False)

        query = tk.StringVar(window)
        entry = tk.Entry(
            window,
            textvariable=query,
            background=self.value("field.background.rest"),
            foreground=self.value("field.text.rest"),
            insertbackground=self.value("text.primary"),
            selectbackground=self.value("selection.fill"),
            font=self.font("font.size.3"),
            relief="flat",
            borderwidth=0,
            highlightthickness=self.value("line.1"),
            highlightbackground=self.value("field.border.rest"),
            highlightcolor=self.value("field.border.focus"),
        )
        entry.pack(fill="x", padx=self.value("space.4"), pady=self.value("space.4"), ipady=self.value("space.3"))
        results = self.listbox(window)
        results.pack(fill="both", expand=True, padx=self.value("space.4"), pady=(0, self.value("space.4")))

        actions: list[tuple[str, Callable[[], None]]] = [
            ("Abrir video                         Ctrl+O", self.open_media),
            ("Cortar e dividir                   Ctrl+1", lambda: self.select_section(SECTIONS[0])),
            ("Transcrever                        Ctrl+2", lambda: self.select_section(SECTIONS[1])),
            ("Abrir fila                         Ctrl+3", lambda: self.select_section(SECTIONS[2])),
            ("Abrir historico                    Ctrl+4", lambda: self.select_section(SECTIONS[3])),
            ("Executar acao principal        Ctrl+Enter", self.preview_process_action),
            ("Cancelar tarefa", self.cancel_active_job),
            ("Alternar tema               Ctrl+Shift+L", self.toggle_theme),
            ("Abrir pasta de saidas", lambda: hasattr(os, "startfile") and os.startfile(default_output_root())),  # type: ignore[attr-defined]
            ("Atualizar historico", self.rescan_history),
            ("Limpar tarefas concluidas", self.clear_finished_jobs),
            ("Executar tarefa novamente", self.retry_selected_job),
            ("Fechar aplicacao                        Esc", self.close),
        ]
        visible: list[tuple[str, Callable[[], None]]] = []

        def refresh(*_args) -> None:
            visible.clear()
            needle = query.get().strip().lower()
            visible.extend(item for item in actions if needle in item[0].lower())
            results.delete(0, tk.END)
            for label, _command in visible:
                results.insert(tk.END, f"  {label}")
            if visible:
                results.selection_set(0)

        def run_selected(_event=None) -> None:
            if not visible:
                return
            indexes = results.curselection()
            index = indexes[0] if indexes else 0
            command = visible[index][1]
            window.destroy()
            self.command_window = None
            command()

        query.trace_add("write", refresh)
        results.bind("<Double-Button-1>", run_selected)
        results.bind("<Return>", run_selected)
        entry.bind("<Return>", run_selected)
        window.bind("<Escape>", lambda _event: window.destroy())
        refresh()
        entry.focus_set()

    def current_interval(self) -> tuple[float, float]:
        start = parse_clock(self.start_var.get())
        end = parse_clock(self.end_var.get())
        if start >= end or end > self.media.duration:
            raise ValueError("O intervalo precisa estar dentro do video")
        return start, end

    def require_real_media(self) -> bool:
        if self.media.path.exists():
            return True
        messagebox.showwarning(
            "Escolha um video",
            "A midia exibida e apenas a amostra visual. Use Ctrl+O para escolher um arquivo real.",
            parent=self.root,
        )
        return False

    def start_video_job(self) -> None:
        if not self.require_real_media() or not self.ensure_idle():
            return
        try:
            start, end = self.current_interval()
        except ValueError as error:
            messagebox.showwarning("Intervalo invalido", str(error), parent=self.root)
            return
        options = ProcessingOptions(
            input_path=self.media.path,
            output_root=default_output_root(),
            parts=self.parts,
            encoder=ENCODER_KEYS.get(self.encoder_var.get(), "auto"),
            quality_profile=QUALITY_KEYS.get(self.quality_var.get(), "equilibrada"),
            start_seconds=start,
            end_seconds=end,
        )
        self.start_job("Video", options)

    def start_transcription_job(self) -> None:
        if not self.require_real_media() or not self.ensure_idle():
            return
        try:
            start, end = self.current_interval()
        except ValueError as error:
            messagebox.showwarning("Intervalo invalido", str(error), parent=self.root)
            return
        options = TranscriptionOptions(
            input_path=self.media.path,
            output_root=default_output_root(),
            model_profile=MODEL_LABELS.get(self.model_var.get(), "equilibrada"),
            language=LANGUAGE_LABELS.get(self.language_var.get(), "pt"),
            start_seconds=start,
            end_seconds=end,
        )
        self.start_job("Transcricao", options)

    def ensure_idle(self) -> bool:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Tarefa em andamento", "Cancele ou aguarde a tarefa atual.", parent=self.root)
            return False
        return True

    def start_job(self, kind: str, options: ProcessingOptions | TranscriptionOptions) -> None:
        job = Job(
            identifier=self.next_job_id,
            kind=kind,
            input_path=options.input_path,
            status="Executando",
            detail="Preparando recursos",
            options=options,
        )
        self.next_job_id += 1
        self.jobs.insert(0, job)
        self.active_job = job
        self.cancel_event.clear()
        self.status_var.set("PROCESSANDO")
        self.status_detail_var.set(f"{kind}: preparando {job.input_path.name}")
        self.worker = threading.Thread(target=self.run_job, args=(job,), daemon=True)
        self.worker.start()
        self.refresh_job_views()
        self.update_progress_visual()

    def run_job(self, job: Job) -> None:
        try:
            progress = lambda payload: self.events.put(("progress", payload))
            log = lambda message: self.events.put(("log", str(message)))
            if isinstance(job.options, ProcessingOptions):
                result = process_video(
                    job.options,
                    progress_callback=progress,
                    log_callback=log,
                    cancel_check=self.cancel_event.is_set,
                )
            elif isinstance(job.options, TranscriptionOptions):
                result = process_transcription(
                    job.options,
                    progress_callback=progress,
                    log_callback=log,
                    cancel_check=self.cancel_event.is_set,
                )
            else:
                raise RuntimeError("Opcoes da tarefa nao foram definidas.")
            self.events.put(("done", result))
        except OperationCancelled as error:
            self.events.put(("cancelled", str(error)))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", str(error)))

    def cancel_active_job(self) -> None:
        if not self.worker or not self.worker.is_alive():
            return
        self.cancel_event.set()
        if self.active_job:
            self.active_job.status = "Cancelando"
            self.active_job.detail = "Aguardando o ponto seguro"
        self.status_var.set("CANCELANDO")
        self.status_detail_var.set("Finalizando a etapa atual com seguranca")
        self.refresh_job_views()

    def poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    self.handle_progress(payload)
                elif event == "log":
                    if self.active_job:
                        self.active_job.logs.append(str(payload))
                elif event == "done":
                    self.handle_job_done(payload)
                elif event == "cancelled":
                    self.handle_job_cancelled(str(payload))
                elif event == "error":
                    self.handle_job_error(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def handle_progress(self, payload: Any) -> None:
        if not self.active_job or not isinstance(payload, dict):
            return
        if payload.get("indeterminate"):
            self.active_job.detail = str(payload.get("details_text") or payload.get("label") or "Processando")
        else:
            self.active_job.progress = min(100.0, max(0.0, float(payload.get("percent", 0.0))))
            self.active_job.detail = str(payload.get("label", "Processando"))
        self.status_detail_var.set(
            f"{self.active_job.kind}: {self.active_job.progress:05.1f}%  |  {self.active_job.detail}"
        )
        self.update_progress_visual()
        self.refresh_job_views()

    def handle_job_done(self, result: ProcessingResult | TranscriptionResult) -> None:
        if self.active_job:
            self.active_job.status = "Concluido"
            self.active_job.progress = 100.0
            self.active_job.output_dir = result.output_dir
            self.active_job.detail = "Arquivos gerados"
        if isinstance(result, TranscriptionResult):
            self.last_transcription = result
        self.status_var.set("CONCLUIDO")
        self.status_detail_var.set(f"Arquivos prontos em {result.output_dir}")
        self.active_job = None
        self.scan_history()
        self.refresh_job_views()
        self.update_progress_visual()
        if self.open_folder_var.get() and hasattr(os, "startfile"):
            os.startfile(result.output_dir)  # type: ignore[attr-defined]
        if self.state["section"] in {SECTIONS[1], SECTIONS[3]}:
            self.render_and_restore()

    def handle_job_cancelled(self, message: str) -> None:
        if self.active_job:
            self.active_job.status = "Cancelado"
            self.active_job.detail = message
        self.active_job = None
        self.status_var.set("CANCELADO")
        self.status_detail_var.set(message)
        self.refresh_job_views()
        self.update_progress_visual()

    def handle_job_error(self, message: str) -> None:
        if self.active_job:
            self.active_job.status = "Erro"
            self.active_job.error = message
            self.active_job.detail = message
        self.active_job = None
        self.status_var.set("ERRO")
        self.status_detail_var.set(message)
        self.refresh_job_views()
        self.update_progress_visual()
        if self.status_label:
            self.status_label.configure(foreground=self.value("status.error"))
        messagebox.showerror("Nao foi possivel concluir", message, parent=self.root)

    def render_and_restore(self) -> None:
        self.capture_panel_widths()
        self.render()
        self.root.after_idle(self.restore_panel_widths)

    def refresh_job_views(self) -> None:
        self.refresh_queue_list()
        if self.cancel_button:
            self.cancel_button.configure(state="normal" if self.active_job else "disabled")

    def scan_history(self) -> None:
        root = default_output_root()
        supported = {".mp4", ".txt", ".srt", ".vtt", ".json"}
        items: list[HistoryItem] = []
        if root.exists():
            for path in root.rglob("*"):
                if len(items) >= 500:
                    break
                if not path.is_file() or path.suffix.lower() not in supported:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                items.append(HistoryItem(path=path, modified_at=stat.st_mtime, size=stat.st_size))
        self.history_items = items

    def filtered_history(self) -> list[HistoryItem]:
        query = self.history_filter_var.get().strip().lower()
        items = [item for item in self.history_items if query in item.path.name.lower()]
        sort_key = self.history_sort_var.get()
        if sort_key == "name":
            return sorted(items, key=lambda item: item.path.name.lower())
        if sort_key == "size":
            return sorted(items, key=lambda item: item.size, reverse=True)
        return sorted(items, key=lambda item: item.modified_at, reverse=True)

    def save_state(self) -> None:
        self.state["history_filter"] = self.history_filter_var.get()
        self.state["history_sort"] = self.history_sort_var.get()
        if self.history_list:
            self.state["history_scroll"] = self.history_list.yview()[0]
        super().save_state()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SeparadorVideo: corte, divisao e transcricao local.")
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--runtime-test", type=Path)
    return parser.parse_args()


def run_self_test() -> None:
    validate_tokens()
    ensure_basic_tools()
    ctranslate2 = get_ctranslate2()
    get_faster_whisper_model_class()
    print(f"GUI_OK | CTranslate2 {ctranslate2.__version__}")


def run_runtime_test(input_path: Path) -> None:
    ensure_basic_tools()
    metadata = ffprobe_video(input_path.resolve())
    duration = float(metadata.get("format", {}).get("duration") or 0.0)
    if duration <= 0:
        raise RuntimeError("O video de teste nao tem duracao valida.")
    result = process_transcription(
        TranscriptionOptions(
            input_path=input_path.resolve(),
            output_root=input_path.resolve().parent / "_teste_executavel",
            model_profile="rapida",
            language="pt",
            start_seconds=0.0,
            end_seconds=min(duration, 7.0),
        ),
        progress_callback=lambda payload: print(
            f"{float(payload.get('percent', 0.0)):05.1f}% | {payload.get('label', 'Processando')}"
        ),
        log_callback=print,
    )
    print(f"RUNTIME_OK | {result.transcript_txt}")


def error_log_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "SeparadorVideo_erro.log"
    return Path.cwd() / "SeparadorVideo_erro.log"


def main() -> None:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
            return
        if args.runtime_test:
            run_runtime_test(args.runtime_test)
            return
        validate_tokens()
        root = tk.Tk()
        WorkbenchApp(root, args.theme)
        root.mainloop()
    except Exception as error:  # noqa: BLE001
        error_log_path().write_text(traceback.format_exc(), encoding="utf-8")
        if args.self_test or args.runtime_test:
            raise
        try:
            messagebox.showerror("SeparadorVideo", f"Nao foi possivel iniciar.\n\n{error}")
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()
