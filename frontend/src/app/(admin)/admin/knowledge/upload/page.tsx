'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Toaster, toast } from 'react-hot-toast';
import { KnowledgeUploadForm } from '../components/KnowledgeUploadForm';
import {
  uploadKnowledgeFile,
  getKnowledgeEditorConfig,
  type KnowledgeEditorConfig,
} from '@/lib/api/knowledge';

interface Preview {
  filename: string;
  fileSizeKb: number;
  textPreview: string | null;
  charCount: number | null;
}

export default function UploadKnowledgePage() {
  const router = useRouter();

  // File state
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);

  // Form fields
  const [category, setCategory] = useState('');
  const [language, setLanguage] = useState<'ja' | 'en'>('ja');
  const [title, setTitle] = useState('');

  // Editor config
  const [editorConfig, setEditorConfig] = useState<KnowledgeEditorConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);

  // Loading states
  const [uploading, setUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  // Fetch editor config on mount
  useEffect(() => {
    const loadConfig = async () => {
      try {
        setConfigLoading(true);
        const config = await getKnowledgeEditorConfig();
        setEditorConfig(config);
      } catch (error) {
        console.error('Failed to load editor config:', error);
        setConfigError(
          error instanceof Error ? error.message : 'エディタ設定の読み込みに失敗しました'
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
      toast.error('PDF または Markdown ファイルのみ対応しています');
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
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

    // Auto-populate title with filename (without extension) if title is empty
    if (!title) {
      const nameWithoutExt = selectedFile.name.replace(/\.[^.]+$/, '');
      setTitle(nameWithoutExt);
    }
  };

  const handleUpload = async () => {
    if (!file || !category) {
      toast.error('ファイルとカテゴリは必須です');
      return;
    }

    setUploading(true);
    try {
      await uploadKnowledgeFile({
        file,
        category,
        language,
        title: title || undefined,
      });
      toast.success('アップロードしました');
      router.push('/admin/knowledge');
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(
        error instanceof Error ? error.message : 'アップロードに失敗しました'
      );
    } finally {
      setUploading(false);
    }
  };

  const handleCancel = () => {
    router.push('/admin/knowledge');
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          {/* Header */}
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

          {/* Config Error Alert */}
          {configError && (
            <div className="px-6 pt-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex justify-between items-center">
                <p className="text-red-700 text-sm">{configError}</p>
                <button
                  onClick={() => window.location.reload()}
                  className="text-red-600 hover:text-red-800 text-sm underline"
                >
                  再読み込み
                </button>
              </div>
            </div>
          )}

          {/* Form */}
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
              onFileSelect={handleFileSelect}
              onDragOver={() => setIsDragOver(true)}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragOver(false);
                const dropped = e.dataTransfer.files[0];
                if (dropped) handleFileSelect(dropped);
              }}
              onCategoryChange={setCategory}
              onLanguageChange={setLanguage}
              onTitleChange={setTitle}
              onUpload={handleUpload}
              onCancel={handleCancel}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
