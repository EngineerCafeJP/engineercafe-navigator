'use client';

import { Camera, Send } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';

interface MediaDeviceInfo {
  deviceId: string;
  label: string;
  kind: string;
}

type OcrMode = 'member_card' | 'handwriting';

interface OcrResponse {
  success: boolean;
  mode: OcrMode;
  member_number: number | null;
  recognized_text: string | null;
  confidence: number;
  language: string | null;
  expression: string | null;
  processing_time_ms: number;
  visitor_identity: Record<string, unknown> | null;
  error: string | null;
}

export default function CameraSettings() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [ocrMode, setOcrMode] = useState<OcrMode>('member_card');
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocrResult, setOcrResult] = useState<OcrResponse | null>(null);
  const [ocrResultMessage, setOcrResultMessage] = useState<string | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);

  const stopStream = useCallback((s: MediaStream | null) => {
    if (!s) return;
    s.getTracks().forEach((t) => t.stop());
  }, []);

  const startStream = useCallback(async (deviceId?: string) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('カメラにアクセスできません。HTTPS または localhost でお試しください。');
      return;
    }
    setError(null);
    try {
      const constraints: MediaStreamConstraints = {
        video: deviceId ? { deviceId: { exact: deviceId } } : true,
        audio: false,
      };
      const newStream = await navigator.mediaDevices.getUserMedia(constraints);
      setStream((prev) => {
        stopStream(prev);
        return newStream;
      });
      if (videoRef.current) {
        videoRef.current.srcObject = newStream;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'カメラの起動に失敗しました。');
    }
  }, [stopStream]);

  useEffect(() => {
    let mounted = true;
    const videoEl = videoRef.current;

    async function init() {
      if (!navigator.mediaDevices?.enumerateDevices) {
        setError('お使いのブラウザではカメラを利用できません。');
        return;
      }
      try {
        await startStream();
        if (!mounted) return;
        const list = await navigator.mediaDevices.enumerateDevices();
        const videoInputs = list
          .filter((d) => d.kind === 'videoinput')
          .map((d) => ({ deviceId: d.deviceId, label: d.label || `カメラ ${d.deviceId.slice(0, 8)}`, kind: d.kind }));
        setDevices(videoInputs);
        if (videoInputs.length > 0) {
          setSelectedDeviceId((prev) => (prev ? prev : videoInputs[0].deviceId));
        }
      } catch {
        if (mounted) setError('カメラの初期化に失敗しました。');
      }
    }

    init();
    return () => {
      mounted = false;
      setStream((prev) => {
        stopStream(prev);
        return null;
      });
      if (videoEl) {
        videoEl.srcObject = null;
      }
    };
    // Intentionally run only on mount; cleanup on unmount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedDeviceId || selectedDeviceId === 'default') return;
    startStream(selectedDeviceId);
  }, [selectedDeviceId, startStream]);

  const handleDeviceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    setSelectedDeviceId(id);
  };

  const handleSendImage = async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !stream || video.readyState < 2) {
      setOcrResult(null);
      setOcrResultMessage('プレビューが準備できていません。');
      return;
    }
    setOcrLoading(true);
    setOcrResult(null);
    setOcrResultMessage(null);
    try {
      const w = video.videoWidth;
      const h = video.videoHeight;
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Canvas 2D not available');
      ctx.drawImage(video, 0, 0);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
      const base64 = dataUrl.replace(/^data:image\/jpeg;base64,/, '');

      const res = await fetch('/api/ocr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_data: base64,
          mode: ocrMode,
          session_id: '',
        }),
      });
      const data = (await res.json()) as Partial<OcrResponse>;
      if (!res.ok) {
        setOcrResult(null);
        setOcrResultMessage(`エラー: ${data?.error ?? res.statusText}`);
        return;
      }
      setOcrResult({
        success: data.success ?? false,
        mode: data.mode ?? ocrMode,
        member_number: data.member_number ?? null,
        recognized_text: data.recognized_text ?? null,
        confidence: data.confidence ?? 0,
        language: data.language ?? null,
        expression: data.expression ?? null,
        processing_time_ms: data.processing_time_ms ?? 0,
        visitor_identity: data.visitor_identity ?? null,
        error: data.error ?? null,
      });
    } catch (e) {
      setOcrResult(null);
      setOcrResultMessage(e instanceof Error ? e.message : '送信に失敗しました。');
    } finally {
      setOcrLoading(false);
    }
  };

  return (
    <div className="mb-4 flex flex-col gap-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Camera className="size-4" />
        カメラ
      </h3>
      {error && (
        <p className="rounded bg-red-50 p-2 text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
      {devices.length > 1 && (
        <div>
          <label className="mb-1 block text-xs text-gray-600">使用するカメラ</label>
          <select
            value={selectedDeviceId}
            onChange={handleDeviceChange}
            className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm"
            aria-label="カメラを選択"
          >
            {devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
      )}
      <div>
        <label className="mb-1 block text-xs text-gray-600">OCRモード</label>
        <select
          value={ocrMode}
          onChange={(e) => setOcrMode(e.target.value as OcrMode)}
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm"
          aria-label="OCRモードを選択"
        >
          <option value="member_card">member_card</option>
          <option value="handwriting">handwriting</option>
        </select>
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-black">
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="h-40 w-full object-contain"
          aria-label="カメラプレビュー"
        />
      </div>
      <canvas ref={canvasRef} className="hidden" aria-hidden />
      <button
        type="button"
        onClick={handleSendImage}
        disabled={ocrLoading || !stream}
        className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:opacity-50"
        aria-label="画像をOCRに送信"
      >
        <Send className="size-4" />
        {ocrLoading ? '送信中…' : '画像を送信'}
      </button>
      {ocrResultMessage && (
        <div className="rounded bg-gray-50 p-2 text-xs text-gray-700" role="status">
          {ocrResultMessage}
        </div>
      )}
      {ocrResult && (
        <div className="space-y-1 rounded bg-gray-50 p-2 text-xs text-gray-700" role="status">
          <p>success: {String(ocrResult.success)}</p>
          <p>mode: {ocrResult.mode}</p>
          <p>recognized_text: {ocrResult.recognized_text ?? 'null'}</p>
          <p>member_number: {ocrResult.member_number ?? 'null'}</p>
          <p>language: {ocrResult.language ?? 'null'}</p>
          <p>expression: {ocrResult.expression ?? 'null'}</p>
          <p>confidence: {ocrResult.confidence.toFixed(2)}</p>
          <p>processing_time_ms: {ocrResult.processing_time_ms}</p>
          {ocrResult.visitor_identity && (
            <p>visitor_identity: {JSON.stringify(ocrResult.visitor_identity)}</p>
          )}
          {ocrResult.error && <p>error: {ocrResult.error}</p>}
        </div>
      )}
    </div>
  );
}
