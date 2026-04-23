import type { KnowledgeEditorConfig } from '@/types/knowledge';
import type { KnowledgePreviewResult } from '@/lib/api/knowledge';

interface Preview {
  filename: string;
  fileSizeKb: number;
  textPreview: string | null;
  charCount: number | null;
}

interface KnowledgeUploadFormProps {
  file: File | null;
  preview: Preview | null;
  isDragOver: boolean;
  category: string;
  language: 'ja' | 'en';
  title: string;
  editorConfig: KnowledgeEditorConfig | null;
  configLoading: boolean;
  uploading: boolean;
  previewResult: KnowledgePreviewResult | null;
  previewLoading: boolean;
  onFileSelect: (file: File) => Promise<void> | void;
  onDragOver: () => void;
  onDragLeave: () => void;
  onCategoryChange: (category: string) => void;
  onLanguageChange: (language: 'ja' | 'en') => void;
  onTitleChange: (title: string) => void;
  onUpload: () => void;
  onCancel: () => void;
  onDownload: (filename: string) => Promise<void>;
}

export function KnowledgeUploadForm({
  file,
  preview,
  isDragOver,
  category,
  language,
  title,
  editorConfig,
  configLoading,
  uploading,
  previewResult,
  previewLoading,
  onFileSelect,
  onDragOver,
  onDragLeave,
  onCategoryChange,
  onLanguageChange,
  onTitleChange,
  onUpload,
  onCancel,
  onDownload,
}: KnowledgeUploadFormProps) {
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    onDragLeave();
    const dropped = e.dataTransfer.files[0];
    if (dropped) {
      onFileSelect(dropped);
    }
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
      }}
      className="space-y-6"
    >
      <div
        onDragOver={(e) => {
          e.preventDefault();
          onDragOver();
        }}
        onDragLeave={onDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        {file ? (
          <p className="text-gray-700 font-medium">📄 {file.name}</p>
        ) : (
          <>
            <p className="text-gray-600 font-medium mb-2">☁ ファイルをドラッグ&ドロップ</p>
            <p className="text-gray-500 text-sm mb-3">または</p>
            <label className="cursor-pointer mb-3 block">
              <span className="inline-block bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
                ファイルを選択
              </span>
              <input
                type="file"
                accept=".pdf,.md,.markdown"
                onChange={(e) => {
                  const selected = e.target.files?.[0];
                  if (selected) {
                    onFileSelect(selected);
                  }
                }}
                className="hidden"
              />
            </label>
          </>
        )}
        <p className="text-xs text-gray-400 mt-2">対応形式: PDF, Markdown（最大 10MB）</p>
      </div>

      {preview && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
          <div className="flex justify-between items-center">
            <span className="font-medium text-gray-700">{preview.filename}</span>
            <span className="text-sm text-gray-500">
              ファイルサイズ: {preview.fileSizeKb} KB
            </span>
          </div>

          {preview.textPreview !== null ? (
            <>
              <div className="text-xs text-gray-500">
                文字数: {preview.charCount?.toLocaleString('ja-JP')} / 50,000
              </div>
              <div className="bg-white border border-gray-100 rounded p-3 text-xs text-gray-600 font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                {preview.textPreview}
                {(preview.charCount ?? 0) > 500 && (
                  <span className="text-gray-400">... （以下省略）</span>
                )}
              </div>
            </>
          ) : null}

          <div className="space-y-3 border-t border-gray-200 pt-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-gray-600">登録前プレビュー</span>
              {previewResult ? (
                <span className="text-xs text-gray-500">
                  {previewResult.file_type === 'pdf' ? 'PDF' : 'Markdown'}
                </span>
              ) : null}
            </div>

            {previewLoading ? (
              <div className="bg-white border border-gray-100 rounded p-3 space-y-2 animate-pulse">
                <div className="h-3 w-28 rounded bg-gray-200" />
                <div className="h-3 w-full rounded bg-gray-200" />
                <div className="h-3 w-5/6 rounded bg-gray-200" />
              </div>
            ) : previewResult ? (
              <div className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="bg-white border border-gray-100 rounded p-3">
                    <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">
                      推定チャンク数
                    </div>
                    <div className="mt-1 text-sm font-semibold text-gray-900">
                      {previewResult.estimated_chunks.toLocaleString('ja-JP')}
                    </div>
                  </div>
                  <div className="bg-white border border-gray-100 rounded p-3">
                    <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">
                      抽出文字数
                    </div>
                    <div className="mt-1 text-sm font-semibold text-gray-900">
                      {previewResult.total_chars.toLocaleString('ja-JP')}
                    </div>
                  </div>
                </div>

                <div className="bg-white border border-gray-100 rounded p-3 space-y-2">
                  <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">
                    抽出テキスト（先頭 1,500 文字）
                  </div>
                  <div className="text-xs text-gray-600 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {previewResult.extracted_preview}
                  </div>
                </div>

                <div className="bg-white border border-gray-100 rounded p-3 space-y-2">
                  <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">
                    登録予定タイトル
                  </div>
                  <ul className="space-y-1 text-xs text-gray-600">
                    {previewResult.chunk_titles.map((chunkTitle) => (
                      <li key={chunkTitle} className="rounded bg-gray-50 px-2 py-1">
                        {chunkTitle}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-500 italic">
                ファイル解析プレビューを取得できませんでした
              </p>
            )}
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          カテゴリ <span className="text-red-500">*</span>
        </label>
        {configLoading ? (
          <div className="h-10 bg-gray-200 rounded-lg animate-pulse" />
        ) : (
          <select
            value={category}
            onChange={(e) => onCategoryChange(e.target.value)}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="">カテゴリを選択...</option>
            {editorConfig?.categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-3">言語</label>
        <div className="flex gap-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="language"
              value="ja"
              checked={language === 'ja'}
              onChange={() => onLanguageChange('ja')}
              className="accent-blue-600"
            />
            <span className="text-sm text-gray-700">日本語</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="language"
              value="en"
              checked={language === 'en'}
              onChange={() => onLanguageChange('en')}
              className="accent-blue-600"
            />
            <span className="text-sm text-gray-700">English</span>
          </label>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">タイトル（任意）</label>
        <input
          type="text"
          value={title}
          onChange={(e) => onTitleChange(e.target.value.slice(0, 200))}
          maxLength={200}
          placeholder="ナレッジのタイトル..."
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <p className="mt-1 text-xs text-gray-400">
          空欄の場合はファイル名がタイトルになります
        </p>
      </div>

      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors font-medium"
        >
          キャンセル
        </button>
        <button
          type="button"
          onClick={onUpload}
          disabled={!file || !category || uploading}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {uploading ? 'アップロード中...' : 'アップロード'}
        </button>
      </div>

      <div className="bg-gradient-to-r from-blue-50 to-cyan-50 border-2 border-blue-300 rounded-lg p-6 mt-8 shadow-sm">
        <div className="space-y-4">
          <div>
            <h3 className="font-bold text-base text-blue-900">複数の知識を一度に登録する方法</h3>
            <p className="text-sm text-blue-800 mt-2">
              テンプレートをダウンロードして、複数のエントリを記入してからアップロードしてください。
            </p>
          </div>

          <ul className="text-sm text-blue-800 space-y-2 ml-2">
            <li>1. 下のボタンからテンプレートまたはガイドをダウンロード</li>
            <li>2. 複数のエントリを記入して、ファイルを保存</li>
            <li>3. このページから完成したファイルをアップロード</li>
          </ul>

          <div className="space-y-2 pt-3 border-t border-blue-200">
            <button
              type="button"
              onClick={() => onDownload('knowledge-template.md')}
              className="w-full px-4 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors text-sm"
            >
              テンプレート（Markdown）DL
            </button>
            <button
              type="button"
              onClick={() => onDownload('knowledge-pdf-template-guide.md')}
              className="w-full px-4 py-2.5 bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700 transition-colors text-sm"
            >
              PDF作成ガイド DL
            </button>
          </div>

          <p className="text-xs text-blue-700 bg-white/60 p-2 rounded border border-blue-100">
            1つの Markdown ファイルに複数エントリをまとめて、まとめて登録できます。
          </p>
        </div>
      </div>
    </form>
  );
}
