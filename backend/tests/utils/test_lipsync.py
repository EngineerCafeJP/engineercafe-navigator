#!/usr/bin/env python3
"""
リップシンクデータ生成のテスト・確認用スクリプト

CharacterControlAgentのgenerate_lipsync_data()メソッドの動作を確認するための
コマンドラインツールです。

使用方法:
    python -m backend.tests.utils.test_lipsync "こんにちは、エンジニアカフェへようこそ"
    python -m backend.tests.utils.test_lipsync "こんにちは" --duration 2.5
    python -m backend.tests.utils.test_lipsync "Hello World" -d 1.0
    python -m backend.tests.utils.test_lipsync "エンジニアカフェへようこそ" -d 3.0 --pretty

出力例（上記1つ目のコマンド実行時）:
    JSON で以下を出力します。
    - input: text（入力）, converted_text（漢字→カタカナ）, audio_duration（未指定時は null）
    - output: frame_count（フレーム数）, frames（各フレームの time, volume, mouthOpen, mouthShape）
    - summary: total_duration（秒）, frame_interval（0.05）, mouth_shapes（使用した口形: A/Closed/E/I/O/U）

    例（要約）:
        {
          "input": {"text": "こんにちは、エンジニアカフェへようこそ", "converted_text": "コンニチハ、エンジニアカフェヘヨウコソ", "audio_duration": null},
          "output": {"frame_count": 57, "frames": [{"time": 0.0, "volume": 0.59..., "mouthOpen": 0.59..., "mouthShape": "O"}, ...]},
          "summary": {"total_duration": 2.8, "frame_interval": 0.05, "mouth_shapes": ["A", "Closed", "E", "I", "O", "U"]}
        }
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.agents.character_control_agent import (  # noqa: E402
    CharacterControlAgent,
)
from backend.utils.kanji_converter import KanjiConverter  # noqa: E402


def main():
    """
    コマンドラインからリップシンクデータ生成を実行する関数
    """
    parser = argparse.ArgumentParser(
        description="リップシンクデータ生成のテスト・確認用コマンドラインツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  %(prog)s "こんにちは"
  %(prog)s "こんにちは" --duration 2.5
  %(prog)s "Hello World" -d 1.0
  %(prog)s "エンジニアカフェへようこそ" --duration 3.0 --pretty
  %(prog)s "テスト" -d 2.0 --verbose
        """,
    )
    parser.add_argument(
        "text",
        type=str,
        metavar="TEXT",
        help="発話テキスト（必須）",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        required=False,
        help="音声の長さ（秒）。未指定の場合は文字数から自動計算",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="JSON出力を整形して表示",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="詳細なログを表示",
    )

    args = parser.parse_args()

    # ログレベルの設定
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s - %(message)s",
        )

    try:
        # CharacterControlAgentのインスタンスを作成
        agent = CharacterControlAgent()

        # 漢字→読みカナ変換を確認
        kanji_converter = KanjiConverter()
        converted_text = kanji_converter.convert_to_kana(args.text)

        # リップシンクデータを生成
        print("リップシンクデータ生成中...", file=sys.stderr)
        if args.duration:
            print(f"  音声長: {args.duration}秒", file=sys.stderr)
        else:
            print("  音声長: 未指定（文字数から自動計算）", file=sys.stderr)
        print(f"  テキスト: {args.text}", file=sys.stderr)
        if converted_text != args.text:
            print(f"  変換後: {converted_text}", file=sys.stderr)
        print("", file=sys.stderr)

        lipsync_data = agent.generate_lipsync_data(
            text=args.text,
            audio_duration=args.duration,
        )

        # 結果をJSON形式で出力
        result = {
            "input": {
                "audio_duration": args.duration,
                "text": args.text,
                "converted_text": converted_text,
            },
            "output": {
                "frame_count": len(lipsync_data),
                "frames": lipsync_data,
            },
            "summary": {
                "total_duration": (lipsync_data[-1]["time"] if lipsync_data else 0.0),
                "frame_interval": (
                    lipsync_data[1]["time"] - lipsync_data[0]["time"]
                    if len(lipsync_data) > 1
                    else 0.0
                ),
                "mouth_shapes": sorted(list(set(frame["mouthShape"] for frame in lipsync_data))),
            },
        }

        if args.pretty:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False))

        return 0

    except KeyboardInterrupt:
        print("\n中断されました", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"エラーが発生しました: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
