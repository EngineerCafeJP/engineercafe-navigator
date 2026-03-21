'use client';

import {
  Camera,
  Film,
  Lightbulb,
  MessageSquare,
  Palette,
  Presentation,
  SlidersHorizontal,
  Volume2,
  X,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import AudioSettings from './AudioSettings';
import BackgroundSelector, {
  type BackgroundOption as BackgroundSelectorOption,
} from './BackgroundSelector';
import CameraSettings from './CameraSettings';
import ControlsSettings, {
  type ControlsState,
  type VRMAnimationOption,
} from './ControlsSettings';
import EnvironmentSettings from './EnvironmentSettings';
import KeyframeSettings from './KeyframeSettings';

const SETTINGS_TAB_LABELS: Record<
  'camera' | 'controls' | 'keyframe' | 'background' | 'lighting' | 'audio' | 'slides',
  string
> = {
  camera: 'Camera',
  controls: 'Controls',
  keyframe: 'Keyframe',
  background: 'Background',
  lighting: 'Lighting',
  audio: 'Audio',
  slides: 'Slides',
};

export type SettingsPanelTab =
  | 'conversation'
  | 'camera'
  | 'controls'
  | 'keyframe'
  | 'background'
  | 'lighting'
  | 'audio'
  | 'slides';

export interface SettingsPanelProps {
  show_close_button?: boolean;
  on_close?: () => void;
  extra_tab?: { label: string; content: ReactNode };
  /** Controls tab (uses ControlsSettings component) */
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
}: SettingsPanelProps) {
  const [active_tab, set_active_tab] = useState<SettingsPanelTab>(
    extra_tab ? 'conversation' : 'controls',
  );
  const [keyframe_json_input, set_keyframe_json_input] = useState('');
  const [keyframe_json_error, set_keyframe_json_error] = useState('');

  const has_slides_tab = on_open_slides != null || on_close_slides != null;
  const tab_list: SettingsPanelTab[] = [
    ...(extra_tab ? (['conversation'] as const) : []),
    ...(has_slides_tab ? (['slides'] as const) : []),
    'camera',
    'controls',
    'keyframe',
    'background',
    'lighting',
    'audio',
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
            {tab === 'controls' && <SlidersHorizontal className="size-4" />}
            {tab === 'keyframe' && <Film className="size-4" />}
            {tab === 'background' && <Palette className="size-4" />}
            {tab === 'lighting' && <Lightbulb className="size-4" />}
            {tab === 'audio' && <Volume2 className="size-4" />}
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

      {active_tab === 'controls' ? (
        <div className="mb-4">
          <ControlsSettings
            state={controls_state}
            vrmExpressionNames={vrm_expression_names}
            expressionWeights={expression_weights}
            onExpressionWeightChange={on_expression_weight_change}
            vrmAnimationOptions={vrm_animation_options}
            onPlayVRMAnimation={on_play_vrm_animation}
            onPositionChange={on_position_change}
            onRotationChange={on_rotation_change}
          />
        </div>
      ) : null}

      {active_tab === 'background' ? (
        <div className="mb-4">
          <BackgroundSelector
            currentBackground={current_background}
            onBackgroundChange={on_background_change}
          />
        </div>
      ) : null}

      {active_tab === 'lighting' ? (
        <div className="mb-4">
          <EnvironmentSettings
            lightingIntensity={lighting_intensity}
            onLightingChange={on_lighting_change}
          />
        </div>
      ) : null}

      {active_tab === 'audio' ? (
        <div className="mb-4">
          <AudioSettings
            volume={volume}
            isMuted={is_muted}
            onVolumeChange={(value) => on_volume_change?.(value)}
            onMuteToggle={() => on_mute_toggle?.()}
          />
        </div>
      ) : null}

      {active_tab === 'camera' ? (
        <div className="mb-4">
          <CameraSettings />
        </div>
      ) : null}

      {active_tab === 'keyframe' ? (
        <div className="mb-4">
          <KeyframeSettings
            jsonInput={keyframe_json_input}
            onJsonInputChange={set_keyframe_json_input}
            error={keyframe_json_error}
            onError={set_keyframe_json_error}
            onRunKeyframe={on_run_keyframe}
            onRunKeyframeClick={() => set_active_tab('controls')}
          />
        </div>
      ) : null}
    </div>
  );
}
