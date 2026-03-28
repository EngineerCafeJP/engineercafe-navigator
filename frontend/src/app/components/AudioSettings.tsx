'use client';

import React from 'react';
import { Volume2, VolumeX } from 'lucide-react';

interface AudioSettingsProps {
  volume: number;
  isMuted: boolean;
  onVolumeChange: (value: number) => void;
  onMuteToggle: () => void;
}

export default function AudioSettings({
  volume,
  isMuted,
  onVolumeChange,
  onMuteToggle,
}: AudioSettingsProps) {
  const effectiveVolume = isMuted ? 0 : volume;

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Volume2 className="w-4 h-4" />
        Audio
      </h3>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onMuteToggle}
          className="p-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
          title={isMuted ? '音声をオンにする' : '音声をオフにする'}
        >
          {isMuted ? (
            <VolumeX className="w-5 h-5 text-gray-600" />
          ) : (
            <Volume2 className="w-5 h-5 text-gray-600" />
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
          className={`flex-1 h-2 rounded-lg appearance-none ${
            isMuted
              ? 'cursor-not-allowed bg-gray-100 opacity-60'
              : 'cursor-pointer bg-gray-200'
          }`}
          title={isMuted ? 'ミュート中は音量を変更できません' : '音量調整'}
        />
      </div>
    </div>
  );
}
