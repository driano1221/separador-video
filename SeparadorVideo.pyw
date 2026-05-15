from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)

    ffmpeg_dir = project_root / "ferramentas" / "ffmpeg" / "bin"
    if ffmpeg_dir.exists():
        os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from app.video_splitter_gui import main as run_gui

    run_gui()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_path = Path(__file__).resolve().with_name("SeparadorVideo_erro.log")
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
