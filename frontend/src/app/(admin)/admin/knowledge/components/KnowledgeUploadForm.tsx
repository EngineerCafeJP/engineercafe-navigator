import { KnowledgeEditorConfig } from '@/types/knowledge';

interface Preview {
  filename: string;
  fileSizeKb: number;
  textPreview: string | null;
  charCount: number | null;
}

interface KnowledgeUploadFormProps {
  // File state
  file: File | null;
  preview: Preview | null;
  isDragOver: boolean;

  // Form fields
  category: string;
  language: 'ja' | 'en';
  title: string;

  // Editor config
  editorConfig: KnowledgeEditorConfig | null;
  configLoading: boolean;

  // Loading states
  uploading: boolean;

  // Handlers
  onFileSelect: (file: File) => void;
  onDragOver: () => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onCategoryChange: (category: string) => void;
  onLanguageChange: (language: 'ja' | 'en') => void;
  onTitleChange: (title: string) => void;
  onUpload: () => void;
  onCancel: () => void;
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
  onFileSelect,
  onDragOver,
  onDragLeave,
  onDrop,
  onCategoryChange,
  onLanguageChange,
  onTitleChange,
  onUpload,
  onCancel,
}: KnowledgeUploadFormProps) {
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    onDragLeave();
    const dropped = e.dataTransfer.files[0];
    if (dropped) {
      onFileSelect(dropped);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      onFileSelect(selected);
    }
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); }} className="space-y-6">
      {/* 1. Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          onDragOver();
        }}
        onDragLeave={onDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragOver
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
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
                onChange={handleFileInputChange}
                className="hidden"
              />
            </label>
          </>
        )}
        <p className="text-xs text-gray-400 mt-2">
          対応形式: PDF, Markdown（最大 10MB）
        </p>
      </div>

      {/* 2. Preview Panel */}
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
                文字数: {preview.charCount?.toLocaleString('ja-JP')} / 5,000
              </div>
              <div className="bg-white border border-gray-100 rounded p-3 text-xs text-gray-600 font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                {preview.textPreview}
                {(preview.charCount ?? 0) > 500 && (
                  <span className="text-gray-400">... （以下省略）</span>
                )}
              </div>
            </>
          ) : (
            <p className="text-xs text-gray-500 italic">
              PDF ファイル - テキストプレビューは対応していません
            </p>
          )}
        </div>
      )}

      {/* 3. Category Select */}
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

      {/* 4. Language Radio */}
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
            <span className="text-sm text-gray-700">● 日本語</span>
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
            <span className="text-sm text-gray-700">○ English</span>
          </label>
        </div>
      </div>

      {/* 5. Title Input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          タイトル（任意）
        </label>
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

      {/* 6. Action Buttons */}
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
    </form>
  );
}
