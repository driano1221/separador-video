import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
SOFTWARE_PRESETS = [
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
]
NVENC_PRESET_MAP = {
    "ultrafast": "p1",
    "superfast": "p2",
    "veryfast": "p3",
    "faster": "p3",
    "fast": "p4",
    "medium": "p5",
    "slow": "p6",
    "slower": "p7",
    "veryslow": "p7",
}


@dataclass(frozen=True)
class QualityProfile:
    key: str
    label: str
    crf: int
    preset: str
    audio_bitrate: str


QUALITY_PROFILES = {
    "alta": QualityProfile("alta", "Alta qualidade", 21, "medium", "160k"),
    "equilibrada": QualityProfile("equilibrada", "Equilibrada", 23, "fast", "128k"),
    "leve": QualityProfile("leve", "Mais leve", 26, "fast", "96k"),
}


@dataclass
class ProcessingOptions:
    input_path: Path
    output_root: Path
    parts: int
    encoder: str = "auto"
    mode: str = "auto"
    quality_profile: str = "equilibrada"
    sample_seconds: float | None = None
    start_seconds: float = 0.0
    end_seconds: float | None = None


@dataclass
class ProcessingResult:
    output_dir: Path
    output_files: list[Path]
    encoder_used: str
    encoder_reason: str
    total_duration: float
    processed_duration: float
    original_size: int
    generated_size: int


ProgressCallback = Callable[[dict], None]
LogCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


class OperationCancelled(RuntimeError):
    pass


def raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check and cancel_check():
        raise OperationCancelled("Operacao cancelada pelo usuario.")


SUBPROCESS_KWARGS: dict = {}
if os.name == "nt":
    SUBPROCESS_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW

AUTO_ENCODER_CACHE: tuple[str, str] | None = None
ENCODER_CACHE_FILENAME = "encoder_cache.json"
TOOL_CACHE: dict[str, str] = {}


def get_tool_search_dirs() -> list[Path]:
    project_root = get_project_root()
    dirs = [
        project_root / "ferramentas" / "ffmpeg" / "bin",
        project_root / "ferramentas" / "ffmpeg",
        project_root / "ferramentas",
        project_root,
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.extend(
            [
                exe_dir,
                exe_dir / "ffmpeg" / "bin",
                exe_dir / "ffmpeg",
                exe_dir / "_internal" / "ffmpeg" / "bin",
                exe_dir / "_internal" / "ffmpeg",
            ]
        )
    return dirs


def resolve_tool(tool_name: str) -> str:
    cached = TOOL_CACHE.get(tool_name)
    if cached:
        return cached

    found = shutil.which(tool_name)
    if found:
        TOOL_CACHE[tool_name] = found
        return found

    executable_name = f"{tool_name}.exe" if os.name == "nt" else tool_name
    checked_dirs = []
    for search_dir in get_tool_search_dirs():
        checked_dirs.append(str(search_dir))
        candidate = search_dir / executable_name
        if candidate.exists():
            resolved = str(candidate)
            TOOL_CACHE[tool_name] = resolved
            return resolved

    install_hint = (
        "Instale o FFmpeg ou copie ffmpeg.exe e ffprobe.exe para "
        "ferramentas\\ffmpeg\\bin dentro desta pasta."
    )
    raise RuntimeError(
        f"'{tool_name}' nao foi encontrado. {install_hint} "
        f"Pastas verificadas: {'; '.join(checked_dirs)}"
    )


def ensure_tool(tool_name: str) -> None:
    resolve_tool(tool_name)


def ensure_basic_tools() -> None:
    ensure_tool("ffmpeg")
    ensure_tool("ffprobe")


def format_seconds(total_seconds: float) -> str:
    rounded = round(total_seconds, 3)
    whole_seconds = int(rounded)
    milliseconds = int(round((rounded - whole_seconds) * 1000))
    if milliseconds == 1000:
        whole_seconds += 1
        milliseconds = 0
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def format_clock(total_seconds: float) -> str:
    whole_seconds = max(0, int(round(total_seconds)))
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def resolve_time_range(
    total_duration: float,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> tuple[float, float]:
    start = max(0.0, float(start_seconds))
    end = total_duration if end_seconds is None else min(float(end_seconds), total_duration)
    if start >= total_duration:
        raise RuntimeError("O inicio do trecho precisa estar dentro do video.")
    if end <= start:
        raise RuntimeError("O fim do trecho precisa ser maior que o inicio.")
    return start, end


def format_path_time(total_seconds: float) -> str:
    return format_clock(total_seconds).replace(":", "-")


def default_output_root(base_dir: Path | None = None) -> Path:
    root = (base_dir or get_project_root()) / "saidas"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.parent.name.lower() == "executaveis":
            return exe_dir.parent.parent
        if exe_dir.name.lower() == "executaveis":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parents[1]


def get_encoder_cache_path() -> Path:
    cache_dir = get_project_root() / "ferramentas"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / ENCODER_CACHE_FILENAME


def load_encoder_cache() -> tuple[str, str] | None:
    cache_path = get_encoder_cache_path()
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    encoder = data.get("encoder")
    reason = data.get("reason")
    if isinstance(encoder, str) and isinstance(reason, str):
        return encoder, reason
    return None


def save_encoder_cache(encoder: str, reason: str) -> None:
    cache_path = get_encoder_cache_path()
    payload = {"encoder": encoder, "reason": reason}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_encoder_cache() -> None:
    global AUTO_ENCODER_CACHE
    AUTO_ENCODER_CACHE = None
    cache_path = get_encoder_cache_path()
    if cache_path.exists():
        cache_path.unlink()


def ffprobe_video(video_path: Path) -> dict:
    command = [
        resolve_tool("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True, **SUBPROCESS_KWARGS)
    return json.loads(result.stdout)


def get_primary_stream(streams: list[dict], stream_type: str) -> dict | None:
    for stream in streams:
        if stream.get("codec_type") == stream_type:
            return stream
    return None


def list_available_encoders() -> set[str]:
    result = subprocess.run(
        [resolve_tool("ffmpeg"), "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
        **SUBPROCESS_KWARGS,
    )
    available: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            available.add(parts[1])
    return available


def map_crf_to_mf_quality(crf: int) -> int:
    quality = 100 - ((crf - 18) * 4)
    return max(45, min(quality, 100))


def build_video_codec_args(encoder: str, profile: QualityProfile) -> list[str]:
    if encoder == "libx264":
        return [
            "-c:v",
            "libx264",
            "-preset",
            profile.preset,
            "-crf",
            str(profile.crf),
            "-pix_fmt",
            "yuv420p",
        ]
    if encoder == "h264_nvenc":
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            NVENC_PRESET_MAP[profile.preset],
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            str(max(0, min(profile.crf, 51))),
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
        ]
    if encoder == "h264_mf":
        return [
            "-c:v",
            "h264_mf",
            "-hw_encoding",
            "1",
            "-rate_control",
            "quality",
            "-quality",
            str(map_crf_to_mf_quality(profile.crf)),
            "-pix_fmt",
            "nv12",
        ]
    raise RuntimeError(f"Encoder nao suportado: {encoder}")


def build_audio_codec_args(has_audio: bool, profile: QualityProfile) -> list[str]:
    if not has_audio:
        return ["-an"]
    return ["-c:a", "aac", "-b:a", profile.audio_bitrate]


def test_encoder(encoder: str, input_path: Path, has_audio: bool, profile: QualityProfile) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="separar-video-") as temp_dir:
            temp_output = Path(temp_dir) / "encoder_probe.mp4"
            command = [
                resolve_tool("ffmpeg"),
                "-v",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
            ]
            command += build_video_codec_args(encoder, profile)
            command += ["-an"]
            command += [str(temp_output)]
            subprocess.run(command, check=True, capture_output=True, text=True, **SUBPROCESS_KWARGS)
            return temp_output.exists() and temp_output.stat().st_size > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def resolve_encoder(
    requested_encoder: str,
    input_path: Path,
    has_audio: bool,
    profile: QualityProfile,
) -> tuple[str, str]:
    global AUTO_ENCODER_CACHE

    if requested_encoder != "auto":
        return requested_encoder, "definido manualmente"

    if AUTO_ENCODER_CACHE is not None:
        return AUTO_ENCODER_CACHE

    persisted = load_encoder_cache()
    if persisted is not None:
        AUTO_ENCODER_CACHE = persisted
        return AUTO_ENCODER_CACHE

    available = list_available_encoders()
    candidates = [
        ("h264_nvenc", "NVIDIA NVENC"),
        ("h264_mf", "Media Foundation com hardware"),
        ("libx264", "software x264"),
    ]
    for encoder, reason in candidates:
        if encoder != "libx264" and encoder not in available:
            continue
        if encoder == "libx264" or test_encoder(encoder, input_path, has_audio, profile):
            AUTO_ENCODER_CACHE = (encoder, reason)
            save_encoder_cache(*AUTO_ENCODER_CACHE)
            return AUTO_ENCODER_CACHE
    AUTO_ENCODER_CACHE = ("libx264", "fallback final em software")
    save_encoder_cache(*AUTO_ENCODER_CACHE)
    return AUTO_ENCODER_CACHE


def parse_progress_time_ms(raw_value: str | None) -> int:
    if not raw_value or raw_value == "N/A":
        return 0
    try:
        return int(raw_value)
    except ValueError:
        return 0


def build_segments(total_duration: float, parts: int, start_offset: float = 0.0) -> list[dict]:
    part_duration = total_duration / parts
    segments = []
    for index in range(parts):
        start_time = start_offset + index * part_duration
        end_time = start_offset + (total_duration if index == parts - 1 else (index + 1) * part_duration)
        segments.append(
            {
                "index": index + 1,
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
            }
        )
    return segments


def build_output_dir(
    output_root: Path,
    input_path: Path,
    parts: int,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> Path:
    grouped_dir = output_root / input_path.stem
    if parts == 1:
        folder_name = "recorte"
    else:
        folder_name = f"{parts}_partes"
    if start_seconds > 0 or end_seconds is not None:
        assert end_seconds is not None
        folder_name += f"_{format_path_time(start_seconds)}_a_{format_path_time(end_seconds)}"
    output_dir = grouped_dir / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def build_output_paths(output_dir: Path, input_path: Path, parts: int) -> list[Path]:
    if parts == 1:
        return [output_dir / f"{input_path.stem}_recorte.mp4"]
    return [
        output_dir / f"{input_path.stem}_parte_{index:02d}_de_{parts:02d}.mp4"
        for index in range(1, parts + 1)
    ]


def clean_output_paths(output_paths: list[Path]) -> None:
    for path in output_paths:
        if path.exists():
            path.unlink()


def build_filter_complex(segments: list[dict], has_audio: bool) -> str:
    video_split_labels = [f"vsplit{index}" for index in range(len(segments))]
    parts = [f"[0:v]split={len(segments)}" + "".join(f"[{label}]" for label in video_split_labels)]

    for index, segment in enumerate(segments):
        parts.append(
            f"[{video_split_labels[index]}]"
            f"trim=start={segment['start']:.6f}:end={segment['end']:.6f},"
            f"setpts=PTS-STARTPTS[vout{index}]"
        )

    if has_audio:
        audio_split_labels = [f"asplit{index}" for index in range(len(segments))]
        parts.append(
            f"[0:a:0]asplit={len(segments)}" + "".join(f"[{label}]" for label in audio_split_labels)
        )
        for index, segment in enumerate(segments):
            parts.append(
                f"[{audio_split_labels[index]}]"
                f"atrim=start={segment['start']:.6f}:end={segment['end']:.6f},"
                f"asetpts=PTS-STARTPTS[aout{index}]"
            )
    return ";".join(parts)


def emit_progress(callback: ProgressCallback | None, payload: dict) -> None:
    if callback:
        callback(payload)


def emit_log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)


def run_command_with_progress(
    command: list[str],
    expected_duration: float,
    label: str,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> None:
    progress_command = command.copy()
    progress_command[1:1] = ["-progress", "pipe:1", "-nostats", "-loglevel", "error"]

    start_monotonic = time.monotonic()
    progress_data: dict[str, str] = {}

    with subprocess.Popen(
        progress_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        universal_newlines=True,
        **SUBPROCESS_KWARGS,
    ) as process:
        assert process.stdout is not None
        for raw_line in process.stdout:
            if cancel_check and cancel_check():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise OperationCancelled("Processamento de video cancelado.")
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            progress_data[key] = value
            if key != "progress":
                continue

            out_time_ms = parse_progress_time_ms(progress_data.get("out_time_ms"))
            processed_seconds = out_time_ms / 1_000_000
            percent = 100.0 if expected_duration <= 0 else min((processed_seconds / expected_duration) * 100, 100.0)
            speed = progress_data.get("speed", "?")
            elapsed = time.monotonic() - start_monotonic
            speed_value = 0.0
            if speed.endswith("x"):
                try:
                    speed_value = float(speed[:-1])
                except ValueError:
                    speed_value = 0.0
            remaining = max(expected_duration - processed_seconds, 0.0)
            eta_seconds = (remaining / speed_value) if speed_value > 0 else 0.0

            emit_progress(
                progress_callback,
                {
                    "label": label,
                    "percent": percent,
                    "elapsed_seconds": elapsed,
                    "remaining_seconds": eta_seconds,
                    "speed": speed,
                    "processed_seconds": processed_seconds,
                    "done": value == "end",
                },
            )

        stderr_output = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, progress_command, stderr=stderr_output)

    emit_progress(
        progress_callback,
        {
            "label": label,
            "percent": 100.0,
            "elapsed_seconds": time.monotonic() - start_monotonic,
            "remaining_seconds": 0.0,
            "speed": "concluido",
            "processed_seconds": expected_duration,
            "done": True,
        },
    )


def append_output_arguments(
    command: list[str],
    output_path: Path,
    output_index: int,
    encoder: str,
    profile: QualityProfile,
    has_audio: bool,
) -> None:
    command += ["-map", f"[vout{output_index}]"]
    if has_audio:
        command += ["-map", f"[aout{output_index}]"]
    command += build_video_codec_args(encoder, profile)
    command += build_audio_codec_args(has_audio, profile)
    command += ["-movflags", "+faststart", str(output_path)]


def run_ffmpeg_onepass(
    input_path: Path,
    output_paths: list[Path],
    segments: list[dict],
    encoder: str,
    profile: QualityProfile,
    has_audio: bool,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> None:
    command = [
        resolve_tool("ffmpeg"),
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        build_filter_complex(segments, has_audio),
    ]

    for index, output_path in enumerate(output_paths):
        segment = segments[index]
        emit_log(
            log_callback,
            f"Gerando {output_path.name} | inicio {format_seconds(segment['start'])} | duracao {format_seconds(segment['duration'])}",
        )
        append_output_arguments(command, output_path, index, encoder, profile, has_audio)

    selected_duration = sum(float(segment["duration"]) for segment in segments)
    run_command_with_progress(
        command,
        selected_duration,
        "Progresso geral",
        progress_callback,
        cancel_check,
    )


def run_ffmpeg_sequential(
    input_path: Path,
    output_paths: list[Path],
    segments: list[dict],
    encoder: str,
    profile: QualityProfile,
    has_audio: bool,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> None:
    for index, output_path in enumerate(output_paths):
        raise_if_cancelled(cancel_check)
        segment = segments[index]
        command = [
            resolve_tool("ffmpeg"),
            "-y",
            "-ss",
            format_seconds(segment["start"]),
            "-i",
            str(input_path),
            "-t",
            format_seconds(segment["duration"]),
            "-map",
            "0:v:0",
        ]
        if has_audio:
            command += ["-map", "0:a?"]
        command += build_video_codec_args(encoder, profile)
        command += build_audio_codec_args(has_audio, profile)
        command += ["-movflags", "+faststart", str(output_path)]

        emit_log(
            log_callback,
            f"Gerando {output_path.name} | inicio {format_seconds(segment['start'])} | duracao {format_seconds(segment['duration'])}",
        )
        run_command_with_progress(
            command,
            segment["duration"],
            f"Parte {segment['index']}/{len(segments)}",
            progress_callback,
            cancel_check,
        )


def process_video(
    options: ProcessingOptions,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ProcessingResult:
    raise_if_cancelled(cancel_check)
    ensure_basic_tools()

    input_path = options.input_path.resolve()
    if not input_path.exists():
        raise RuntimeError(f"Arquivo nao encontrado: {input_path}")
    if options.parts not in {1, 2, 3, 4}:
        raise RuntimeError("A quantidade de partes deve ser de 1 a 4.")

    profile = QUALITY_PROFILES.get(options.quality_profile, QUALITY_PROFILES["equilibrada"])
    probe_data = ffprobe_video(input_path)
    metadata = probe_data["format"]
    streams = probe_data.get("streams", [])

    video_stream = get_primary_stream(streams, "video")
    if video_stream is None:
        raise RuntimeError("O arquivo nao possui stream de video.")
    has_audio = get_primary_stream(streams, "audio") is not None

    total_duration = float(metadata["duration"])
    original_size = int(metadata.get("size", 0))
    range_start, range_end = resolve_time_range(
        total_duration,
        options.start_seconds,
        options.end_seconds,
    )
    if options.sample_seconds is not None:
        if options.sample_seconds <= 0:
            raise RuntimeError("--sample-seconds deve ser maior que zero.")
        range_end = min(range_end, range_start + options.sample_seconds)
    processed_duration = range_end - range_start

    output_root = options.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    custom_range = range_start > 0 or range_end < total_duration
    output_dir = build_output_dir(
        output_root,
        input_path,
        options.parts,
        range_start if custom_range else 0.0,
        range_end if custom_range else None,
    )
    output_paths = build_output_paths(output_dir, input_path, options.parts)
    clean_output_paths(output_paths)
    segments = build_segments(processed_duration, options.parts, range_start)

    encoder_used, encoder_reason = resolve_encoder(options.encoder, input_path, has_audio, profile)

    emit_log(log_callback, f"Video: {input_path.name}")
    emit_log(log_callback, f"Duracao total: {format_seconds(total_duration)}")
    emit_log(
        log_callback,
        f"Trecho selecionado: {format_seconds(range_start)} a {format_seconds(range_end)}",
    )
    emit_log(log_callback, f"Partes: {options.parts}")
    emit_log(log_callback, f"Perfil: {profile.label}")
    emit_log(log_callback, f"Encoder: {encoder_used} ({encoder_reason})")
    emit_log(log_callback, f"Saida: {output_dir}")

    def run_selected_pipeline(selected_encoder: str) -> None:
        if options.mode in {"auto", "onepass"}:
            emit_log(log_callback, "Estrategia: corte preciso em um unico processamento.")
            run_ffmpeg_onepass(
                input_path=input_path,
                output_paths=output_paths,
                segments=segments,
                encoder=selected_encoder,
                profile=profile,
                has_audio=has_audio,
                progress_callback=progress_callback,
                log_callback=log_callback,
                cancel_check=cancel_check,
            )
        else:
            emit_log(log_callback, "Estrategia: processamento sequencial.")
            run_ffmpeg_sequential(
                input_path=input_path,
                output_paths=output_paths,
                segments=segments,
                encoder=selected_encoder,
                profile=profile,
                has_audio=has_audio,
                progress_callback=progress_callback,
                log_callback=log_callback,
                cancel_check=cancel_check,
            )

    try:
        run_selected_pipeline(encoder_used)
    except OperationCancelled:
        clean_output_paths(output_paths)
        emit_log(log_callback, "Processamento cancelado. Arquivos parciais removidos.")
        raise
    except subprocess.CalledProcessError as error:
        if options.encoder == "auto" and encoder_used != "libx264":
            emit_log(log_callback, "Encoder acelerado falhou. Limpando cache e tentando software x264.")
            clear_encoder_cache()
            clean_output_paths(output_paths)
            encoder_used = "libx264"
            encoder_reason = "fallback automatico apos falha do encoder acelerado"
            save_encoder_cache(encoder_used, encoder_reason)
            run_selected_pipeline(encoder_used)
        elif options.mode == "auto":
            emit_log(log_callback, "Onepass falhou. Fazendo fallback automatico para modo sequential.")
            clean_output_paths(output_paths)
            run_ffmpeg_sequential(
                input_path=input_path,
                output_paths=output_paths,
                segments=segments,
                encoder=encoder_used,
                profile=profile,
                has_audio=has_audio,
                progress_callback=progress_callback,
                log_callback=log_callback,
                cancel_check=cancel_check,
            )
        else:
            raise RuntimeError(error.stderr or "Falha ao executar o ffmpeg.") from error

    generated_files = [path for path in output_paths if path.exists()]
    generated_size = sum(path.stat().st_size for path in generated_files)
    emit_log(log_callback, f"Concluido. Arquivos gerados: {len(generated_files)}")
    if generated_size:
        emit_log(log_callback, f"Tamanho total gerado: {generated_size / (1024 ** 3):.2f} GB")

    return ProcessingResult(
        output_dir=output_dir,
        output_files=generated_files,
        encoder_used=encoder_used,
        encoder_reason=encoder_reason,
        total_duration=total_duration,
        processed_duration=processed_duration,
        original_size=original_size,
        generated_size=generated_size,
    )
