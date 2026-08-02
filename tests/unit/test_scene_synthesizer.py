"""
tests/unit/test_scene_synthesizer.py — synthesize_scene() (010-topic-video-
generation, T026).

⚠️ Constitution §VI: mock adapter TTS (edge-tts) VÀ `get_media_duration`
(ffprobe) — không test nào phụ thuộc binary ngoài hay gọi TTS provider thật.
"""

from __future__ import annotations

import pytest

from tts import scene_synthesizer


def test_synthesize_scene_returns_real_measured_duration(tmp_path, monkeypatch):
    written: dict = {}

    def fake_adapter(text, out):
        written["text"] = text
        written["out"] = out
        out.write_bytes(b"fake-wav-bytes")

    monkeypatch.setattr(
        scene_synthesizer, "_get_adapter", lambda provider, voice_id: fake_adapter
    )
    # Duration thật đo từ ffprobe — KHÔNG phải ước lượng ký tự/giây
    monkeypatch.setattr(scene_synthesizer, "get_media_duration", lambda path: 4.27)

    output_path = tmp_path / "scenes" / "0" / "voice.wav"
    duration = scene_synthesizer.synthesize_scene("Xin chào các bạn.", output_path)

    assert duration == 4.27
    assert written["text"] == "Xin chào các bạn."
    assert output_path.exists()
    assert output_path.read_bytes() == b"fake-wav-bytes"


def test_synthesize_scene_creates_parent_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        scene_synthesizer,
        "_get_adapter",
        lambda provider, voice_id: (lambda text, out: out.write_bytes(b"x")),
    )
    monkeypatch.setattr(scene_synthesizer, "get_media_duration", lambda path: 1.0)

    output_path = tmp_path / "nested" / "dir" / "voice.wav"
    scene_synthesizer.synthesize_scene("x", output_path)

    assert output_path.parent.exists()


def test_synthesize_scene_passes_provider_and_voice_id(tmp_path, monkeypatch):
    captured = {}

    def fake_get_adapter(provider, voice_id):
        captured["provider"] = provider
        captured["voice_id"] = voice_id
        return lambda text, out: out.write_bytes(b"x")

    monkeypatch.setattr(scene_synthesizer, "_get_adapter", fake_get_adapter)
    monkeypatch.setattr(scene_synthesizer, "get_media_duration", lambda path: 2.0)

    scene_synthesizer.synthesize_scene(
        "x", tmp_path / "v.wav", provider="lucyai", voice_id="voice-42"
    )

    assert captured == {"provider": "lucyai", "voice_id": "voice-42"}


def test_synthesize_scene_propagates_adapter_errors(tmp_path, monkeypatch):
    def failing_adapter(provider, voice_id):
        raise RuntimeError("provider yêu cầu voice_id")

    monkeypatch.setattr(scene_synthesizer, "_get_adapter", failing_adapter)

    with pytest.raises(RuntimeError):
        scene_synthesizer.synthesize_scene("x", tmp_path / "v.wav", provider="lucyai")
