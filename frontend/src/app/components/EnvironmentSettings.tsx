'use client';

import React from 'react';
import { Sun, Lightbulb, Zap } from 'lucide-react';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';

interface EnvironmentSettingsProps {
  lightingIntensity: number;
  onLightingChange: (intensity: number) => void;
  kiosk_language?: 'ja' | 'en';
}

export default function EnvironmentSettings({
  lightingIntensity,
  onLightingChange,
  kiosk_language = 'ja',
}: EnvironmentSettingsProps) {
  const t = kioskSettingsLabels[kiosk_language];

  const lightingPresets = [
    { label: t.lightingPresetDim, value: 0.5, icon: <Sun className="w-3 h-3" /> },
    { label: t.lightingPresetNormal, value: 1.0, icon: <Lightbulb className="w-3 h-3" /> },
    { label: t.lightingPresetBright, value: 1.5, icon: <Zap className="w-3 h-3" /> },
    { label: t.lightingPresetStudio, value: 2.0, icon: <Sun className="w-3 h-3" /> },
  ];

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value);
    onLightingChange(value);
    // Update CSS variable for slider fill
    e.target.style.setProperty('--value', `${(value / 2) * 100}%`);
  };

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Lightbulb className="w-4 h-4" />
        {t.lightingTitle}
      </h3>

      {/* Intensity Slider */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">
          {t.lightingIntensityLabel}: {Math.round(lightingIntensity * 100)}%
        </label>
        <input
          type="range"
          min="0.2"
          max="2"
          step="0.1"
          value={lightingIntensity}
          onChange={handleSliderChange}
          className="slider w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          style={
            {
              '--value': `${(lightingIntensity / 2) * 100}%`,
              background: `linear-gradient(to right, #3B82F6 0%, #3B82F6 ${(lightingIntensity / 2) * 100}%, #E5E7EB ${(lightingIntensity / 2) * 100}%, #E5E7EB 100%)`
            } as React.CSSProperties
          }
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>20%</span>
          <span>200%</span>
        </div>
      </div>

      {/* Preset Buttons */}
      <div className="grid grid-cols-2 gap-2">
        {lightingPresets.map((preset) => (
          <button
            key={preset.label}
            onClick={() => onLightingChange(preset.value)}
            className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
              Math.abs(lightingIntensity - preset.value) < 0.1
                ? 'bg-primary text-white shadow-md'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {preset.icon}
            {preset.label}
          </button>
        ))}
      </div>

      {/* Current Settings Display */}
      <div className="mt-3 p-2 bg-gray-50 rounded text-xs">
        <div className="font-medium text-gray-700 mb-1">{t.lightingCurrentSettingsTitle}:</div>
        <div className="text-gray-600">
          {t.lightingIntensityValueLabel}: {Math.round(lightingIntensity * 100)}%
          {lightingIntensity <= 0.7 && ` (${t.lightingToneSoft})`}
          {lightingIntensity > 0.7 && lightingIntensity <= 1.3 && ` (${t.lightingToneBalanced})`}
          {lightingIntensity > 1.3 && ` (${t.lightingToneIntense})`}
        </div>
      </div>
    </div>
  );
}