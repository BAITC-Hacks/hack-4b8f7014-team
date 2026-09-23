from app.config import Settings
from scripts.evaluate_stt import word_errors


def test_word_error_count_includes_insertions_deletions_and_substitutions():
    assert word_errors("Срок — в четверг", "срок в четверг") == (0, 3)
    assert word_errors("один два три", "один другой") == (2, 3)
    assert word_errors("бір екі", "бір екі үш") == (1, 2)


def test_gpu_stt_does_not_move_cpu_diarization():
    settings = Settings(_env_file=None, device="cpu", stt_device="cuda",
                        stt_compute_type="int8_float16")
    assert settings.device == "cpu"
    assert settings.stt_device == "cuda"
    assert settings.stt_compute_type == "int8_float16"
