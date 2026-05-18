import type { EmotionData } from '@/lib/emotion-manager';
import type { VRM } from '@pixiv/three-vrm';
import type { MutableRefObject, ReactNode } from 'react';
import type { CharacterAnimationData } from '../../utils/character-animation-utils';
import type { BackgroundOption as BackgroundSelectorOption } from '../BackgroundSelector';
import type { SettingsPanelPropsFromSource } from '../SettingsPanel';

export interface CharacterState {
  expression: string;
  animation: string;
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number };
  model: string;
}

export interface BackgroundOption {
  id?: string;
  name?: string;
  type: 'solid' | 'gradient' | 'image';
  value?: string;
  color1?: string;
  color2?: string;
  angle?: number;
  imageUrl?: string;
}

export interface CharacterAvatarProps {
  modelPath?: string;
  initialExpression?: string;
  initialAnimation?: string;
  sessionState?: 'idle' | 'listening' | 'processing' | 'speaking';
  autoRotate?: boolean;
  showControls?: boolean;
  background?: BackgroundOption;
  lightingIntensity?: number;
  cameraPositionOffset?: { x: number; y: number; z: number };
  modelPositionOffset?: { x: number; y: number; z: number };
  modelRotationOffset?: { x: number; y: number; z: number };
  enableClickAnimation?: boolean;
  onCharacterLoad?: (character: VRM) => void;
  onStateChange?: (state: CharacterState) => void;
  onEmotionUpdate?: (applyEmotion: (emotion: EmotionData) => void) => void;
  onVisemeControl?: (setViseme: (viseme: string, intensity: number) => void) => void;
  onExpressionControl?: (setExpression: (expression: string, weight: number) => void) => void;
  onKeyframeAnimationControl?: (
    playKeyframeAnimation: (animation: CharacterAnimationData) => void
  ) => void;
  /** Called when user changes background from Settings panel (for parent state sync) */
  onBackgroundChange?: (background: BackgroundSelectorOption) => void;
  /** Called when user changes lighting intensity from Settings panel */
  onLightingChange?: (intensity: number) => void;
  /** Audio: volume 0–100, used when rendering Audio tab */
  volume?: number;
  onVolumeChange?: (value: number) => void;
  isMuted?: boolean;
  onMuteToggle?: () => void;
  /** When set, settings panel is rendered into this element id (e.g. from page layout) */
  settingsPortalTargetId?: string | null;
  /** Controlled open state when using portal */
  settingsOpen?: boolean;
  /** Called when user closes the settings panel (when using portal) */
  onSettingsClose?: () => void;
  /** Extra tab shown first in settings (e.g. conversation history from page) */
  extraSettingsTab?: { label: string; content: ReactNode };
  /** When set, panel is rendered by parent (e.g. page); this ref is filled with panel props each render */
  settingsPanelPropsRef?: MutableRefObject<SettingsPanelPropsFromSource | null>;
  /** When using settingsPanelPropsRef, notify parent to re-render */
  onSettingsPanelPropsChange?: (props: SettingsPanelPropsFromSource) => void;
}
