# /project-overview - プロジェクト概要

## 概要
プロジェクトの全体像を表示します。新しいメンバーやコンテキストリフレッシュに使用。

## 実行内容

1. **アーキテクチャ概要**
   - 技術スタック
   - ディレクトリ構成
   - エージェント一覧

2. **開発状況**
   - LangGraph 移行の進捗
   - 各フェーズのステータス
   - 担当者割り当て

3. **重要なルール**
   - Tailwind CSS バージョン制約
   - Embedding 次元数
   - モバイル対応の注意点

## 出力形式

```
🏗 Engineer Cafe Navigator

📚 技術スタック:
- Frontend: Next.js 15 + Mastra + TypeScript
- Backend: Python + LangGraph (移行中)
- Database: Supabase + PostgreSQL + pgvector

🤖 エージェント (12個):
- RouterAgent, BusinessInfoAgent, FacilityAgent...

📊 移行進捗: [X]% 完了

⚠️ 重要ルール:
- Tailwind CSS v3.4.17 必須
- OpenAI Embeddings 1536次元
```

## 使用例

Cursor で「プロジェクトの概要を教えて」と言うと実行
