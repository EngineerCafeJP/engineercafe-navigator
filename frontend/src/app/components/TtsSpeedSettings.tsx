'use client';

import { Gauge } from 'lucide-react';
import {
  KIISK_TTS_SPEED_DEFAULT,
  KIISK_TTS_SPEED_MAX,
  KIISK_TTS_SPEED_MIN,
  KIISK_TTS_SPEED_STEP,
  readKioskTtsSpeed,
  writeKioskTtsSpeed,
} from '@/lib/kiosk-constants';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';

export interface TtsSpeedSettingsProps {
  kiosk_language?: 'ja' | 'en';
  speed: number;
  onSpeedChange: (value: number) => void;
}

export default function TtsSpeedSettings({
  kiosk_language = 'ja',
  speed,
  onSpeedChange,
}: TtsSpeedSettingsProps) {
  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Gauge className="w-4 h-4" />
        {kioskSettingsLabels[kiosk_language].ttsSpeedTitle}
      </h3>
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-500 whitespace-nowrap">
          {kioskSettingsLabels[kiosk_language].ttsSpeedSlow}
        </span>
        <input
          type="range"
          min={KIISK_TTS_SPEED_MIN}
          max={KIISK_TTS_SPEED_MAX}
          step={KIISK_TTS_SPEED_STEP}
          value={speed}
          onChange={(e) => {
            const next = Number(e.target.value);
            onSpeedChange(next);
            writeKioskTtsSpeed(next);
          }}
          className="h-2 flex-1 appearance-none cursor-pointer rounded-lg bg-gray-200"
          title={kioskSettingsLabels[kiosk_language].ttsSpeedTitle}
        />
        <span className="text-xs text-gray-500 whitespace-nowrap">
          {kioskSettingsLabels[kiosk_language].ttsSpeedFast}
        </span>
        <span className="w-10 text-right text-xs font-medium text-gray-700 tabular-nums">
          {speed.toFixed(2)}x
        </span>
      </div>
      <p className="mt-2 text-xs text-gray-400">
        {kioskSettingsLabels[kiosk_language].ttsSpeedHint}
      </p>
    </div>
  );
}

export function getInitialTtsSpeed(): number {
  return readKioskTtsSpeed() ?? KIISK_TTS_SPEED_DEFAULT;
}
