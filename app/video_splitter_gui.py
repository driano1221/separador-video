import argparse
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.transcription_core import (
    TRANSCRIPTION_LANGUAGES,
    TRANSCRIPTION_MODELS,
    TranscriptionOptions,
    get_ctranslate2,
    get_faster_whisper_model_class,
    is_model_downloaded,
    prepare_transcription_model,
    process_transcription,
)
from app.video_splitter_core import (
    ProcessingOptions,
    default_output_root,
    ensure_basic_tools,
    ffprobe_video,
    format_clock,
    format_path_time,
    process_video,
    resolve_time_range,
)


COLORS = {
    "window": "#181B18",
    "surface": "#222622",
    "surface_alt": "#2A2F29",
    "field": "#30362F",
    "border": "#41483F",
    "text": "#F1F0E9",
    "muted": "#AAB0A5",
    "moss": "#738066",
    "copper": "#C07A4A",
    "copper_active": "#D08A58",
}
ENCODER_LABELS = {
    "auto": "Automático (recomendado)",
    "h264_nvenc": "NVIDIA NVENC",
    "h264_mf": "Media Foundation",
    "libx264": "Software (x264)",
}
QUALITY_LABELS = {
    "alta": "Alta qualidade",
    "equilibrada": "Equilibrada",
    "leve": "Arquivo menor",
}
PART_LABELS = {
    "1": "Recorte único",
    "2": "2 partes iguais",
    "3": "3 partes iguais",
    "4": "4 partes iguais",
}
TRANSCRIPTION_MODEL_LABELS = {key: value["label"] for key, value in TRANSCRIPTION_MODELS.items()}
TRANSCRIPTION_LANGUAGE_LABELS = {key: value["label"] for key, value in TRANSCRIPTION_LANGUAGES.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--runtime-test", type=Path)
    return parser.parse_args()


def parse_time_value(value: str) -> float:
    text = value.strip().replace(",", ".")
    if not text:
        raise ValueError("Informe o horário no formato HH:MM:SS.")
    fields = text.split(":")
    if len(fields) > 3:
        raise ValueError("Use o formato HH:MM:SS.")
    try:
        numbers = [float(field) for field in fields]
    except ValueError as error:
        raise ValueError("Use apenas números no intervalo.") from error
    if any(number < 0 for number in numbers):
        raise ValueError("O intervalo não pode ter valores negativos.")
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
    elif len(numbers) == 2:
        hours, minutes, seconds = 0.0, numbers[0], numbers[1]
    else:
        hours, minutes, seconds = 0.0, 0.0, numbers[0]
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutos e segundos devem ser menores que 60.")
    return hours * 3600 + minutes * 60 + seconds


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_path / relative_path


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Separador de Vídeo")
        icon_path = resource_path("assets/SeparadorVideo.ico")
        if icon_path.exists():
            self.root.iconbitmap(default=str(icon_path))
        self.root.geometry("1000x740")
        self.root.minsize(900, 720)
        self.root.configure(background=COLORS["window"])
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.log_messages: list[str] = []
        self.video_duration = 0.0

        self.input_var = tk.StringVar()
        self.output_root_var = tk.StringVar(value=str(default_output_root()))
        self.video_info_var = tk.StringVar(value="Nenhum vídeo selecionado")
        self.use_range_var = tk.BooleanVar(value=False)
        self.start_var = tk.StringVar(value="00:00:00")
        self.end_var = tk.StringVar(value="00:00:00")
        self.parts_var = tk.StringVar(value=PART_LABELS["1"])
        self.quality_var = tk.StringVar(value=QUALITY_LABELS["equilibrada"])
        self.encoder_var = tk.StringVar(value=ENCODER_LABELS["auto"])
        self.transcription_model_var = tk.StringVar(value=TRANSCRIPTION_MODEL_LABELS["equilibrada"])
        self.transcription_language_var = tk.StringVar(value=TRANSCRIPTION_LANGUAGE_LABELS["pt"])
        self.open_folder_var = tk.BooleanVar(value=True)
        self.model_status_var = tk.StringVar(value="Verificando modelo...")
        self.output_preview_var = tk.StringVar(value="A pasta final aparecerá aqui.")
        self.status_var = tk.StringVar(value="Pronto para começar")
        self.details_var = tk.StringVar(value="Escolha um vídeo e uma tarefa.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_mode = "determinate"

        self.configure_style()
        self.build_ui()
        self.on_range_toggle()
        self.update_output_preview()
        self.refresh_model_status()
        self.root.after(150, self.poll_events)

    def configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.option_add("*Font", ("Segoe UI", 10))
        style.configure("TFrame", background=COLORS["window"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("TLabel", background=COLORS["window"], foreground=COLORS["text"])
        style.configure("Title.TLabel", background=COLORS["window"], foreground=COLORS["text"], font=("Segoe UI Semibold", 23))
        style.configure("Section.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=("Segoe UI Semibold", 11))
        style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", background=COLORS["window"], foreground=COLORS["muted"])
        style.configure("SurfaceMuted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
        style.configure("TEntry", fieldbackground=COLORS["field"], foreground=COLORS["text"], insertcolor=COLORS["text"], bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"], padding=8)
        style.map("TEntry", fieldbackground=[("disabled", COLORS["surface_alt"])])
        style.configure("TCombobox", fieldbackground=COLORS["field"], background=COLORS["field"], foreground=COLORS["text"], arrowcolor=COLORS["muted"], bordercolor=COLORS["border"], padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["field"])], foreground=[("readonly", COLORS["text"])], selectbackground=[("readonly", COLORS["field"])], selectforeground=[("readonly", COLORS["text"])])
        style.configure("TButton", background=COLORS["surface_alt"], foreground=COLORS["text"], bordercolor=COLORS["border"], padding=(14, 8))
        style.map("TButton", background=[("active", COLORS["field"]), ("disabled", COLORS["surface"])], foreground=[("disabled", COLORS["muted"])])
        style.configure("Accent.TButton", background=COLORS["copper"], foreground="#17130F", bordercolor=COLORS["copper"], font=("Segoe UI Semibold", 10), padding=(18, 9))
        style.map("Accent.TButton", background=[("active", COLORS["copper_active"]), ("disabled", COLORS["surface_alt"])], foreground=[("disabled", COLORS["muted"])])
        style.configure("TCheckbutton", background=COLORS["surface"], foreground=COLORS["text"], indicatorcolor=COLORS["field"], padding=2)
        style.map("TCheckbutton", background=[("active", COLORS["surface"])], indicatorcolor=[("selected", COLORS["moss"])])
        style.configure("TNotebook", background=COLORS["window"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["surface"], foreground=COLORS["muted"], padding=(20, 10), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", COLORS["surface_alt"]), ("active", COLORS["field"])], foreground=[("selected", COLORS["text"]), ("active", COLORS["text"])])
        style.configure("Rustic.Horizontal.TProgressbar", troughcolor=COLORS["surface_alt"], background=COLORS["copper"], bordercolor=COLORS["surface_alt"], lightcolor=COLORS["copper"], darkcolor=COLORS["copper"])

    def build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=(28, 22, 28, 20))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Separador de Vídeo", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Corte, divisão e transcrição em um só lugar", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Checkbutton(header, text="Abrir pasta ao terminar", variable=self.open_folder_var).grid(row=0, column=1, rowspan=2, sticky="e")

        source = ttk.Frame(main, style="Surface.TFrame", padding=16)
        source.grid(row=1, column=0, sticky="ew")
        source.columnconfigure(1, weight=1)
        ttk.Label(source, text="ARQUIVO", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 9))
        ttk.Label(source, text="Vídeo", style="SurfaceMuted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.input_entry = ttk.Entry(source, textvariable=self.input_var)
        self.input_entry.grid(row=1, column=1, sticky="ew")
        self.input_entry.bind("<FocusOut>", lambda _event: self.load_video_metadata(show_errors=False))
        ttk.Button(source, text="Escolher", command=self.choose_input).grid(row=1, column=2, padx=(10, 0))
        ttk.Label(source, textvariable=self.video_info_var, style="SurfaceMuted.TLabel").grid(row=2, column=1, columnspan=2, sticky="w", pady=(7, 0))

        interval = ttk.Frame(main, style="Surface.TFrame", padding=16)
        interval.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        interval.columnconfigure(5, weight=1)
        ttk.Label(interval, text="INTERVALO", style="Section.TLabel").grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 9))
        ttk.Checkbutton(interval, text="Usar apenas um trecho", variable=self.use_range_var, command=self.on_range_toggle).grid(row=1, column=0, sticky="w", padx=(0, 22))
        ttk.Label(interval, text="Início", style="SurfaceMuted.TLabel").grid(row=1, column=1, sticky="e", padx=(0, 7))
        self.start_entry = ttk.Entry(interval, textvariable=self.start_var, width=12)
        self.start_entry.grid(row=1, column=2, sticky="w")
        ttk.Label(interval, text="Fim", style="SurfaceMuted.TLabel").grid(row=1, column=3, sticky="e", padx=(18, 7))
        self.end_entry = ttk.Entry(interval, textvariable=self.end_var, width=12)
        self.end_entry.grid(row=1, column=4, sticky="w")
        ttk.Label(interval, text="Formato HH:MM:SS", style="SurfaceMuted.TLabel").grid(row=2, column=1, columnspan=4, sticky="w", pady=(7, 0))
        self.start_var.trace_add("write", lambda *_args: self.update_output_preview())
        self.end_var.trace_add("write", lambda *_args: self.update_output_preview())

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self.update_output_preview())
        video_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=18)
        transcription_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=18)
        self.notebook.add(video_tab, text="Cortar e dividir")
        self.notebook.add(transcription_tab, text="Transcrever")
        for tab in (video_tab, transcription_tab):
            for column in range(3):
                tab.columnconfigure(column, weight=1)

        ttk.Label(video_tab, text="Resultado", style="SurfaceMuted.TLabel").grid(row=0, column=0, sticky="w")
        parts_combo = ttk.Combobox(video_tab, textvariable=self.parts_var, state="readonly", values=list(PART_LABELS.values()))
        parts_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))
        parts_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_output_preview())
        ttk.Label(video_tab, text="Qualidade", style="SurfaceMuted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Combobox(video_tab, textvariable=self.quality_var, state="readonly", values=list(QUALITY_LABELS.values())).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 0))
        ttk.Label(video_tab, text="Processamento", style="SurfaceMuted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Combobox(video_tab, textvariable=self.encoder_var, state="readonly", values=list(ENCODER_LABELS.values())).grid(row=1, column=2, sticky="ew", pady=(4, 0))
        self.start_video_button = ttk.Button(video_tab, text="Gerar vídeo", style="Accent.TButton", command=self.start_video_processing)
        self.start_video_button.grid(row=2, column=2, sticky="e", pady=(18, 0))

        ttk.Label(transcription_tab, text="Modelo", style="SurfaceMuted.TLabel").grid(row=0, column=0, sticky="w")
        model_combo = ttk.Combobox(transcription_tab, textvariable=self.transcription_model_var, state="readonly", values=list(TRANSCRIPTION_MODEL_LABELS.values()))
        model_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))
        model_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_model_status())
        ttk.Label(transcription_tab, text="Idioma", style="SurfaceMuted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Combobox(transcription_tab, textvariable=self.transcription_language_var, state="readonly", values=list(TRANSCRIPTION_LANGUAGE_LABELS.values())).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.download_model_button = ttk.Button(transcription_tab, text="Baixar modelo", command=self.start_model_download)
        self.download_model_button.grid(row=1, column=2, sticky="ew", pady=(4, 0))
        ttk.Label(transcription_tab, textvariable=self.model_status_var, style="SurfaceMuted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.start_transcription_button = ttk.Button(transcription_tab, text="Transcrever trecho", style="Accent.TButton", command=self.start_transcription_processing)
        self.start_transcription_button.grid(row=2, column=2, sticky="e", pady=(12, 0))

        work = ttk.Frame(main)
        work.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        work.columnconfigure(0, weight=1)
        work.rowconfigure(3, weight=1)
        ttk.Label(work, textvariable=self.output_preview_var, style="Muted.TLabel", wraplength=900).grid(row=0, column=0, sticky="w")
        status_row = ttk.Frame(work)
        status_row.grid(row=1, column=0, sticky="ew", pady=(13, 6))
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.log_toggle_button = ttk.Button(status_row, text="Ver detalhes", command=self.toggle_log)
        self.log_toggle_button.grid(row=0, column=1, sticky="e")
        self.progress_bar = ttk.Progressbar(work, variable=self.progress_var, maximum=100, mode="determinate", style="Rustic.Horizontal.TProgressbar")
        self.progress_bar.grid(row=2, column=0, sticky="ew")
        ttk.Label(work, textvariable=self.details_var, style="Muted.TLabel", wraplength=900).grid(row=3, column=0, sticky="nw", pady=(6, 0))
        self.log_frame = ttk.Frame(work, style="Surface.TFrame", padding=10)
        self.log_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_box = scrolledtext.ScrolledText(self.log_frame, height=7, wrap="word", state="disabled", font=("Cascadia Mono", 9), background=COLORS["surface"], foreground=COLORS["muted"], insertbackground=COLORS["text"], selectbackground=COLORS["moss"], relief="flat", borderwidth=0)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_frame.grid_remove()

    def choose_input(self) -> None:
        selected = filedialog.askopenfilename(title="Escolha um vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.avi *.m4v *.webm"), ("Todos os arquivos", "*.*")])
        if selected:
            self.input_var.set(selected)
            self.load_video_metadata(show_errors=True)

    def load_video_metadata(self, show_errors: bool) -> bool:
        input_text = self.input_var.get().strip()
        if not input_text:
            return False
        input_path = Path(input_text)
        if not input_path.exists():
            if show_errors:
                messagebox.showerror("Arquivo não encontrado", "O vídeo escolhido não existe.")
            return False
        try:
            data = ffprobe_video(input_path)
            self.video_duration = float(data["format"]["duration"])
            size = int(data["format"].get("size", input_path.stat().st_size))
        except Exception as error:  # noqa: BLE001
            if show_errors:
                messagebox.showerror("Vídeo inválido", str(error))
            return False
        self.video_info_var.set(f"{format_clock(self.video_duration)}  |  {format_size(size)}")
        self.end_var.set(format_clock(self.video_duration))
        self.update_output_preview()
        return True

    def on_range_toggle(self) -> None:
        state = "normal" if self.use_range_var.get() else "disabled"
        self.start_entry.configure(state=state)
        self.end_entry.configure(state=state)
        self.update_output_preview()

    def selected_range(self) -> tuple[float, float | None]:
        if not self.use_range_var.get():
            return 0.0, None
        start = parse_time_value(self.start_var.get())
        end = parse_time_value(self.end_var.get())
        if self.video_duration > 0:
            start, end = resolve_time_range(self.video_duration, start, end)
        elif end <= start:
            raise ValueError("O fim do trecho precisa ser maior que o início.")
        return start, end

    def validate_video(self) -> tuple[Path, Path, float, float | None] | None:
        if not self.load_video_metadata(show_errors=True):
            if not self.input_var.get().strip():
                messagebox.showwarning("Vídeo faltando", "Escolha um vídeo para continuar.")
            return None
        try:
            start, end = self.selected_range()
        except (ValueError, RuntimeError) as error:
            messagebox.showwarning("Intervalo inválido", str(error))
            return None
        output_root = Path(self.output_root_var.get().strip() or default_output_root())
        output_root.mkdir(parents=True, exist_ok=True)
        return Path(self.input_var.get().strip()), output_root, start, end

    def update_output_preview(self) -> None:
        input_text = self.input_var.get().strip()
        if not input_text:
            self.output_preview_var.set("A pasta final aparecerá aqui.")
            return
        output_root = Path(self.output_root_var.get().strip() or default_output_root(Path.cwd()))
        input_path = Path(input_text)
        suffix = ""
        if self.use_range_var.get():
            try:
                start = parse_time_value(self.start_var.get())
                end = parse_time_value(self.end_var.get())
                suffix = f"_{format_path_time(start)}_a_{format_path_time(end)}"
            except ValueError:
                suffix = "_intervalo"
        if hasattr(self, "notebook") and self.notebook.index("current") == 1:
            folder = f"transcricao{suffix}"
        else:
            parts = self.get_key_from_label(PART_LABELS, self.parts_var.get())
            folder = ("recorte" if parts == "1" else f"{parts}_partes") + suffix
        self.output_preview_var.set(f"Saída: {output_root / input_path.stem / folder}")

    def start_video_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        validated = self.validate_video()
        if validated is None:
            return
        input_path, output_root, start, end = validated
        options = ProcessingOptions(input_path=input_path, output_root=output_root, parts=int(self.get_key_from_label(PART_LABELS, self.parts_var.get())), encoder=self.get_key_from_label(ENCODER_LABELS, self.encoder_var.get()), mode="auto", quality_profile=self.get_key_from_label(QUALITY_LABELS, self.quality_var.get()), start_seconds=start, end_seconds=end)
        self.begin_work("Preparando o vídeo...", "Lendo o intervalo e escolhendo o encoder.")
        self.worker = threading.Thread(target=self.run_video_processing, args=(options,), daemon=True)
        self.worker.start()

    def start_transcription_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        validated = self.validate_video()
        if validated is None:
            return
        input_path, output_root, start, end = validated
        options = TranscriptionOptions(input_path=input_path, output_root=output_root, model_profile=self.get_key_from_label(TRANSCRIPTION_MODEL_LABELS, self.transcription_model_var.get()), language=self.get_key_from_label(TRANSCRIPTION_LANGUAGE_LABELS, self.transcription_language_var.get()), start_seconds=start, end_seconds=end)
        self.begin_work("Preparando a transcrição...", "Verificando modelo e analisando o áudio.")
        self.worker = threading.Thread(target=self.run_transcription_processing, args=(options,), daemon=True)
        self.worker.start()

    def start_model_download(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        profile_key = self.get_key_from_label(TRANSCRIPTION_MODEL_LABELS, self.transcription_model_var.get())
        self.begin_work("Preparando o modelo...", "O download acontece somente na primeira vez.")
        self.worker = threading.Thread(target=self.run_model_download, args=(profile_key,), daemon=True)
        self.worker.start()

    def begin_work(self, status: str, details: str) -> None:
        self.progress_var.set(0.0)
        self.status_var.set(status)
        self.details_var.set(details)
        self.set_progress_indeterminate()
        self.set_buttons_state("disabled")
        self.clear_log()

    def set_buttons_state(self, state: str) -> None:
        self.start_video_button.configure(state=state)
        self.start_transcription_button.configure(state=state)
        self.download_model_button.configure(state=state)

    def run_video_processing(self, options: ProcessingOptions) -> None:
        try:
            result = process_video(options, progress_callback=lambda payload: self.events.put(("progress", payload)), log_callback=lambda message: self.events.put(("log", message)))
            self.events.put(("done", result))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", str(error)))

    def run_transcription_processing(self, options: TranscriptionOptions) -> None:
        try:
            result = process_transcription(options, progress_callback=lambda payload: self.events.put(("progress", payload)), log_callback=lambda message: self.events.put(("log", message)))
            self.events.put(("done", result))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", str(error)))

    def run_model_download(self, profile_key: str) -> None:
        try:
            prepared = prepare_transcription_model(profile_key, progress_callback=lambda payload: self.events.put(("progress", payload)), log_callback=lambda message: self.events.put(("log", message)))
            self.events.put(("model_ready", prepared))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", str(error)))

    def poll_events(self) -> None:
        try:
            while True:
                event_type, payload = self.events.get_nowait()
                if event_type == "log":
                    self.append_log(str(payload))
                elif event_type == "progress":
                    self.handle_progress(payload)
                elif event_type == "done":
                    self.handle_done(payload)
                elif event_type == "model_ready":
                    self.handle_model_ready(payload)
                elif event_type == "error":
                    self.handle_error(str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self.poll_events)

    def handle_progress(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if bool(data.get("indeterminate")):
            self.set_progress_indeterminate()
            self.status_var.set(str(data.get("label", "Processando...")))
            self.details_var.set(str(data.get("details_text") or data.get("speed", "Aguarde...")))
            return
        self.set_progress_determinate()
        percent = float(data.get("percent", 0.0))
        self.progress_var.set(percent)
        self.status_var.set(str(data.get("label", "Processando...")))
        details_text = str(data.get("details_text", "")).strip()
        self.details_var.set(details_text or f"{percent:5.1f}%  |  decorrido {format_clock(float(data.get('elapsed_seconds', 0.0)))}  |  restante {format_clock(float(data.get('remaining_seconds', 0.0)))}  |  {data.get('speed', '?')}")

    def handle_done(self, result: object) -> None:
        self.set_buttons_state("normal")
        self.set_progress_determinate()
        self.progress_var.set(100.0)
        output_dir = getattr(result, "output_dir", None)
        self.status_var.set("Concluído")
        self.details_var.set(f"Arquivos prontos em {output_dir}")
        self.append_log(f"Finalizado. Pasta de saída: {output_dir}")
        if output_dir is not None and self.open_folder_var.get():
            os.startfile(output_dir)  # type: ignore[attr-defined]
        self.refresh_model_status()

    def handle_error(self, message: str) -> None:
        self.set_buttons_state("normal")
        self.set_progress_determinate()
        self.status_var.set("Não foi possível concluir")
        self.details_var.set(message)
        self.append_log(f"Erro: {message}")
        messagebox.showerror("Erro", message)
        self.refresh_model_status()

    def handle_model_ready(self, payload: object) -> None:
        self.set_buttons_state("normal")
        self.set_progress_determinate()
        self.progress_var.set(100.0)
        data = payload if isinstance(payload, dict) else {}
        model_id = str(data.get("model_id", "modelo"))
        self.status_var.set("Modelo pronto")
        self.details_var.set(f"O modelo {model_id} está disponível para transcrição.")
        self.refresh_model_status()

    def refresh_model_status(self) -> None:
        profile_key = self.get_key_from_label(TRANSCRIPTION_MODEL_LABELS, self.transcription_model_var.get())
        model_id = TRANSCRIPTION_MODELS[profile_key]["model_id"]
        if is_model_downloaded(model_id):
            self.model_status_var.set(f"Modelo {model_id} pronto para uso")
        else:
            self.model_status_var.set(f"Modelo {model_id} será baixado na primeira utilização")

    def append_log(self, message: str) -> None:
        self.log_messages.append(message)
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_messages.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def toggle_log(self) -> None:
        if self.log_frame.winfo_ismapped():
            self.log_frame.grid_remove()
            self.log_toggle_button.configure(text="Ver detalhes")
        else:
            self.log_frame.grid()
            self.log_toggle_button.configure(text="Ocultar detalhes")

    @staticmethod
    def get_key_from_label(mapping: dict[str, str], selected_label: str) -> str:
        for key, label in mapping.items():
            if label == selected_label:
                return key
        return next(iter(mapping))

    def set_progress_indeterminate(self) -> None:
        if self.progress_mode == "indeterminate":
            return
        self.progress_mode = "indeterminate"
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(12)

    def set_progress_determinate(self) -> None:
        if self.progress_mode == "determinate":
            return
        self.progress_mode = "determinate"
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")


def main() -> None:
    args = parse_args()
    if args.self_test:
        ensure_basic_tools()
        get_ctranslate2()
        get_faster_whisper_model_class()
        print("GUI_OK")
        return
    if args.runtime_test:
        process_transcription(
            TranscriptionOptions(
                input_path=args.runtime_test,
                output_root=default_output_root() / "_teste_executavel",
                model_profile="equilibrada",
                language="pt",
                start_seconds=2.0,
                end_seconds=7.0,
            )
        )
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
        (base_dir / "SeparadorVideo_erro.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
