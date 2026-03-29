'use client';

import Link from 'next/link';
import { type MouseEvent, useCallback, useState } from 'react';
import useSWR from 'swr';
import { Toaster, toast } from 'react-hot-toast';
import { deleteKnowledge, getKnowledgeList } from '@/lib/api/knowledge';
import { KnowledgeTable } from './components/KnowledgeTable';

export default function KnowledgeAdminPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState('');
  const [category, setCategory] = useState('');

  const { data, error, mutate } = useSWR({ search, language, category, page }, getKnowledgeList);

  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    mutate();
  }, [mutate]);

  const handleDelete = useCallback(async (id: string) => {
    if (!confirm('削除してもよろしいですか？')) return;

    try {
      await deleteKnowledge(id);
      toast.success('削除しました');
      mutate();
    } catch (error) {
      console.error('Delete error:', error);
      toast.error(error instanceof Error ? error.message : '削除に失敗しました');
    }
  }, [mutate]);

  const handleHardNavigation = useCallback((event: MouseEvent<HTMLAnchorElement>, href: string) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }

    event.preventDefault();
    window.location.assign(href);
  }, []);

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-700">エラーが発生しました: {error.message}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex justify-between items-center">
              <h1 className="text-2xl font-bold text-gray-900">知識ベース管理</h1>
              <div className="flex gap-3">
                <Link
                  href="/admin/knowledge/upload"
                  prefetch={false}
                  onClick={(event) => handleHardNavigation(event, '/admin/knowledge/upload')}
                  className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors"
                >
                  ファイルアップロード
                </Link>
                <Link
                  href="/admin/knowledge/new"
                  prefetch={false}
                  onClick={(event) => handleHardNavigation(event, '/admin/knowledge/new')}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
                >
                  新規作成
                </Link>
              </div>
            </div>
          </div>

          <div className="p-6">
            <form onSubmit={handleSearch} className="mb-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">検索</label>
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="コンテンツで検索..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">言語</label>
                  <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="">すべて</option>
                    <option value="ja">日本語</option>
                    <option value="en">英語</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">カテゴリ</label>
                  <input
                    type="text"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="カテゴリ名..."
                  />
                </div>

                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700 transition-colors"
                  >
                    検索
                  </button>
                </div>
              </div>
            </form>

            {data ? (
              <KnowledgeTable
                data={data}
                onDelete={handleDelete}
                page={page}
                onPageChange={setPage}
              />
            ) : (
              <div className="flex justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
