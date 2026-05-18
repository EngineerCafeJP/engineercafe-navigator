import { VRM } from '@pixiv/three-vrm';
import * as THREE from 'three';

// VRM Animation Manager
export class VRMAnimationManager {
  private mixer: THREE.AnimationMixer;
  private clips: Map<string, THREE.AnimationClip> = new Map();
  private currentAction: THREE.AnimationAction | null = null;
  private fadeDuration = 0.5;

  constructor(private vrm: VRM) {
    this.mixer = new THREE.AnimationMixer(vrm.scene);
  }

  addClip(name: string, clip: THREE.AnimationClip): void {
    this.clips.set(name, clip);
  }

  playAnimation(name: string, fadeIn = true, loop = true): THREE.AnimationAction | null {
    const clip = this.clips.get(name);
    if (!clip) return null;

    const action = this.mixer.clipAction(clip);
    action.loop = loop ? THREE.LoopRepeat : THREE.LoopOnce;

    if (this.currentAction && fadeIn) {
      this.currentAction.fadeOut(this.fadeDuration);
      action.reset().fadeIn(this.fadeDuration).play();
    } else {
      action.reset().play();
    }

    this.currentAction = action;
    return action;
  }

  stopCurrentAnimation(fadeOut = true): void {
    if (this.currentAction) {
      if (fadeOut) {
        this.currentAction.fadeOut(this.fadeDuration);
      } else {
        this.currentAction.stop();
      }
      this.currentAction = null;
    }
  }

  update(deltaTime: number): void {
    this.mixer.update(deltaTime);
  }

  setFadeDuration(duration: number): void {
    this.fadeDuration = duration;
  }

  dispose(): void {
    this.mixer.stopAllAction();
    this.clips.clear();
    this.currentAction = null;
  }
}
