'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Toaster, toast } from 'react-hot-toast';
import { createKnowledge } from '@/lib/api/knowledge';
import { KnowledgeEditor } from '../components/KnowledgeEditor';

export default function NewKnowledgePage() {
  const router = useRouter();

  const handleSave = async (formData: Parameters<typeof createKnowledge>[0]) => {
    try {
      await createKnowledge(formData);
      toast.success('作成しました');
      router.push('/admin/knowledge');
    } catch (error) {
      console.error('Save error:', error);
      toast.error(error instanceof Error ? error.message : '保存に失敗しました');
      throw error;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex justify-between items-center">
              <h1 className="text-2xl font-bold text-gray-900">新規知識ベースエントリ作成</h1>
              <Link href="/admin/knowledge" className="text-gray-600 hover:text-gray-800">
                一覧に戻る
              </Link>
            </div>
          </div>

          <div className="p-6">
            <KnowledgeEditor
              onSave={handleSave}
              onCancel={() => router.push('/admin/knowledge')}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
