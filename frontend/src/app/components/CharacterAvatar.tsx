'use client';

import { EmotionData, EmotionManager } from '@/lib/emotion-manager';
import { ExpressionController } from '@/lib/expression-controller';
import { LipSyncAnalyzer } from '@/lib/lip-sync-analyzer';
import {
  DEFAULT_IDLE_VRMA_URL,
  isDefaultIdleVrmaRequest,
  loadVRMAAnimationClipFromUrl,
} from '@/lib/vrm-animation-clip';
import { VRMBlendShapeController, VRMUtils, getLipSyncFactorFromEmotions } from '@/lib/vrm-utils';
import { VRM, VRMLoaderPlugin } from '@pixiv/three-vrm';
import { Settings, User, VolumeX } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import SettingsPanel, {
  type SettingsPanelPropsFromSource,
} from './SettingsPanel';
import { type BackgroundOption as BackgroundSelectorOption } from './BackgroundSelector';
import { type VRMAnimationOption } from './CharacterSettings';

interface CharacterState {
  expression: string;
  animation: string;
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number };
  model: string;
}

type JsonRecord = Record<string, unknown>;

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

interface CharacterAvatarProps {
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
  settingsPanelPropsRef?: React.MutableRefObject<SettingsPanelPropsFromSource | null>;
  /** When using settingsPanelPropsRef, notify parent to re-render */
  onSettingsPanelPropsChange?: (props: SettingsPanelPropsFromSource) => void;
}

const SETTINGS_TAB_LABELS: Record<
  'controls' | 'keyframe' | 'background' | 'lighting' | 'audio',
  string
> = {
  controls: 'Character',
  keyframe: 'Keyframe',
  background: 'Background',
  lighting: 'Lighting',
  audio: 'Audio',
};

const VISEME_NAMES = ['aa', 'ih', 'ou', 'ee', 'oh'] as const;
const MIN_LIP_SYNC_UI_FACTOR = 0.2;
const VISEME_SMOOTHING_ALPHA = 0.35;

const DEFAULT_LOOKAT_TARGET = new THREE.Vector3(0, 1, 1); // 1m ahead, 1m up

const getSessionPoseOffsets = (sessionState: 'idle' | 'listening' | 'processing' | 'speaking') => {
  switch (sessionState) {
    case 'listening':
      return {
        position: { x: 0, y: 0, z: 0.08 },
        rotation: { x: -0.08, y: 0, z: 0 },
        expression: 'happy',
        animation: 'idle',
      };
    case 'processing':
      return {
        position: { x: 0.02, y: 0, z: 0.04 },
        rotation: { x: -0.03, y: 0.08, z: 0.03 },
        expression: 'thinking',
        animation: 'thinking',
      };
    case 'speaking':
      return {
        position: { x: 0.03, y: 0, z: 0.05 },
        rotation: { x: -0.04, y: -0.04, z: 0 },
        expression: 'happy',
        animation: 'idle',
      };
    default:
      return {
        position: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0 },
        expression: 'neutral',
        animation: 'idle',
      };
  }
};

const getRootScenePosition = (
  modelPositionOffset: { x: number; y: number; z: number },
  sessionState: 'idle' | 'listening' | 'processing' | 'speaking',
) => {
  const sessionPose = getSessionPoseOffsets(sessionState);

  return {
    x: modelPositionOffset.x + sessionPose.position.x,
    y: modelPositionOffset.y + sessionPose.position.y,
    z: modelPositionOffset.z + sessionPose.position.z,
  };
};

const asRecord = (value: unknown): JsonRecord | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as JsonRecord;
};

const getVrmSpecVersion = (gltf: { parser?: { json?: { extensions?: JsonRecord } } }, vrm?: VRM | null): string | null => {
  const extensions = gltf.parser?.json?.extensions;
  const vrm0Extension = asRecord(extensions?.VRM);
  if (typeof vrm0Extension?.specVersion === 'string') {
    return vrm0Extension.specVersion;
  }

  const vrm1Extension = asRecord(extensions?.VRMC_vrm);
  if (typeof vrm1Extension?.specVersion === 'string') {
    return vrm1Extension.specVersion;
  }

  const vrmMeta = asRecord(asRecord(vrm)?.meta);
  if (typeof vrmMeta?.metaVersion === 'string') {
    return vrmMeta.metaVersion;
  }

  return null;
};
export default function CharacterAvatar({
  modelPath = '/characters/models/sakura.vrm',
  initialExpression = 'neutral',
  initialAnimation = 'idle',
  sessionState = 'idle',
  autoRotate = false,
  showControls = true,
  background = {
    type: 'gradient',
    color1: '#e0e7ff',
    color2: '#c7d2fe',
    angle: 135
  },
  lightingIntensity = 1,
  cameraPositionOffset = { x: 0, y: 0, z: 0 },
  modelPositionOffset = { x: 0, y: 0, z: 0 },
  modelRotationOffset = { x: 0, y: 0, z: 0 },
  enableClickAnimation = false,
  onCharacterLoad,
  onStateChange,
  onEmotionUpdate,
  onVisemeControl,
  onExpressionControl,
  onKeyframeAnimationControl,
  onBackgroundChange,
  onLightingChange,
  volume = 80,
  onVolumeChange,
  isMuted = false,
  onMuteToggle,
  settingsPortalTargetId = null,
  settingsOpen = false,
  onSettingsClose,
  extraSettingsTab,
  settingsPanelPropsRef,
  onSettingsPanelPropsChange,
}: CharacterAvatarProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const charactersRef = useRef<VRM | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const clockRef = useRef<THREE.Clock | null>(null);
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const currentActionRef = useRef<THREE.AnimationAction | null>(null);
  const isPlayingSequence = useRef(false);
  const blendShapeControllerRef = useRef<VRMBlendShapeController | null>(null);
  const lipSyncAnalyzerRef = useRef<LipSyncAnalyzer | null>(null);
  const expressionControllerRef = useRef<ExpressionController | null>(null);
  const autoBlinkCleanupRef = useRef<(() => void) | null>(null);
  const onVisemeControlRef = useRef(onVisemeControl);
  const onExpressionControlRef = useRef(onExpressionControl);
  const onKeyframeAnimationControlRef = useRef(onKeyframeAnimationControl);
  const currentExpressionRef = useRef<{ expression: string; weight: number }>({ expression: 'neutral', weight: 1.0 });
  const expressionTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const keyframeAnimationTimeoutsRef = useRef<NodeJS.Timeout[]>([]);
  const playKeyframeAnimationInternalRef = useRef<((animation: CharacterAnimationData) => void) | null>(null);
  const setExpressionWeightsRef = useRef<(weights: Record<string, number>) => void>(() => {});
  // VRM-applied expression weights (includes visemes after attenuation)
  const expressionWeightsAppliedRef = useRef<Record<string, number>>({});
  // UI display values (visemes may be shown as estimated raw values)
  const expressionWeightsDisplayRef = useRef<Record<string, number>>({});
  const expressionWeightsUiRef = useRef<Record<string, number>>({});
  const lastManualExpressionUpdateMsRef = useRef<Record<string, number>>({});
  const lastSettingsPanelEmitMsRef = useRef(0);

  useEffect(() => {
    onVisemeControlRef.current = onVisemeControl;
    onExpressionControlRef.current = onExpressionControl;
    onKeyframeAnimationControlRef.current = onKeyframeAnimationControl;
  }, [onExpressionControl, onKeyframeAnimationControl, onVisemeControl]);
  const initializeSceneRef = useRef<() => { ok: boolean; disposeResize?: () => void }>(() => ({ ok: false }));
  const loadCharacterRef = useRef<() => Promise<void>>(async () => {});
  const cleanupRef = useRef<() => void>(() => {});
  const updateCharacterExpressionRef = useRef<(expression: string) => Promise<void>>(async () => {});
  const updateCharacterAnimationRef = useRef<(animation: string) => Promise<void>>(async () => {});
  const updateSceneBackgroundRef = useRef<(options: BackgroundOption) => void>(() => {});
  const loadedModelPathRef = useRef(modelPath);
  const loadedVrmSpecVersionRef = useRef<string | null>(null);
  /** Hips X/Z at t=0 from {@link DEFAULT_IDLE_VRMA_URL}; used to align other VRMA clips. */
  const idleHipsBaselineRef = useRef<{ x: number; z: number } | null>(null);

  const applyRootScenePosition = useCallback((vrm?: VRM | null) => {
    const targetVrm = vrm ?? charactersRef.current;
    if (!targetVrm) return;

    const position = getRootScenePosition(modelPositionOffset, sessionState);
    targetVrm.scene.position.set(position.x, position.y, position.z);
  }, [modelPositionOffset, sessionState]);

  const [isLoading, setIsLoading] = useState(true);
  const [avatarRenderMode, setAvatarRenderMode] = useState<'webgl' | 'fallback'>('webgl');
  const [error, setError] = useState<string | null>(null);
  const [characterState, setCharacterState] = useState<CharacterState>({
    expression: initialExpression,
    animation: initialAnimation,
    position: { x: 0, y: 0, z: 0 },
    rotation: { x: 0, y: 0, z: 0 },
    model: modelPath,
  });
  const [showSettings, setShowSettings] = useState(false);
  const [availableExpressions, setAvailableExpressions] = useState<string[]>([]);
  const [availableAnimations, setAvailableAnimations] = useState<string[]>([]);
  const [vrmAnimationOptions, setVrmAnimationOptions] = useState<VRMAnimationOption[]>([]);
  const [vrmExpressionNames, setVrmExpressionNames] = useState<string[]>([]);
  const [expressionWeights, setExpressionWeights] = useState<Record<string, number>>({});

  setExpressionWeightsRef.current = (weights: Record<string, number>) => {
    expressionWeightsUiRef.current = { ...weights };
    setExpressionWeights(weights);
  };

  // Initialize Three.js scene
  useEffect(() => {
    const init = initializeSceneRef.current();
    if (!init.ok) {
      setAvatarRenderMode('fallback');
      setIsLoading(false);
      return () => {
        cleanupRef.current();
      };
    }
    void loadCharacterRef.current();
    return () => {
      cleanupRef.current();
      init.disposeResize?.();
    };
  }, []);

  // Handle model path changes
  useEffect(() => {
    if (loadedModelPathRef.current !== modelPath) {
      loadedModelPathRef.current = modelPath;
      setCharacterState(prev => ({ ...prev, model: modelPath }));
      void loadCharacterRef.current();
    }
  }, [modelPath]);

  // Update camera position when offset changes
  useEffect(() => {
    if (cameraRef.current) {
      cameraRef.current.position.set(
        0 + cameraPositionOffset.x,
        1.4 + cameraPositionOffset.y,
        1.5 + cameraPositionOffset.z
      );
      cameraRef.current.lookAt(0 + cameraPositionOffset.x, 1, 0);
    }
  }, [cameraPositionOffset]);

  // Update model position when offset changes
  useEffect(() => {
    applyRootScenePosition();
  }, [applyRootScenePosition]);

  // Update model rotation when offset changes
  useEffect(() => {
    if (charactersRef.current) {
      const sessionPose = getSessionPoseOffsets(sessionState);
      charactersRef.current.scene.rotation.set(
        modelRotationOffset.x + sessionPose.rotation.x,
        Math.PI + modelRotationOffset.y + sessionPose.rotation.y,
        modelRotationOffset.z + sessionPose.rotation.z
      );
    }
  }, [modelRotationOffset, sessionState]);

  // Update character state when props change
  useEffect(() => {
    if (charactersRef.current) {
      void updateCharacterAnimationRef.current(initialAnimation);
    }
  }, [initialExpression, initialAnimation]);

  useEffect(() => {
    if (!charactersRef.current) {
      return;
    }

    const sessionPose = getSessionPoseOffsets(sessionState);
    void updateCharacterAnimationRef.current(sessionPose.animation);
  }, [sessionState]);

  // Update background when options change
  useEffect(() => {
    if (sceneRef.current && background) {
      updateSceneBackgroundRef.current(background);
    }
  }, [background]);

  // Update lighting when intensity changes
  useEffect(() => {
    if (sceneRef.current) {
      sceneRef.current.traverse((child) => {
        if (child instanceof THREE.Light) {
          if (child instanceof THREE.AmbientLight) {
            child.intensity = 0.7 * lightingIntensity;
          } else if (child instanceof THREE.DirectionalLight) {
            const position = child.position;
            if (position.x === 2 && position.y === 3 && position.z === 2) {
              child.intensity = 0.9 * lightingIntensity; // Main key light
            } else if (position.x === -2 && position.y === 2 && position.z === 2) {
              child.intensity = 0.4 * lightingIntensity; // Fill light
            } else if (position.x === 0 && position.y === 2 && position.z === -3) {
              child.intensity = 0.3 * lightingIntensity; // Rim light
            }
          }
        }
      });
    }
  }, [lightingIntensity]);

  const parseGradientColors = (color: string): string => {
    // Parse CSS gradient values like "linear-gradient(45deg, #ff0000, #00ff00)"
    const gradientMatch = color.match(/linear-gradient\((.*)\)/);
    if (gradientMatch) {
      const parts = gradientMatch[1].split(',').map(s => s.trim());
      if (parts.length >= 2) {
        // Return the first color from the gradient
        return parts[1].replace(/\s+\d+%?$/, '');
      }
    }
    return color;
  };

  const createGradientTexture = (options: BackgroundOption): THREE.Texture => {
    const canvas = document.createElement('canvas');
    canvas.width = 1024;
    canvas.height = 1024;
    const context = canvas.getContext('2d')!;
    
    // Parse colors if they contain gradient values
    const color1 = parseGradientColors(options.color1 || '#e0e7ff');
    const color2 = parseGradientColors(options.color2 || '#c7d2fe');
    
    // Calculate gradient angle
    const angle = (options.angle || 0) * Math.PI / 180;
    const x1 = canvas.width / 2 - Math.cos(angle) * canvas.width / 2;
    const y1 = canvas.height / 2 - Math.sin(angle) * canvas.height / 2;
    const x2 = canvas.width / 2 + Math.cos(angle) * canvas.width / 2;
    const y2 = canvas.height / 2 + Math.sin(angle) * canvas.height / 2;
    
    const gradient = context.createLinearGradient(x1, y1, x2, y2);
    gradient.addColorStop(0, color1);
    gradient.addColorStop(1, color2);
    
    context.fillStyle = gradient;
    context.fillRect(0, 0, canvas.width, canvas.height);
    
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    return texture;
  };

  /** Normalize BackgroundSelector-style option (gradient value as CSS) to scene format */
  const normalizeBackgroundForScene = (options: BackgroundOption): BackgroundOption => {
    if (options.type !== 'gradient' || options.color1) return options;
    const css = options.value || '';
    const angleMatch = css.match(/(\d+)deg/);
    const angle = angleMatch ? Number(angleMatch[1]) : 135;
    const colorMatches = css.match(/#[0-9a-fA-F]{6}|rgb\([^)]+\)|rgba\([^)]+\)/g);
    const color1 = colorMatches?.[0] ?? '#e0e7ff';
    const color2 = colorMatches?.[colorMatches.length - 1] ?? '#c7d2fe';
    return { ...options, color1, color2, angle };
  };

  const fallbackSurfaceStyle = useMemo((): CSSProperties => {
    const bg =
      background ?? {
        type: 'gradient' as const,
        color1: '#e0e7ff',
        color2: '#c7d2fe',
        angle: 135,
      };
    const normalized = normalizeBackgroundForScene(bg);
    if (normalized.type === 'solid') {
      const color = parseGradientColors(normalized.color1 || normalized.value || '#f5f5f5');
      return { backgroundColor: color };
    }
    if (normalized.type === 'gradient') {
      const c1 = normalized.color1 || '#e0e7ff';
      const c2 = normalized.color2 || '#c7d2fe';
      const angle = normalized.angle ?? 135;
      return { background: `linear-gradient(${angle}deg, ${c1}, ${c2})` };
    }
    if (normalized.type === 'image' && (normalized.imageUrl || normalized.value)) {
      const url = normalized.imageUrl || normalized.value || '';
      return {
        backgroundImage: `url(${JSON.stringify(url)})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      };
    }
    return { background: 'linear-gradient(135deg, #e0e7ff, #c7d2fe)' };
  }, [background]);

  const updateSceneBackground = (options: BackgroundOption) => {
    if (!sceneRef.current) return;

    // Dispose of previous background texture if it exists
    const previousBackground = sceneRef.current.background;
    if (previousBackground instanceof THREE.Texture) {
      previousBackground.dispose();
    }

    const normalized = normalizeBackgroundForScene(options);
    if (normalized.type === 'solid') {
      const color = parseGradientColors(normalized.color1 || normalized.value || '#f5f5f5');
      sceneRef.current.background = new THREE.Color(color);
    } else if (normalized.type === 'gradient') {
      sceneRef.current.background = createGradientTexture(normalized);
    } else if (normalized.type === 'image' && (normalized.imageUrl || normalized.value)) {
      const loader = new THREE.TextureLoader();
      const imageUrl = normalized.imageUrl || normalized.value || '';
      if (imageUrl) {
        loader.load(
          imageUrl,
        (texture) => {
          texture.colorSpace = THREE.SRGBColorSpace;
          if (sceneRef.current) {
            // Dispose of previous texture
            const prev = sceneRef.current.background;
            if (prev instanceof THREE.Texture) {
              prev.dispose();
            }
            sceneRef.current.background = texture;
          }
        },
        undefined,
        (error) => {
          console.error('Error loading background image:', error);
          // Fallback to solid color
          if (sceneRef.current) {
            sceneRef.current.background = new THREE.Color('#f5f5f5');
          }
        }
        );
      }
    } else {
      sceneRef.current.background = new THREE.Color('#f5f5f5');
    }
  };

  const initializeScene = (): { ok: boolean; disposeResize?: () => void } => {
    if (!containerRef.current) {
      return { ok: false };
    }

    const clearSceneRefsOnFailure = () => {
      const current = sceneRef.current;
      if (current?.background instanceof THREE.Texture) {
        current.background.dispose();
      }
      sceneRef.current = null;
      cameraRef.current = null;
    };

    // Scene with better background
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // Set initial background
    if (background) {
      updateSceneBackground(background);
    } else {
      scene.background = new THREE.Color('#f5f5f5');
    }

    scene.fog = new THREE.Fog(0xf5f5f5, 5, 10);

    // Camera
    const camera = new THREE.PerspectiveCamera(
      50,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.1,
      1000
    );
    camera.position.set(
      0 + cameraPositionOffset.x,
      1.4 + cameraPositionOffset.y,
      1.5 + cameraPositionOffset.z
    );
    camera.lookAt(0 + cameraPositionOffset.x, 1, 0);
    cameraRef.current = camera;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: 'low-power',
      });
    } catch (err) {
      console.warn('[CharacterAvatar] WebGL unavailable; using static avatar fallback.', err);
      clearSceneRefsOnFailure();
      return { ok: false };
    }

    if (!renderer.getContext()) {
      renderer.dispose();
      console.warn(
        '[CharacterAvatar] WebGL unavailable; using static avatar fallback.',
        new Error('No WebGL rendering context')
      );
      clearSceneRefsOnFailure();
      return { ok: false };
    }

    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);

    const pixelRatio = window.devicePixelRatio;
    renderer.setPixelRatio(pixelRatio);

    renderer.outputColorSpace = THREE.SRGBColorSpace;

    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    renderer.domElement.addEventListener('click', handleCanvasClick);
    renderer.domElement.style.cursor = enableClickAnimation ? 'pointer' : 'default';

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7 * lightingIntensity);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9 * lightingIntensity);
    directionalLight.position.set(2, 3, 2);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    directionalLight.shadow.camera.near = 0.1;
    directionalLight.shadow.camera.far = 10;
    directionalLight.shadow.camera.left = -2;
    directionalLight.shadow.camera.right = 2;
    directionalLight.shadow.camera.top = 2;
    directionalLight.shadow.camera.bottom = -2;
    scene.add(directionalLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.4 * lightingIntensity);
    fillLight.position.set(-2, 2, 2);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.3 * lightingIntensity);
    rimLight.position.set(0, 2, -3);
    scene.add(rimLight);

    clockRef.current = new THREE.Clock();

    const handleResize = () => {
      if (!containerRef.current || !camera || !renderer) return;

      camera.aspect = containerRef.current.clientWidth / containerRef.current.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    };

    window.addEventListener('resize', handleResize);

    animate();

    return {
      ok: true,
      disposeResize: () => {
        window.removeEventListener('resize', handleResize);
      },
    };
  };

  const loadVRMAnimation = async (
    animationUrl: string,
    vrm: VRM,
    loop: boolean = true,
  ) => {
    try {
      const { clip: initialClip } = await loadVRMAAnimationClipFromUrl(animationUrl, vrm);
      if (!initialClip) {
        return { success: false, duration: 0 };
      }
      let clip = initialClip;

      if (isDefaultIdleVrmaRequest(animationUrl)) {
        const baseline = VRMUtils.sampleHipsPositionXZAtTime(clip, vrm, 0);
        if (baseline) {
          idleHipsBaselineRef.current = baseline;
        }
      } else {
        let baseline = idleHipsBaselineRef.current;
        if (!baseline) {
          const idlePack = await loadVRMAAnimationClipFromUrl(DEFAULT_IDLE_VRMA_URL, vrm);
          if (idlePack.clip) {
            baseline = VRMUtils.sampleHipsPositionXZAtTime(idlePack.clip, vrm, 0);
            if (baseline) {
              idleHipsBaselineRef.current = baseline;
            }
          }
        }
        const other = VRMUtils.sampleHipsPositionXZAtTime(clip, vrm, 0);
        if (baseline && other) {
          clip = VRMUtils.rebaseHipsHorizontalInClip(clip, vrm, baseline, other);
        }
      }

      if (!mixerRef.current) {
        mixerRef.current = new THREE.AnimationMixer(vrm.scene);
      }

      if (currentActionRef.current) {
        currentActionRef.current.stop();
      }

      const action = mixerRef.current.clipAction(clip);
      if (loop) {
        action.setLoop(THREE.LoopRepeat, Infinity);
      } else {
        action.setLoop(THREE.LoopOnce, 1);
        action.clampWhenFinished = true;
      }
      action.play();
      currentActionRef.current = action;

      applyRootScenePosition(vrm);

      return { success: true, duration: clip.duration };
    } catch (error) {
      console.error('Error loading VRM animation:', error);
    }

    return { success: false, duration: 0 };
  };

  const playRandomAnimation = async (vrm: VRM) => {
    if (isPlayingSequence.current) return;
    
    isPlayingSequence.current = true;
    const animations = ['VRMA_03', 'VRMA_04', 'VRMA_05', 'VRMA_06', 'VRMA_07'];
    
    // Select a random animation
    const randomIndex = Math.floor(Math.random() * animations.length);
    const animName = animations[randomIndex];
    const animUrl = `/animations/${animName}.vrma`;
    
    
    try {
      // Load animation without looping and get its duration
      const result = await loadVRMAnimation(animUrl, vrm, false);
      
      if (result.success) {
        // Wait for the animation to complete based on its actual duration
        const waitTime = (result.duration * 1000) + 100; // Add 100ms buffer
        await new Promise(resolve => setTimeout(resolve, waitTime));
      } else {
        // Fallback wait time if duration couldn't be determined
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    } catch (error) {
      console.error(`Failed to play animation ${animName}:`, error);
    }
    
    // Return to idle animation
    await loadVRMAnimation(DEFAULT_IDLE_VRMA_URL, vrm, true);
    isPlayingSequence.current = false;
  };

  const handleCanvasClick = () => {
    if (enableClickAnimation && charactersRef.current && !isPlayingSequence.current) {
      playRandomAnimation(charactersRef.current);
    }
  };

  const loadCharacter = async () => {
    if (!sceneRef.current) return;

    try {
      setIsLoading(true);
      setError(null);
      loadedVrmSpecVersionRef.current = null;

      // Remove existing character
      if (charactersRef.current) {
        sceneRef.current.remove(charactersRef.current.scene);
        charactersRef.current = null;
      }
      idleHipsBaselineRef.current = null;

      // Load VRM model via fetch + parseAsync so texture base path is correct.
      // Force TextureLoader instead of ImageBitmapLoader: blob URLs from bufferView
      // often fail with ImageBitmapLoader ("Couldn't load texture blob:..."), and
      // failed textures become undefined, causing three-vrm setTextureColorSpace to throw.
      const prev_create_image_bitmap =
        typeof window !== 'undefined' ? window.createImageBitmap : undefined;
      if (typeof window !== 'undefined') {
        (window as unknown as { createImageBitmap?: unknown }).createImageBitmap = undefined;
      }
      try {
        const loader = new GLTFLoader();
        loader.register((parser) => new VRMLoaderPlugin(parser));

        const absolute_url = new URL(modelPath, window.location.origin).href;
        const response = await fetch(absolute_url);
        if (!response.ok) {
          throw new Error(`Failed to fetch VRM: ${response.status} ${response.statusText}`);
        }
        const array_buffer = await response.arrayBuffer();
        const base_path = absolute_url.substring(0, absolute_url.lastIndexOf('/') + 1);
        const gltf = await loader.parseAsync(array_buffer, base_path);
        const vrm = gltf.userData.vrm as VRM;

        if (!vrm) {
          throw new Error('Failed to load VRM from file');
        }

        loadedVrmSpecVersionRef.current = getVrmSpecVersion(gltf, vrm);

        // Add to scene
        sceneRef.current.add(vrm.scene);
        charactersRef.current = vrm;

        // Rotate character 180 degrees to face forward
        vrm.scene.rotation.set(
          modelRotationOffset.x,
          Math.PI + modelRotationOffset.y,
          modelRotationOffset.z
        );

        // Set initial position
        applyRootScenePosition(vrm);

        // Initialize lip-sync and expression controllers
        blendShapeControllerRef.current = new VRMBlendShapeController(vrm);
        expressionControllerRef.current = new ExpressionController();

        // Initialize LipSyncAnalyzer without AudioContext (will be initialized on first use)
        lipSyncAnalyzerRef.current = new LipSyncAnalyzer();

        const available_expressions = blendShapeControllerRef.current.getAvailableExpressions();
        setVrmExpressionNames(available_expressions);

        const requiredVisemes = ['aa', 'ih', 'ou', 'ee', 'oh'];
        const missingVisemes = requiredVisemes.filter(v => !available_expressions.includes(v));
        if (missingVisemes.length > 0) {
          console.warn(
            `[CharacterAvatar] VRM model missing lip sync expressions: ${missingVisemes.join(', ')}. ` +
            `Available: ${available_expressions.join(', ')}`
          );
        }

        const initial_weights: Record<string, number> = {};
        available_expressions.forEach((name) => {
          initial_weights[name] = name === 'neutral' ? 1 : 0;
        });
        setExpressionWeights(initial_weights);

        if (vrm.expressionManager?.expressionMap) {
        }
        // Start automatic blinking
        if (autoBlinkCleanupRef.current) {
          autoBlinkCleanupRef.current();
        }
        autoBlinkCleanupRef.current = blendShapeControllerRef.current.startAutoBlink();

        // Set initial pose
        await updateCharacterExpression(characterState.expression);
        await updateCharacterAnimation(characterState.animation);

        // Get available expressions and animations
        await fetchAvailableFeatures();

        // Load default idle animation
        try {
          await loadVRMAnimation(DEFAULT_IDLE_VRMA_URL, vrm, true);
        } catch (animationError) {
          console.error('[CharacterAvatar] Failed to load default idle animation:', animationError);
        }
      } finally {
        if (typeof window !== 'undefined' && prev_create_image_bitmap !== undefined) {
          (window as unknown as { createImageBitmap?: unknown }).createImageBitmap =
            prev_create_image_bitmap;
        }
      }

      // Create viseme control function (attenuate based on active emotion max)
      const setViseme = (viseme: string, intensity: number) => {
        if (blendShapeControllerRef.current) {
          const visemeMap: Record<string, string> = {
            'A': 'aa',
            'I': 'ih',
            'U': 'ou',
            'E': 'ee',
            'O': 'oh',
            'Closed': 'neutral'
          };
          const vrmExpression = visemeMap[viseme] || 'neutral';
          const factor = getLipSyncFactorFromEmotions(expressionWeightsAppliedRef.current);
          blendShapeControllerRef.current.setViseme(vrmExpression, intensity * factor);
        }
      };

      // Create expression control function
      const setExpression = (expression: string, weight: number) => {
        
        // Clear existing timeout if any
        if (expressionTimeoutRef.current) {
          clearTimeout(expressionTimeoutRef.current);
          expressionTimeoutRef.current = null;
        }
        
        // Map expressions to available ones if VRM doesn't support them
        // Fallback to expressions that are guaranteed to exist in the VRM model
        const expressionFallbackMap: Record<string, string> = {
          'curious': 'neutral',     // curious doesn't exist in VRM
          'surprised': 'happy',     // surprised might not exist in some VRM models, use happy as fallback
        };
        
        const mappedExpression = expressionFallbackMap[expression] || expression;
        
        if (blendShapeControllerRef.current) {
          // Use the VRM expression manager to set expressions (use ref so setExpression works outside inner try scope)
          const expressionManager = charactersRef.current?.expressionManager;
          
          if (expressionManager) {
            // Log available expressions for debugging
            const availableExpressions = Object.keys(expressionManager.expressionMap);
            
            // Reset all expressions first if weight is significant
            if (weight > 0.1) {
              availableExpressions.forEach(name => {
                if (name !== expression) {
                  expressionManager.setValue(name, 0);
                }
              });
            }
            
            // Set the target expression
            if (expressionManager.expressionMap[mappedExpression]) {
              expressionManager.setValue(mappedExpression, weight);
              
              // Store current expression for restoration after lip-sync
              currentExpressionRef.current = { expression: mappedExpression, weight };
              
              // Set timer to return to neutral after 5 seconds (only for non-neutral expressions)
              if (mappedExpression !== 'neutral' && weight > 0.1) {
                expressionTimeoutRef.current = setTimeout(() => {
                  // Gradually transition back to neutral
                  availableExpressions.forEach(name => {
                    if (name !== 'neutral') {
                      expressionManager.setValue(name, 0);
                    }
                  });
                  expressionManager.setValue('neutral', 1.0);
                  currentExpressionRef.current = { expression: 'neutral', weight: 1.0 };
                }, 5000);
              }
            } else {
              // Try to find a similar expression
              const similarExpression = availableExpressions.find(name => 
                name.toLowerCase().includes(mappedExpression.toLowerCase()) ||
                mappedExpression.toLowerCase().includes(name.toLowerCase())
              );
              
              if (similarExpression) {
                expressionManager.setValue(similarExpression, weight);
                // Store current expression for restoration after lip-sync
                currentExpressionRef.current = { expression: similarExpression, weight };
                
                // Set timer to return to neutral after 5 seconds (only for non-neutral expressions)
                if (similarExpression !== 'neutral' && weight > 0.1) {
                  expressionTimeoutRef.current = setTimeout(() => {
                    // Gradually transition back to neutral
                    availableExpressions.forEach(name => {
                      if (name !== 'neutral') {
                        expressionManager.setValue(name, 0);
                      }
                    });
                    expressionManager.setValue('neutral', 1.0);
                    currentExpressionRef.current = { expression: 'neutral', weight: 1.0 };
                  }, 5000);
                }
              } else {
                // Fallback to neutral expression which should always exist
                expressionManager.setValue('neutral', 1.0);
                currentExpressionRef.current = { expression: 'neutral', weight: 1.0 };
              }
            }
          } else {
            console.error('[CharacterAvatar] Expression manager not available');
          }
        } else {
          console.error('[CharacterAvatar] BlendShape controller not available');
        }
      };

      // Initialize with neutral expression
      try {
        setExpression('neutral', 1.0);
      } catch (error) {
        console.error('[CharacterAvatar] Error setting initial neutral expression:', error);
      }

      const playKeyframeAnimation = (animation: CharacterAnimationData) => {
        const vrmRef = charactersRef.current;
        const blendShapeRef = blendShapeControllerRef.current;
        if (!vrmRef || !blendShapeRef) return;

        keyframeAnimationTimeoutsRef.current.forEach((id) => clearTimeout(id));
        keyframeAnimationTimeoutsRef.current = [];

        isPlayingSequence.current = true;

        animation.keyframes.forEach((keyframe) => {
          const timeout_id = setTimeout(() => {
            if (keyframe.bones) {
              Object.entries(keyframe.bones).forEach(([bone_name, bone_data]) => {
                const rot = bone_data.rotation;
                const euler = new THREE.Euler(rot.x, rot.y, rot.z);
                VRMUtils.setHumanoidBoneRotation(vrmRef, bone_name, euler, 0);
              });
            }
            if (keyframe.expressions && blendShapeControllerRef.current) {
              const factor = getLipSyncFactorFromEmotions(keyframe.expressions);
              const blended = { ...keyframe.expressions };
              VISEME_NAMES.forEach((name) => {
                const v = blended[name];
                if (typeof v === 'number') {
                  blended[name] = v * factor;
                }
              });

              blendShapeControllerRef.current.setExpressions(blended);
              const current = blendShapeControllerRef.current.getCurrentExpressions();
              setExpressionWeightsRef.current(current);
            }
          }, keyframe.time);
          keyframeAnimationTimeoutsRef.current.push(timeout_id);
        });

        const end_timeout = setTimeout(() => {
          keyframeAnimationTimeoutsRef.current = [];
          isPlayingSequence.current = false;
        }, animation.duration + 100);
        keyframeAnimationTimeoutsRef.current.push(end_timeout);
      };

      playKeyframeAnimationInternalRef.current = playKeyframeAnimation;
      if (charactersRef.current) onCharacterLoad?.(charactersRef.current);
      onEmotionUpdate?.(applyEmotionToCharacter);
      onVisemeControl?.(setViseme);
      onExpressionControl?.(setExpression);
      onKeyframeAnimationControl?.(playKeyframeAnimation);
      setIsLoading(false);
    } catch (error) {
      console.error('Error loading character:', error);
      setError('Failed to load character model. Please try again.');
      setIsLoading(false);
    }
  };

  const fetchAvailableFeatures = async () => {
    try {
      const response = await fetch('/api/character?action=supported_features');
      const result = await response.json();

      if (result.success) {
        setAvailableExpressions(result.expressions || []);
        setAvailableAnimations(result.animations || []);
      }
    } catch (error) {
      console.error('Error fetching available features:', error);
    }
  };

  const fetchVrmAnimations = useCallback(async () => {
    try {
      const response = await fetch('/api/animations');
      const result = await response.json();
      const files: string[] = result.animations ?? [];
      setVrmAnimationOptions(
        files.map((file) => ({
          value: file.startsWith('/') ? file : `/animations/${file}`,
          label: file,
        })),
      );
    } catch (error) {
      console.error('Error fetching VRM animations:', error);
    }
  }, []);

  const handle_play_vrm_animation = async (url: string, loop: boolean) => {
    const vrm = charactersRef.current;
    if (!vrm) return;
    await loadVRMAnimation(url, vrm, loop);
  };

  const handle_expression_weight_change = (name: string, weight: number) => {
    const is_viseme = (VISEME_NAMES as readonly string[]).includes(name);
    const factor = is_viseme
      ? getLipSyncFactorFromEmotions(expressionWeightsAppliedRef.current)
      : 1;
    const applied_weight = is_viseme ? weight * factor : weight;

    // UI holds the raw value; attenuation happens only when applying to the VRM.
    const next = { ...expressionWeightsUiRef.current, [name]: weight };
    expressionWeightsUiRef.current = next;
    lastManualExpressionUpdateMsRef.current = {
      ...lastManualExpressionUpdateMsRef.current,
      [name]: Date.now(),
    };
    setExpressionWeights(next);
    blendShapeControllerRef.current?.setExpression(name, applied_weight);
  };

  useEffect(() => {
    if (avatarRenderMode !== 'fallback') return;
    onVisemeControlRef.current?.(() => {});
    onExpressionControlRef.current?.(() => {});
    onKeyframeAnimationControlRef.current?.(() => {});
  }, [avatarRenderMode]);

  useEffect(() => {
    if (avatarRenderMode === 'fallback') return;
    fetchVrmAnimations();
  }, [fetchVrmAnimations, avatarRenderMode]);

  const updateCharacterExpression = async (expression: string) => {
    if (!charactersRef.current || !expression) return;

    try {
      const expressionManager = charactersRef.current.expressionManager;
      if (expressionManager) {
        const availableExpressions = Object.keys(expressionManager.expressionMap);

        Object.keys(expressionManager.expressionMap).forEach(name => {
          const currentValue = expressionManager.getValue(name) || 0;
          if (currentValue > 0 && name !== expression) {
            expressionManager.setValue(name, 0);
          }
        });

        if (expressionManager.expressionMap[expression]) {
          expressionManager.setValue(expression, 1);
          currentExpressionRef.current = { expression, weight: 1.0 };
        } else {
          const similarExpression = availableExpressions.find(expr =>
            expr.toLowerCase().includes(expression.toLowerCase()) ||
            expression.toLowerCase().includes(expr.toLowerCase())
          );
          if (similarExpression) {
            expressionManager.setValue(similarExpression, 1);
            currentExpressionRef.current = { expression: similarExpression, weight: 1.0 };
          }
        }
      }

      setCharacterState(prev => ({ ...prev, expression }));
      onStateChange?.({ ...characterState, expression });
    } catch (error) {
      console.error('Error updating expression:', error);
    }
  };

  const applyEmotionToCharacter = (emotionData: EmotionData, transitionDuration: number = 500) => {
    if (!charactersRef.current) return;

    try {
      // Use the EmotionManager to apply emotion to VRM
      EmotionManager.applyEmotionToVRM(charactersRef.current, emotionData, transitionDuration);
      
      // Update character state
      const mapping = EmotionManager.mapEmotionToVRM(emotionData);
      setCharacterState(prev => ({ ...prev, expression: mapping.primary }));
      onStateChange?.({ ...characterState, expression: mapping.primary });

    } catch (error) {
      console.error('Error applying emotion to character:', error);
    }
  };

  const updateCharacterAnimation = async (animation: string) => {
    if (!charactersRef.current || !animation) return;

    try {
      const animationUrl = `/animations/${animation}.vrma`;
      await loadVRMAnimation(animationUrl, charactersRef.current, true);

      setCharacterState(prev => ({ ...prev, animation }));
      onStateChange?.({ ...characterState, animation });
    } catch (error) {
      console.error('Error updating animation:', error);
    }
  };

  const updateCharacterPosition = (position: { x: number; y: number; z: number }) => {
    if (!charactersRef.current) return;

    charactersRef.current.scene.position.set(position.x, position.y, position.z);
    setCharacterState(prev => ({ ...prev, position }));
    onStateChange?.({ ...characterState, position });
  };

  const updateCharacterRotation = (rotation: { x: number; y: number; z: number }) => {
    if (!charactersRef.current) return;

    charactersRef.current.scene.rotation.set(rotation.x, rotation.y, rotation.z);
    setCharacterState(prev => ({ ...prev, rotation }));
    onStateChange?.({ ...characterState, rotation });
  };

  const resetCharacter = async () => {
    if (!charactersRef.current) return;

    try {
      if (charactersRef.current) {
        applyRootScenePosition();
        charactersRef.current.scene.rotation.set(0, 0, 0);
        
        await updateCharacterExpression('neutral');
        await updateCharacterAnimation('idle');
      }
    } catch (error) {
      console.error('Error resetting character:', error);
    }
  };

  const animate = () => {
    if (!rendererRef.current || !sceneRef.current || !cameraRef.current) return;

    animationFrameRef.current = requestAnimationFrame(animate);

    const deltaTime = clockRef.current?.getDelta() || 0;
    
    // Skip frame for performance on mobile devices
    // iOS detection removed - focusing on desktop/PC experience
    // Removed iOS frame skipping - desktop can handle full frame rate

    // Update animation mixer
    if (mixerRef.current && deltaTime > 0) {
      mixerRef.current.update(deltaTime);
    }

    // Update VRM
    if (charactersRef.current) {
      charactersRef.current.update(deltaTime);

      // Sync expression weights from VRM to Character sliders (keyframe, .vrma, lip-sync, etc.)
      const blend_shape = blendShapeControllerRef.current;
      if (blend_shape) {
        const current = blend_shape.getCurrentExpressions();
        const last = expressionWeightsAppliedRef.current;
        const current_keys = Object.keys(current);
        const last_keys = Object.keys(last);
        const EPSILON = 0.0001;
        const MANUAL_HOLD_MS = 250;
        let changed = current_keys.length !== last_keys.length;
        if (!changed) {
          for (let i = 0; i < current_keys.length; i++) {
            const name = current_keys[i];
            const a = current[name] ?? 0;
            const b = last[name] ?? 0;
            // Lip-sync (viseme) weights can change in very small increments; use a tighter epsilon
            // so the UI sliders track the current VRM state smoothly.
            if (Math.abs(a - b) > EPSILON) {
              changed = true;
              break;
            }
          }
        }
        if (changed) {
          const now = Date.now();
          const manual = lastManualExpressionUpdateMsRef.current;
          const ui = expressionWeightsUiRef.current;
          // Convert VRM-applied viseme (often attenuated) into an estimated raw value for UI display:
          // raw ≈ applied / factor, where factor is based on active mouth-using emotions.
          const factor = getLipSyncFactorFromEmotions(current);
          const display: Record<string, number> = { ...current };
          if (factor > 0.001) {
            const effective_factor = Math.max(factor, MIN_LIP_SYNC_UI_FACTOR);
            VISEME_NAMES.forEach((name) => {
              const v = display[name];
              if (typeof v === 'number') {
                display[name] = Math.max(0, Math.min(1, v / effective_factor));
              }
            });
          } else {
            // When factor is 0, lip-sync is fully suppressed; display raw as 0 to avoid inf/NaN.
            VISEME_NAMES.forEach((name) => {
              if (typeof display[name] === 'number') {
                display[name] = 0;
              }
            });
          }

          // Smooth viseme sliders to avoid visual jitter and division noise amplification.
          const prev_display = expressionWeightsDisplayRef.current;
          VISEME_NAMES.forEach((name) => {
            const next_value = display[name];
            const prev_value = prev_display[name];
            if (typeof next_value === 'number' && typeof prev_value === 'number') {
              display[name] =
                prev_value + (next_value - prev_value) * VISEME_SMOOTHING_ALPHA;
            }
          });

          // Preserve user's manual slider input briefly to avoid "fight" with VRM updates.
          for (const [name, ts] of Object.entries(manual)) {
            if (now - ts < MANUAL_HOLD_MS && typeof ui[name] === 'number') {
              display[name] = ui[name];
            }
          }

          setExpressionWeightsRef.current(display);
          expressionWeightsDisplayRef.current = { ...display };
          // Keep this ref as the VRM-applied values (not the UI display values) for stable change detection.
          expressionWeightsAppliedRef.current = { ...current };
        }
      }

    }

    // Auto-rotate
    if (autoRotate && charactersRef.current) {
      charactersRef.current.scene.rotation.y += 0.005;
    }

    rendererRef.current.render(sceneRef.current, cameraRef.current);
  };
  
  const cleanup = () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    // Stop auto-blink
    if (autoBlinkCleanupRef.current) {
      autoBlinkCleanupRef.current();
      autoBlinkCleanupRef.current = null;
    }

    // Clear expression timeout
    if (expressionTimeoutRef.current) {
      clearTimeout(expressionTimeoutRef.current);
      expressionTimeoutRef.current = null;
    }
    
    // Stop and clean up animations
    if (currentActionRef.current) {
      currentActionRef.current.stop();
      currentActionRef.current = null;
    }
    
    if (mixerRef.current) {
      mixerRef.current.stopAllAction();
      mixerRef.current = null;
    }

    keyframeAnimationTimeoutsRef.current.forEach((id) => clearTimeout(id));
    keyframeAnimationTimeoutsRef.current = [];
    playKeyframeAnimationInternalRef.current = null;

    // Dispose of background texture if it exists
    if (sceneRef.current?.background instanceof THREE.Texture) {
      sceneRef.current.background.dispose();
    }

    if (rendererRef.current && containerRef.current) {
      rendererRef.current.domElement.removeEventListener('click', handleCanvasClick);
      containerRef.current.removeChild(rendererRef.current.domElement);
      rendererRef.current.dispose();
    }

    if (charactersRef.current) {
      VRMUtils.dispose(charactersRef.current);
    }

    idleHipsBaselineRef.current = null;
    loadedVrmSpecVersionRef.current = null;
  };

  initializeSceneRef.current = initializeScene;
  loadCharacterRef.current = loadCharacter;
  cleanupRef.current = cleanup;
  updateCharacterExpressionRef.current = updateCharacterExpression;
  updateCharacterAnimationRef.current = updateCharacterAnimation;
  updateSceneBackgroundRef.current = updateSceneBackground;

  const takeScreenshot = () => {
    if (!rendererRef.current) return;

    const canvas = rendererRef.current.domElement;
    const link = document.createElement('a');
    link.download = `character-${Date.now()}.png`;
    link.href = canvas.toDataURL();
    link.click();
  };


  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-100">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error}</p>
          <button
            onClick={loadCharacter}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="character-avatar-root"
      data-avatar-render-mode={avatarRenderMode}
      className="relative h-full bg-gray-100 rounded-lg overflow-hidden"
    >
      {avatarRenderMode === 'fallback' ? (
        <div
          data-testid="character-avatar-fallback"
          className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-4 text-gray-700"
          style={fallbackSurfaceStyle}
        >
          <User className="h-16 w-16 opacity-80" aria-hidden />
          <p className="max-w-sm text-center text-sm">
            3Dアバターを表示できませんが、音声でのご利用はそのままお楽しみいただけます。
          </p>
        </div>
      ) : (
        <div ref={containerRef} className="h-full w-full" />
      )}

      {avatarRenderMode !== 'fallback' && isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-80">
          <div className="text-center">
            <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-blue-500"></div>
            <p className="text-gray-600">Loading character...</p>
          </div>
        </div>
      )}

      {/* Controls - z-30 so gear button stays in front of Settings Panel (z-20). Hide gear when panel is rendered by parent (portal or ref). */}
      {showControls && !isLoading && !settingsPortalTargetId && !settingsPanelPropsRef && (
        <div className="absolute top-4 right-4 z-30 flex flex-col space-y-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 bg-white bg-opacity-80 hover:bg-opacity-100 rounded-full shadow-md transition-colors"
            title="Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      )}

      {/* Settings Panel - when settingsPanelPropsRef is set, parent renders the panel; otherwise render locally or via portal */}
      {(() => {
        if (settingsPanelPropsRef) {
          const next_props: SettingsPanelPropsFromSource = {
            controls_state: characterState,
            vrm_expression_names: vrmExpressionNames,
            expression_weights: expressionWeights,
            on_expression_weight_change: handle_expression_weight_change,
            vrm_animation_options: vrmAnimationOptions,
            on_play_vrm_animation: handle_play_vrm_animation,
            on_position_change: updateCharacterPosition,
            on_rotation_change: updateCharacterRotation,
            current_background: background as BackgroundSelectorOption,
            on_background_change: (bg) => {
              updateSceneBackground(bg);
              onBackgroundChange?.(bg);
            },
            lighting_intensity: lightingIntensity,
            on_lighting_change: onLightingChange ?? (() => {}),
            volume: volume,
            is_muted: isMuted,
            on_volume_change: onVolumeChange,
            on_mute_toggle: onMuteToggle,
            on_run_keyframe: (animation) =>
              playKeyframeAnimationInternalRef.current?.(animation),
          };
          settingsPanelPropsRef.current = next_props;
          if (onSettingsPanelPropsChange) {
            const now = Date.now();
            const EMIT_INTERVAL_MS = 100;
            if (now - lastSettingsPanelEmitMsRef.current >= EMIT_INTERVAL_MS) {
              lastSettingsPanelEmitMsRef.current = now;
              // Defer parent setState: calling onSettingsPanelPropsChange during render
              // updates Home and violates React's "no setState while rendering another component".
              queueMicrotask(() => {
                onSettingsPanelPropsChange(next_props);
              });
            }
          }
          return null;
        }

        const is_panel_open = settingsPortalTargetId ? settingsOpen : showSettings;
        if (!is_panel_open) return null;

        const panel_content = (
          <SettingsPanel
            show_close_button={Boolean(settingsPortalTargetId && onSettingsClose)}
            on_close={onSettingsClose}
            extra_tab={
              extraSettingsTab
                ? { label: extraSettingsTab.label, content: extraSettingsTab.content }
                : undefined
            }
            controls_state={characterState}
            vrm_expression_names={vrmExpressionNames}
            expression_weights={expressionWeights}
            on_expression_weight_change={handle_expression_weight_change}
            vrm_animation_options={vrmAnimationOptions}
            on_play_vrm_animation={handle_play_vrm_animation}
            on_position_change={updateCharacterPosition}
            on_rotation_change={updateCharacterRotation}
            current_background={background as BackgroundSelectorOption}
            on_background_change={(bg) => {
              updateSceneBackground(bg);
              onBackgroundChange?.(bg);
            }}
            lighting_intensity={lightingIntensity}
            on_lighting_change={onLightingChange ?? (() => {})}
            volume={volume}
            is_muted={isMuted}
            on_volume_change={onVolumeChange}
            on_mute_toggle={onMuteToggle}
            on_run_keyframe={(animation) =>
              playKeyframeAnimationInternalRef.current?.(animation)
            }
          />
        );

        if (settingsPortalTargetId && settingsOpen && typeof document !== 'undefined') {
          const portal_el = document.getElementById(settingsPortalTargetId);
          return portal_el ? createPortal(panel_content, portal_el) : null;
        }
        return <div className="absolute top-4 right-4 z-20">{panel_content}</div>;
      })()}
    </div>
  );
}
