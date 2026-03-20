"""GCP Text-to-Speech wrapper with content-hash audio caching."""

from __future__ import annotations

import hashlib
import logging
import struct
import wave
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "audio_cache"

# Voice map: language → (voice_name, ssml_gender)
VOICE_MAP = {
    "ja-JP-male": ("ja-JP-Neural2-B", "MALE"),
    "ja-JP-female": ("ja-JP-Neural2-C", "FEMALE"),
    "ko-KR-female": ("ko-KR-Neural2-A", "FEMALE"),
    "ko-KR-male": ("ko-KR-Neural2-C", "MALE"),
}

DEFAULT_VOICES = {
    "ja-JP": "ja-JP-male",
    "ko-KR": "ko-KR-female",
}


class TTSGenerator:
    """Generate audio from text via GCP Text-to-Speech with local caching."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self._client: Any = None
        self.sample_rate = sample_rate
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google.cloud import texttospeech

            self._client = texttospeech.TextToSpeechClient()
        return self._client

    def _cache_key(self, text: str, voice_key: str) -> str:
        """Content-hash key for cache lookup."""
        h = hashlib.sha256(f"{text}:{voice_key}:{self.sample_rate}".encode()).hexdigest()[:16]
        return h

    def generate(self, text: str, language: str = "ja-JP", voice_key: str | None = None, ssml: bool = False) -> bytes:
        """Generate LINEAR16 WAV audio from text or SSML.

        Args:
            text: Text or SSML markup to synthesize.
            language: Language code (ja-JP or ko-KR).
            voice_key: Specific voice from VOICE_MAP (e.g. "ja-JP-male").
                       Defaults to language default.
            ssml: If True, treat text as SSML markup (enables pauses, rate changes).

        Returns:
            Raw WAV bytes (LINEAR16, mono).
        """
        if voice_key is None:
            voice_key = DEFAULT_VOICES.get(language, "ja-JP-male")

        cache_id = self._cache_key(text, voice_key)
        cache_path = CACHE_DIR / f"{cache_id}.wav"

        if cache_path.exists():
            log.debug("TTS cache hit: %s", cache_id)
            return cache_path.read_bytes()

        voice_name, gender = VOICE_MAP[voice_key]
        client = self._ensure_client()

        from google.cloud import texttospeech

        if ssml:
            synthesis_input = texttospeech.SynthesisInput(ssml=text)
        else:
            synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=language,
            name=voice_name,
            ssml_gender=getattr(texttospeech.SsmlVoiceGender, gender),
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.sample_rate,
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config,
        )

        cache_path.write_bytes(response.audio_content)
        log.info("TTS generated and cached: %s (%d bytes)", cache_id, len(response.audio_content))
        return response.audio_content

    def text_to_ssml(self, text: str) -> str:
        """Convert plain text with noise markers to SSML for realistic TTS.

        Converts filler words to pauses and speaking rate changes.
        """
        import re
        ssml = text
        # Noise markers → silence breaks
        noise_markers = {"[咳]": '<break time="500ms"/>', "[雑音]": '<break time="300ms"/>',
                        "[一時停止]": '<break time="800ms"/>', "[ノイズ]": '<break time="200ms"/>',
                        "[電話の音]": '<break time="400ms"/>', "[기침]": '<break time="500ms"/>',
                        "[잡음]": '<break time="300ms"/>', "[일시정지]": '<break time="800ms"/>'}
        for marker, ssml_break in noise_markers.items():
            ssml = ssml.replace(marker, ssml_break)
        # Filler words → slow rate
        filler_patterns = [
            (r"(えーと|えーっと|あのー|そのー|うーん)", r'<prosody rate="slow">\1</prosody><break time="200ms"/>'),
            (r"(음+|그+|어+|저기)", r'<prosody rate="slow">\1</prosody><break time="200ms"/>'),
        ]
        for pattern, replacement in filler_patterns:
            ssml = re.sub(pattern, replacement, ssml)
        return f'<speak>{ssml}</speak>'

    def generate_meeting(
        self,
        speakers: list[dict],
        silence_gap_sec: float = 0.5,
        alternate_voices: bool = True,
    ) -> bytes:
        """Generate multi-speaker meeting audio by concatenating per-speaker segments.

        Args:
            speakers: List of {"role": str, "lang": str, "text": str, "voice_key": str (optional)}.
            silence_gap_sec: Seconds of silence between speakers.
            alternate_voices: If True, auto-assign male/female voices to different speakers.

        Returns:
            Combined WAV bytes.
        """
        silence_samples = int(self.sample_rate * silence_gap_sec)
        silence_bytes = struct.pack(f"<{silence_samples}h", *([0] * silence_samples))

        # Auto-assign alternating voices for different speakers
        if alternate_voices:
            role_voices: dict[str, str] = {}
            voice_cycle = {"ja-JP": ["ja-JP-male", "ja-JP-female"], "ko-KR": ["ko-KR-male", "ko-KR-female"]}
            role_counters: dict[str, int] = {"ja-JP": 0, "ko-KR": 0}

        all_pcm = b""
        for i, speaker in enumerate(speakers):
            voice_key = speaker.get("voice_key")
            lang = speaker.get("lang", "ja-JP")

            if voice_key is None and alternate_voices:
                role = speaker.get("role", f"speaker_{i}")
                if role not in role_voices:
                    lang_key = lang if lang in voice_cycle else "ja-JP"
                    idx = role_counters[lang_key] % len(voice_cycle[lang_key])
                    role_voices[role] = voice_cycle[lang_key][idx]
                    role_counters[lang_key] += 1
                voice_key = role_voices[role]

            wav_bytes = self.generate(
                text=speaker["text"],
                language=lang,
                voice_key=voice_key,
            )
            # Extract raw PCM from WAV (skip header)
            pcm = self._wav_to_pcm(wav_bytes)
            all_pcm += pcm
            if i < len(speakers) - 1:
                all_pcm += silence_bytes

        return self._pcm_to_wav(all_pcm)

    def generate_call(self, text: str, language: str = "ja-JP") -> bytes:
        """Generate 8kHz call audio (Asterisk format)."""
        orig_rate = self.sample_rate
        self.sample_rate = 8000
        try:
            return self.generate(text, language)
        finally:
            self.sample_rate = orig_rate

    @staticmethod
    def _wav_to_pcm(wav_bytes: bytes) -> bytes:
        """Extract raw PCM data from WAV bytes."""
        import io

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            return wf.readframes(wf.getnframes())

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """Wrap raw PCM data in a WAV container."""
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)
        return buf.getvalue()
