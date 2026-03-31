'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Mic } from 'lucide-react';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';
interface AudioDeviceInfo {
  deviceId: string;
  label: string;
  kind: string;
}

export interface MicrophoneSettingsProps {
  kiosk_language?: 'ja' | 'en';
  storageKey?: string;
}

const DEFAULT_STORAGE_KEY = 'selected_mic_device_id';

export default function MicrophoneSettings({
  kiosk_language = 'ja',
  storageKey = DEFAULT_STORAGE_KEY,
}: MicrophoneSettingsProps) {
  const [micDevices, setMicDevices] = useState<AudioDeviceInfo[]>([]);
  const [selectedMicDeviceId, setSelectedMicDeviceId] = useState<string>('');
  const [micError, setMicError] = useState<string | null>(null);

  const refresh_mic_devices = useCallback(async () => {
    if (typeof window === 'undefined') {
      return;
    }
    if (!navigator.mediaDevices?.enumerateDevices) {
      setMicError('お使いのブラウザではマイクを選択できません。');
      return;
    }

    setMicError(null);

    // NOTE: label を取るために一度だけ権限を取り、すぐ停止する（録音は開始しない）
    if (navigator.mediaDevices.getUserMedia) {
      try {
        const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        tempStream.getTracks().forEach((t) => t.stop());
      } catch (e) {
        // 権限拒否でも enumerateDevices は動くが、label が空になることがある
        setMicError(e instanceof Error ? e.message : 'マイクへのアクセスが許可されていません。');
      }
    }

    try {
      const list = await navigator.mediaDevices.enumerateDevices();
      const rawInputs = list.filter((d) => d.kind === 'audioinput');
      const inputs = rawInputs
        .filter((d) => d.deviceId !== 'default')
        .map((d) => ({
          deviceId: d.deviceId,
          label: d.label || `マイク ${d.deviceId.slice(0, 8)}`,
          kind: d.kind,
        }));

      setMicDevices(inputs);

      const saved = window.localStorage.getItem(storageKey) ?? '';
      const savedExists = saved && saved !== 'default' && inputs.some((d) => d.deviceId === saved);
      const next = savedExists ? saved : inputs[0]?.deviceId ?? '';
      setSelectedMicDeviceId(next);
      if (next) {
        window.localStorage.setItem(storageKey, next);
      }
    } catch {
      setMicError('マイク一覧の取得に失敗しました。');
    }
  }, [storageKey]);

  useEffect(() => {
    void refresh_mic_devices();
    const handle_device_change = () => {
      void refresh_mic_devices();
    };
    navigator.mediaDevices?.addEventListener?.('devicechange', handle_device_change);
    return () => {
      navigator.mediaDevices?.removeEventListener?.('devicechange', handle_device_change);
    };
  }, [refresh_mic_devices]);

  const handleMicDeviceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    setSelectedMicDeviceId(id);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, id);
    }
  };

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Mic className="w-4 h-4" />
        {kioskSettingsLabels[kiosk_language].microphoneDeviceTitle}
      </h3>
      {micError && (
        <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-700" role="alert">
          {micError}
        </p>
      )}
      {micDevices.length > 0 && (
        <div className="mt-3">
          <select
            value={selectedMicDeviceId}
            onChange={handleMicDeviceChange}
            className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm"
            aria-label="マイクを選択"
          >
            {micDevices.map((d) => (
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

