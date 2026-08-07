'use client';

import { EmotionData, EmotionManager } from '@/lib/emotion-manager';
import { ExpressionController } from '@/lib/expression-controller';
import { LipSyncAnalyzer } from '@/lib/lip-sync-analyzer';
import {
  DEFAULT_IDLE_VRMA_URL,
} from '@/lib/vrm-animation-clip';
import { VRMBlendShapeController, VRMUtils, getLipSyncFactorFromEmotions } from '@/lib/vrm-utils';
import { VRM, VRMLoaderPlugin } from '@pixiv/three-vrm';
import { Settings, User } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import { type VRMAnimationOption } from './CharacterSettings';
import { getFallbackSurfaceStyle, updateThreeSceneBackground } from './character-avatar/background';
import { loadCharacterVrmAnimation, playRandomVrmAnimation } from './character-avatar/animation';
import { CharacterAvatarSettingsPanel } from './character-avatar/CharacterAvatarSettingsPanel';
import {
  createExpressionSetter,
  createKeyframeAnimationPlayer,
  createVisemeSetter,
  syncExpressionWeightsFromVrm,
} from './character-avatar/controls';
import { initializeCharacterScene } from './character-avatar/scene';
import type { BackgroundOption, CharacterAvatarProps, CharacterState } from './character-avatar/types';
import {
  getRootScenePosition,
  getSessionPoseOffsets,
  getVrmSpecVersion,
  VISEME_NAMES,
} from './character-avatar/utils';

export type { BackgroundOption, CharacterAvatarProps, CharacterState } from './character-avatar/types';
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
  const currentRebasedClipRef = useRef<THREE.AnimationClip | null>(null);
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
  const stopKeyframeAnimationInternalRef = useRef<(() => void) | null>(null);
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

  const fallbackSurfaceStyle = useMemo(() => getFallbackSurfaceStyle(background), [background]);

  const updateSceneBackground = (options: BackgroundOption) => {
    updateThreeSceneBackground(sceneRef.current, options);
  };

  const initializeScene = (): { ok: boolean; disposeResize?: () => void } => {
    return initializeCharacterScene({
      container: containerRef.current,
      sceneRef,
      rendererRef,
      cameraRef,
      clockRef,
      background,
      cameraPositionOffset,
      lightingIntensity,
      enableClickAnimation,
      handleCanvasClick,
      animate,
    });
  };

  const loadVRMAnimation = async (
    animationUrl: string,
    vrm: VRM,
    loop: boolean = true,
  ) => {
    return loadCharacterVrmAnimation({
      animationUrl,
      vrm,
      loop,
      mixerRef,
      currentActionRef,
      currentRebasedClipRef,
      idleHipsBaselineRef,
      applyRootScenePosition,
    });
  };

  const playRandomAnimation = async (vrm: VRM) => {
    if (isPlayingSequence.current) return;
    isPlayingSequence.current = true;
    await playRandomVrmAnimation(vrm, loadVRMAnimation);
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

      const setViseme = createVisemeSetter(
        blendShapeControllerRef,
        expressionWeightsAppliedRef,
      );

      const setExpression = createExpressionSetter(
        charactersRef,
        blendShapeControllerRef,
        expressionTimeoutRef,
        currentExpressionRef,
      );

      // Initialize with neutral expression
      try {
        setExpression('neutral', 1.0);
      } catch (error) {
        console.error('[CharacterAvatar] Error setting initial neutral expression:', error);
      }

      const { play: playKeyframeAnimation, stop: stopKeyframeAnimation } =
        createKeyframeAnimationPlayer(
          charactersRef,
          blendShapeControllerRef,
          keyframeAnimationTimeoutsRef,
          isPlayingSequence,
          setExpressionWeightsRef,
        );

      playKeyframeAnimationInternalRef.current = playKeyframeAnimation;
      stopKeyframeAnimationInternalRef.current = stopKeyframeAnimation;
      if (charactersRef.current) onCharacterLoad?.(charactersRef.current);
      onEmotionUpdate?.(applyEmotionToCharacter);
      onVisemeControl?.(setViseme);
      onExpressionControl?.(setExpression);
      onKeyframeAnimationControl?.({ play: playKeyframeAnimation, stop: stopKeyframeAnimation });
      setIsLoading(false);
    } catch (error) {
      console.error('Error loading character:', error);
      setError('Failed to load character model. Please try again.');
      setIsLoading(false);
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
    onKeyframeAnimationControlRef.current?.({ play: () => {}, stop: () => {} });
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

      syncExpressionWeightsFromVrm({
        blendShapeController: blendShapeControllerRef.current,
        expressionWeightsAppliedRef,
        lastManualExpressionUpdateMsRef,
        expressionWeightsUiRef,
        expressionWeightsDisplayRef,
        setExpressionWeightsRef,
      });
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
      if (currentRebasedClipRef.current) {
        mixerRef.current.uncacheClip(currentRebasedClipRef.current);
        currentRebasedClipRef.current = null;
      }
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
      <CharacterAvatarSettingsPanel
        settingsPanelPropsRef={settingsPanelPropsRef}
        onSettingsPanelPropsChange={onSettingsPanelPropsChange}
        lastSettingsPanelEmitMsRef={lastSettingsPanelEmitMsRef}
        characterState={characterState}
        vrmExpressionNames={vrmExpressionNames}
        expressionWeights={expressionWeights}
        onExpressionWeightChange={handle_expression_weight_change}
        vrmAnimationOptions={vrmAnimationOptions}
        onPlayVrmAnimation={handle_play_vrm_animation}
        onPositionChange={updateCharacterPosition}
        onRotationChange={updateCharacterRotation}
        background={background}
        onApplyBackground={(bg) => {
          updateSceneBackground(bg);
          onBackgroundChange?.(bg);
        }}
        lightingIntensity={lightingIntensity}
        onLightingChange={onLightingChange}
        volume={volume}
        isMuted={isMuted}
        onVolumeChange={onVolumeChange}
        onMuteToggle={onMuteToggle}
        onRunKeyframe={(animation) => playKeyframeAnimationInternalRef.current?.(animation)}
        settingsPortalTargetId={settingsPortalTargetId}
        settingsOpen={settingsOpen}
        showSettings={showSettings}
        onSettingsClose={onSettingsClose}
        extraSettingsTab={extraSettingsTab}
      />
    </div>
  );
}
