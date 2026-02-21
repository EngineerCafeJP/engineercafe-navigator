"""healthcheck.py のユニットテスト

check_url() と main() の動作を網羅的に検証する。
外部ネットワーク依存を排除するため urllib.request.urlopen をモック化する。
"""

import sys
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from backend.scripts.healthcheck import check_url, main


# ---------------------------------------------------------------------------
# check_url テスト
# ---------------------------------------------------------------------------


class TestCheckUrl:
    """check_url() 関数のテストスイート"""

    def _make_mock_response(self, status: int) -> MagicMock:
        """指定ステータスコードを返すモックレスポンスを生成する"""
        mock_response = MagicMock()
        mock_response.status = status
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_returns_true_on_200_response(self, mock_urlopen: MagicMock) -> None:
        """ステータス200の場合にTrueを返すことを検証する"""
        mock_urlopen.return_value = self._make_mock_response(200)

        result = check_url("http://localhost:8000/health")

        assert result is True

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_returns_false_on_non_200_response(self, mock_urlopen: MagicMock) -> None:
        """ステータスが200以外の場合にFalseを返すことを検証する"""
        mock_urlopen.return_value = self._make_mock_response(503)

        result = check_url("http://localhost:8000/health")

        assert result is False

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_returns_false_on_url_error(self, mock_urlopen: MagicMock) -> None:
        """URLErrorが発生した場合にFalseを返すことを検証する"""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = check_url("http://localhost:8000/health")

        assert result is False

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_returns_false_on_http_error(self, mock_urlopen: MagicMock) -> None:
        """HTTPErrorが発生した場合にFalseを返すことを検証する"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://localhost:8000/health",
            code=500,
            msg="Internal Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=BytesIO(b""),
        )

        result = check_url("http://localhost:8000/health")

        assert result is False

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_returns_false_on_timeout_error(self, mock_urlopen: MagicMock) -> None:
        """TimeoutErrorが発生した場合にFalseを返すことを検証する"""
        mock_urlopen.side_effect = TimeoutError("Request timed out")

        result = check_url("http://localhost:8000/health")

        assert result is False

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_returns_false_on_os_error(self, mock_urlopen: MagicMock) -> None:
        """OSErrorが発生した場合にFalseを返すことを検証する"""
        mock_urlopen.side_effect = OSError("Network unreachable")

        result = check_url("http://localhost:8000/health")

        assert result is False

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_verbose_prints_success_message(
        self, mock_urlopen: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """verbose=Trueの場合に成功メッセージが出力されることを検証する"""
        mock_urlopen.return_value = self._make_mock_response(200)

        check_url("http://localhost:8000/health", verbose=True)

        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "http://localhost:8000/health" in captured.out
        assert "status=200" in captured.out

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_verbose_prints_failure_message_on_non_200(
        self, mock_urlopen: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """verbose=Trueかつ非200ステータスの場合に失敗メッセージが出力されることを検証する"""
        mock_urlopen.return_value = self._make_mock_response(503)

        check_url("http://localhost:8000/health", verbose=True)

        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "http://localhost:8000/health" in captured.out
        assert "status=503" in captured.out

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_verbose_prints_failure_message_on_exception(
        self, mock_urlopen: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """verbose=Trueかつ例外発生時に失敗メッセージが出力されることを検証する"""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        check_url("http://localhost:8000/health", verbose=True)

        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "http://localhost:8000/health" in captured.out
        assert "Connection refused" in captured.out

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_no_output_when_verbose_is_false(
        self, mock_urlopen: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """verbose=Falseの場合に何も出力されないことを検証する"""
        mock_urlopen.return_value = self._make_mock_response(200)

        check_url("http://localhost:8000/health", verbose=False)

        captured = capsys.readouterr()
        assert captured.out == ""

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_custom_timeout_is_passed_to_urlopen(self, mock_urlopen: MagicMock) -> None:
        """指定したtimeout値がurlopenに渡されることを検証する"""
        mock_urlopen.return_value = self._make_mock_response(200)

        check_url("http://localhost:8000/health", timeout=15)

        call_args = mock_urlopen.call_args
        assert (
            call_args.kwargs.get("timeout") == 15
            or call_args[1].get("timeout") == 15
            or (len(call_args[0]) > 1 and call_args[0][1] == 15)
        )

    @patch("backend.scripts.healthcheck.urllib.request.urlopen")
    def test_uses_get_method(self, mock_urlopen: MagicMock) -> None:
        """GETリクエストが送信されることを検証する"""
        mock_urlopen.return_value = self._make_mock_response(200)

        check_url("http://localhost:8000/health")

        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        assert request_obj.method == "GET"


# ---------------------------------------------------------------------------
# main テスト
# ---------------------------------------------------------------------------


class TestMain:
    """main() 関数のテストスイート"""

    @patch("backend.scripts.healthcheck.check_url")
    def test_returns_0_when_healthy(self, mock_check_url: MagicMock) -> None:
        """ヘルスエンドポイントが正常な場合に0を返すことを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py"]):
            result = main()

        assert result == 0

    @patch("backend.scripts.healthcheck.check_url")
    def test_returns_1_when_unhealthy(self, mock_check_url: MagicMock) -> None:
        """ヘルスエンドポイントが異常な場合に1を返すことを検証する"""
        mock_check_url.return_value = False

        with patch.object(sys, "argv", ["healthcheck.py"]):
            result = main()

        assert result == 1

    @patch("backend.scripts.healthcheck.check_url")
    def test_checks_health_endpoint(self, mock_check_url: MagicMock) -> None:
        """メインのヘルスエンドポイントURLが正しいことを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py"]):
            main()

        first_call_args = mock_check_url.call_args_list[0]
        assert first_call_args[0][0] == "http://localhost:8000/health"

    @patch("backend.scripts.healthcheck.check_url")
    def test_default_timeout_is_5(self, mock_check_url: MagicMock) -> None:
        """デフォルトのタイムアウトが5秒であることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py"]):
            main()

        first_call_kwargs = mock_check_url.call_args_list[0][1]
        assert first_call_kwargs["timeout"] == 5

    @patch("backend.scripts.healthcheck.check_url")
    def test_custom_timeout(self, mock_check_url: MagicMock) -> None:
        """--timeoutオプションでタイムアウト値をカスタマイズできることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py", "--timeout", "10"]):
            main()

        first_call_kwargs = mock_check_url.call_args_list[0][1]
        assert first_call_kwargs["timeout"] == 10

    @patch("backend.scripts.healthcheck.check_url")
    def test_check_services_calls_additional_urls(self, mock_check_url: MagicMock) -> None:
        """--check-servicesオプションでVoiceVoxとKokoroのURLも確認されることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py", "--check-services"]):
            main()

        called_urls = [call[0][0] for call in mock_check_url.call_args_list]
        assert "http://localhost:8000/health" in called_urls
        assert "http://localhost:50021/version" in called_urls
        assert "http://localhost:8880/v1/audio/voices" in called_urls
        assert len(called_urls) == 3

    @patch("backend.scripts.healthcheck.check_url")
    def test_without_check_services_only_checks_health(self, mock_check_url: MagicMock) -> None:
        """--check-servicesなしの場合はヘルスエンドポイントのみ確認されることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py"]):
            main()

        assert mock_check_url.call_count == 1

    @patch("backend.scripts.healthcheck.check_url")
    def test_verbose_produces_output(
        self, mock_check_url: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--verboseオプションで出力が生成されることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py", "--verbose"]):
            main()

        captured = capsys.readouterr()
        assert "Running healthcheck..." in captured.out
        assert "HEALTHY" in captured.out

    @patch("backend.scripts.healthcheck.check_url")
    def test_verbose_unhealthy_produces_failure_output(
        self, mock_check_url: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--verboseかつ異常時にUNHEALTHYメッセージが出力されることを検証する"""
        mock_check_url.return_value = False

        with patch.object(sys, "argv", ["healthcheck.py", "--verbose"]):
            main()

        captured = capsys.readouterr()
        assert "Running healthcheck..." in captured.out
        assert "UNHEALTHY" in captured.out

    @patch("backend.scripts.healthcheck.check_url")
    def test_returns_0_even_if_optional_service_is_down(self, mock_check_url: MagicMock) -> None:
        """オプションサービスが落ちていてもヘルスが正常なら0を返すことを検証する"""

        def side_effect(url: str, **kwargs) -> bool:
            if url == "http://localhost:8000/health":
                return True
            return False

        mock_check_url.side_effect = side_effect

        with patch.object(sys, "argv", ["healthcheck.py", "--check-services"]):
            result = main()

        assert result == 0

    @patch("backend.scripts.healthcheck.check_url")
    def test_check_services_verbose_prints_warning_for_unavailable_service(
        self, mock_check_url: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--check-services --verbose時にサービスが落ちているとWARNINGが出力されることを検証する"""

        def side_effect(url: str, **kwargs) -> bool:
            if url == "http://localhost:8000/health":
                return True
            return False

        mock_check_url.side_effect = side_effect

        with patch.object(sys, "argv", ["healthcheck.py", "--check-services", "--verbose"]):
            main()

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    @patch("backend.scripts.healthcheck.check_url")
    def test_verbose_flag_is_passed_to_check_url(self, mock_check_url: MagicMock) -> None:
        """--verboseフラグがcheck_urlに正しく渡されることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py", "--verbose"]):
            main()

        first_call_kwargs = mock_check_url.call_args_list[0][1]
        assert first_call_kwargs["verbose"] is True

    @patch("backend.scripts.healthcheck.check_url")
    def test_verbose_flag_defaults_to_false(self, mock_check_url: MagicMock) -> None:
        """デフォルトではverbose=Falseがcheck_urlに渡されることを検証する"""
        mock_check_url.return_value = True

        with patch.object(sys, "argv", ["healthcheck.py"]):
            main()

        first_call_kwargs = mock_check_url.call_args_list[0][1]
        assert first_call_kwargs["verbose"] is False
