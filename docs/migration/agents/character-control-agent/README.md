# Character Control Agent

> 3Dキャラクターの表情・アニメーション・リップシンクを制御するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **takegg0311** | メイン実装 |
| **YukitoLyn** | レビュー・サポート |

## 概要

Character Control Agentは、VRM形式の3Dキャラクターの表情、アニメーション、リップシンク（口パク）を制御します。他のエージェントからの感情情報や音声データを受け取り、キャラクターの動作に変換します。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **表情制御** | 感情に応じた顔の表情を設定 |
| **アニメーション選択** | 状況に応じたアニメーションを選択 |
| **リップシンク生成** | 音声データから口の動きを生成 |
| **状態遷移** | 表情・アニメーションの滑らかな遷移 |

### 責任範囲外

- 音声生成（VoiceOutputAgentの責務）
- 感情検出（EmotionManagerの責務）
- 3Dレンダリング（フロントエンドの責務）

## アーキテクチャ上の位置づけ

```
[他のエージェント]
       │
       ▼ emotion, audioData
┌──────────────────────────┐
│ Character Control Agent  │ ← このエージェント
└───────────┬──────────────┘
            │
    ┌───────┼───────┐
    ▼       ▼       ▼
┌──────┐ ┌──────┐ ┌──────────┐
│表情   │ │アニメ│ │リップシンク│
│マッピング│ │選択  │ │  解析    │
└──────┘ └──────┘ └──────────┘
            │
            ▼
┌──────────────────────────┐
│   フロントエンド (VRM)    │
└──────────────────────────┘
```

## 入力仕様

### CharacterControlRequest

```typescript
interface CharacterControlRequest {
  emotion?: string;           // 感情タグ
  text?: string;              // テキスト（感情分析用）
  audioData?: ArrayBuffer;    // 音声データ（リップシンク用）
  duration?: number;          // アニメーション時間
  intensity?: number;         // 感情の強度 (0-1)
  agentName?: string;         // 呼び出し元エージェント名
}
```

## 出力仕様

### CharacterControlResponse

```typescript
interface CharacterControlResponse {
  success: boolean;
  expression?: string;        // 表情名
  animation?: string;         // アニメーション名
  lipSyncData?: LipSyncFrame[];  // リップシンクデータ
  emotionIntensity?: number;  // 感情強度
  error?: string;
}

interface LipSyncFrame {
  time: number;               // タイムスタンプ (ms)
  volume: number;             // 音量 (0-1)
  mouthOpen: number;          // 口の開き具合 (0-1)
  mouthShape: 'A' | 'I' | 'U' | 'E' | 'O' | 'Closed';
}
```

## 感情から表情へのマッピング

| 感情タグ | VRM表情 | アニメーション |
|---------|--------|--------------|
| `happy` | happy | greeting |
| `sad` | sad | thinking |
| `angry` | angry | explaining |
| `relaxed` | neutral | idle |
| `surprised` | surprised | greeting |
| `neutral` | neutral | idle |

## リップシンクシステム

### 口の形状（5母音 + 閉）

| 形状 | 説明 | トリガー |
|-----|------|---------|
| A | 口を大きく開く | 「あ」音 |
| I | 横に引く | 「い」音 |
| U | 口をすぼめる | 「う」音 |
| E | 少し開く | 「え」音 |
| O | 丸く開く | 「お」音 |
| Closed | 閉じる | 無音時 |

### リップシンク生成フロー

```
[音声データ]
     │
     ▼
┌─────────────┐
│ キャッシュ確認 │
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
[キャッシュ] [解析]
  あり      │
   │        ▼
   │   ┌──────────┐
   │   │周波数解析 │
   │   └────┬─────┘
   │        │
   │        ▼
   │   ┌──────────┐
   │   │口形状決定 │
   │   └────┬─────┘
   │        │
   └────┬───┘
        ▼
   [LipSyncFrame[]]
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/character-control-agent.ts
engineer-cafe-navigator-repo/src/lib/lip-sync-analyzer.ts
engineer-cafe-navigator-repo/src/lib/lip-sync-cache.ts
engineer-cafe-navigator-repo/src/lib/emotion-mapping.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `processCharacterControl()` | メイン制御処理 |
| `getExpressionFromEmotion()` | 感情→表情変換 |
| `getAnimationForEmotion()` | 感情→アニメーション変換 |
| `generateLipSyncData()` | リップシンク生成 |
| `transitionEmotion()` | 感情遷移処理 |

## LangGraph移行後の設計

### ノード定義

```python
def character_control_node(state: WorkflowState) -> dict:
    """キャラクター制御ノード"""
    emotion = state.get("emotion", "neutral")
    audio_data = state.get("audio_data")

    # 表情とアニメーションを決定
    expression = map_emotion_to_expression(emotion)
    animation = map_emotion_to_animation(emotion)

    # リップシンク生成（音声データがある場合）
    lip_sync_data = None
    if audio_data:
        lip_sync_data = generate_lip_sync(audio_data)

    return {
        "character_control": {
            "expression": expression,
            "animation": animation,
            "lip_sync_data": lip_sync_data
        }
    }
```

## パフォーマンス最適化

### リップシンクキャッシュ

- **キャッシュキー**: 音声データのハッシュ値
- **保存先**: メモリ + localStorage
- **有効期限**: 7日間
- **最大サイズ**: 10MB / 100エントリ

### 処理時間目標

| 処理 | 目標時間 |
|-----|---------|
| 表情マッピング | 10ms以下 |
| リップシンク（キャッシュあり） | 50ms以下 |
| リップシンク（新規解析） | 1-3秒 |

## モバイル対応

### 既知の制限

- **iOS Safari**: AudioContext制限によりリップシンク生成が失敗する場合あり
- **対策**: フォールバックリップシンク（単純な口パク）を使用

```typescript
private generateFallbackLipSync(audioByteLength: number): LipSyncFrame[] {
  // 音声サイズから推定した単純な口パクパターン
}
```

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] 感情→表情マッピングを把握した
- [ ] リップシンク解析の仕組みを理解した
- [ ] キャッシュシステムを理解した
- [ ] モバイル制限と対策を確認した
- [ ] VRMフォーマットの基本を理解した

## 関連ドキュメント

- [Voice Agent](../voice-agent/README.md) - 音声処理
- [Emotion Mapping](../../lib/emotion-mapping.md) - 感情マッピング
- [Lip Sync Analyzer](../../lib/lip-sync-analyzer.md) - リップシンク解析
