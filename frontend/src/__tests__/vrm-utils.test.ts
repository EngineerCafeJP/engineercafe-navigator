import assert from 'node:assert/strict';
import test from 'node:test';

import { VRMUtils } from '@/lib/vrm-utils';
import type { VRM } from '@pixiv/three-vrm';
import * as THREE from 'three';

const createVrmWithHips = (hipsName = 'hips'): VRM => ({
  humanoid: {
    getNormalizedBoneNode: (name: string) => (name === 'hips' ? { name: hipsName } : null),
  },
}) as unknown as VRM;

test('sampleHipsPositionXZAtTime returns null for degenerate hips values', () => {
  const vrm = createVrmWithHips();
  const clip = new THREE.AnimationClip('degenerate', 1, [
    new THREE.VectorKeyframeTrack('hips.position', [0], [1, 2]),
  ]);

  assert.equal(VRMUtils.sampleHipsPositionXZAtTime(clip, vrm, 0), null);
});

test('sampleHipsPositionXZAtTime returns null for non-finite hips values', () => {
  const vrm = createVrmWithHips();
  const clip = new THREE.AnimationClip('nan', 1, [
    new THREE.VectorKeyframeTrack('hips.position', [0], [1, 2, Number.NaN]),
  ]);

  assert.equal(VRMUtils.sampleHipsPositionXZAtTime(clip, vrm, 0), null);
});

test('rebaseHipsHorizontalInClip leaves degenerate hips tracks unchanged', () => {
  const vrm = createVrmWithHips();
  const track = new THREE.VectorKeyframeTrack('hips.position', [0], [1, 2]);
  const clip = new THREE.AnimationClip('degenerate', 1, [track]);

  const result = VRMUtils.rebaseHipsHorizontalInClip(
    clip,
    vrm,
    { x: 10, z: 20 },
    { x: 1, z: 2 },
  );

  assert.equal(result, clip);
  assert.deepEqual(Array.from(track.values), [1, 2]);
});
