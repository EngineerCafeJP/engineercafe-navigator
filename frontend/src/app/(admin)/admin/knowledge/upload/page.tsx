'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Toaster, toast } from 'react-hot-toast';
import {
  KnowledgeUploadFileError,
  downloadTemplate,
  getKnowledgeEditorConfig,
  previewKnowledgeFile,
  uploadKnowledgeFile,
} from '@/lib/api/knowledge';
import type { KnowledgeEditorConfig } from '@/types/knowledge';
import type { KnowledgePreviewResult } from '@/lib/api/knowledge';
import {
  transformKnowledgeUploadData,
  validateKnowledgeUploadForm,
} from '../utils/validation';
import { KnowledgeUploadForm } from '../components/KnowledgeUploadForm';

interface Preview {
  filename: string;
  fileSizeKb: number;
  textPreview: string | null;
  charCount: number | null;
}

const PREVIEW_REFRESH_DEBOUNCE_MS = 300;

function deriveTitleFromFilename(filename: string): string {
  return filename.replace(/\.[^.]+$/, '');
}

function remapPreviewChunkTitles(
  chunkTitles: readonly string[],
  previousTitle: string,
  nextTitle: string,
): string[] {
  if (!previousTitle || !nextTitle || previousTitle === nextTitle) {
    return [...chunkTitles];
  }

  return chunkTitles.map((chunkTitle) => {
    if (chunkTitle === previousTitle) {
      return nextTitle;
    }
    if (chunkTitle.startsWith(`${previousTitle} `)) {
      return `${nextTitle}${chunkTitle.slice(previousTitle.length)}`;
    }
    return chunkTitle;
  });
}

export default function UploadKnowledgePage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [category, setCategory] = useState('');
  const [language, setLanguage] = useState<'ja' | 'en'>('ja');
  const [title, setTitle] = useState('');
  const [editorConfig, setEditorConfig] = useState<KnowledgeEditorConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewResult, setPreviewResult] = useState<KnowledgePreviewResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewRequestId = useRef(0);

  const clearSelectedFile = () => {
    previewRequestId.current += 1;
    setFile(null);
    setPreview(null);
    setPreviewResult(null);
    setPreviewLoading(false);
  };

  useEffect(() => {
    const loadConfig = async () => {
      try {
        setConfigLoading(true);
        setConfigError(null);
        setEditorConfig(await getKnowledgeEditorConfig());
      } catch (error) {
        console.error('Failed to load editor config:', error);
        setConfigError(
          error instanceof Error ? error.message : 'エディタ設定の読み込みに失敗しました',
        );
      } finally {
        setConfigLoading(false);
      }
    };

    loadConfig();
  }, []);

  const handleFileSelect = async (selectedFile: File) => {
    const ext = selectedFile.name.split('.').pop()?.toLowerCase();
    if (!ext || !['pdf', 'md', 'markdown'].includes(ext)) {
      clearSelectedFile();
      toast.error('PDF または Markdown ファイルのみ対応しています');
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      clearSelectedFile();
      toast.error('ファイルサイズは 10MB 以内にしてください');
      return;
    }

    let textPreview: string | null = null;
    let charCount: number | null = null;

    if (ext === 'md' || ext === 'markdown') {
      try {
        const fullText = await selectedFile.text();
        charCount = fullText.length;
        textPreview = fullText.slice(0, 500);
      } catch (error) {
        console.error('Failed to read file:', error);
        clearSelectedFile();
        toast.error('ファイルの読み込みに失敗しました');
        return;
      }
    }

    setFile(selectedFile);
    setPreview({
      filename: selectedFile.name,
      fileSizeKb: Math.round(selectedFile.size / 1024),
      textPreview,
      charCount,
    });

    if (!title) {
      setTitle(deriveTitleFromFilename(selectedFile.name));
    }
  };

  useEffect(() => {
    if (!file) {
      previewRequestId.current += 1;
      setPreviewLoading(false);
      setPreviewResult(null);
      return;
    }

    const requestId = previewRequestId.current + 1;
    previewRequestId.current = requestId;
    setPreviewLoading(true);
    setPreviewResult(null);

    const refreshPreview = window.setTimeout(() => {
      void (async () => {
        try {
          const result = await previewKnowledgeFile({
            file,
            language,
            category: category || undefined,
            title: title.trim() || undefined,
          });

          if (previewRequestId.current === requestId) {
            setPreviewResult(result);
          }
        } catch (err) {
          console.error('Preview failed:', err);
          if (previewRequestId.current === requestId) {
            setPreviewResult(null);
          }
        } finally {
          if (previewRequestId.current === requestId) {
            setPreviewLoading(false);
          }
        }
      })();
    }, PREVIEW_REFRESH_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(refreshPreview);
    };
  }, [category, file, language, title]);

  const displayPreviewResult = useMemo<KnowledgePreviewResult | null>(() => {
    if (!previewResult || !file) {
      return previewResult;
    }

    const fileTitle = deriveTitleFromFilename(file.name);
    const effectiveTitle = title.trim() || fileTitle;
    return {
      ...previewResult,
      chunk_titles: remapPreviewChunkTitles(previewResult.chunk_titles, fileTitle, effectiveTitle),
    };
  }, [file, previewResult, title]);

  const handleUpload = async () => {
    const validationErrors = validateKnowledgeUploadForm({
      file,
      category,
      language,
      title,
    });

    const firstError = Object.values(validationErrors)[0];
    if (firstError) {
      toast.error(firstError);
      return;
    }

    setUploading(true);
    try {
      await uploadKnowledgeFile(
        transformKnowledgeUploadData({
          file,
          category,
          language,
          title,
        }),
      );
      toast.success('アップロードしました');
      router.push('/admin/knowledge');
    } catch (error) {
      console.error('Upload error:', error);
      if (error instanceof KnowledgeUploadFileError && error.conflicts?.length) {
        const lines = error.conflicts.map(
          (c) =>
            `Chunk ${c.chunk_index !== null ? c.chunk_index + 1 : '?'}: 「${c.title}」は既存と重複`,
        );
        toast.error(lines.join('\n'), { duration: 8000 });
      } else {
        toast.error(error instanceof Error ? error.message : 'アップロードに失敗しました');
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (filename: string) => {
    try {
      const blob = await downloadTemplate({ filename, timestamp: Date.now() });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
      toast.error(error instanceof Error ? error.message : 'ファイルのダウンロードに失敗しました');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex justify-between items-center">
              <h1 className="text-2xl font-bold text-gray-900">ファイルアップロード</h1>
              <Link
                href="/admin/knowledge"
                className="text-gray-600 hover:text-gray-800 transition-colors"
              >
                一覧に戻る
              </Link>
            </div>
          </div>

          {configError && (
            <div className="px-6 pt-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex justify-between items-center gap-3">
                <p className="text-red-700 text-sm">{configError}</p>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="text-red-600 hover:text-red-800 text-sm underline"
                >
                  再読み込み
                </button>
              </div>
            </div>
          )}

          <div className="p-6">
            <KnowledgeUploadForm
              file={file}
              preview={preview}
              isDragOver={isDragOver}
              category={category}
              language={language}
              title={title}
              editorConfig={editorConfig}
              configLoading={configLoading}
              uploading={uploading}
              previewResult={displayPreviewResult}
              previewLoading={previewLoading}
              onFileSelect={handleFileSelect}
              onDragOver={() => setIsDragOver(true)}
              onDragLeave={() => setIsDragOver(false)}
              onCategoryChange={setCategory}
              onLanguageChange={setLanguage}
              onTitleChange={setTitle}
              onUpload={handleUpload}
              onCancel={() => router.push('/admin/knowledge')}
              onDownload={handleDownload}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
