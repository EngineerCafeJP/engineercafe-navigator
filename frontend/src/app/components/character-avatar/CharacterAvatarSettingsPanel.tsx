'use client';

import { createPortal } from 'react-dom';
import type { MutableRefObject, ReactNode } from 'react';
import type { CharacterAnimationData } from '../../utils/character-animation-utils';
import type { BackgroundOption as BackgroundSelectorOption } from '../BackgroundSelector';
import type { VRMAnimationOption } from '../CharacterSettings';
import SettingsPanel, { type SettingsPanelPropsFromSource } from '../SettingsPanel';
import type { CharacterState, BackgroundOption } from './types';

interface CharacterAvatarSettingsPanelProps {
  settingsPanelPropsRef?: MutableRefObject<SettingsPanelPropsFromSource | null>;
  onSettingsPanelPropsChange?: (props: SettingsPanelPropsFromSource) => void;
  lastSettingsPanelEmitMsRef: MutableRefObject<number>;
  characterState: CharacterState;
  vrmExpressionNames: string[];
  expressionWeights: Record<string, number>;
  onExpressionWeightChange: (name: string, weight: number) => void;
  vrmAnimationOptions: VRMAnimationOption[];
  onPlayVrmAnimation: (url: string, loop: boolean) => void | Promise<void>;
  onPositionChange: (position: { x: number; y: number; z: number }) => void;
  onRotationChange: (rotation: { x: number; y: number; z: number }) => void;
  background: BackgroundOption;
  onApplyBackground: (background: BackgroundSelectorOption) => void;
  lightingIntensity: number;
  onLightingChange?: (intensity: number) => void;
  volume: number;
  isMuted: boolean;
  onVolumeChange?: (value: number) => void;
  onMuteToggle?: () => void;
  onRunKeyframe: (animation: CharacterAnimationData) => void;
  settingsPortalTargetId?: string | null;
  settingsOpen: boolean;
  showSettings: boolean;
  onSettingsClose?: () => void;
  extraSettingsTab?: { label: string; content: ReactNode };
}

export function CharacterAvatarSettingsPanel({
  settingsPanelPropsRef,
  onSettingsPanelPropsChange,
  lastSettingsPanelEmitMsRef,
  characterState,
  vrmExpressionNames,
  expressionWeights,
  onExpressionWeightChange,
  vrmAnimationOptions,
  onPlayVrmAnimation,
  onPositionChange,
  onRotationChange,
  background,
  onApplyBackground,
  lightingIntensity,
  onLightingChange,
  volume,
  isMuted,
  onVolumeChange,
  onMuteToggle,
  onRunKeyframe,
  settingsPortalTargetId,
  settingsOpen,
  showSettings,
  onSettingsClose,
  extraSettingsTab,
}: CharacterAvatarSettingsPanelProps) {
  const panelProps: SettingsPanelPropsFromSource = {
    controls_state: characterState,
    vrm_expression_names: vrmExpressionNames,
    expression_weights: expressionWeights,
    on_expression_weight_change: onExpressionWeightChange,
    vrm_animation_options: vrmAnimationOptions,
    on_play_vrm_animation: onPlayVrmAnimation,
    on_position_change: onPositionChange,
    on_rotation_change: onRotationChange,
    current_background: background as BackgroundSelectorOption,
    on_background_change: onApplyBackground,
    lighting_intensity: lightingIntensity,
    on_lighting_change: onLightingChange ?? (() => {}),
    volume,
    is_muted: isMuted,
    on_volume_change: onVolumeChange,
    on_mute_toggle: onMuteToggle,
    on_run_keyframe: onRunKeyframe,
  };

  if (settingsPanelPropsRef) {
    settingsPanelPropsRef.current = panelProps;
    if (onSettingsPanelPropsChange) {
      const now = Date.now();
      const EMIT_INTERVAL_MS = 100;
      if (now - lastSettingsPanelEmitMsRef.current >= EMIT_INTERVAL_MS) {
        lastSettingsPanelEmitMsRef.current = now;
        // Defer parent setState: calling onSettingsPanelPropsChange during render
        // updates Home and violates React's "no setState while rendering another component".
        queueMicrotask(() => {
          onSettingsPanelPropsChange(panelProps);
        });
      }
    }
    return null;
  }

  const isPanelOpen = settingsPortalTargetId ? settingsOpen : showSettings;
  if (!isPanelOpen) return null;

  const panelContent = (
    <SettingsPanel
      show_close_button={Boolean(settingsPortalTargetId && onSettingsClose)}
      on_close={onSettingsClose}
      extra_tab={
        extraSettingsTab
          ? { label: extraSettingsTab.label, content: extraSettingsTab.content }
          : undefined
      }
      {...panelProps}
    />
  );

  if (settingsPortalTargetId && settingsOpen && typeof document !== 'undefined') {
    const portalEl = document.getElementById(settingsPortalTargetId);
    return portalEl ? createPortal(panelContent, portalEl) : null;
  }
  return <div className="absolute top-4 right-4 z-20">{panelContent}</div>;
}
