'use client';

import {
  Camera,
  Languages,
  MessageSquare,
  Presentation,
  Shield,
  SlidersHorizontal,
  User,
  X,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import type { KioskMicMode, KioskTriggerMode } from '@/lib/kiosk-constants';
import { kioskSettingsLabels } from '@/lib/kiosk-labels';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import AudioSettings from './AudioSettings';
import BackgroundSelector, {
  type BackgroundOption as BackgroundSelectorOption,
} from './BackgroundSelector';
import CameraSettings from './CameraSettings';
import CharacterSettings, {
  type ControlsState,
  type VRMAnimationOption,
} from './CharacterSettings';
import EnvironmentSettings from './EnvironmentSettings';

const SETTINGS_TAB_LABELS: Record<
  | 'camera'
  | 'controls'
  | 'slides'
  | 'kiosk'
  | 'admin',
  string
> = {
  camera: 'Camera',
  controls: 'Character',
  slides: 'Slides',
  kiosk: 'Kiosk',
  admin: 'Admin',
};

export type SettingsPanelTab =
  | 'conversation'
  | 'camera'
  | 'controls'
  | 'slides'
  | 'kiosk'
  | 'admin';

export interface SettingsPanelProps {
  show_close_button?: boolean;
  on_close?: () => void;
  extra_tab?: { label: string; content: ReactNode };
  /** Character tab (uses CharacterSettings component) */
  controls_state: ControlsState;
  vrm_expression_names: string[];
  expression_weights: Record<string, number>;
  on_expression_weight_change: (name: string, weight: number) => void;
  vrm_animation_options: VRMAnimationOption[];
  on_play_vrm_animation: (url: string, loop: boolean) => void;
  on_position_change: (position: ControlsState['position']) => void;
  on_rotation_change: (rotation: ControlsState['rotation']) => void;
  /** Background tab */
  current_background: BackgroundSelectorOption;
  on_background_change: (background: BackgroundSelectorOption) => void;
  /** Lighting tab */
  lighting_intensity: number;
  on_lighting_change: (intensity: number) => void;
  /** Audio tab */
  volume: number;
  is_muted: boolean;
  on_volume_change?: (value: number) => void;
  on_mute_toggle?: () => void;
  /** Keyframe tab - run callback is passed from parent */
  on_run_keyframe: (animation: CharacterAnimationData) => void;
  /** Slides tab - when set, a "Slides" tab is shown for opening/closing slide mode */
  slide_mode_open?: boolean;
  on_open_slides?: () => void;
  on_close_slides?: () => void;
  open_slides_label?: string;
  close_slides_label?: string;
  /** Kiosk settings tab */
  kiosk_language?: 'ja' | 'en';
  kiosk_trigger_mode?: KioskTriggerMode;
  kiosk_mic_mode?: KioskMicMode;
  on_kiosk_language_change?: (language: 'ja' | 'en') => void;
  on_kiosk_trigger_mode_change?: (mode: KioskTriggerMode) => void;
  on_kiosk_mic_mode_change?: (mode: KioskMicMode) => void;
}

/** Props that a parent (e.g. CharacterAvatar) can provide via ref for page to merge with UI props */
export type SettingsPanelPropsFromSource = Omit<
  SettingsPanelProps,
  | 'show_close_button'
  | 'on_close'
  | 'extra_tab'
  | 'slide_mode_open'
  | 'on_open_slides'
  | 'on_close_slides'
  | 'open_slides_label'
  | 'close_slides_label'
>;

export default function SettingsPanel({
  show_close_button = false,
  on_close,
  extra_tab,
  controls_state,
  vrm_expression_names,
  expression_weights,
  on_expression_weight_change,
  vrm_animation_options,
  on_play_vrm_animation,
  on_position_change,
  on_rotation_change,
  current_background,
  on_background_change,
  lighting_intensity,
  on_lighting_change,
  volume,
  is_muted,
  on_volume_change,
  on_mute_toggle,
  on_run_keyframe,
  slide_mode_open = false,
  on_open_slides,
  on_close_slides,
  open_slides_label = 'Open slides',
  close_slides_label = 'Close slides',
  kiosk_language = 'ja',
  kiosk_trigger_mode,
  kiosk_mic_mode,
  on_kiosk_language_change,
  on_kiosk_trigger_mode_change,
  on_kiosk_mic_mode_change,
}: SettingsPanelProps) {
  const [active_tab, set_active_tab] = useState<SettingsPanelTab>(
    extra_tab ? 'conversation' : 'controls',
  );
  const [keyframe_json_input, set_keyframe_json_input] = useState('');
  const [keyframe_json_error, set_keyframe_json_error] = useState('');

  const has_slides_tab = on_open_slides != null || on_close_slides != null;
  const has_kiosk_tab =
    kiosk_trigger_mode != null &&
    kiosk_mic_mode != null &&
    on_kiosk_language_change != null &&
    on_kiosk_trigger_mode_change != null &&
    on_kiosk_mic_mode_change != null;
  const kiosk_labels = kioskSettingsLabels[kiosk_language];
  const tab_list: SettingsPanelTab[] = [
    ...(extra_tab ? (['conversation'] as const) : []),
    ...(has_kiosk_tab ? (['kiosk'] as const) : []),
    'admin',
    'controls',
  ];

  return (
    <div className="flex w-80 max-h-[85vh] flex-col overflow-y-auto rounded-lg bg-white bg-opacity-95 p-4 shadow-lg">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">Settings</h3>
        {show_close_button && on_close ? (
          <button
            type="button"
            onClick={on_close}
            className="rounded-full p-1.5 transition-colors hover:bg-gray-200"
            aria-label="Close"
          >
            <X className="size-4 text-gray-600" />
          </button>
        ) : null}
      </div>

      <div className="mb-3 flex flex-wrap gap-1 border-b border-gray-200">
        {tab_list.map((tab) => (
          <button
            key={tab}
            type="button"
            title={
              tab === 'conversation' && extra_tab
                ? extra_tab.label
                : SETTINGS_TAB_LABELS[tab as keyof typeof SETTINGS_TAB_LABELS]
            }
            onClick={() => set_active_tab(tab)}
            className={`rounded-t-md p-2 transition-colors ${
              active_tab === tab
                ? 'border-b-2 border-blue-500 bg-blue-100 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {tab === 'conversation' && <MessageSquare className="size-4" />}
            {tab === 'slides' && <Presentation className="size-4" />}
            {tab === 'camera' && <Camera className="size-4" />}
            {tab === 'kiosk' && <SlidersHorizontal className="size-4" />}
            {tab === 'admin' && <Shield className="size-4" />}
            {tab === 'controls' && <User className="size-4" />}
          </button>
        ))}
      </div>

      {active_tab === 'conversation' && extra_tab ? (
        <div className="mb-4">{extra_tab.content}</div>
      ) : null}

      {active_tab === 'slides' && has_slides_tab ? (
        <div className="mb-4 flex flex-col gap-3">
          {slide_mode_open && on_close_slides ? (
            <button
              type="button"
              onClick={on_close_slides}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
              aria-label={close_slides_label}
            >
              <X className="size-4" />
              {close_slides_label}
            </button>
          ) : null}
          {!slide_mode_open && on_open_slides ? (
            <button
              type="button"
              onClick={on_open_slides}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-700 shadow-sm transition-colors hover:bg-blue-100"
              aria-label={open_slides_label}
            >
              <Presentation className="size-4" />
              {open_slides_label}
            </button>
          ) : null}
        </div>
      ) : null}

      {active_tab === 'kiosk' && has_kiosk_tab ? (
        <div className="mb-4 space-y-4">
          <div className="rounded-lg border border-gray-200 p-3">
            <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Languages className="size-4" />
              {kiosk_labels.displayLangTitle}
            </h4>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => on_kiosk_language_change?.('ja')}
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
                onClick={() => on_kiosk_language_change?.('en')}
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

          <div className="rounded-lg border border-gray-200 p-3">
            <h4 className="mb-2 text-sm font-semibold">{kiosk_labels.triggerTitle}</h4>
            <div className="space-y-2 text-sm">
              <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
                <input
                  type="radio"
                  name="settings-kiosk-trigger-mode"
                  className="mt-1"
                  checked={kiosk_trigger_mode === 'screen'}
                  onChange={() => on_kiosk_trigger_mode_change?.('screen')}
                />
                <span>{kiosk_labels.triggerScreen}</span>
              </label>
              <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
                <input
                  type="radio"
                  name="settings-kiosk-trigger-mode"
                  className="mt-1"
                  checked={kiosk_trigger_mode === 'device'}
                  onChange={() => on_kiosk_trigger_mode_change?.('device')}
                />
                <span>{kiosk_labels.triggerDevice}</span>
              </label>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 p-3">
            <h4 className="mb-2 text-sm font-semibold">{kiosk_labels.micModeTitle}</h4>
            <div className="space-y-2 text-sm">
              <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
                <input
                  type="radio"
                  name="settings-kiosk-mic-mode"
                  className="mt-1"
                  checked={kiosk_mic_mode === 'toggle'}
                  onChange={() => on_kiosk_mic_mode_change?.('toggle')}
                />
                <span>{kiosk_labels.micToggle}</span>
              </label>
              <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-2 has-[:checked]:border-blue-400">
                <input
                  type="radio"
                  name="settings-kiosk-mic-mode"
                  className="mt-1"
                  checked={kiosk_mic_mode === 'push_to_talk'}
                  onChange={() => on_kiosk_mic_mode_change?.('push_to_talk')}
                />
                <span>{kiosk_labels.micPushToTalk}</span>
              </label>
            </div>
          </div>

          <AudioSettings
            volume={volume}
            isMuted={is_muted}
            onVolumeChange={(value) => on_volume_change?.(value)}
            onMuteToggle={() => on_mute_toggle?.()}
          />
        </div>
      ) : null}

      {active_tab === 'admin' ? (
        <div className="mb-4 flex flex-col gap-3">
          <a
            href="./admin/knowledge"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
            aria-label="知識ベース管理"
          >
            知識ベース管理
          </a>
          <a
            href="./admin/vosk-settings"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
            aria-label="音声認識語彙管理"
          >
            音声認識語彙管理
          </a>
          <a
            href="./admin/avatar-lab"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
            aria-label="Avatar Lab"
          >
            Avatar Lab
          </a>
        </div>
      ) : null}

      {active_tab === 'controls' ? (
        <div className="mb-4">
          <CharacterSettings
            state={controls_state}
            vrmExpressionNames={vrm_expression_names}
            expressionWeights={expression_weights}
            onExpressionWeightChange={on_expression_weight_change}
            vrmAnimationOptions={vrm_animation_options}
            onPlayVRMAnimation={on_play_vrm_animation}
            onPositionChange={on_position_change}
            onRotationChange={on_rotation_change}
            keyframe_json_input={keyframe_json_input}
            on_keyframe_json_input_change={set_keyframe_json_input}
            keyframe_json_error={keyframe_json_error}
            on_keyframe_json_error={set_keyframe_json_error}
            on_run_keyframe={on_run_keyframe}
          />
          <div className="mt-3 space-y-3">
            <EnvironmentSettings
              lightingIntensity={lighting_intensity}
              onLightingChange={on_lighting_change}
            />
            <BackgroundSelector
              currentBackground={current_background}
              onBackgroundChange={on_background_change}
            />
          </div>
        </div>
      ) : null}

      {active_tab === 'camera' ? (
        <div className="mb-4">
          <CameraSettings />
        </div>
      ) : null}

    </div>
  );
}
