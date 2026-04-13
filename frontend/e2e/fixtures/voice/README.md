# Voice Fixture: `sample.wav`

Deterministic audio payload used by `frontend/e2e/voice-live.spec.ts` to drive the
browser voice pipeline against a live Cloud Run backend. The Playwright spec
injects this WAV through a deterministic `MediaRecorder` shim so the merge gate
does not depend on headless Chromium's flaky fake-microphone behavior. CI does
**not** regenerate this file; it is committed as a binary fixture.

## Details

| Field | Value |
|-------|-------|
| Phrase | `tell me about engineer cafe` |
| Voice | macOS `say` (Samantha, en_US) |
| Format | 16 kHz mono PCM16 WAV |
| Duration | ~1.81 s |
| Size | 58034 bytes (~57 KB) |
| sha256 | `9dc855c41a184383ab88c1f7826ac63292dcee2dda0522d71568ab539b22f351` |

## Regenerate (only on intentional change)

Run the helper script from this directory:

```sh
cd frontend/e2e/fixtures/voice
./generate.sh
```

Primary (macOS) equivalent commands:

```sh
say -v Samantha -o /tmp/ecn-voice-sample.aiff "tell me about engineer cafe"
ffmpeg -y -i /tmp/ecn-voice-sample.aiff \
  -ar 16000 -ac 1 -sample_fmt s16 \
  sample.wav
shasum -a 256 sample.wav
```

Fallback (Linux, optional, only if macOS `say` is unavailable):

```sh
# Requires piper (https://github.com/rhasspy/piper)
piper --model en_US-libritts-high --output_file /tmp/piper.wav \
  <<<"tell me about engineer cafe"
ffmpeg -y -i /tmp/piper.wav -ar 16000 -ac 1 -sample_fmt s16 sample.wav
```

After regenerating, update the `sha256` row in this README and note the
rationale in the regenerating PR. The spec uses loose transcript matching, so
minor phoneme drift is fine.

## Why This Phrase

The Cloud Run backend (`engineer-cafe-backend` rev `00079`) routes STT through
Qwen 0.6B. English accuracy is high and deterministic for short utterances.
Japanese accuracy is still unstable (`"エンジニアカフェについて教えて"` has been
observed transcribing as `"現地にカフェについてはせて"`). The fixture is therefore
fixed to English and the spec asserts only *non-empty response-text change*,
not literal transcript content.

## Why This Format

- `16 kHz mono PCM16` matches the Qwen STT preprocessor's native sample rate,
  so backend-side resampling is skipped.
- `audio/wav` with a real RIFF header is what the Playwright recorder shim emits
  into `VoiceRecorder.onstop`, so `VoiceInterface.handleRecordedAudio` stays on
  its production path.
- ≤ 80 KB target keeps the fixture well inside git (no LFS required).
