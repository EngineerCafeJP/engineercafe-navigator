import {
  type KnowledgeCategoriesResponse,
  type KnowledgeEditorConfig,
  type KnowledgeItem,
  type KnowledgeListResponse,
  type KnowledgeResponse,
  type KnowledgeUploadConflict,
} from '@/types/knowledge';

export type {
  KnowledgeCategoriesResponse,
  KnowledgeEditorConfig,
  KnowledgeItem,
  KnowledgeListResponse,
  KnowledgeResponse,
};
export type { KnowledgeUploadConflict } from '@/types/knowledge';

interface KnowledgeTemplatesResponse {
  templates: Record<string, Record<string, unknown>>;
  availableCategories: string[];
}

interface KnowledgeMutationPayload {
  title: string;
  content: string;
  category: string;
  language: string;
  subcategory?: string;
  source?: string;
  metadata?: Record<string, unknown>;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      searchParams.set(key, String(value));
    }
  });

  const query = searchParams.toString();
  return query ? `?${query}` : '';
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  const text = await response.text();
  if (!text) {
    return fallback;
  }

  try {
    const data = JSON.parse(text) as {
      detail?: string;
      error?: string;
      message?: string;
    };
    return data.error || data.detail || data.message || fallback;
  } catch {
    return text;
  }
}

export async function getKnowledgeList(params: {
  search?: string;
  category?: string;
  language?: string;
  page?: number;
  limit?: number;
}): Promise<KnowledgeListResponse> {
  const response = await fetch(
    `/api/admin/knowledge${buildQuery({
      search: params.search,
      category: params.category,
      language: params.language,
      page: params.page ?? 1,
      limit: params.limit ?? 20,
    })}`,
  );

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to fetch knowledge entries'));
  }

  return response.json();
}

export async function getKnowledgeById(id: string): Promise<KnowledgeItem> {
  const response = await fetch(`/api/admin/knowledge/${id}`);

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to fetch knowledge entry'));
  }

  return response.json();
}

export async function createKnowledge(body: KnowledgeMutationPayload): Promise<KnowledgeItem> {
  const response = await fetch('/api/admin/knowledge', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to create knowledge entry'));
  }

  const json = (await response.json()) as KnowledgeResponse | KnowledgeItem;
  return 'data' in json ? json.data : json;
}

export async function updateKnowledge(
  id: string,
  body: Partial<KnowledgeMutationPayload>,
): Promise<KnowledgeItem> {
  const response = await fetch(`/api/admin/knowledge/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to update knowledge entry'));
  }

  const json = (await response.json()) as KnowledgeResponse | KnowledgeItem;
  return 'data' in json ? json.data : json;
}

export async function deleteKnowledge(id: string): Promise<void> {
  const response = await fetch(`/api/admin/knowledge/${id}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to delete knowledge entry'));
  }
}

export class KnowledgeUploadFileError extends Error {
  conflicts?: KnowledgeUploadConflict[];
  constructor(detail: { message: string; conflicts?: KnowledgeUploadConflict[] }) {
    super(detail.message);
    this.name = 'KnowledgeUploadFileError';
    this.conflicts = detail.conflicts;
  }
}

export async function uploadKnowledgeFile(params: {
  file: File;
  category: string;
  language: string;
  title?: string;
}): Promise<KnowledgeItem> {
  const formData = new FormData();
  formData.append('file', params.file);
  formData.append('category', params.category);
  formData.append('language', params.language);
  if (params.title) {
    formData.append('title', params.title);
  }

  const response = await fetch('/api/admin/knowledge/upload', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text();
    if (text) {
      try {
        const data = JSON.parse(text) as {
          detail?: string | { message: string; conflicts?: KnowledgeUploadConflict[] };
          error?: string;
          message?: string;
        };
        if (typeof data.detail === 'object' && data.detail !== null) {
          throw new KnowledgeUploadFileError(data.detail);
        }
        throw new Error(
          data.error ||
            (typeof data.detail === 'string' ? data.detail : '') ||
            data.message ||
            'Failed to upload knowledge file',
        );
      } catch (e) {
        if (e instanceof KnowledgeUploadFileError) throw e;
        if (e instanceof Error) throw e;
        throw new Error(text);
      }
    }
    throw new Error('Failed to upload knowledge file');
  }

  const json = (await response.json()) as KnowledgeResponse | KnowledgeItem;
  return 'data' in json ? json.data : json;
}

export async function getKnowledgeEditorConfig(): Promise<KnowledgeEditorConfig> {
  const [editorConfigResponse, templatesResponse] = await Promise.all([
    fetch('/api/admin/knowledge/editor-config'),
    fetch('/api/admin/knowledge/metadata-templates'),
  ]);

  if (!editorConfigResponse.ok) {
    throw new Error(await getErrorMessage(editorConfigResponse, 'Failed to fetch editor config'));
  }

  if (!templatesResponse.ok) {
    throw new Error(await getErrorMessage(templatesResponse, 'Failed to fetch metadata templates'));
  }

  const editorConfig = (await editorConfigResponse.json()) as KnowledgeCategoriesResponse;
  const templates = (await templatesResponse.json()) as KnowledgeTemplatesResponse;

  return {
    ...editorConfig,
    templates: templates.templates,
    availableCategories: templates.availableCategories,
  };
}

export async function downloadTemplate(params: {
  filename: string;
  timestamp: number;
}): Promise<Blob> {
  const response = await fetch(
    `/api/admin/knowledge/templates/${encodeURIComponent(params.filename)}${buildQuery({
      t: params.timestamp,
    })}`,
  );

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to download template'));
  }

  return response.blob();
}
