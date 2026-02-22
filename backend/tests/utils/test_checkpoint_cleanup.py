"""
CheckpointCleanup ユーティリティのユニットテスト

初期化時のデフォルト値とカスタム値を検証する。
"""

from backend.utils.checkpoint_cleanup import (
    DEFAULT_MAX_MESSAGES_PER_SESSION,
    DEFAULT_TTL_HOURS,
    CheckpointCleanup,
)

# ============================================
# Initialization
# ============================================


def test_initialization_defaults():
    """デフォルト引数で初期化した場合、デフォルト定数が使われる"""
    cleanup = CheckpointCleanup()

    assert cleanup.ttl_hours == DEFAULT_TTL_HOURS
    assert cleanup.max_messages == DEFAULT_MAX_MESSAGES_PER_SESSION
    assert cleanup._running is False
    assert cleanup._task is None


def test_initialization_custom():
    """カスタム引数で初期化した場合、指定値が使われる"""
    cleanup = CheckpointCleanup(ttl_hours=48, max_messages=100)

    assert cleanup.ttl_hours == 48
    assert cleanup.max_messages == 100
