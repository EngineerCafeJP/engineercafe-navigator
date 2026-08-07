import assert from 'node:assert/strict';
import { test } from 'node:test';

import { playRandomVrmAnimation } from '../app/components/character-avatar/animation';

test('playRandomVrmAnimation uses real animation names from /api/animations (#948)', async () => {
  // /api/animations の応答をモック（実ファイル名の一覧）
  const originalFetch = global.fetch;
  global.fetch = (async (_input: unknown) => {
    return {
      ok: true,
      json: async () => ({
        animations: [
          'idle.vrma',
          'bowing.vrma',
          'greeting.vrma',
          'looking.vrma',
          'talking.vrma',
          'thinking.vrma',
          'surprised.vrma',
        ],
      }),
    } as Response;
  }) as typeof fetch;

  try {
    const requestedUrls: string[] = [];
    const loadVRMAnimation = async (animationUrl: string, _vrm: unknown) => {
      requestedUrls.push(animationUrl);
      return { success: true, duration: 0 }; // duration 0 で待ち時間を最小化
    };

    // ランダムだが、idle は除外され、実在するファイル名のみが使われることを検証
    for (let i = 0; i < 3; i++) {
      await playRandomVrmAnimation({} as never, loadVRMAnimation as never);
    }

    assert.ok(requestedUrls.length > 0, 'should have requested animations');
    // 偶数回目は「再生後に戻る待機モーション」(idle)、奇数回目がランダム対象
    for (let i = 0; i < requestedUrls.length; i++) {
      const name = requestedUrls[i].replace('/animations/', '').replace('.vrma', '');
      if (i % 2 === 1) {
        assert.equal(name, 'idle', 'should return to idle after the random animation');
      } else {
        assert.notEqual(name, 'idle', 'idle should be excluded from random clicks');
        // 実在するファイル名のみ（ハードコードされた VRMA_0x が残っていないこと）
        assert.ok(
          !/^VRMA_\d+$/.test(name),
          `legacy VRMA_0x name should not be used, got: ${name}`,
        );
      }
    }
  } finally {
    global.fetch = originalFetch;
  }
});

test('playRandomVrmAnimation falls back to known names when API fails (#948)', async () => {
  const originalFetch = global.fetch;
  global.fetch = (async () => {
    return { ok: false, json: async () => ({}) } as Response;
  }) as typeof fetch;

  try {
    const requestedUrls: string[] = [];
    const loadVRMAnimation = async (animationUrl: string, _vrm: unknown) => {
      requestedUrls.push(animationUrl);
      return { success: true, duration: 1.0 };
    };

    await playRandomVrmAnimation({} as never, loadVRMAnimation as never);

    assert.ok(requestedUrls.length > 0, 'fallback should still request an animation');
    const url = requestedUrls[0];
    const name = url.replace('/animations/', '').replace('.vrma', '');
    // フォールバックリストは実在する名前のみ
    assert.ok(
      ['bowing', 'greeting', 'looking', 'surprised', 'talking', 'thinking', 'thinking2'].includes(name),
      `fallback should use a known animation name, got: ${name}`,
    );
  } finally {
    global.fetch = originalFetch;
  }
});
