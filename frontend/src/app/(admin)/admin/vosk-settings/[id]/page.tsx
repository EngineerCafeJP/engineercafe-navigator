"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Toaster, toast } from "react-hot-toast";
import { VocabularyCategory, VocabularyItem } from "@/types/vosk";
import { getVocabularyDetail, updateVocabulary } from "@/lib/api/stt-vocabulary";
import {
  VocabularyFormData,
  ValidationErrors,
  validateVocabularyForm,
  transformVocabularyData,
} from "../utils/validation";
import { VocabularyForm } from "../components/form/VocabularyForm";

export default function VoskEditPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({});
  const [formData, setFormData] = useState<VocabularyFormData>({
    word: "",
    reading: "",
    category: "",
    priority: 5,
  });

  // 初期データ取得
  useEffect(() => {
    const fetchData = async () => {
      try {
        const item: VocabularyItem = await getVocabularyDetail(id);
        setFormData({
          word: item.word,
          reading: item.reading,
          category: item.category,
          priority: item.priority,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : "データの取得に失敗しました";
        toast.error(message);
        router.push("/admin/vosk-settings");
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [id, router]);

  const handleWordChange = useCallback((value: string) => {
    setFormData((prev) => ({ ...prev, word: value }));
    setValidationErrors({});
  }, []);

  const handleReadingChange = useCallback((value: string) => {
    setFormData((prev) => ({ ...prev, reading: value }));
    setValidationErrors({});
  }, []);

  const handleCategoryChange = useCallback((value: VocabularyCategory) => {
    setFormData((prev) => ({ ...prev, category: value }));
    setValidationErrors({});
  }, []);

  const handlePriorityChange = useCallback((value: number) => {
    setFormData((prev) => ({ ...prev, priority: value }));
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();

      // バリデーション
      const errors = validateVocabularyForm(formData);
      if (Object.keys(errors).length > 0) {
        setValidationErrors(errors);
        return;
      }

      setIsSaving(true);
      try {
        const apiData = transformVocabularyData(formData);
        await updateVocabulary(id, apiData);
        toast.success("語彙を更新しました");
        router.push("/admin/vosk-settings");
      } catch (error) {
        const message = error instanceof Error ? error.message : "更新に失敗しました";
        toast.error(message);
      } finally {
        setIsSaving(false);
      }
    },
    [formData, id, router]
  );

  const handleCancel = useCallback(() => {
    router.push("/admin/vosk-settings");
  }, [router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-8 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          {/* Header */}
          <div className="border-b border-gray-200 p-6">
            <h1 className="text-2xl font-bold text-gray-900">語彙を編集</h1>
          </div>

          {/* Content */}
          <div className="p-6">
            {/* Form */}
            <VocabularyForm
              data={formData}
              errors={validationErrors}
              onWordChange={handleWordChange}
              onReadingChange={handleReadingChange}
              onCategoryChange={handleCategoryChange}
              onPriorityChange={handlePriorityChange}
              onSubmit={handleSubmit}
              onCancel={handleCancel}
              isLoading={isSaving}
              submitLabel="更新"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
