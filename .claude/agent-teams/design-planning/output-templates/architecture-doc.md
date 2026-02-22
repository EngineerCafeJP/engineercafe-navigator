# アーキテクチャ設計: [機能名]

**作成日時**: YYYY-MM-DD HH:mm
**作成者**: Architect Agent
**プランドキュメント**: [リンク]
**ステータス**: Draft / Under Review / Approved

---

## 概要

[アーキテクチャの簡潔な説明]

---

## ファイル構成

### 新規作成するファイル

```
[フォルダ名]/
├── [new_file_1.py]    # [役割]
├── [new_file_2.py]    # [役割]
└── [new_file_3.tsx]   # [役割]
```

### 修正するファイル

- `path/to/existing_file.py` - [修正内容]
- `path/to/another_file.ts` - [修正内容]

---

## 各ファイルの機能定義

### `path/to/new_file_1.py`

**役割**: [このファイルの単一の責任]

**実装する関数・クラス**:

```python
def function_name(param1: Type1, param2: Type2) -> ReturnType:
    """
    [関数の説明]

    引数:
        param1: [説明]
        param2: [説明]

    戻り値:
        [説明]
    """
```

---

### `path/to/new_file_2.tsx`

**役割**: [このファイルの単一の責任]

**実装するコンポーネント**:

```typescript
interface ComponentProps {
  prop1: Type1;   // 必須、最大100文字、半角のみ
  prop2: Type2;   // 任意、0以上
}

function ComponentName(props: ComponentProps) {
  // [処理の説明]

  return (
    <div>
      {/* [返すUIの説明] */}
    </div>
  );
}
```

---

## ファイル間の依存関係

```
[new_file_1.py]
    ↓ インポート
[new_file_2.ts]
    ↓ 使用
[new_file_3.tsx]
```

**データの流れ**:

1. [new_file_1.py] でビジネスロジックを処理
2. [new_file_2.ts] でAPIとして公開
3. [new_file_3.tsx] でUIに表示

---

## API設計（該当する場合）

### エンドポイント: `POST /api/[endpoint]`

**リクエスト**:

```typescript
interface RequestBody {
  field1: string; // 必須、最大100文字、半角のみ
  field2: number; // 必須、0以上
}
```

**レスポンス**:

```typescript
interface ResponseBody {
  success: boolean;
  data: {
    id: string;
    field1: string;
  };
}
```

---

## データベース設計（該当する場合）

### テーブル: `table_name`

```sql
CREATE TABLE table_name (
  id UUID PRIMARY KEY,
  field1 VARCHAR(100) NOT NULL,
  field2 INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- インデックス
CREATE INDEX idx_table_field1 ON table_name(field1);
```

---

## 設計の根拠

### なぜこのファイル構成を選択したか

- [理由1]: 既存の[類似機能]と同じパターンを採用
- [理由2]: 1ファイル1責任を守るため、[機能A]と[機能B]を分離

### 既存パターンとの整合性

- [既存機能へのパス]と同様の構成を採用

### YAGNIの確認

- [機能X]は今回の要件に含まれていないため、実装しない
- 将来[機能Y]が必要になったら、その時に追加すればよい

---

## 実装例

### `path/to/new_file_1.py` の実装例

```python
# [ファイルの役割の説明]

def process_data(input_data: dict) -> dict:
    """
    データを処理する

    引数:
        input_data: 入力データ

    戻り値:
        処理済みデータ
    """
    # バリデーション
    if not input_data.get("field1"):
        raise ValueError("field1 is required")

    # 処理
    result = {
        "id": generate_id(),
        "field1": input_data["field1"],
        "processed_at": datetime.now()
    }

    return result
```

---

## セキュリティ考慮（該当する場合）

- **入力バリデーション**: すべての入力を検証する
- **認証・認可**: [具体的な方法]
- **SQLインジェクション対策**: パラメータ化クエリを使用

---

## パフォーマンス考慮（該当する場合）

- **目標応答時間**: [XX]秒以内
- **最適化ポイント**: [具体的な方法]

---

## エラーハンドリング

```python
try:
    result = process_data(input_data)
except ValueError as e:
    # バリデーションエラー
    return {"success": False, "error": str(e)}
except Exception as e:
    # 予期しないエラー
    log_error(e)
    return {"success": False, "error": "Internal error"}
```

---

## テスト戦略

### 単体テスト

- [new_file_1.py] の各関数を独立してテスト

### 統合テスト

- API全体の動作をテスト

---

## 備考

- [その他の重要な情報]
