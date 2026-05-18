import * as THREE from 'three';
import { updateThreeSceneBackground } from './background';
import type { MutableRefObject } from 'react';
import type { BackgroundOption } from './types';

interface InitializeCharacterSceneArgs {
  container: HTMLDivElement | null;
  sceneRef: MutableRefObject<THREE.Scene | null>;
  rendererRef: MutableRefObject<THREE.WebGLRenderer | null>;
  cameraRef: MutableRefObject<THREE.PerspectiveCamera | null>;
  clockRef: MutableRefObject<THREE.Clock | null>;
  background?: BackgroundOption;
  cameraPositionOffset: { x: number; y: number; z: number };
  lightingIntensity: number;
  enableClickAnimation: boolean;
  handleCanvasClick: () => void;
  animate: () => void;
}

export const initializeCharacterScene = ({
  container,
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
}: InitializeCharacterSceneArgs): { ok: boolean; disposeResize?: () => void } => {
  if (!container) {
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
    updateThreeSceneBackground(scene, background);
  } else {
    scene.background = new THREE.Color('#f5f5f5');
  }

  scene.fog = new THREE.Fog(0xf5f5f5, 5, 10);

  // Camera
  const camera = new THREE.PerspectiveCamera(
    50,
    container.clientWidth / container.clientHeight,
    0.1,
    1000,
  );
  camera.position.set(
    0 + cameraPositionOffset.x,
    1.4 + cameraPositionOffset.y,
    1.5 + cameraPositionOffset.z,
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
      new Error('No WebGL rendering context'),
    );
    clearSceneRefsOnFailure();
    return { ok: false };
  }

  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);
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
    if (!container || !camera || !renderer) return;

    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  };

  window.addEventListener('resize', handleResize);
  window.addEventListener('orientationchange', handleResize);
  window.visualViewport?.addEventListener('resize', handleResize);
  const resizeObserver =
    typeof ResizeObserver !== 'undefined' && container
      ? new ResizeObserver(handleResize)
      : null;
  resizeObserver?.observe(container);

  animate();

  return {
    ok: true,
    disposeResize: () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
      window.visualViewport?.removeEventListener('resize', handleResize);
      resizeObserver?.disconnect();
    },
  };
};
