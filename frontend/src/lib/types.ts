/**
 * Shared frontend language definitions.
 *
 * backend/api/knowledge_models.py currently validates knowledge mutations as
 * ja/en. Keep this local union narrow until generated backend API types are
 * available to the frontend build.
 */

export type SupportedLanguage = 'ja' | 'en';
