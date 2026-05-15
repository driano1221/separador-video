import argparse
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from app.video_splitter_core import (
    QUALITY_PROFILES,
    ProcessingOptions,
    default_output_root,
    format_clock,
    process_video,
)
from app.transcription_core import (
    TRANSCRIPTION_LANGUAGES,
    TRANSCRIPTION_MODELS,
    TranscriptionOptions,
    is_model_downloaded,
    prepare_transcription_model,
    process_transcription,
)


ENCODER_LABELS = {
    "auto": "Automatico (recomendado)",
    "h264_nvenc": "NVIDIA NVENC",
    "h264_mf": "Media Foundation",
    "libx264": "Software (x264)",
}
MODE_LABELS = {
    "auto": "Automatico",
    "onepass": "Mais rapido e preciso",
    "sequential": "Compatibilidade maxima",
}
QUALITY_LABELS = {
    "alta": "Alta qualidade",
    "equilibrada": "Equilibrada (recomendada)",
    "leve": "Mais leve",
}
TRANSCRIPTION_MODEL_LABELS = {
    key: value["label"] for key, value in TRANSCRIPTION_MODELS.items()
}
TRANSCRIPTION_LANGUAGE_LABELS = {
    key: value["label"] for key, value in TRANSCRIPTION_LANGUAGES.items()
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Separador e Transcritor de Video")
        self.root.geometry("1320x1040")
        self.root.minsize(1160, 940)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.log_window: tk.Toplevel | None = None
        self.detached_log_box: scrolledtext.ScrolledText | None = None
        self.log_messages: list[str] = []

        self.input_var = tk.StringVar()
        self.output_root_var = tk.StringVar(value=str(default_output_root()))
        self.parts_var = tk.StringVar(value="3")
        self.quality_var = tk.StringVar(value=QUALITY_LABELS["equilibrada"])
        self.encoder_var = tk.StringVar(value=ENCODER_LABELS["auto"])
        self.mode_var = tk.StringVar(value=MODE_LABELS["auto"])
        self.transcription_model_var = tk.StringVar(value=TRANSCRIPTION_MODEL_LABELS["equilibrada"])
        self.transcription_language_var = tk.StringVar(value=TRANSCRIPTION_LANGUAGE_LABELS["pt"])
        self.open_folder_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Escolha um video para comecar.")
        self.details_var = tk.StringVar(value="Nada em processamento no momento.")
        self.split_output_preview_var = tk.StringVar(value="A pasta final aparecera aqui.")
        self.transcription_output_preview_var = tk.StringVar(value="A pasta de transcricao aparecera aqui.")
        self.model_status_var = tk.StringVar(value="Status do modelo: ainda nao verificado.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_mode = "determinate"

        self.build_ui()
        self.update_output_preview()
        self.root.after(150, self.poll_events)

    def build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        title = ttk.Label(main, text="Separador, Compressor e Transcritor de Video", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            main,
            text="Escolha o video e use corte/compressao ou transcricao. As saidas ficam organizadas em /saidas.",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 16))

        paned = ttk.Panedwindow(main, orient=tk.VERTICAL)
        paned.grid(row=2, column=0, sticky="nsew")

        top_content = ttk.Frame(paned, padding=0)
        top_content.columnconfigure(0, weight=1)
        top_content.rowconfigure(4, weight=0)
        paned.add(top_content, weight=4)

        source_frame = ttk.LabelFrame(top_content, text="Entrada e destino", padding=12)
        source_frame.grid(row=0, column=0, sticky="ew")
        source_frame.columnconfigure(1, weight=1)

        ttk.Label(source_frame, text="Video").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(source_frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(source_frame, text="Escolher...", command=self.choose_input).grid(row=0, column=2, pady=4)

        ttk.Label(source_frame, text="Saidas").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(source_frame, textvariable=self.output_root_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(source_frame, text="Escolher...", command=self.choose_output_root).grid(row=1, column=2, pady=4)

        ttk.Label(source_frame, text="Saida video").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=(8, 4))
        ttk.Label(source_frame, textvariable=self.split_output_preview_var, wraplength=640).grid(
            row=2, column=1, columnspan=2, sticky="w", pady=(8, 4)
        )
        ttk.Label(source_frame, text="Saida texto").grid(row=3, column=0, sticky="nw", padx=(0, 8), pady=(4, 4))
        ttk.Label(source_frame, textvariable=self.transcription_output_preview_var, wraplength=640).grid(
            row=3, column=1, columnspan=2, sticky="w", pady=(4, 4)
        )

        config_frame = ttk.LabelFrame(top_content, text="Configuracoes", padding=12)
        config_frame.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        for col in range(4):
            config_frame.columnconfigure(col, weight=1)

        ttk.Label(config_frame, text="Partes").grid(row=0, column=0, sticky="w")
        parts_combo = ttk.Combobox(config_frame, textvariable=self.parts_var, state="readonly", values=["2", "3", "4"])
        parts_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 8))
        parts_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_output_preview())

        ttk.Label(config_frame, text="Qualidade").grid(row=0, column=1, sticky="w")
        quality_combo = ttk.Combobox(
            config_frame,
            textvariable=self.quality_var,
            state="readonly",
            values=list(QUALITY_LABELS.values()),
        )
        quality_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(4, 8))

        ttk.Label(config_frame, text="Encoder").grid(row=0, column=2, sticky="w")
        encoder_combo = ttk.Combobox(
            config_frame,
            textvariable=self.encoder_var,
            state="readonly",
            values=list(ENCODER_LABELS.values()),
        )
        encoder_combo.grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(4, 8))

        ttk.Label(config_frame, text="Modo").grid(row=0, column=3, sticky="w")
        mode_combo = ttk.Combobox(
            config_frame,
            textvariable=self.mode_var,
            state="readonly",
            values=list(MODE_LABELS.values()),
        )
        mode_combo.grid(row=1, column=3, sticky="ew", pady=(4, 8))

        hints = ttk.Label(
            config_frame,
            text=(
                "Perfis: alta = melhor imagem, equilibrada = recomendado, "
                "leve = arquivo menor."
            ),
        )
        hints.grid(row=2, column=0, columnspan=4, sticky="w")

        transcription_frame = ttk.LabelFrame(top_content, text="Transcricao", padding=12)
        transcription_frame.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        for col in range(2):
            transcription_frame.columnconfigure(col, weight=1)

        ttk.Label(transcription_frame, text="Perfil").grid(row=0, column=0, sticky="w")
        model_combo = ttk.Combobox(
            transcription_frame,
            textvariable=self.transcription_model_var,
            state="readonly",
            values=list(TRANSCRIPTION_MODEL_LABELS.values()),
        )
        model_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 8))
        model_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_model_status())

        ttk.Label(transcription_frame, text="Idioma").grid(row=0, column=1, sticky="w")
        language_combo = ttk.Combobox(
            transcription_frame,
            textvariable=self.transcription_language_var,
            state="readonly",
            values=list(TRANSCRIPTION_LANGUAGE_LABELS.values()),
        )
        language_combo.grid(row=1, column=1, sticky="ew", pady=(4, 8))

        transcription_hint = ttk.Label(
            transcription_frame,
            text=(
                "Gera arquivos TXT, SRT, VTT e JSON. "
                "Equilibrada costuma ser a melhor opcao para reunioes longas."
            ),
        )
        transcription_hint.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(transcription_frame, textvariable=self.model_status_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        actions = ttk.Frame(top_content)
        actions.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        actions.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            actions,
            text="Abrir pasta final quando terminar",
            variable=self.open_folder_var,
        ).grid(row=0, column=0, sticky="w")

        buttons = ttk.Frame(actions)
        buttons.grid(row=0, column=1, sticky="e")
        self.expand_log_button = ttk.Button(buttons, text="Abrir log grande", command=self.open_log_window)
        self.expand_log_button.grid(row=0, column=0, padx=(0, 8))
        self.download_model_button = ttk.Button(buttons, text="Baixar modelo", command=self.start_model_download)
        self.download_model_button.grid(row=0, column=1, padx=(0, 8))
        self.start_video_button = ttk.Button(buttons, text="Processar video", command=self.start_video_processing)
        self.start_video_button.grid(row=0, column=2, padx=(0, 8))
        self.start_transcription_button = ttk.Button(buttons, text="Transcrever video", command=self.start_transcription_processing)
        self.start_transcription_button.grid(row=0, column=3)

        progress_frame = ttk.LabelFrame(top_content, text="Progresso", padding=12)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        progress_frame.columnconfigure(0, weight=1)

        ttk.Label(progress_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        ttk.Label(progress_frame, textvariable=self.details_var).grid(row=2, column=0, sticky="w")

        log_frame = ttk.LabelFrame(paned, text="Andamento", padding=12)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        paned.add(log_frame, weight=3)

        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            height=18,
            wrap="word",
            state="disabled",
            font=("Consolas", 11),
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.refresh_model_status()

    def choose_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Escolha um video",
            filetypes=[
                ("Videos", "*.mp4 *.mov *.mkv *.avi *.m4v *.webm"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if selected:
            self.input_var.set(selected)
            self.update_output_preview()

    def choose_output_root(self) -> None:
        selected = filedialog.askdirectory(title="Escolha a pasta base das saidas")
        if selected:
            self.output_root_var.set(selected)
            self.update_output_preview()

    def update_output_preview(self) -> None:
        input_text = self.input_var.get().strip()
        output_root = Path(self.output_root_var.get().strip() or default_output_root(Path.cwd()))
        if input_text:
            input_path = Path(input_text)
            split_preview = output_root / input_path.stem / f"{self.parts_var.get()}_partes"
            transcription_preview = output_root / input_path.stem / "transcricao"
            self.split_output_preview_var.set(str(split_preview))
            self.transcription_output_preview_var.set(str(transcription_preview))
        else:
            self.split_output_preview_var.set(str(output_root / "<nome-do-video>" / f"{self.parts_var.get()}_partes"))
            self.transcription_output_preview_var.set(str(output_root / "<nome-do-video>" / "transcricao"))

    def append_log(self, message: str) -> None:
        self.log_messages.append(message)
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        if self.detached_log_box is not None and self.detached_log_box.winfo_exists():
            self.detached_log_box.configure(state="normal")
            self.detached_log_box.insert("end", message + "\n")
            self.detached_log_box.see("end")
            self.detached_log_box.configure(state="disabled")

    def refresh_model_status(self) -> None:
        profile_key = self.get_key_from_label(TRANSCRIPTION_MODEL_LABELS, self.transcription_model_var.get())
        model_id = TRANSCRIPTION_MODELS[profile_key]["model_id"]
        if is_model_downloaded(model_id):
            self.model_status_var.set(f"Status do modelo: '{model_id}' ja baixado.")
        else:
            self.model_status_var.set(
                f"Status do modelo: '{model_id}' sera baixado na primeira vez. "
                "Se o Hugging Face falhar, o app usa OpenAI Whisper automaticamente."
            )

    def start_video_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        input_text = self.input_var.get().strip()
        if not input_text:
            messagebox.showwarning("Video faltando", "Escolha um video antes de processar.")
            return

        input_path = Path(input_text)
        if not input_path.exists():
            messagebox.showerror("Arquivo nao encontrado", "O video escolhido nao existe mais.")
            return

        output_root = Path(self.output_root_var.get().strip() or default_output_root())
        output_root.mkdir(parents=True, exist_ok=True)

        self.progress_var.set(0.0)
        self.status_var.set("Preparando processamento...")
        self.details_var.set("Lendo metadados e preparando encoder...")
        self.set_progress_indeterminate()
        self.start_video_button.configure(state="disabled")
        self.start_transcription_button.configure(state="disabled")
        self.download_model_button.configure(state="disabled")
        self.clear_log()

        options = ProcessingOptions(
            input_path=input_path,
            output_root=output_root,
            parts=int(self.parts_var.get()),
            encoder=self.get_key_from_label(ENCODER_LABELS, self.encoder_var.get()),
            mode=self.get_key_from_label(MODE_LABELS, self.mode_var.get()),
            quality_profile=self.get_key_from_label(QUALITY_LABELS, self.quality_var.get()),
        )

        self.worker = threading.Thread(target=self.run_video_processing, args=(options,), daemon=True)
        self.worker.start()

    def start_transcription_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        input_text = self.input_var.get().strip()
        if not input_text:
            messagebox.showwarning("Video faltando", "Escolha um video antes de transcrever.")
            return

        input_path = Path(input_text)
        if not input_path.exists():
            messagebox.showerror("Arquivo nao encontrado", "O video escolhido nao existe mais.")
            return

        output_root = Path(self.output_root_var.get().strip() or default_output_root())
        output_root.mkdir(parents=True, exist_ok=True)

        self.progress_var.set(0.0)
        self.status_var.set("Preparando transcricao...")
        self.details_var.set("Verificando modelo, carregando runtime e preparando o video...")
        self.set_progress_indeterminate()
        self.start_video_button.configure(state="disabled")
        self.start_transcription_button.configure(state="disabled")
        self.download_model_button.configure(state="disabled")
        self.clear_log()

        options = TranscriptionOptions(
            input_path=input_path,
            output_root=output_root,
            model_profile=self.get_key_from_label(TRANSCRIPTION_MODEL_LABELS, self.transcription_model_var.get()),
            language=self.get_key_from_label(TRANSCRIPTION_LANGUAGE_LABELS, self.transcription_language_var.get()),
        )

        self.worker = threading.Thread(target=self.run_transcription_processing, args=(options,), daemon=True)
        self.worker.start()

    def start_model_download(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        self.progress_var.set(0.0)
        self.status_var.set("Preparando download do modelo...")
        self.details_var.set("Baixando e armazenando o modelo para uso futuro...")
        self.set_progress_indeterminate()
        self.start_video_button.configure(state="disabled")
        self.start_transcription_button.configure(state="disabled")
        self.download_model_button.configure(state="disabled")
        self.clear_log()

        profile_key = self.get_key_from_label(TRANSCRIPTION_MODEL_LABELS, self.transcription_model_var.get())
        self.worker = threading.Thread(target=self.run_model_download, args=(profile_key,), daemon=True)
        self.worker.start()

    def clear_log(self) -> None:
        self.log_messages.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        if self.detached_log_box is not None and self.detached_log_box.winfo_exists():
            self.detached_log_box.configure(state="normal")
            self.detached_log_box.delete("1.0", "end")
            self.detached_log_box.configure(state="disabled")

    def run_video_processing(self, options: ProcessingOptions) -> None:
        try:
            result = process_video(
                options,
                progress_callback=lambda payload: self.events.put(("progress", payload)),
                log_callback=lambda message: self.events.put(("log", message)),
            )
            self.events.put(("done", result))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", str(error)))

    def run_transcription_processing(self, options: TranscriptionOptions) -> None:
        try:
            result = process_transcription(
                options,
                progress_callback=lambda payload: self.events.put(("progress", payload)),
                log_callback=lambda message: self.events.put(("log", message)),
            )
            self.events.put(("done", result))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", str(error)))

    def run_model_download(self, profile_key: str) -> None:
        try:
            prepared = prepare_transcription_model(
                profile_key,
                progress_callback=lambda payload: self.events.put(("progress", payload)),
                log_callback=lambda message: self.events.put(("log", message)),
            )
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
            details_text = str(data.get("details_text", "")).strip()
            self.details_var.set(details_text or str(data.get("speed", "Aguarde...")))
            return

        self.set_progress_determinate()
        percent = float(data.get("percent", 0.0))
        self.progress_var.set(percent)
        self.status_var.set(str(data.get("label", "Processando...")))
        details_text = str(data.get("details_text", "")).strip()
        if details_text:
            self.details_var.set(details_text)
            return
        self.details_var.set(
            f"{percent:5.1f}% | decorrido {format_clock(float(data.get('elapsed_seconds', 0.0)))} | "
            f"restante {format_clock(float(data.get('remaining_seconds', 0.0)))} | "
            f"velocidade {data.get('speed', '?')}"
        )

    def handle_done(self, result: object) -> None:
        self.start_video_button.configure(state="normal")
        self.start_transcription_button.configure(state="normal")
        self.download_model_button.configure(state="normal")
        self.set_progress_determinate()
        self.progress_var.set(100.0)
        output_dir = getattr(result, "output_dir", None)
        generated_size = getattr(result, "generated_size", 0)
        original_size = getattr(result, "original_size", 0)
        self.status_var.set("Processamento concluido.")
        reduction_text = ""
        if generated_size and original_size:
            reduction = ((original_size - generated_size) / original_size) * 100
            reduction_text = f" | reducao aproximada {reduction:.2f}%"
        self.details_var.set(f"Arquivos prontos em {output_dir}{reduction_text}")
        self.append_log(f"Finalizado. Pasta de saida: {output_dir}")
        if output_dir is not None and self.open_folder_var.get():
            os.startfile(output_dir)  # type: ignore[attr-defined]
        self.refresh_model_status()

    def handle_error(self, message: str) -> None:
        self.start_video_button.configure(state="normal")
        self.start_transcription_button.configure(state="normal")
        self.download_model_button.configure(state="normal")
        self.set_progress_determinate()
        self.status_var.set("Falha no processamento.")
        self.details_var.set(message)
        self.append_log(f"Erro: {message}")
        messagebox.showerror("Erro", message)
        self.refresh_model_status()

    def handle_model_ready(self, payload: object) -> None:
        self.start_video_button.configure(state="normal")
        self.start_transcription_button.configure(state="normal")
        self.download_model_button.configure(state="normal")
        self.set_progress_determinate()
        self.progress_var.set(100.0)
        data = payload if isinstance(payload, dict) else {}
        model_id = str(data.get("model_id", "modelo"))
        backend = str(data.get("backend", "transcricao"))
        self.status_var.set("Modelo pronto.")
        self.details_var.set(f"Modelo '{model_id}' pronto para transcricoes via {backend}.")
        self.append_log(f"Modelo '{model_id}' pronto para uso via {backend}.")
        self.refresh_model_status()

    def open_log_window(self) -> None:
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus_force()
            return

        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("Log ampliado")
        self.log_window.geometry("1200x700")
        self.log_window.minsize(900, 500)
        self.log_window.columnconfigure(0, weight=1)
        self.log_window.rowconfigure(0, weight=1)
        self.log_window.protocol("WM_DELETE_WINDOW", self.close_log_window)

        self.detached_log_box = scrolledtext.ScrolledText(
            self.log_window,
            wrap="word",
            state="disabled",
            font=("Consolas", 11),
        )
        self.detached_log_box.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.detached_log_box.configure(state="normal")
        self.detached_log_box.insert("1.0", "\n".join(self.log_messages))
        if self.log_messages:
            self.detached_log_box.insert("end", "\n")
        self.detached_log_box.configure(state="disabled")
        self.detached_log_box.see("end")

    def close_log_window(self) -> None:
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.destroy()
        self.log_window = None
        self.detached_log_box = None

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
        self.progress_bar.start(10)

    def set_progress_determinate(self) -> None:
        if self.progress_mode == "determinate":
            return
        self.progress_mode = "determinate"
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")


def main() -> None:
    args = parse_args()
    if args.self_test:
        print("GUI_OK")
        return

    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
