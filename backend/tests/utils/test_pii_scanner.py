"""Tests for backend.utils.pii_scanner -- PII detection and masking."""

from backend.utils.pii_scanner import contains_pii, scan_and_mask


class TestScanAndMaskEmail:
    """メールアドレスの検出・マスキング"""

    def test_simple_email(self):
        text = "連絡先は user@example.com です"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_EMAIL]" in masked
        assert "user@example.com" not in masked
        assert len(items) == 1
        assert items[0]["type"] == "EMAIL"
        assert items[0]["original"] == "user@example.com"

    def test_email_with_plus(self):
        text = "送信先: test+tag@gmail.com"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_EMAIL]" in masked
        assert items[0]["original"] == "test+tag@gmail.com"

    def test_email_with_subdomain(self):
        text = "admin@mail.corp.example.co.jp に送信しました"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_EMAIL]" in masked

    def test_multiple_emails(self):
        text = "cc: a@b.com, d@e.org"
        masked, items = scan_and_mask(text)
        assert masked.count("[REDACTED_EMAIL]") == 2
        assert len(items) == 2


class TestScanAndMaskPhone:
    """電話番号の検出・マスキング (日本国内・国際形式)"""

    def test_japanese_mobile_with_hyphens(self):
        text = "電話番号は 090-1234-5678 です"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked
        assert "090-1234-5678" not in masked

    def test_japanese_mobile_no_hyphens(self):
        text = "電話: 09012345678"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_japanese_landline(self):
        text = "お問合せは 03-1234-5678 まで"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_japanese_landline_no_hyphens(self):
        text = "TEL: 0312345678"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_fullwidth_phone(self):
        text = "電話: ０９０ー１２３４ー５６７８"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_international_format(self):
        text = "Call +81-90-1234-5678"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_us_format(self):
        text = "Phone: +1-555-123-4567"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_080_mobile(self):
        text = "080-9876-5432 に連絡ください"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked

    def test_070_mobile(self):
        text = "070-1111-2222"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_PHONE]" in masked


class TestScanAndMaskCreditCard:
    """クレジットカード番号の検出・マスキング"""

    def test_credit_card_with_hyphens(self):
        text = "カード番号: 4111-1111-1111-1111"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_CREDIT_CARD]" in masked
        assert "4111-1111-1111-1111" not in masked

    def test_credit_card_with_spaces(self):
        text = "カード: 4111 1111 1111 1111"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_CREDIT_CARD]" in masked

    def test_credit_card_no_separator(self):
        text = "番号は4111111111111111です"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_CREDIT_CARD]" in masked

    def test_fullwidth_credit_card(self):
        text = "カード: ４１１１ー１１１１ー１１１１ー１１１１"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_CREDIT_CARD]" in masked


class TestScanAndMaskMyNumber:
    """マイナンバー (個人番号) の検出・マスキング"""

    def test_my_number_with_hyphens(self):
        text = "マイナンバー: 1234-5678-9012"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_MY_NUMBER]" in masked
        assert "1234-5678-9012" not in masked

    def test_my_number_no_separator(self):
        text = "個人番号は123456789012です"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_MY_NUMBER]" in masked

    def test_fullwidth_my_number(self):
        text = "番号: １２３４ー５６７８ー９０１２"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_MY_NUMBER]" in masked

    def test_fullwidth_my_number_no_separator(self):
        text = "個人番号: １２３４５６７８９０１２"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_MY_NUMBER]" in masked


class TestScanAndMaskIPAddress:
    """IPアドレスの検出・マスキング"""

    def test_ipv4_address(self):
        text = "サーバーIP: 192.168.1.100"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_IP_ADDRESS]" in masked
        assert "192.168.1.100" not in masked

    def test_loopback_address(self):
        text = "localhost: 127.0.0.1"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_IP_ADDRESS]" in masked

    def test_public_ip(self):
        text = "接続元: 203.0.113.42"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_IP_ADDRESS]" in masked

    def test_ip_in_sentence(self):
        text = "アクセスは 10.0.0.1 から行われました"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_IP_ADDRESS]" in masked


class TestScanAndMaskURLWithCredentials:
    """認証情報を含むURLの検出・マスキング"""

    def test_url_with_basic_auth(self):
        text = "接続先: https://admin:password123@example.com/api"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_URL_WITH_CREDENTIALS]" in masked
        assert "password123" not in masked

    def test_url_with_api_key_param(self):
        text = "URL: https://api.example.com/data?api_key=sk-abc123secret"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_URL_WITH_CREDENTIALS]" in masked
        assert "sk-abc123secret" not in masked

    def test_url_with_token_param(self):
        text = "https://example.com/webhook?token=my-secret-token"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_URL_WITH_CREDENTIALS]" in masked

    def test_url_with_password_param(self):
        text = "https://app.example.com/login?password=hunter2"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_URL_WITH_CREDENTIALS]" in masked

    def test_normal_url_not_flagged(self):
        text = "詳細は https://example.com/help をご確認ください"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert len(items) == 0


class TestScanAndMaskMixedContent:
    """複数種類のPIIが混在するテキスト"""

    def test_email_and_phone(self):
        text = "連絡先: user@example.com / 090-1234-5678"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_EMAIL]" in masked
        assert "[REDACTED_PHONE]" in masked
        assert len(items) == 2

    def test_multiple_pii_types(self):
        text = "お客様情報: メール user@test.com、" "電話 03-1234-5678、" "IP 192.168.0.1"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_EMAIL]" in masked
        assert "[REDACTED_PHONE]" in masked
        assert "[REDACTED_IP_ADDRESS]" in masked
        assert len(items) == 3

    def test_pii_surrounded_by_normal_text(self):
        text = "エンジニアカフェへようこそ。ご連絡は info@cafe.jp までお願いします。営業時間は9時から21時です。"
        masked, items = scan_and_mask(text)
        assert "[REDACTED_EMAIL]" in masked
        assert "エンジニアカフェへようこそ" in masked
        assert "営業時間は9時から21時です。" in masked

    def test_items_have_correct_structure(self):
        text = "email: test@example.com"
        _, items = scan_and_mask(text)
        assert len(items) == 1
        item = items[0]
        assert "type" in item
        assert "original" in item
        assert "position" in item
        assert isinstance(item["position"], int)


class TestScanAndMaskNormalText:
    """正常なテキストがPIIとして誤検出されないこと"""

    def test_empty_string(self):
        masked, items = scan_and_mask("")
        assert masked == ""
        assert items == []

    def test_simple_japanese(self):
        text = "エンジニアカフェの営業時間は9時から21時までです"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_simple_english(self):
        text = "Welcome to Engineer Cafe. How can I help you?"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_japanese_address(self):
        """日本の住所はPIIとして検出されないこと (番地の数字)"""
        text = "福岡市中央区天神1丁目15番30号"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_time_and_dates(self):
        """時刻・日付の数字がPIIとして誤検出されないこと"""
        text = "2026年2月22日 14:30に予約しました"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_price_numbers(self):
        """金額の数字がPIIとして誤検出されないこと"""
        text = "利用料金は500円です。Wi-Fiは無料です。"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_normal_url(self):
        """認証情報のないURLは検出されないこと"""
        text = "https://engineercafe.jp/access にアクセスしてください"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_room_numbers(self):
        """部屋番号等の短い数字がPIIとして誤検出されないこと"""
        text = "会議室A-101をご利用ください"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []

    def test_version_numbers(self):
        """バージョン番号がIPアドレスとして誤検出されないこと"""
        text = "Python 3.11を使用しています"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []


class TestContainsPii:
    """contains_pii 便利関数のテスト"""

    def test_empty_string(self):
        assert contains_pii("") is False

    def test_no_pii(self):
        assert contains_pii("エンジニアカフェへようこそ") is False

    def test_with_email(self):
        assert contains_pii("連絡先: user@example.com") is True

    def test_with_phone(self):
        assert contains_pii("電話: 090-1234-5678") is True

    def test_with_credit_card(self):
        assert contains_pii("カード: 4111-1111-1111-1111") is True

    def test_with_my_number(self):
        assert contains_pii("マイナンバー: 1234-5678-9012") is True

    def test_with_ip_address(self):
        assert contains_pii("IP: 192.168.1.1") is True

    def test_with_url_credentials(self):
        assert contains_pii("https://user:pass@host.com") is True

    def test_normal_japanese_text(self):
        assert contains_pii("今日の天気は晴れです。気温は25度です。") is False

    def test_normal_english_text(self):
        assert contains_pii("The meeting room is available from 2pm.") is False


class TestScanAndMaskReturnStructure:
    """戻り値の構造が正しいこと"""

    def test_return_type_is_tuple(self):
        result = scan_and_mask("test@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_masked_text_is_string(self):
        masked, _ = scan_and_mask("test@example.com")
        assert isinstance(masked, str)

    def test_items_is_list(self):
        _, items = scan_and_mask("test@example.com")
        assert isinstance(items, list)

    def test_items_ordered_by_position(self):
        text = "a@b.com then 090-1234-5678"
        _, items = scan_and_mask(text)
        if len(items) > 1:
            positions = [item["position"] for item in items]
            assert positions == sorted(positions)

    def test_no_pii_returns_original_text(self):
        text = "通常のテキストです"
        masked, items = scan_and_mask(text)
        assert masked == text
        assert items == []
