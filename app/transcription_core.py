import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

import ctranslate2
from huggingface_hub import snapshot_download
from faster_whisper import WhisperModel

from app.video_splitter_core import (
    LogCallback,
    ProgressCallback,
    default_output_root,
    emit_log,
    emit_progress,
    ffprobe_video,
    get_project_root,
)


OPENAI_WHISPER_MODULE = None


def get_openai_whisper():
    global OPENAI_WHISPER_MODULE
    if OPENAI_WHISPER_MODULE is None:
        try:
            import whisper as openai_whisper
        except Exception as error:  # noqa: BLE001
            raise RuntimeError(
                "Backend alternativo OpenAI Whisper indisponivel neste executavel. "
                "Use o Faster-Whisper ou gere o app incluindo torch/openai-whisper."
            ) from error
        OPENAI_WHISPER_MODULE = openai_whisper
    return OPENAI_WHISPER_MODULE


def is_torch_cuda_available() -> bool:
    try:
        import torch
    except Exception:
        return False
    return bool(torch.cuda.is_available())


TRANSCRIPTION_MODELS = {
    "rapida": {
        "label": "Rapida",
        "model_id": "small",
        "description": "Mais leve e boa para testes ou maquinas mais fracas.",
    },
    "equilibrada": {
        "label": "Equilibrada (recomendada)",
        "model_id": "distil-large-v3",
        "description": "Melhor equilibrio entre qualidade e velocidade para reunioes.",
    },
    "maxima": {
        "label": "Maxima qualidade",
        "model_id": "large-v3",
        "description": "Maior qualidade, com custo maior de download e processamento.",
    },
}

TRANSCRIPTION_LANGUAGES = {
    "auto": {"label": "Detectar automaticamente", "code": None},
    "pt": {"label": "Português", "code": "pt"},
    "en": {"label": "English", "code": "en"},
    "es": {"label": "Español", "code": "es"},
}
TRANSCRIPTION_REQUIRED_FILES = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
)
OPENAI_WHISPER_MODELS = {
    "rapida": {
        "model_id": "small",
        "label": "OpenAI Whisper Small",
    },
    "equilibrada": {
        "model_id": "turbo",
        "label": "OpenAI Whisper Turbo",
    },
    "maxima": {
        "model_id": "large-v3",
        "label": "OpenAI Whisper Large v3",
    },
}


@dataclass
class TranscriptionOptions:
    input_path: Path
    output_root: Path
    model_profile: str = "equilibrada"
    language: str = "pt"
    task: str = "transcribe"
    word_timestamps: bool = True
    vad_filter: bool = True


@dataclass
class TranscriptionResult:
    output_dir: Path
    transcript_txt: Path
    transcript_srt: Path
    transcript_vtt: Path
    transcript_json: Path
    language: str
    language_probability: float
    duration: float
    segments_count: int
    model_id: str
    backend: str
    device: str
    compute_type: str


def ensure_transcription_runtime() -> None:
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")


def get_transcription_models_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        root = Path(local_appdata) / "SeparadorVideo" / "modelos" / "faster-whisper"
    else:
        root = get_project_root() / "ferramentas" / "modelos" / "faster-whisper"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_hf_cache_root() -> Path:
    root = get_transcription_models_root() / "_hf_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_openai_transcription_models_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        root = Path(local_appdata) / "SeparadorVideo" / "modelos" / "openai-whisper"
    else:
        root = get_project_root() / "ferramentas" / "modelos" / "openai-whisper"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_local_model_path(model_id: str) -> Path:
    return get_transcription_models_root() / model_id


def resolve_openai_profile(profile_key: str) -> dict[str, str]:
    return OPENAI_WHISPER_MODELS.get(profile_key, OPENAI_WHISPER_MODELS["equilibrada"])


def get_openai_model_path(model_name: str) -> Path:
    openai_whisper = get_openai_whisper()
    url = openai_whisper._MODELS[model_name]
    return get_openai_transcription_models_root() / os.path.basename(url)


def is_model_downloaded(model_id: str) -> bool:
    model_path = get_local_model_path(model_id)
    if not model_path.exists():
        return False
    required_files = ("config.json", "model.bin", "tokenizer.json")
    for filename in required_files:
        file_path = model_path / filename
        if not file_path.exists():
            return False
        try:
            if file_path.stat().st_size <= 0:
                return False
        except OSError:
            return False

    vocabulary_candidates = list(model_path.glob("vocabulary.*"))
    if not vocabulary_candidates:
        return False
    try:
        if all(candidate.stat().st_size <= 0 for candidate in vocabulary_candidates):
            return False
    except OSError:
        return False
    return True


def is_openai_model_downloaded(model_name: str) -> bool:
    model_path = get_openai_model_path(model_name)
    if not model_path.exists():
        return False
    try:
        return model_path.stat().st_size > 1024 * 1024
    except OSError:
        return False


def get_directory_size_bytes(root: Path) -> tuple[int, int]:
    if root.is_file():
        try:
            return root.stat().st_size, 1
        except OSError:
            return 0, 0

    total_bytes = 0
    file_count = 0
    if not root.exists():
        return total_bytes, file_count

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".cache" in path.parts:
            continue
        if path.name.endswith(".metadata") or path.name.endswith(".incomplete"):
            continue
        try:
            total_bytes += path.stat().st_size
            file_count += 1
        except OSError:
            continue
    return total_bytes, file_count


def format_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def monitor_model_download(
    model_path: Path,
    stop_event: threading.Event,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> None:
    last_log_time = 0.0
    last_size = -1

    while not stop_event.wait(2.0):
        size_bytes, file_count = get_directory_size_bytes(model_path)
        changed = size_bytes != last_size
        now = time.time()
        details_text = (
            f"Baixado ate agora: {format_size(size_bytes)} em {file_count} arquivo(s)."
        )

        emit_progress(
            progress_callback,
            {
                "percent": 0.0,
                "elapsed_seconds": 0.0,
                "remaining_seconds": 0.0,
                "speed": "baixando...",
                "label": f"Baixando modelo '{model_path.name}'...",
                "indeterminate": True,
                "details_text": details_text,
            },
        )

        if changed or now - last_log_time >= 10.0:
            emit_log(log_callback, details_text)
            last_log_time = now
            last_size = size_bytes


def ensure_transcription_model(
    model_profile: str,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> Path:
    ensure_transcription_runtime()
    profile = resolve_transcription_profile(model_profile)
    model_id = profile["model_id"]
    model_path = get_local_model_path(model_id)
    if is_model_downloaded(model_id):
        emit_log(log_callback, f"Modelo '{model_id}' ja esta baixado.")
        emit_log(log_callback, f"Pasta do modelo: {model_path}")
        return model_path

    emit_log(log_callback, f"Baixando modelo '{model_id}'. Isso pode levar varios minutos na primeira vez.")
    emit_log(log_callback, f"Pasta do modelo: {model_path}")
    if model_path.exists():
        emit_log(log_callback, "Cache parcial encontrado. Limpando arquivos incompletos antes de tentar novamente.")
        shutil.rmtree(model_path, ignore_errors=True)
    model_path.mkdir(parents=True, exist_ok=True)
    emit_progress(
        progress_callback,
        {
            "percent": 0.0,
            "elapsed_seconds": 0.0,
            "remaining_seconds": 0.0,
            "speed": "baixando...",
            "label": f"Baixando modelo '{model_id}'...",
            "indeterminate": True,
            "details_text": "Preparando download e verificando arquivos do modelo...",
        },
    )
    stop_event = threading.Event()
    monitor = threading.Thread(
        target=monitor_model_download,
        args=(model_path, stop_event, progress_callback, log_callback),
        daemon=True,
    )
    monitor.start()
    try:
        snapshot_download(
            repo_id=f"Systran/faster-whisper-{model_id}",
            local_dir=str(model_path),
            cache_dir=str(get_hf_cache_root()),
            local_files_only=False,
            allow_patterns=list(TRANSCRIPTION_REQUIRED_FILES),
            etag_timeout=60,
            max_workers=1,
        )
    except Exception as error:  # noqa: BLE001
        stop_event.set()
        monitor.join(timeout=3.0)
        error_text = str(error)
        if "429" in error_text:
            reason = "O servidor limitou temporariamente as requisicoes."
        elif "ReadTimeout" in error_text or "timed out" in error_text.lower():
            reason = "A conexao com o servidor expirou antes de responder."
        else:
            reason = "A conexao com o Hugging Face ficou lenta, limitada ou bloqueada."
        raise RuntimeError(
            "Falha ao baixar o modelo de transcricao. "
            f"{reason} Tente novamente em alguns minutos."
        ) from error
    finally:
        stop_event.set()
        monitor.join(timeout=3.0)

    if not is_model_downloaded(model_id):
        raise RuntimeError(
            "O download terminou, mas o modelo ficou incompleto. "
            "Tente novamente para baixar uma copia limpa."
        )

    emit_log(log_callback, f"Modelo '{model_id}' pronto para uso.")
    return model_path


def ensure_openai_transcription_model(
    model_profile: str,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> Path:
    profile = resolve_openai_profile(model_profile)
    model_id = profile["model_id"]
    model_path = get_openai_model_path(model_id)
    models_root = get_openai_transcription_models_root()

    if is_openai_model_downloaded(model_id):
        emit_log(log_callback, f"Modelo alternativo '{model_id}' ja esta baixado.")
        emit_log(log_callback, f"Pasta do modelo alternativo: {model_path}")
        return model_path

    emit_log(log_callback, f"Baixando modelo alternativo '{model_id}' pela CDN da OpenAI.")
    emit_log(log_callback, f"Pasta do modelo alternativo: {model_path}")
    emit_progress(
        progress_callback,
        {
            "percent": 0.0,
            "elapsed_seconds": 0.0,
            "remaining_seconds": 0.0,
            "speed": "baixando...",
            "label": f"Baixando modelo alternativo '{model_id}'...",
            "indeterminate": True,
            "details_text": "Usando rota alternativa fora do Hugging Face para baixar o modelo.",
        },
    )

    stop_event = threading.Event()
    monitor = threading.Thread(
        target=monitor_model_download,
        args=(model_path, stop_event, progress_callback, log_callback),
        daemon=True,
    )
    monitor.start()
    try:
        openai_whisper = get_openai_whisper()
        openai_whisper._download(
            openai_whisper._MODELS[model_id],
            str(models_root),
            False,
        )
    except Exception as error:  # noqa: BLE001
        stop_event.set()
        monitor.join(timeout=3.0)
        raise RuntimeError(
            "Falha ao baixar o modelo alternativo da OpenAI. "
            "A rota secundaria tambem falhou."
        ) from error
    finally:
        stop_event.set()
        monitor.join(timeout=3.0)

    if not is_openai_model_downloaded(model_id):
        raise RuntimeError(
            "O download do modelo alternativo terminou, mas o arquivo ficou incompleto."
        )

    emit_log(log_callback, f"Modelo alternativo '{model_id}' pronto para uso.")
    return model_path


def prepare_transcription_model(
    model_profile: str,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, Any]:
    preferred_profile = resolve_transcription_profile(model_profile)
    try:
        model_path = ensure_transcription_model(
            model_profile,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
        return {
            "backend": "faster-whisper",
            "model_id": preferred_profile["model_id"],
            "model_path": model_path,
        }
    except RuntimeError as error:
        emit_log(log_callback, f"Faster-Whisper indisponivel: {error}")
        if is_model_downloaded("small"):
            fallback_path = get_local_model_path("small")
            emit_log(
                log_callback,
                "Usando fallback local offline com o modelo 'small', que ja esta pronto nesta maquina.",
            )
            return {
                "backend": "faster-whisper",
                "model_id": "small",
                "model_path": fallback_path,
                "fallback_from_error": str(error),
            }

        emit_log(log_callback, "Tentando baixar o fallback local 'small'.")
        try:
            fallback_path = ensure_transcription_model(
                "rapida",
                progress_callback=progress_callback,
                log_callback=log_callback,
            )
            return {
                "backend": "faster-whisper",
                "model_id": "small",
                "model_path": fallback_path,
                "fallback_from_error": str(error),
            }
        except RuntimeError as small_error:
            emit_log(log_callback, f"Fallback local 'small' tambem falhou: {small_error}")

        emit_log(log_callback, "Tentando backend alternativo OpenAI Whisper.")
        emit_progress(
            progress_callback,
            {
                "percent": 0.0,
                "elapsed_seconds": 0.0,
                "remaining_seconds": 0.0,
                "speed": "fallback",
                "label": "Mudando para backend alternativo...",
                "indeterminate": True,
                "details_text": "Hugging Face falhou. O app vai usar OpenAI Whisper para continuar.",
            },
        )
        fallback_profile = resolve_openai_profile(model_profile)
        model_path = ensure_openai_transcription_model(
            model_profile,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
        return {
            "backend": "openai-whisper",
            "model_id": fallback_profile["model_id"],
            "model_path": model_path,
            "fallback_from_error": str(error),
        }


def build_transcription_output_dir(output_root: Path, input_path: Path) -> Path:
    output_dir = output_root / input_path.stem / "transcricao"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def resolve_transcription_profile(profile_key: str) -> dict[str, str]:
    return TRANSCRIPTION_MODELS.get(profile_key, TRANSCRIPTION_MODELS["equilibrada"])


def resolve_language(language_key: str) -> str | None:
    return TRANSCRIPTION_LANGUAGES.get(language_key, TRANSCRIPTION_LANGUAGES["pt"])["code"]


def choose_device_and_compute_type() -> tuple[str, str]:
    if ctranslate2.get_cuda_device_count() > 0:
        return "cuda", "float16"
    return "cpu", "int8"


def format_timestamp(seconds: float, always_include_hours: bool = True, decimal_marker: str = ",") -> str:
    milliseconds = int(round(seconds * 1000))
    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000
    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000
    secs = milliseconds // 1000
    milliseconds -= secs * 1000
    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return f"{hours_marker}{minutes:02d}:{secs:02d}{decimal_marker}{milliseconds:03d}"


def write_srt(output_path: Path, segments: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}"
        )
        lines.append(segment["text"].strip())
        lines.append("")
    safe_write_text(output_path, "\n".join(lines).strip() + "\n")


def write_vtt(output_path: Path, segments: list[dict[str, Any]]) -> None:
    lines = ["WEBVTT", ""]
    for segment in segments:
        lines.append(
            f"{format_timestamp(segment['start'], decimal_marker='.')} --> "
            f"{format_timestamp(segment['end'], decimal_marker='.')}"
        )
        lines.append(segment["text"].strip())
        lines.append("")
    safe_write_text(output_path, "\n".join(lines).strip() + "\n")


def make_output_path_writable(output_path: Path) -> None:
    if not output_path.exists():
        return
    try:
        os.chmod(output_path, 0o666)
    except OSError:
        pass


def fallback_output_path(output_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")


def safe_write_text(output_path: Path, content: str) -> Path:
    make_output_path_writable(output_path)
    try:
        output_path.write_text(content, encoding="utf-8")
        return output_path
    except PermissionError:
        alternate_path = fallback_output_path(output_path)
        alternate_path.write_text(content, encoding="utf-8")
        return alternate_path


def serialize_segments(segments: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for segment in segments:
        serialized.append(
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability,
                    }
                    for word in (segment.words or [])
                ],
            }
        )
    return serialized


def serialize_openai_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for segment in segments:
        serialized.append(
            {
                "id": segment.get("id"),
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": str(segment.get("text", "")),
                "words": [
                    {
                        "word": word.get("word", ""),
                        "start": word.get("start"),
                        "end": word.get("end"),
                        "probability": word.get("probability"),
                    }
                    for word in (segment.get("words") or [])
                ],
            }
        )
    return serialized


def process_transcription(
    options: TranscriptionOptions,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> TranscriptionResult:
    ensure_transcription_runtime()

    input_path = options.input_path.resolve()
    if not input_path.exists():
        raise RuntimeError(f"Arquivo nao encontrado: {input_path}")

    output_root = options.output_root.resolve() if options.output_root else default_output_root()
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = build_transcription_output_dir(output_root, input_path)

    requested_profile_key = options.model_profile
    profile = resolve_transcription_profile(requested_profile_key)
    language = resolve_language(options.language)
    prepared = prepare_transcription_model(
        requested_profile_key,
        progress_callback=progress_callback,
        log_callback=log_callback,
    )
    backend = str(prepared["backend"])
    model_id = str(prepared["model_id"])
    model_path = Path(prepared["model_path"])

    if backend == "faster-whisper":
        device, compute_type = choose_device_and_compute_type()
    else:
        device = "cuda" if is_torch_cuda_available() else "cpu"
        compute_type = "fp16" if device == "cuda" else "fp32"

    transcript_txt = output_dir / f"{input_path.stem}_transcricao.txt"
    transcript_srt = output_dir / f"{input_path.stem}_transcricao.srt"
    transcript_vtt = output_dir / f"{input_path.stem}_transcricao.vtt"
    transcript_json = output_dir / f"{input_path.stem}_transcricao.json"

    emit_log(log_callback, f"Video: {input_path.name}")
    emit_log(log_callback, f"Perfil de transcricao: {profile['label']}")
    emit_log(log_callback, f"Backend de transcricao: {backend}")
    requested_model_id = profile["model_id"]
    if backend == "faster-whisper" and model_id != requested_model_id:
        emit_log(
            log_callback,
            f"Fallback ativo: o app trocou do modelo '{requested_model_id}' para o modelo local '{model_id}'.",
        )
    if backend != "faster-whisper":
        emit_log(
            log_callback,
            "Fallback ativo: o app usou OpenAI Whisper porque o download do Faster-Whisper falhou na sua rede.",
        )
    emit_log(log_callback, f"Modelo: {model_id}")
    emit_log(log_callback, f"Pasta local do modelo: {model_path}")
    emit_log(log_callback, f"Idioma: {TRANSCRIPTION_LANGUAGES.get(options.language, TRANSCRIPTION_LANGUAGES['pt'])['label']}")
    emit_log(log_callback, f"Runtime: {device} | {compute_type}")
    emit_log(log_callback, f"Saida: {output_dir}")
    emit_log(log_callback, "Carregando modelo de transcricao na memoria.")
    probe_data = ffprobe_video(input_path)
    total_duration = float(probe_data["format"]["duration"])
    started_at = time.monotonic()

    if backend == "faster-whisper":
        try:
            model = WhisperModel(
                str(model_path),
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )
        except Exception as error:  # noqa: BLE001
            raise RuntimeError(
                "Nao foi possivel carregar o modelo local do Faster-Whisper."
            ) from error

        emit_log(log_callback, "Modelo pronto. Iniciando transcricao.")
        segments_iterable, info = model.transcribe(
            str(input_path),
            language=language,
            task=options.task,
            vad_filter=options.vad_filter,
            word_timestamps=options.word_timestamps,
            beam_size=5,
        )

        serialized_segments: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for raw_segment in segments_iterable:
            segment = serialize_segments([raw_segment])[0]
            serialized_segments.append(segment)
            text_parts.append(segment["text"].strip())
            elapsed_wall = time.monotonic() - started_at
            percent = min((segment["end"] / max(total_duration, 0.001)) * 100, 100.0)
            remaining_audio = max(total_duration - segment["end"], 0.0)
            speed_value = (segment["end"] / elapsed_wall) if elapsed_wall > 0 else 0.0
            eta_seconds = (remaining_audio / speed_value) if speed_value > 0 else 0.0
            emit_progress(
                progress_callback,
                {
                    "label": "Transcricao",
                    "percent": percent,
                    "elapsed_seconds": elapsed_wall,
                    "remaining_seconds": eta_seconds,
                    "speed": f"{speed_value:.2f}x" if speed_value > 0 else "processando",
                    "processed_seconds": segment["end"],
                    "done": False,
                },
            )
    else:
        emit_progress(
            progress_callback,
            {
                "percent": 0.0,
                "elapsed_seconds": 0.0,
                "remaining_seconds": 0.0,
                "speed": "processando",
                "label": "Transcricao (OpenAI Whisper)",
                "indeterminate": True,
                "details_text": "Transcrevendo com backend alternativo. O progresso desta etapa nao e percentual.",
            },
        )
        try:
            openai_whisper = get_openai_whisper()
            model = openai_whisper.load_model(
                model_id,
                device=device,
                download_root=str(get_openai_transcription_models_root()),
            )
            emit_log(log_callback, "Modelo alternativo pronto. Iniciando transcricao.")
            openai_result = model.transcribe(
                str(input_path),
                language=language,
                task=options.task,
                word_timestamps=options.word_timestamps,
                verbose=False,
                fp16=device == "cuda",
            )
        except Exception as error:  # noqa: BLE001
            raise RuntimeError(
                "Nao foi possivel transcrever com o backend alternativo OpenAI Whisper."
            ) from error

        serialized_segments = serialize_openai_segments(openai_result.get("segments", []))
        text_parts = [segment["text"].strip() for segment in serialized_segments]

        class OpenAIInfo:
            language = openai_result.get("language", language or "auto")
            language_probability = 1.0
            duration = total_duration
            duration_after_vad = total_duration

        info = OpenAIInfo()

    if not serialized_segments:
        raise RuntimeError("Nenhum trecho de fala foi encontrado para transcrever.")

    transcript_txt = safe_write_text(transcript_txt, "\n".join(part for part in text_parts if part).strip() + "\n")
    write_srt(transcript_srt, serialized_segments)
    write_vtt(transcript_vtt, serialized_segments)
    transcript_json = safe_write_text(
        transcript_json,
        json.dumps(
            {
                "input_file": str(input_path),
                "model_id": model_id,
                "backend": backend,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "duration_after_vad": info.duration_after_vad,
                "segments": serialized_segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    emit_progress(
        progress_callback,
        {
            "label": "Transcricao",
            "percent": 100.0,
            "elapsed_seconds": time.monotonic() - started_at,
            "remaining_seconds": 0.0,
            "speed": "concluido",
            "processed_seconds": total_duration,
            "done": True,
        },
    )
    emit_log(log_callback, f"Concluido. Segmentos transcritos: {len(serialized_segments)}")
    emit_log(
        log_callback,
        f"Arquivos gerados: {transcript_txt.name}, {transcript_srt.name}, {transcript_vtt.name}, {transcript_json.name}",
    )

    return TranscriptionResult(
        output_dir=output_dir,
        transcript_txt=transcript_txt,
        transcript_srt=transcript_srt,
        transcript_vtt=transcript_vtt,
        transcript_json=transcript_json,
        language=info.language,
        language_probability=info.language_probability,
        duration=info.duration,
        segments_count=len(serialized_segments),
        model_id=model_id,
        backend=backend,
        device=device,
        compute_type=compute_type,
    )
