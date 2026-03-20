"""TTS→STT round-trip tests — verify audio transcribes back accurately.

Run with: RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_tts_pipeline.py -v -m "tts"
"""

from __future__ import annotations

import pytest

from .conftest import load_test_scripts

# Use a small subset of voice scripts for TTS round-trip
VOICE_SCRIPTS = load_test_scripts("voice_request")[:5]
MEETING_SCRIPTS = load_test_scripts("meeting")[:3]

VOICE_IDS = [s["id"] for s in VOICE_SCRIPTS]
MEETING_IDS = [s["id"] for s in MEETING_SCRIPTS]


@pytest.mark.prompt_test
@pytest.mark.tts
@pytest.mark.timeout(180)
@pytest.mark.parametrize("script", VOICE_SCRIPTS, ids=VOICE_IDS)
async def test_tts_voice_roundtrip(script, tts_generator, live_voice_service, structural_evaluator):
    """Generate TTS audio from voice script, transcribe back, analyze with Gemini."""
    text = script["text"]
    language = script.get("language", "ja-JP")

    # Step 1: Generate audio via TTS
    audio_bytes = tts_generator.generate(text, language=language)
    assert len(audio_bytes) > 100, "TTS generated too-small audio"

    # Step 2: Transcribe back via STT
    transcript = await live_voice_service.transcribe_audio(audio_bytes, lang=language)
    assert len(transcript) > 10, f"STT returned too-short transcript: '{transcript}'"

    # Step 3: Analyze transcription with Gemini
    result = await live_voice_service._analyze(transcript)

    # Step 4: Structural check on analysis
    eval_result = structural_evaluator.evaluate(result, script["expected"])
    # TTS round-trip is lossy (especially with noise), accept score > 0.4
    assert eval_result.score >= 0.4, (
        f"TTS round-trip for {script['id']} scored too low: {eval_result.summary()}\n"
        f"Original: {text[:100]}...\n"
        f"Transcribed: {transcript[:100]}..."
    )


@pytest.mark.prompt_test
@pytest.mark.tts
@pytest.mark.timeout(240)
@pytest.mark.parametrize("script", MEETING_SCRIPTS, ids=MEETING_IDS)
async def test_tts_meeting_roundtrip(script, tts_generator, live_meeting_service, structural_evaluator):
    """Generate multi-speaker TTS audio for meeting, transcribe, extract items."""
    transcript_text = script["transcript"]
    language = script.get("language", "ja-JP")

    # For meetings, generate single-speaker audio from the full transcript
    # (multi-speaker TTS would require parsing speaker segments)
    lang_code = "ja-JP" if language in ("ja-JP", "mixed") else "ko-KR"
    audio_bytes = tts_generator.generate(transcript_text[:500], language=lang_code)
    assert len(audio_bytes) > 100, "TTS generated too-small audio"

    # Transcribe
    stt_transcript = await live_meeting_service.transcribe_audio(audio_bytes, language=lang_code)
    assert len(stt_transcript) > 10, f"STT returned too-short transcript: '{stt_transcript}'"

    # Extract items from transcription
    result = await live_meeting_service._extract_items(stt_transcript)

    # Meeting TTS round-trip is even lossier with noise, accept lower threshold
    eval_result = structural_evaluator.evaluate(result, script["expected"])
    assert eval_result.score >= 0.2, (
        f"TTS meeting round-trip for {script['id']} scored too low: {eval_result.summary()}\n"
        f"Transcribed: {stt_transcript[:200]}..."
    )
