'use client';

import React from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';
import TtsSpeedSettings from './TtsSpeedSettings';

export interface SpeakerSettingsProps {
  kiosk_language?: 'ja' | 'en';
  volume: number;
  isMuted: boolean;
  onVolumeChange: (value: number) => void;
  onMuteToggle: () => void;
  /** TTS 合成速度倍率（1.0=標準・小さいほど遅い） */
  ttsSpeed?: number;
  onTtsSpeedChange?: (value: number) => void;
}

export default function SpeakerSettings({
  kiosk_language = 'ja',
  volume,
  isMuted,
  onVolumeChange,
  onMuteToggle,
  ttsSpeed,
  onTtsSpeedChange,
}: SpeakerSettingsProps) {
  const effectiveVolume = isMuted ? 0 : volume;

  return (
    <div className="space-y-3">
      <div className="bg-white rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Volume2 className="w-4 h-4" />
          {kioskSettingsLabels[kiosk_language].speakerVolumeTitle}
        </h3>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onMuteToggle}
            className="rounded-lg bg-gray-100 p-2 transition-colors hover:bg-gray-200"
            title={isMuted ? '音声をオンにする' : '音声をオフにする'}
          >
            {isMuted ? (
              <VolumeX className="h-5 w-5 text-gray-600" />
            ) : (
              <Volume2 className="h-5 w-5 text-gray-600" />
            )}
          </button>
          <input
            type="range"
            min="0"
            max="100"
            value={effectiveVolume}
            onChange={(e) => {
              if (isMuted) {
                return;
              }
              onVolumeChange(Number(e.target.value));
            }}
            disabled={isMuted}
            className={`h-2 flex-1 appearance-none rounded-lg ${
              isMuted ? 'cursor-not-allowed bg-gray-100 opacity-60' : 'cursor-pointer bg-gray-200'
            }`}
            title={isMuted ? 'ミュート中は音量を変更できません' : '音量調整'}
          />
        </div>
      </div>

      {typeof ttsSpeed === 'number' && onTtsSpeedChange ? (
        <TtsSpeedSettings
          kiosk_language={kiosk_language}
          speed={ttsSpeed}
          onSpeedChange={onTtsSpeedChange}
        />
      ) : null}
    </div>
  );
}

