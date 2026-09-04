import argparse
import sys
from pathlib import Path

from app.transcription_core import (
    TRANSCRIPTION_LANGUAGES,
    TRANSCRIPTION_MODELS,
    TranscriptionOptions,
    process_transcription,
)
from app.video_splitter_core import default_output_root, format_clock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcreve um video ou audio em TXT, SRT, VTT e JSON.")
    parser.add_argument("-i", "--input", type=Path, required=True, help="Video ou audio de entrada.")
    parser.add_argument(
        "--perfil",
        default="equilibrada",
        choices=list(TRANSCRIPTION_MODELS.keys()),
        help="Perfil de transcricao.",
    )
    parser.add_argument(
        "--idioma",
        default="pt",
        choices=list(TRANSCRIPTION_LANGUAGES.keys()),
        help="Idioma da transcricao.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Pasta base das saidas. Padrao: ./saidas",
    )
    parser.add_argument("--inicio", type=float, default=0.0, help="Inicio do trecho em segundos.")
    parser.add_argument("--fim", type=float, help="Fim do trecho em segundos.")
    return parser.parse_args()


def create_progress_handler():
    last_length = {"value": 0}

    def handle(payload: dict) -> None:
        if payload.get("indeterminate"):
            message = f"{payload['label']}: {payload.get('details_text', payload.get('speed', 'aguarde'))}"
            padded = message.ljust(last_length["value"])
            print(f"\r{padded}", end="", flush=True)
            last_length["value"] = len(message)
            return
        message = (
            f"{payload['label']}: {payload['percent']:5.1f}% | "
            f"decorrido {format_clock(payload['elapsed_seconds'])} | "
            f"restante {format_clock(payload['remaining_seconds'])} | "
            f"velocidade {payload['speed']}"
        )
        padded = message.ljust(last_length["value"])
        print(f"\r{padded}", end="", flush=True)
        last_length["value"] = len(message)
        if payload.get("done"):
            print()

    return handle


def main() -> None:
    args = parse_args()
    output_root = args.output_root.resolve() if args.output_root else default_output_root(Path.cwd())
    progress_handler = create_progress_handler()

    def log(message: str) -> None:
        print(message)

    result = process_transcription(
        TranscriptionOptions(
            input_path=args.input,
            output_root=output_root,
            model_profile=args.perfil,
            language=args.idioma,
            start_seconds=args.inicio,
            end_seconds=args.fim,
        ),
        progress_callback=progress_handler,
        log_callback=log,
    )
    print(f"Pasta final: {result.output_dir}")
    print(f"Idioma detectado/final: {result.language} ({result.language_probability:.2f})")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001
        print(f"Erro: {error}", file=sys.stderr)
        raise SystemExit(1) from error
