'use client';

import { useEffect, useState } from 'react';
<<<<<<< HEAD
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Toaster, toast } from 'react-hot-toast';
import { KnowledgeUploadForm } from '../components/KnowledgeUploadForm';
import {
  uploadKnowledgeFile,
  getKnowledgeEditorConfig,
  type KnowledgeEditorConfig,
} from '@/lib/api/knowledge';
=======
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Toaster, toast } from 'react-hot-toast';
import { downloadTemplate, getKnowledgeEditorConfig, uploadKnowledgeFile } from '@/lib/api/knowledge';
import type { KnowledgeEditorConfig } from '@/types/knowledge';
import {
  transformKnowledgeUploadData,
  validateKnowledgeUploadForm,
} from '../utils/validation';
import { KnowledgeUploadForm } from '../components/KnowledgeUploadForm';
>>>>>>> origin/develop

interface Preview {
  filename: string;
  fileSizeKb: number;
  textPreview: string | null;
  charCount: number | null;
}

export default function UploadKnowledgePage() {
  const router = useRouter();
<<<<<<< HEAD

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
=======
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

>>>>>>> origin/develop
  useEffect(() => {
    const loadConfig = async () => {
      try {
        setConfigLoading(true);
<<<<<<< HEAD
        const config = await getKnowledgeEditorConfig();
        setEditorConfig(config);
      } catch (error) {
        console.error('Failed to load editor config:', error);
        setConfigError(
          error instanceof Error ? error.message : 'エディタ設定の読み込みに失敗しました'
=======
        setConfigError(null);
        setEditorConfig(await getKnowledgeEditorConfig());
      } catch (error) {
        console.error('Failed to load editor config:', error);
        setConfigError(
          error instanceof Error ? error.message : 'エディタ設定の読み込みに失敗しました',
>>>>>>> origin/develop
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

<<<<<<< HEAD
    // Auto-populate title with filename (without extension) if title is empty
    if (!title) {
      const nameWithoutExt = selectedFile.name.replace(/\.[^.]+$/, '');
      setTitle(nameWithoutExt);
=======
    if (!title) {
      setTitle(selectedFile.name.replace(/\.[^.]+$/, ''));
>>>>>>> origin/develop
    }
  };

  const handleUpload = async () => {
<<<<<<< HEAD
    if (!file || !category) {
      toast.error('ファイルとカテゴリは必須です');
=======
    const validationErrors = validateKnowledgeUploadForm({
      file,
      category,
      language,
      title,
    });

    const firstError = Object.values(validationErrors)[0];
    if (firstError) {
      toast.error(firstError);
>>>>>>> origin/develop
      return;
    }

    setUploading(true);
    try {
<<<<<<< HEAD
      await uploadKnowledgeFile({
        file,
        category,
        language,
        title: title || undefined,
      });
=======
      await uploadKnowledgeFile(
        transformKnowledgeUploadData({
          file,
          category,
          language,
          title,
        }),
      );
>>>>>>> origin/develop
      toast.success('アップロードしました');
      router.push('/admin/knowledge');
    } catch (error) {
      console.error('Upload error:', error);
<<<<<<< HEAD
      toast.error(
        error instanceof Error ? error.message : 'アップロードに失敗しました'
      );
=======
      toast.error(error instanceof Error ? error.message : 'アップロードに失敗しました');
>>>>>>> origin/develop
    } finally {
      setUploading(false);
    }
  };

<<<<<<< HEAD
  const handleCancel = () => {
    router.push('/admin/knowledge');
=======
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
>>>>>>> origin/develop
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
<<<<<<< HEAD
          {/* Header */}
=======
>>>>>>> origin/develop
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

<<<<<<< HEAD
          {/* Config Error Alert */}
          {configError && (
            <div className="px-6 pt-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex justify-between items-center">
                <p className="text-red-700 text-sm">{configError}</p>
                <button
=======
          {configError && (
            <div className="px-6 pt-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex justify-between items-center gap-3">
                <p className="text-red-700 text-sm">{configError}</p>
                <button
                  type="button"
>>>>>>> origin/develop
                  onClick={() => window.location.reload()}
                  className="text-red-600 hover:text-red-800 text-sm underline"
                >
                  再読み込み
                </button>
              </div>
            </div>
          )}

<<<<<<< HEAD
          {/* Form */}
=======
>>>>>>> origin/develop
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
<<<<<<< HEAD
              onDrop={(e) => {
                e.preventDefault();
                setIsDragOver(false);
                const dropped = e.dataTransfer.files[0];
                if (dropped) handleFileSelect(dropped);
              }}
=======
>>>>>>> origin/develop
              onCategoryChange={setCategory}
              onLanguageChange={setLanguage}
              onTitleChange={setTitle}
              onUpload={handleUpload}
<<<<<<< HEAD
              onCancel={handleCancel}
=======
              onCancel={() => router.push('/admin/knowledge')}
              onDownload={handleDownload}
>>>>>>> origin/develop
            />
          </div>
        </div>
      </div>
    </div>
  );
}
