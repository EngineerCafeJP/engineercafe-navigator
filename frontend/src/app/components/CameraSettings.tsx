'use client';

import { Camera } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';

interface MediaDeviceInfo {
  deviceId: string;
  label: string;
  kind: string;
}

export interface CameraSettingsProps {
  kiosk_language?: 'ja' | 'en';
}

export default function CameraSettings({ kiosk_language = 'ja' }: CameraSettingsProps) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const refresh_camera_devices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setError('お使いのブラウザではカメラを利用できません。');
      return;
    }

    setError(null);
    try {
      // NOTE: device label を取得するために一度だけ権限を取り、すぐ停止する
      // (プレビューは表示しない)
      if (navigator.mediaDevices.getUserMedia) {
        try {
          const tempStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
          tempStream.getTracks().forEach((t) => t.stop());
        } catch (e) {
          // 権限拒否でも enumerateDevices は動くが、label が空になることがある
          setError(e instanceof Error ? e.message : 'カメラへのアクセスが許可されていません。');
        }
      }

      const list = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = list
        .filter((d) => d.kind === 'videoinput')
        .map((d) => ({
          deviceId: d.deviceId,
          label: d.label || `カメラ ${d.deviceId.slice(0, 8)}`,
          kind: d.kind,
        }));

      setDevices(videoInputs);
      if (videoInputs.length > 0) {
        setSelectedDeviceId((prev) => (prev ? prev : videoInputs[0].deviceId));
      }
    } catch {
      setError('カメラ一覧の取得に失敗しました。');
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    async function init() {
      try {
        await refresh_camera_devices();
      } catch {
        if (mounted) setError('カメラの初期化に失敗しました。');
      }
    }

    init();
    const handle_device_change = () => {
      refresh_camera_devices();
    };
    navigator.mediaDevices?.addEventListener?.('devicechange', handle_device_change);
    return () => {
      mounted = false;
      navigator.mediaDevices?.removeEventListener?.('devicechange', handle_device_change);
    };
  }, [refresh_camera_devices]);

  const handleDeviceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    setSelectedDeviceId(id);
  };

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Camera className="size-4" />
        {kioskSettingsLabels[kiosk_language].cameraDeviceTitle}
      </h3>
      {error && (
        <p className="rounded bg-red-50 p-2 text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
      {devices.length > 0 && (
        <div className="mt-2">
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
    </div>
  );
}
