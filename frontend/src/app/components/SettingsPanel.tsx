'use client';

import {
  MessageSquare,
  Shield,
  SlidersHorizontal,
  Video,
  User,
  X,
} from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import type { KioskMicMode, KioskTriggerMode } from '@/lib/kiosk-constants';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import SpeakerSettings from './SpeakerSettings';
import MicrophoneSettings from './MicrophoneSettings';
import BackgroundSelector, {
  type BackgroundOption as BackgroundSelectorOption,
} from './BackgroundSelector';
import CameraSettings from './CameraSettings';
import CharacterSettings, {
  type ControlsState,
  type VRMAnimationOption,
} from './CharacterSettings';
import EnvironmentSettings from './EnvironmentSettings';
import KioskSettings from './KioskSettings';

const SETTINGS_TAB_LABELS: Record<
  | 'multimedia'
  | 'kiosk'
  | 'admin'
  | 'controls',
  string
> = {
  multimedia: 'Multimedia',
  kiosk: 'Kiosk',
  admin: 'Admin',
  controls: 'Character',
};

export type SettingsPanelTab =
  | 'conversation'
  | 'multimedia'
  | 'kiosk'
  | 'admin'
  | 'controls';

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
  /** TTS 合成速度（1.0=標準・小さいほど遅い） */
  tts_speed?: number;
  on_tts_speed_change?: (value: number) => void;
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
  tts_speed,
  on_tts_speed_change,
  on_run_keyframe,
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

  const has_kiosk_tab =
    kiosk_trigger_mode != null &&
    kiosk_mic_mode != null &&
    on_kiosk_language_change != null &&
    on_kiosk_trigger_mode_change != null &&
    on_kiosk_mic_mode_change != null;
  /** Public kiosk: hide admin links; same flag as avatar dev controls (see page / .env.example). */
  const show_admin_tab = process.env.NEXT_PUBLIC_SHOW_AVATAR_SETTINGS === 'true';
  const tab_list: SettingsPanelTab[] = [
    ...(extra_tab ? (['conversation'] as const) : []),
    ...(has_kiosk_tab ? (['kiosk'] as const) : []),
    'multimedia',
    ...(show_admin_tab ? (['admin'] as const) : []),
    'controls',
  ];

  useEffect(() => {
    if (!show_admin_tab && active_tab === 'admin') {
      set_active_tab('controls');
    }
  }, [active_tab, show_admin_tab]);

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
            {tab === 'multimedia' && <Video className="size-4" />}
            {tab === 'kiosk' && <SlidersHorizontal className="size-4" />}
            {tab === 'admin' && <Shield className="size-4" />}
            {tab === 'controls' && <User className="size-4" />}
          </button>
        ))}
      </div>

      {active_tab === 'conversation' && extra_tab ? (
        <div className="mb-4">{extra_tab.content}</div>
      ) : null}

      {active_tab === 'kiosk' && has_kiosk_tab ? (
        <KioskSettings
          kiosk_language={kiosk_language}
          kiosk_trigger_mode={kiosk_trigger_mode}
          kiosk_mic_mode={kiosk_mic_mode}
          on_kiosk_language_change={on_kiosk_language_change}
          on_kiosk_trigger_mode_change={on_kiosk_trigger_mode_change}
          on_kiosk_mic_mode_change={on_kiosk_mic_mode_change}
        />
      ) : null}

      {active_tab === 'multimedia' && (
        <div className="mb-4 space-y-3">
          <SpeakerSettings
            kiosk_language={kiosk_language}
            volume={volume}
            isMuted={is_muted}
            onVolumeChange={(value) => on_volume_change?.(value)}
            onMuteToggle={() => on_mute_toggle?.()}
            ttsSpeed={tts_speed}
            onTtsSpeedChange={on_tts_speed_change}
          />

          <MicrophoneSettings
            kiosk_language={kiosk_language}
            storageKey="kiosk-mic-device-id"
          />

          <CameraSettings kiosk_language={kiosk_language} />
        </div>
      )}

      {show_admin_tab && active_tab === 'admin' ? (
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
          <a
            href="./admin/voice-lab"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
            aria-label="Voice Lab"
          >
            Voice Lab
          </a>
        </div>
      ) : null}

      {active_tab === 'controls' ? (
        <div className="mb-4 space-y-3">
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
            <EnvironmentSettings
              lightingIntensity={lighting_intensity}
              onLightingChange={on_lighting_change}
            kiosk_language={kiosk_language}
            />
            <BackgroundSelector
              currentBackground={current_background}
              onBackgroundChange={on_background_change}
            />
          </div>
      ) : null}

    </div>
  );
}
