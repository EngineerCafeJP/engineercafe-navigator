export function getBackendApiUrl(): string {
  const url = process.env.BACKEND_API_URL;
  if (url) return url;
  if (process.env.NODE_ENV === 'development') return 'http://localhost:8000';
  throw new Error('BACKEND_API_URL environment variable is required');
}
