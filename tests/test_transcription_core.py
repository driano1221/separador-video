import tempfile
import unittest
from pathlib import Path

from app.transcription_core import (
    FASTER_WHISPER_REPOSITORIES,
    TRANSCRIPTION_MODELS,
    TranscriptionOptions,
    load_transcription_checkpoint,
    save_transcription_checkpoint,
    transcription_checkpoint_metadata,
)
from app.video_splitter_core import build_segments, resolve_time_range
from app.video_splitter_gui import parse_time_value


class TranscriptionCoreTest(unittest.TestCase):
    def test_time_range_and_split_keep_absolute_video_times(self):
        start, end = resolve_time_range(120.0, 30.0, 90.0)
        segments = build_segments(end - start, 2, start)
        self.assertEqual((segments[0]["start"], segments[0]["end"]), (30.0, 60.0))
        self.assertEqual((segments[1]["start"], segments[1]["end"]), (60.0, 90.0))

    def test_time_input_accepts_hours_minutes_and_seconds(self):
        self.assertEqual(parse_time_value("01:12:30"), 4350.0)
        self.assertEqual(parse_time_value("08:15"), 495.0)

    def test_balanced_profile_uses_multilingual_turbo_repository(self):
        model_id = TRANSCRIPTION_MODELS["equilibrada"]["model_id"]
        self.assertEqual(model_id, "turbo")
        self.assertEqual(
            FASTER_WHISPER_REPOSITORIES[model_id],
            "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        )

    def test_checkpoint_only_resumes_matching_input_and_options(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            input_path = root / "video.mp4"
            input_path.write_bytes(b"video")
            options = TranscriptionOptions(input_path=input_path, output_root=root)
            metadata = transcription_checkpoint_metadata(input_path, "turbo", options)
            checkpoint_path = root / "checkpoint.json"
            segments = [{"start": 0.0, "end": 12.5, "text": "Teste", "words": []}]

            save_transcription_checkpoint(checkpoint_path, metadata, segments)

            self.assertEqual(
                load_transcription_checkpoint(checkpoint_path, metadata),
                segments,
            )
            changed_metadata = {**metadata, "language": "en"}
            self.assertEqual(
                load_transcription_checkpoint(checkpoint_path, changed_metadata),
                [],
            )


if __name__ == "__main__":
    unittest.main()
