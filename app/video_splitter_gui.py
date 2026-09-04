"""Compatibility entry point for the production desktop workbench."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.video_workbench_gui import main


def parse_time_value(value: str) -> float:
    """Parse seconds, MM:SS or HH:MM:SS used by the legacy CLI/tests."""
    text = value.strip().replace(",", ".")
    if not text:
        raise ValueError("Informe o horario no formato HH:MM:SS.")
    fields = text.split(":")
    if len(fields) > 3:
        raise ValueError("Use o formato HH:MM:SS.")
    try:
        numbers = [float(field) for field in fields]
    except ValueError as error:
        raise ValueError("Use apenas numeros no intervalo.") from error
    if any(number < 0 for number in numbers):
        raise ValueError("O intervalo nao pode ter valores negativos.")
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
    elif len(numbers) == 2:
        hours, minutes, seconds = 0.0, numbers[0], numbers[1]
    else:
        hours, minutes, seconds = 0.0, 0.0, numbers[0]
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutos e segundos devem ser menores que 60.")
    return hours * 3600 + minutes * 60 + seconds


if __name__ == "__main__":
    main()
