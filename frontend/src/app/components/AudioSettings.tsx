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
          value={volume}
          onChange={(e) => onVolumeChange(Number(e.target.value))}
          className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          title="音量調整"
        />
      </div>
    </div>
  );
}
