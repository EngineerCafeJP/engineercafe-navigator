"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Toaster, toast } from "react-hot-toast";
import { VocabularyCategory } from "@/types/vosk";
import { createVocabulary } from "@/lib/api/stt-vocabulary";
import {
  VocabularyFormData,
  ValidationErrors,
  validateVocabularyForm,
  transformVocabularyData,
} from "../utils/validation";
import { VocabularyForm } from "../components/form/VocabularyForm";

export default function VoskCreatePage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>(
    {},
  );
  const [formData, setFormData] = useState<VocabularyFormData>({
    word: "",
    reading: "",
    category: "",
    priority: 5,
  });

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

      setIsLoading(true);
      try {
        const apiData = transformVocabularyData(formData);
        await createVocabulary(apiData);
        toast.success("語彙を登録しました");
        router.push("/admin/vosk-settings");
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "登録に失敗しました";
        toast.error(message);
      } finally {
        setIsLoading(false);
      }
    },
    [formData, router],
  );

  const handleCancel = useCallback(() => {
    router.push("/admin/vosk-settings");
  }, [router]);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          {/* Header */}
          <div className="border-b border-gray-200 p-6">
            <h1 className="text-2xl font-bold text-gray-900">語彙を新規追加</h1>
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
              isLoading={isLoading}
              submitLabel="登録"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
