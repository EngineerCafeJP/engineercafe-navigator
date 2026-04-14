'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

const VRM_EMOTIONS = [
  { value: '', label: '指定なし（テキスト内タグ優先）' },
  { value: 'neutral', label: 'neutral' },
  { value: 'happy', label: 'happy' },
  { value: 'sad', label: 'sad' },
  { value: 'angry', label: 'angry' },
  { value: 'surprised', label: 'surprised' },
  { value: 'relaxed', label: 'relaxed' },
] as const;

type TtsPreview = {
  url: string;
  format: string;
  durationMs: number | null;
};

async function measureAudioDurationMs(blob: Blob): Promise<number | null> {
  if (typeof window === 'undefined') {
    return null;
  }
  const w = window as Window & { webkitAudioContext?: typeof AudioContext };
  const AC = typeof AudioContext !== 'undefined' ? AudioContext : w.webkitAudioContext ?? null;
  if (!AC) {
    return null;
  }
  const ctx = new AC();
  try {
    const ab = await blob.arrayBuffer();
    const audioBuffer = await ctx.decodeAudioData(ab.slice(0));
    const ms = Math.round(audioBuffer.duration * 1000);
    return Number.isFinite(ms) && ms >= 0 ? ms : null;
  } catch {
    return null;
  } finally {
    void ctx.close();
  }
}

function extensionForMime(mime: string): string {
  if (mime === 'audio/mpeg') return 'mp3';
  if (mime === 'audio/wav') return 'wav';
  return 'bin';
}

const FALLBACK_TTS_PROVIDERS: { id: string; label: string }[] = [
  { id: 'voicevox', label: 'VoiceVox' },
  { id: 'piper', label: 'Piper-plus' },
  { id: 'google', label: 'Google Cloud TTS' },
];

function parseTtsProviders(data: unknown): { id: string; label: string }[] {
  if (!data || typeof data !== 'object' || !('ttsProviders' in data)) {
    return FALLBACK_TTS_PROVIDERS;
  }
  const raw = (data as { ttsProviders: unknown }).ttsProviders;
  if (!Array.isArray(raw) || raw.length === 0) {
    return FALLBACK_TTS_PROVIDERS;
  }
  const out: { id: string; label: string }[] = [];
  for (const item of raw) {
    if (item && typeof item === 'object' && 'id' in item) {
      const id = String((item as { id: unknown }).id);
      if (id) {
        const label =
          'label' in item && typeof (item as { label: unknown }).label === 'string'
            ? (item as { label: string }).label
            : id;
        out.push({ id, label });
      }
    }
  }
  return out.length > 0 ? out : FALLBACK_TTS_PROVIDERS;
}

function parseDefaultTtsProvider(data: unknown): string | null {
  if (!data || typeof data !== 'object' || !('defaultTtsProvider' in data)) {
    return null;
  }
  const v = (data as { defaultTtsProvider: unknown }).defaultTtsProvider;
  if (typeof v !== 'string' || !v.trim()) {
    return null;
  }
  return v.trim().toLowerCase();
}

function labelForDefaultTtsOption(
  metaLoaded: boolean,
  defaultId: string | null,
  options: { id: string; label: string }[],
): string {
  if (!metaLoaded) {
    return 'サーバー既定（TTS_PROVIDER）';
  }
  if (!defaultId) {
    return 'サーバー既定（TTS_PROVIDER）';
  }
  const opt = options.find((o) => o.id === defaultId);
  const name = opt?.label ?? defaultId;
  return `サーバー既定（${defaultId}）`;
}

export default function VoiceLabPage() {
  const [text, setText] = useState('');
  const [language, setLanguage] = useState<'ja' | 'en'>('ja');
  const [emotion, setEmotion] = useState('');
  const [ttsProviderId, setTtsProviderId] = useState('');
  const [ttsProviderOptions, setTtsProviderOptions] =
    useState<{ id: string; label: string }[]>(FALLBACK_TTS_PROVIDERS);
  const [voiceMetaLoaded, setVoiceMetaLoaded] = useState(false);
  const [serverDefaultTtsId, setServerDefaultTtsId] = useState<string | null>(null);
  const [preferMp3, setPreferMp3] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<TtsPreview | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const releaseObjectUrl = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  useEffect(() => () => releaseObjectUrl(), [releaseObjectUrl]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch('/api/voice');
        if (!res.ok) {
          if (!cancelled) {
            setVoiceMetaLoaded(true);
          }
          return;
        }
        if (cancelled) return;
        const data: unknown = await res.json();
        if (cancelled) return;
        setTtsProviderOptions(parseTtsProviders(data));
        setServerDefaultTtsId(parseDefaultTtsProvider(data));
        setVoiceMetaLoaded(true);
      } catch {
        /* keep fallback list */
        if (!cancelled) {
          setVoiceMetaLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleGenerate = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('テキストを入力してください。');
      return;
    }

    setError(null);
    releaseObjectUrl();
    setPreview(null);
    setLoading(true);

    try {
      const body: Record<string, unknown> = {
        action: 'text_to_speech',
        text: trimmed,
        language,
      };
      if (emotion.trim()) {
        body.emotion = emotion.trim();
      }
      if (preferMp3) {
        body.outputEncoding = 'mp3';
      }
      if (ttsProviderId.trim()) {
        body.ttsProvider = ttsProviderId.trim();
      }

      const res = await fetch('/api/voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = (await res.json()) as Record<string, unknown>;

      if (!res.ok) {
        const msg =
          typeof data.error === 'string'
            ? data.error
            : typeof data.detail === 'string'
              ? data.detail
              : `HTTP ${res.status}`;
        setError(msg);
        return;
      }

      if (data.success !== true) {
        setError(typeof data.error === 'string' ? data.error : '音声の生成に失敗しました。');
        return;
      }

      const b64 = data.audioResponse;
      if (typeof b64 !== 'string' || b64.length === 0) {
        setError('音声データが返されませんでした。');
        return;
      }

      const mime =
        typeof data.audioFormat === 'string' && data.audioFormat.length > 0
          ? data.audioFormat
          : 'audio/wav';

      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }

      const blob = new Blob([bytes], { type: mime });
      const durationMs = await measureAudioDurationMs(blob);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setPreview({ url, format: mime, durationMs });
    } catch (e) {
      setError(e instanceof Error ? e.message : '不明なエラーが発生しました。');
    } finally {
      setLoading(false);
    }
  }, [text, language, emotion, preferMp3, ttsProviderId, releaseObjectUrl]);

  const downloadName = `voice-lab-${Date.now()}.${preview ? extensionForMime(preview.format) : 'wav'}`;

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-3xl">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">Voice Lab</h1>
          <Link
            href="/admin/knowledge"
            className="text-sm font-medium text-gray-600 hover:text-gray-900"
          >
            管理トップへ
          </Link>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <p className="mb-4 text-sm text-gray-600">
            本番と同じ <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">VoiceAgent.text_to_speech</code>{' '}
            経路（<code className="rounded bg-gray-100 px-1 py-0.5 text-xs">POST /api/voice</code>
            ）で音声を生成します。TTS
            エンジンは環境変数{' '}
            <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">TTS_PROVIDER</code>{' '}
            の既定、または下で選んだプロバイダー（<code className="rounded bg-gray-100 px-1 py-0.5 text-xs">ttsProvider</code>
            ）を使います。Piper-plus を選ぶと{' '}
            <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">PIPER_PLUS_API_URL</code>{' '}
            の HTTP API に接続します。既定は WAV 出力です。チェックを入れたときのみ MP3
            変換を行います（WAV ソース時はサーバ側で変換、ffmpeg 必須。Google TTS など既に
            MP3 の場合はそのまま）。
          </p>

          <div className="space-y-4">
            <div>
              <label htmlFor="voice-lab-tts" className="mb-1 block text-sm font-medium text-gray-700">
                TTS エンジン
              </label>
              <select
                id="voice-lab-tts"
                value={ttsProviderId}
                onChange={(e) => setTtsProviderId(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">
                  {labelForDefaultTtsOption(voiceMetaLoaded, serverDefaultTtsId, ttsProviderOptions)}
                </option>
                {ttsProviderOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label} ({p.id})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="voice-lab-text" className="mb-1 block text-sm font-medium text-gray-700">
                テキスト
              </label>
              <textarea
                id="voice-lab-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={6}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="合成したい文章を入力（感情タグ [happy] なども利用可能）"
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="voice-lab-lang" className="mb-1 block text-sm font-medium text-gray-700">
                  言語
                </label>
                <select
                  id="voice-lab-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as 'ja' | 'en')}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="ja">日本語 (ja)</option>
                  <option value="en">English (en)</option>
                </select>
              </div>

              <div>
                <label htmlFor="voice-lab-emotion" className="mb-1 block text-sm font-medium text-gray-700">
                  感情（任意）
                </label>
                <select
                  id="voice-lab-emotion"
                  value={emotion}
                  onChange={(e) => setEmotion(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {VRM_EMOTIONS.map((opt) => (
                    <option key={opt.value || 'none'} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={preferMp3}
                onChange={(e) => setPreferMp3(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              MP3 で取得（オフのときは WAV のまま。オンで WAV→MP3 変換または既存 MP3 を返す）
            </label>

            <button
              type="button"
              onClick={() => void handleGenerate()}
              disabled={loading}
              className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? '生成中…' : '音声を生成'}
            </button>
          </div>

          {error ? (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {error}
            </div>
          ) : null}

          {preview ? (
            <div className="mt-6 space-y-3 border-t border-gray-100 pt-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-gray-700">試聴</p>
                <p className="text-sm text-gray-600">
                  音声の長さ:{' '}
                  {preview.durationMs !== null ? (
                    <span className="font-medium tabular-nums text-gray-900">
                      {preview.durationMs.toLocaleString('ja-JP')} ms
                    </span>
                  ) : (
                    <span className="text-gray-500">計測できませんでした</span>
                  )}
                </p>
              </div>
              <audio controls className="w-full" src={preview.url} preload="auto" />
              <a
                href={preview.url}
                download={downloadName}
                className="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
              >
                ファイルを保存（.{extensionForMime(preview.format)}）
              </a>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
