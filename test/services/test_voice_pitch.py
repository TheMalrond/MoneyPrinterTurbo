"""Fork Clippa: --voice-pitch chega ao Edge TTS com e sem pausas no roteiro."""

from unittest.mock import patch

import pytest

from app.services import voice as vs


@pytest.mark.parametrize(
    "text", ["Texto sem pausa.", "Primeira parte. [pause: 1s] Segunda parte."]
)
def test_voice_pitch_reaches_edge_tts(text, tmp_path):
    seen = []

    def fake_azure(text, voice_name, voice_rate, voice_file, voice_pitch="+0Hz"):
        seen.append(voice_pitch)
        return None  # falha controlada: só interessa o parâmetro recebido

    with patch.object(vs, "azure_tts_v1", side_effect=fake_azure):
        vs.tts(
            text=text,
            voice_name="pt-BR-FranciscaNeural-Female",
            voice_rate=1.0,
            voice_file=str(tmp_path / "out.mp3"),
            voice_pitch="-10Hz",
        )
    assert seen and all(p == "-10Hz" for p in seen)
