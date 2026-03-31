'use client';

import React from 'react';
import { Languages, Hand, Mic } from 'lucide-react';
import type { KioskMicMode, KioskTriggerMode } from '@/lib/kiosk-constants';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';

export interface KioskSettingsProps {
  kiosk_language: 'ja' | 'en';
  kiosk_trigger_mode: KioskTriggerMode;
  kiosk_mic_mode: KioskMicMode;
  on_kiosk_language_change: (language: 'ja' | 'en') => void;
  on_kiosk_trigger_mode_change: (mode: KioskTriggerMode) => void;
  on_kiosk_mic_mode_change: (mode: KioskMicMode) => void;
}

export default function KioskSettings({
  kiosk_language,
  kiosk_trigger_mode,
  kiosk_mic_mode,
  on_kiosk_language_change,
  on_kiosk_trigger_mode_change,
  on_kiosk_mic_mode_change,
}: KioskSettingsProps) {
  const kiosk_labels = kioskSettingsLabels[kiosk_language];

  return (
    <div className="mb-4 space-y-3">
      <div className="bg-white rounded-lg p-4 shadow-sm">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <Languages className="size-4" />
          {kiosk_labels.displayLangTitle}
        </h3>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => on_kiosk_language_change('ja')}
            className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
              kiosk_language === 'ja'
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {kiosk_labels.displayLangJa}
          </button>
          <button
            type="button"
            onClick={() => on_kiosk_language_change('en')}
            className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
              kiosk_language === 'en'
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {kiosk_labels.displayLangEn}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg p-4 shadow-sm">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <Hand className="size-4" />{kiosk_labels.triggerTitle}
        </h3>
        <div className="space-y-2 text-sm">
          <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
            <input
              type="radio"
              name="settings-kiosk-trigger-mode"
              className="mt-1"
              checked={kiosk_trigger_mode === 'screen'}
              onChange={() => on_kiosk_trigger_mode_change('screen')}
            />
            <span>{kiosk_labels.triggerScreen}</span>
          </label>
          <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
            <input
              type="radio"
              name="settings-kiosk-trigger-mode"
              className="mt-1"
              checked={kiosk_trigger_mode === 'device'}
              onChange={() => on_kiosk_trigger_mode_change('device')}
            />
            <span>{kiosk_labels.triggerDevice}</span>
          </label>
        </div>
      </div>

      <div className="bg-white rounded-lg p-4 shadow-sm">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <Mic className="size-4" />{kiosk_labels.micModeTitle}
        </h3>
        <div className="space-y-2 text-sm">
          <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
            <input
              type="radio"
              name="settings-kiosk-mic-mode"
              className="mt-1"
              checked={kiosk_mic_mode === 'toggle'}
              onChange={() => on_kiosk_mic_mode_change('toggle')}
            />
            <span>{kiosk_labels.micToggle}</span>
          </label>
          <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
            <input
              type="radio"
              name="settings-kiosk-mic-mode"
              className="mt-1"
              checked={kiosk_mic_mode === 'push_to_talk'}
              onChange={() => on_kiosk_mic_mode_change('push_to_talk')}
            />
            <span>{kiosk_labels.micPushToTalk}</span>
          </label>
        </div>
      </div>
    </div>
  );
}

