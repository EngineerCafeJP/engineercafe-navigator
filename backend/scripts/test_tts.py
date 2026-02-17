"""
日本語・英語 TTS の動作確認スクリプト

VoiceVox（日本語）と Kokoro TTS（英語）を続けて試します。

Usage:
    プロジェクトルートから:
        python -m backend.scripts.test_tts
    backend から:
        python -m scripts.test_tts
"""

import asyncio
import sys


def _ensure_path():
    """backend から実行された場合にプロジェクトルートを path に追加"""
    if "backend" not in sys.path and "backend.agents" not in str(sys.path):
        try:
            from pathlib import Path
            backend_dir = Path(__file__).resolve().parent.parent
            root = backend_dir.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
        except Exception:
            pass


async def main():
    _ensure_path()
    from backend.agents.voice_agent import VoiceAgent

    agent = VoiceAgent(tts_provider="voicevox")

    # 日本語
    print("--- 日本語 TTS (VoiceVox) ---")
    result_ja = await agent.text_to_speech("こんにちは、エンジニアカフェへようこそ！", language="ja")
    print(f"  Success: {result_ja['success']}")
    print(f"  Language: {result_ja.get('language')}")
    print(f"  Format: {result_ja.get('format')}")
    print(f"  Audio (base64 length): {len(result_ja.get('audioResponse', ''))}")
    if not result_ja["success"]:
        print(f"  Error: {result_ja.get('error')}")
    print()

    # 英語
    print("--- 英語 TTS (Kokoro TTS) ---")
    result_en = await agent.text_to_speech("Hello, welcome to Engineer Cafe!", language="en")
    print(f"  Success: {result_en['success']}")
    print(f"  Language: {result_en.get('language')}")
    print(f"  Format: {result_en.get('format')}")
    print(f"  Audio (base64 length): {len(result_en.get('audioResponse', ''))}")
    if not result_en["success"]:
        print(f"  Error: {result_en.get('error')}")
    print()

    if result_ja["success"] and result_en["success"]:
        print("✅ 日本語・英語とも TTS 成功")
    else:
        print("⚠️ いずれかが失敗しています（VoiceVox / Kokoro TTS の起動を確認してください）")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
