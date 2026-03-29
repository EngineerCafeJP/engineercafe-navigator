'use client';

import { useEffect, useMemo, useState } from 'react';
import MDEditor from '@uiw/react-md-editor';
import toast from 'react-hot-toast';
import {
  createKnowledge,
  getKnowledgeEditorConfig,
  updateKnowledge,
} from '@/lib/api/knowledge';
import {
  type KnowledgeEditorConfig,
  type KnowledgeItem,
  type MetadataFieldConfig,
  METADATA_FIELD_TYPES,
} from '@/types/knowledge';

interface KnowledgeFormData {
  id?: string;
  title: string;
  content: string;
  category: string;
  subcategory: string;
  language: 'ja' | 'en';
  source: string;
  metadata: Record<string, unknown>;
}

interface KnowledgeEditorProps {
  entry?: KnowledgeItem;
  onSave?: (entry: KnowledgeFormData) => Promise<void>;
  onCancel?: () => void;
}

export function KnowledgeEditor({ entry, onSave, onCancel }: KnowledgeEditorProps) {
  const metadataFieldTypes: Record<string, MetadataFieldConfig> = METADATA_FIELD_TYPES;
  const [formData, setFormData] = useState<KnowledgeFormData>({
    id: entry?.id,
    title: entry?.title || '',
    content: entry?.content || '',
    category: entry?.category || '',
    subcategory: entry?.subcategory || '',
    language: entry?.language === 'en' ? 'en' : 'ja',
    source: entry?.source || '',
    metadata: entry?.metadata || {},
  });
  const [loading, setLoading] = useState(false);
  const [dataLoading, setDataLoading] = useState(true);
  const [dataError, setDataError] = useState<string | null>(null);
  const [editorConfig, setEditorConfig] = useState<KnowledgeEditorConfig | null>(null);
  const [showCustomCategory, setShowCustomCategory] = useState(false);
  const [showCustomSubcategory, setShowCustomSubcategory] = useState(false);
  const [showCustomSource, setShowCustomSource] = useState(false);
  const [customCategory, setCustomCategory] = useState('');
  const [customSubcategory, setCustomSubcategory] = useState('');
  const [customSource, setCustomSource] = useState('');

  useEffect(() => {
    const loadData = async () => {
      try {
        setDataLoading(true);
        setDataError(null);
        setEditorConfig(await getKnowledgeEditorConfig());
      } catch (error) {
        console.error('Failed to load editor config:', error);
        setDataError(error instanceof Error ? error.message : 'Failed to load editor config');
      } finally {
        setDataLoading(false);
      }
    };

    loadData();
  }, []);

  const handleCategoryChange = (category: string) => {
    setFormData((prev) => {
      const nextMetadata =
        Object.keys(prev.metadata).length === 0 && editorConfig?.templates[category]
          ? { ...editorConfig.templates[category] }
          : prev.metadata;

      return {
        ...prev,
        category,
        subcategory: '',
        metadata: nextMetadata,
      };
    });
  };

  const handleCustomCategorySubmit = () => {
    if (customCategory.trim()) {
      handleCategoryChange(customCategory.trim());
      setShowCustomCategory(false);
      setCustomCategory('');
    }
  };

  const handleCustomSubcategorySubmit = () => {
    if (customSubcategory.trim()) {
      setFormData((prev) => ({ ...prev, subcategory: customSubcategory.trim() }));
      setShowCustomSubcategory(false);
      setCustomSubcategory('');
    }
  };

  const handleCustomSourceSubmit = () => {
    if (customSource.trim()) {
      setFormData((prev) => ({ ...prev, source: customSource.trim() }));
      setShowCustomSource(false);
      setCustomSource('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.title.trim()) {
      toast.error('タイトルは必須です');
      return;
    }

    if (!formData.content.trim()) {
      toast.error('コンテンツは必須です');
      return;
    }

    setLoading(true);

    try {
      if (onSave) {
        await onSave(formData);
      } else if (entry?.id) {
        await updateKnowledge(entry.id, formData);
        toast.success('更新しました');
      } else {
        await createKnowledge(formData);
        toast.success('作成しました');
        setFormData({
          title: '',
          content: '',
          category: '',
          subcategory: '',
          language: 'ja',
          source: '',
          metadata: {},
        });
      }
    } catch (error) {
      console.error('Save error:', error);
      toast.error(error instanceof Error ? error.message : '保存に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const handleMetadataChange = (key: string, value: string | string[]) => {
    setFormData((prev) => ({
      ...prev,
      metadata: {
        ...prev.metadata,
        [key]: value,
      },
    }));
  };

  const addMetadataField = () => {
    const key = prompt('メタデータのキーを入力してください:');
    if (key && key.trim()) {
      handleMetadataChange(key.trim(), '');
    }
  };

  const availableMetadataFields = useMemo(
    () =>
      Object.entries(metadataFieldTypes).filter(
        ([fieldKey]) => !Object.prototype.hasOwnProperty.call(formData.metadata, fieldKey),
      ),
    [formData.metadata, metadataFieldTypes],
  );

  const recommendedMetadataFields = useMemo(
    () => Object.keys(editorConfig?.templates[formData.category] || {}),
    [editorConfig?.templates, formData.category],
  );

  const renderMetadataField = (key: string, value: unknown) => {
    const fieldConfig: MetadataFieldConfig = metadataFieldTypes[key] || { type: 'text' };

    switch (fieldConfig.type) {
      case 'select':
        return (
          <select
            value={typeof value === 'string' ? value : ''}
            onChange={(e) => handleMetadataChange(key, e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="">選択してください...</option>
            {fieldConfig.options?.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        );
      case 'date':
        return (
          <input
            type="date"
            value={
              typeof value === 'string' && value
                ? new Date(value).toISOString().split('T')[0]
                : ''
            }
            onChange={(e) =>
              handleMetadataChange(
                key,
                e.target.value ? new Date(e.target.value).toISOString() : '',
              )
            }
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        );
      case 'tags': {
        const tagsArray = Array.isArray(value)
          ? value.filter((item): item is string => typeof item === 'string')
          : typeof value === 'string'
            ? value
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean)
            : [];

        return (
          <div className="flex-1">
            <input
              type="text"
              value={tagsArray.join(', ')}
              onChange={(e) => {
                const tags = e.target.value
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean);
                handleMetadataChange(key, tags);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="タグをカンマ区切りで入力 (例: tag1, tag2, tag3)"
            />
          </div>
        );
      }
      default:
        return (
          <input
            type="text"
            value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
            onChange={(e) => handleMetadataChange(key, e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="値"
          />
        );
    }
  };

  const removeMetadataField = (key: string) => {
    setFormData((prev) => {
      const nextMetadata = { ...prev.metadata };
      delete nextMetadata[key];
      return {
        ...prev,
        metadata: nextMetadata,
      };
    });
  };

  if (dataLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (dataError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700">設定の読み込みに失敗しました: {dataError}</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-2">タイトル *</label>
        <input
          id="title"
          type="text"
          value={formData.title}
          onChange={(e) =>
            setFormData((prev) => ({ ...prev, title: e.target.value.slice(0, 200) }))
          }
          maxLength={200}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          placeholder="ナレッジのタイトルを入力..."
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label htmlFor="category" className="block text-sm font-medium text-gray-700 mb-2">カテゴリ</label>
          <div className="space-y-2">
            <select
              id="category"
              value={showCustomCategory ? '__custom__' : formData.category}
              onChange={(e) => {
                if (e.target.value === '__custom__') {
                  setShowCustomCategory(true);
                } else {
                  setShowCustomCategory(false);
                  handleCategoryChange(e.target.value);
                }
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">カテゴリを選択...</option>
              {editorConfig?.categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
              <option value="__custom__">+ 新しいカテゴリを追加</option>
            </select>

            {showCustomCategory && (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={customCategory}
                  onChange={(e) => setCustomCategory(e.target.value)}
                  placeholder="新しいカテゴリ名"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <button
                  type="button"
                  onClick={handleCustomCategorySubmit}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  追加
                </button>
              </div>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="subcategory" className="block text-sm font-medium text-gray-700 mb-2">サブカテゴリ</label>
          <div className="space-y-2">
            <select
              id="subcategory"
              value={showCustomSubcategory ? '__custom__' : formData.subcategory}
              onChange={(e) => {
                if (e.target.value === '__custom__') {
                  setShowCustomSubcategory(true);
                } else {
                  setShowCustomSubcategory(false);
                  setFormData((prev) => ({ ...prev, subcategory: e.target.value }));
                }
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              disabled={!formData.category}
            >
              <option value="">サブカテゴリを選択...</option>
              {formData.category &&
                editorConfig?.subcategories[formData.category]?.map((subcat) => (
                  <option key={subcat} value={subcat}>
                    {subcat}
                  </option>
                ))}
              <option value="__custom__">+ 新しいサブカテゴリを追加</option>
            </select>

            {showCustomSubcategory && (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={customSubcategory}
                  onChange={(e) => setCustomSubcategory(e.target.value)}
                  placeholder="新しいサブカテゴリ名"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <button
                  type="button"
                  onClick={handleCustomSubcategorySubmit}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  追加
                </button>
              </div>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="language" className="block text-sm font-medium text-gray-700 mb-2">言語</label>
          <select
            id="language"
            value={formData.language}
            onChange={(e) =>
              setFormData((prev) => ({
                ...prev,
                language: e.target.value === 'en' ? 'en' : 'ja',
              }))
            }
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="ja">日本語</option>
            <option value="en">English</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">ソース</label>
          <div className="space-y-2">
            <select
              value={showCustomSource ? '__custom__' : formData.source}
              onChange={(e) => {
                if (e.target.value === '__custom__') {
                  setShowCustomSource(true);
                } else {
                  setShowCustomSource(false);
                  setFormData((prev) => ({ ...prev, source: e.target.value }));
                }
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">ソースを選択...</option>
              {editorConfig?.sources.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
              <option value="__custom__">+ 新しいソースを追加</option>
            </select>

            {showCustomSource && (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={customSource}
                  onChange={(e) => setCustomSource(e.target.value)}
                  placeholder="新しいソース名"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <button
                  type="button"
                  onClick={handleCustomSourceSubmit}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  追加
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div data-color-mode="light">
        <label className="block text-sm font-medium text-gray-700 mb-2">コンテンツ *</label>
        <MDEditor
          value={formData.content}
          onChange={(value) => setFormData((prev) => ({ ...prev, content: value || '' }))}
          height={400}
          preview="edit"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-700">メタデータ</label>
          {formData.category && editorConfig?.templates[formData.category] && (
            <button
              type="button"
              onClick={() => {
                const template =
                  editorConfig.templates[formData.category] || editorConfig.templates.default || {};
                setFormData((prev) => ({
                  ...prev,
                  metadata: { ...template },
                }));
              }}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              テンプレート適用
            </button>
          )}
        </div>

        <div className="space-y-3">
          {Object.entries(formData.metadata).map(([key, value]) => (
            <div key={key} className="border border-gray-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={key}
                    onChange={(e) => {
                      const newKey = e.target.value;
                      if (!newKey || newKey === key) {
                        return;
                      }
                      setFormData((prev) => {
                        const nextMetadata = { ...prev.metadata };
                        delete nextMetadata[key];
                        nextMetadata[newKey] = value;
                        return { ...prev, metadata: nextMetadata };
                      });
                    }}
                    className="px-2 py-1 text-sm font-medium border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-gray-50"
                    placeholder="キー名"
                  />
                  {metadataFieldTypes[key] && (
                    <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded">
                      {metadataFieldTypes[key].type}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeMetadataField(key)}
                  className="text-red-600 hover:text-red-800 text-sm"
                >
                  削除
                </button>
              </div>

              {renderMetadataField(key, value)}
            </div>
          ))}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={addMetadataField}
              className="text-blue-600 hover:text-blue-800 text-sm px-3 py-1 border border-blue-300 rounded-lg hover:bg-blue-50"
            >
              + カスタムフィールド
            </button>

            {availableMetadataFields.map(([fieldKey, config]) => {
              const defaultValue =
                config.type === 'tags'
                  ? []
                  : config.type === 'date'
                    ? new Date().toISOString()
                    : config.type === 'select' && config.options
                      ? config.options[0]
                      : '';

              return (
                <button
                  key={fieldKey}
                  type="button"
                  onClick={() => handleMetadataChange(fieldKey, defaultValue)}
                  className="text-gray-600 hover:text-gray-800 text-sm px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                >
                  + {fieldKey}
                </button>
              );
            })}

            {editorConfig?.templates.default && (
              <button
                type="button"
                onClick={() => {
                  setFormData((prev) => ({
                    ...prev,
                    metadata: { ...editorConfig.templates.default, ...prev.metadata },
                  }));
                }}
                className="text-green-600 hover:text-green-800 text-sm px-3 py-1 border border-green-300 rounded-lg hover:bg-green-50"
              >
                基本テンプレート適用
              </button>
            )}
          </div>

          {formData.category && editorConfig?.templates[formData.category] && (
            <div className="mt-2 p-3 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-2">
                推奨メタデータフィールド ({formData.category}):
              </p>
              <div className="flex flex-wrap gap-1">
                {recommendedMetadataFields.map((field) => (
                  <span key={field} className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
                    {field}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-6 border-t border-gray-200">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-6 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
          >
            キャンセル
          </button>
        )}
        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '保存中...' : entry?.id ? '更新' : '作成'}
        </button>
      </div>
    </form>
  );
}
