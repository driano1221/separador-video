import argparse
import sys
from pathlib import Path

from app.video_splitter_core import (
    QUALITY_PROFILES,
    SOFTWARE_PRESETS,
    ProcessingOptions,
    default_output_root,
    format_clock,
    format_seconds,
    process_video,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Divide um video em partes iguais e comprime cada parte."
    )
    parser.add_argument("-i", "--input", type=Path, help="Video de entrada.")
    parser.add_argument(
        "-p",
        "--partes",
        type=int,
        choices=range(2, 5),
        metavar="[2-4]",
        help="Quantidade de partes iguais.",
    )
    parser.add_argument(
        "--qualidade",
        default="equilibrada",
        choices=list(QUALITY_PROFILES.keys()),
        help="Perfil pronto de qualidade.",
    )
    parser.add_argument(
        "--encoder",
        default="auto",
        choices=["auto", "libx264", "h264_nvenc", "h264_mf"],
        help="Encoder de video.",
    )
    parser.add_argument(
        "--modo",
        default="auto",
        choices=["auto", "onepass", "sequential"],
        help="Estrategia de processamento.",
    )
    parser.add_argument(
        "--sample-seconds",
        type=float,
        help="Processa apenas os primeiros X segundos do video.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Pasta base das saidas. Padrao: ./saidas",
    )
    parser.add_argument(
        "--listar-perfis",
        action="store_true",
        help="Mostra os perfis prontos e sai.",
    )
    return parser.parse_args()


def print_profiles() -> None:
    print("Perfis disponiveis:")
    for profile in QUALITY_PROFILES.values():
        print(
            f"- {profile.key}: {profile.label} | "
            f"CRF {profile.crf} | preset {profile.preset} | audio {profile.audio_bitrate}"
        )


def create_progress_handler():
    last_length = {"value": 0}

    def handle(payload: dict) -> None:
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
    if args.listar_perfis:
        print_profiles()
        return
    if args.input is None or args.partes is None:
        raise SystemExit("Informe --input e --partes, ou use --listar-perfis.")

    output_root = args.output_root.resolve() if args.output_root else default_output_root(Path.cwd())
    progress_handler = create_progress_handler()

    def log(message: str) -> None:
        print(message)

    options = ProcessingOptions(
        input_path=args.input,
        output_root=output_root,
        parts=args.partes,
        encoder=args.encoder,
        mode=args.modo,
        quality_profile=args.qualidade,
        sample_seconds=args.sample_seconds,
    )
    result = process_video(options, progress_callback=progress_handler, log_callback=log)
    print(f"Pasta final: {result.output_dir}")
    if result.generated_size and result.original_size:
        reduction = ((result.original_size - result.generated_size) / result.original_size) * 100
        print(f"Reducao aproximada: {reduction:.2f}%")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001
        print(f"Erro: {error}", file=sys.stderr)
        raise SystemExit(1) from error
