"""Fallback search and text matching helpers for EnhancedRAGSearch."""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from backend.tools.enhanced_rag_circuit import _rag_circuit_breaker
from backend.tools.enhanced_rag_constants import (
    MEMBERSHIP_QUERY_TERMS,
    MEMBERSHIP_RESULT_TERMS,
    QUERY_EXPANSION_MAP,
    RAG_CATEGORY_ALIASES,
    SAINO_QUERY_TERMS,
)

logger = logging.getLogger(__name__)


class RAGFallbackMixin:
    def _expand_query(self, query: str, category: str, language: str) -> str:
        """クエリを同義語・多言語キーワードで拡張する。

        短いクエリやドメイン固有の用語に対してベクトル検索の精度を向上させる。

        Args:
            query: 元のクエリ
            category: クエリカテゴリ
            language: 言語コード

        Returns:
            拡張されたクエリ文字列
        """
        expansions: list[str] = []

        # Entity anchoring: short non-general queries default to Engineer Cafe.
        # Do not add that anchor to explicit Saino queries; it can make Saino
        # business-hours questions rank as Engineer Cafe hours.
        if (
            category not in {"general", "saino-cafe"}
            and len(query) < 15
            and not self._query_mentions_engineer_cafe(query)
            and not self._query_mentions_saino(query)
        ):
            query = f"エンジニアカフェ {query}"

        # クエリ内のキーワードに基づく拡張
        query_lower = query.lower()
        for key, synonyms in QUERY_EXPANSION_MAP.items():
            if key.lower() in query_lower:
                expansions.extend(synonyms)

        # カテゴリベースの拡張キーワード
        category_keywords: Dict[str, List[str]] = {
            "hours": ["営業時間", "opening hours", "business hours", "開館時間"],
            "pricing": ["料金", "price", "pricing", "cost", "利用料金"],
            "location": ["場所", "アクセス", "location", "access", "住所", "address"],
            "facility-info": [
                "設備",
                "facility",
                "facilities",
                "space",
                "spaces",
                "施設",
                "equipment",
            ],
            "consultation": ["相談", "コミュニティマネージャー", "career", "consultation"],
            "smoking": ["喫煙", "禁煙", "smoking", "흡연", "금연"],
            "food_drink": ["飲食", "食べ物", "drink", "food"],
            "parking": ["駐車場", "parking"],
            "bicycle": ["駐輪場", "bicycle parking"],
            "policy": ["ルール", "ポリシー", "同伴", "補助犬", "一時外出", "policy"],
            "saino-cafe": [
                "saino",
                "cafe&bar saino",
                "サイノカフェ",
                "営業時間",
                "メニュー",
                "カフェ",
                "バー",
            ],
        }

        if category in category_keywords:
            expansions.extend(category_keywords[category])

        # 重複除去して元クエリと結合
        seen: set[str] = set()
        unique_expansions: list[str] = []
        for exp in expansions:
            if exp.lower() not in seen and exp.lower() not in query_lower:
                seen.add(exp.lower())
                unique_expansions.append(exp)

        if unique_expansions:
            # 拡張キーワードを元クエリに付加（最大5個）
            return f"{query} ({' '.join(unique_expansions[:5])})"

        return query

    async def _text_fallback_search(
        self,
        query: str,
        category: str,
        language: str,
        max_results: int,
    ) -> List[Dict]:
        """テキストベースのフォールバック検索。

        ベクトル検索で十分な結果が得られない場合に、カテゴリとキーワードで
        knowledge_baseを直接検索する。

        Args:
            query: 検索クエリ
            category: カテゴリ
            language: 言語コード
            max_results: 最大結果数

        Returns:
            検索結果のリスト
        """
        try:
            # カテゴリベースの検索
            query_builder = (
                self.supabase.table("knowledge_base")
                .select("id, content, category, subcategory, language, source, metadata")
                .not_.is_("content_embedding", "null")
            )

            # カテゴリフィルタ（generalカテゴリ以外の場合）
            if category and category != "general":
                query_builder = query_builder.eq("category", category)

            # KB is Japanese-only; filter to ja for reliable results
            # (English content_en chunks are stored with language='en')
            if language == "en":
                query_builder = query_builder.in_("language", ["en", "ja"])
            else:
                query_builder = query_builder.eq("language", "ja")

            result = query_builder.limit(max_results).execute()

            result_data = result.data if isinstance(result.data, list) else []

            if not result_data:
                # カテゴリフィルタなしで再試行
                result = (
                    self.supabase.table("knowledge_base")
                    .select("id, content, category, subcategory, language, source, metadata")
                    .not_.is_("content_embedding", "null")
                    .eq("language", "ja")
                    .limit(max_results)
                    .execute()
                )
                result_data = result.data if isinstance(result.data, list) else []

            if result_data:
                # テキストマッチングでスコア付け
                scored: list[Dict] = []
                for row in result_data:
                    match_score = self._calculate_text_match_score(row, query, category, language)
                    if match_score > 0:
                        scored.append({**row, "similarity": min(match_score, 0.7)})

                scored.sort(key=lambda x: x.get("similarity", 0), reverse=True)
                return scored[:max_results]

            return []

        except Exception as e:
            logger.error("Text fallback search error: %s", e)
            return []

    async def _fallback_search_response(
        self,
        query: str,
        category: str,
        language: str,
        include_advice: bool,
        max_results: int,
        error: str,
    ) -> Dict:
        """Build a normal search response from non-vector fallbacks."""
        results = await self._text_fallback_search(query, category, language, max_results)
        if not results:
            results = self._local_knowledge_fallback_search(query, category, language, max_results)

        if not results:
            return {"success": False, "error": error}

        scored_results = self._score_results(results, query, category, language)
        scored_results = self._grade_result_relevance(
            scored_results, query, category, language=language
        )
        needs_entity_fallback = (
            self._query_mentions_saino(query)
            and not self._query_mentions_engineer_cafe(query)
            and not any(r.get("entity") == "saino" for r in scored_results)
        )
        needs_membership_fallback = self._needs_membership_fallback(query, scored_results)
        if not scored_results or needs_entity_fallback or needs_membership_fallback:
            local_results = self._local_knowledge_fallback_search(
                query, category, language, max_results
            )
            if local_results:
                scored_results = self._score_results(local_results, query, category, language)
                scored_results = self._grade_result_relevance(
                    scored_results, query, category, language=language
                )
        top_results = scored_results[:max_results]
        context = self._build_context_from_results(top_results, category, language)

        if include_advice:
            advice = self._generate_practical_advice(top_results, query, category, language)
            if advice:
                context += f"\n\n{advice}"

        _rag_circuit_breaker.record_success()
        return {
            "success": True,
            "data": {
                "context": context,
                "results": top_results,
                "totalResults": len(scored_results),
                "topEntity": top_results[0].get("entity", "general") if top_results else "general",
            },
        }

    def _local_knowledge_fallback_search(
        self,
        query: str,
        category: str,
        language: str,
        max_results: int,
    ) -> List[Dict]:
        """Search the checked-in official YAML knowledge used to seed live RAG."""
        try:
            data_dir = Path(__file__).resolve().parents[1] / "knowledge" / "data"
            rows: list[Dict] = []
            for path in sorted(data_dir.glob("*.yaml")):
                with open(path, encoding="utf-8") as fh:
                    payload = yaml.safe_load(fh) or {}
                for entry in payload.get("entries", []):
                    content = entry.get("content_en") if language == "en" else entry.get("content")
                    if not content:
                        content = entry.get("content") or entry.get("content_en") or ""
                    entity = self._infer_entity_from_yaml_entry(entry)
                    row = {
                        "id": entry.get("id"),
                        "title": entry.get("title_en") if language == "en" else entry.get("title"),
                        "content": content,
                        "category": entry.get("category", "general"),
                        "subcategory": entry.get("subcategory"),
                        "language": language,
                        "source": entry.get("source") or "official-yaml",
                        "metadata": {
                            "entity": entity,
                            "tags": entry.get("tags", []),
                            "priority": entry.get("priority", 50),
                            "verified": entry.get("verified", False),
                            "local_fallback": True,
                        },
                    }
                    score = self._calculate_text_match_score(row, query, category, language)
                    if score > 0:
                        rows.append({**row, "similarity": min(score, 0.7)})

            rows.sort(
                key=lambda row: (
                    row.get("similarity", 0.0),
                    row.get("metadata", {}).get("priority", 0),
                ),
                reverse=True,
            )
            return rows[:max_results]
        except Exception as e:
            logger.error("Local YAML fallback search error: %s", e)
            return []

    def _calculate_text_match_score(
        self,
        row: Dict,
        query: str,
        category: str,
        language: str,
    ) -> float:
        searchable = " ".join(
            str(part)
            for part in (
                row.get("title", ""),
                row.get("content", ""),
                (
                    " ".join(row.get("metadata", {}).get("tags", []))
                    if isinstance(row.get("metadata"), dict)
                    else ""
                ),
            )
        ).lower()
        terms = self._extract_text_query_terms(query, category, language)
        row_entity = self._detect_entity(row)

        if (
            self._query_mentions_saino(query)
            and not self._query_mentions_engineer_cafe(query)
            and row_entity != "saino"
        ):
            return 0.0

        row_category = row.get("category")
        if not self._category_matches(row_category, category, row=row, query=query):
            return 0.0
        if category == "hours" and row_entity == "saino" and row_category != "hours":
            if not any(
                term in searchable
                for term in (
                    "営業時間",
                    "opening hours",
                    "business hours",
                    "open",
                    "night time",
                    "12:00",
                    "20:00",
                )
            ):
                return 0.0

        match_score = 0.0
        has_content_match = False
        for term in terms:
            if term in searchable:
                match_score += 0.08 if self._contains_cjk(term) else 0.12
                has_content_match = True

        query_lower = query.lower()
        if any(term in query_lower for term in ("wi-fi", "wifi", "ssid", "接続")) and any(
            term in searchable for term in ("ssid", "engnecf", "password", "パスワード")
        ):
            match_score += 0.28
            has_content_match = True
        if any(term in query for term in ("料金", "いくら", "無料")) and any(
            term in searchable for term in ("無料", "free")
        ):
            match_score += 0.24
            has_content_match = True
        if (
            any(term in query for term in ("予約", "予約なし", "予約不要"))
            or any(
                term in query_lower
                for term in ("reservation", "without a reservation", "no reservation")
            )
        ) and any(
            term in searchable
            for term in (
                "予約不要",
                "予約なし",
                "does not require a reservation",
                "no reservation",
            )
        ):
            match_score += 0.35
            has_content_match = True
        if any(term in query for term in ("受付", "初めて", "再受付", "登録")) and any(
            term in searchable for term in ("受付", "registration", "会員番号", "reception")
        ):
            match_score += 0.2
            has_content_match = True
        if any(term in query for term in ("再受付", "以前登録", "登録した", "2回目")) and any(
            term in searchable for term in ("2回目以降", "会員番号", "受付カード", "受付")
        ):
            match_score += 0.3
            has_content_match = True
        if self._is_membership_query(query) and any(
            term.lower() in searchable for term in MEMBERSHIP_RESULT_TERMS
        ):
            match_score += 0.32
            has_content_match = True
        if self._query_mentions_saino(query) and row_entity == "saino":
            match_score += 0.34
            has_content_match = True
            if category in {"hours", "saino-cafe"} and any(
                term in searchable
                for term in ("営業時間", "opening hours", "business hours", "12:00", "20:00")
            ):
                match_score += 0.18

        if not has_content_match:
            return 0.0

        if category != "general" and self._category_matches(
            row_category, category, row=row, query=query
        ):
            match_score += 0.18

        priority = row.get("metadata", {}).get("priority", 50)
        if isinstance(priority, int):
            match_score += min(priority, 100) / 1000

        return match_score

    def _extract_text_query_terms(self, query: str, category: str, language: str) -> list[str]:
        text = self._expand_query(query, category, language).lower()
        terms = set(
            re.findall(
                r"[a-z0-9][a-z0-9_.+-]*|[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]{2,}",
                text,
            )
        )

        domain_terms = (
            "wi-fi",
            "wifi",
            "ssid",
            "料金",
            "無料",
            "利用",
            "受付",
            "初めて",
            "登録",
            "会員",
            "会員制度",
            "会員番号",
            "membership",
            "member",
            "registration",
            "register",
            "会员",
            "會員",
            "登记",
            "회원",
            "멤버십",
            "가입",
            "등록",
            "予約",
            "営業時間",
            "開館",
            "駐車",
            "電源",
            "喫煙",
            "禁煙",
            "흡연",
            "금연",
            "담배",
        )
        query_lower = query.lower()
        for term in domain_terms:
            if term.lower() in query_lower:
                terms.add(term.lower())

        cjk_compounds = [term for term in terms if self._contains_cjk(term)]
        for term in cjk_compounds:
            terms.update(term[i : i + 2] for i in range(len(term) - 1))

        stop_terms = {
            "です",
            "ます",
            "ませ",
            "さい",
            "くだ",
            "テスト",
            "テス",
            "スト",
            "教え",
            "えて",
            "して",
            "した",
            "the",
            "tell",
            "about",
            "me",
            "your",
            "like",
            "can",
            "how",
            "what",
            "where",
            "is",
            "to",
            "i",
        }
        return sorted(term for term in terms if len(term) >= 2 and term not in stop_terms)

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any(
            "\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff" or "\uac00" <= c <= "\ud7af"
            for c in text
        )

    @staticmethod
    def _query_mentions_saino(query: str) -> bool:
        query_lower = query.lower()
        return any(term.lower() in query_lower for term in SAINO_QUERY_TERMS)

    @staticmethod
    def _query_mentions_engineer_cafe(query: str) -> bool:
        query_lower = query.lower()
        return any(
            term in query_lower
            for term in (
                "engineer cafe",
                "engineercafe",
                "エンジニアカフェ",
                "エンジニア カフェ",
            )
        )

    @staticmethod
    def _is_membership_query(query: str) -> bool:
        query_lower = query.lower()
        return any(term.lower() in query_lower for term in MEMBERSHIP_QUERY_TERMS)

    def _needs_membership_fallback(self, query: str, scored_results: List[Dict]) -> bool:
        """Force official local knowledge for membership queries with no membership hit."""
        return (
            self._is_strong_membership_query(query)
            and not self._query_mentions_saino(query)
            and not any(self._result_has_membership_content(result) for result in scored_results)
        )

    @staticmethod
    def _is_strong_membership_query(query: str) -> bool:
        query_lower = query.lower()
        if re.search(r"\bmembership\b|\bmembers?\b", query_lower):
            return True
        return any(
            term in query_lower
            for term in (
                "会員",
                "会員制度",
                "会員登録",
                "利用登録",
                "會員",
                "会员",
                "회원",
                "멤버십",
            )
        )

    @staticmethod
    def _result_has_membership_content(result: Dict) -> bool:
        metadata = result.get("metadata", {})
        tags = metadata.get("tags", []) if isinstance(metadata, dict) else []
        combined = " ".join(
            str(part)
            for part in (
                result.get("id", ""),
                result.get("title", ""),
                result.get("content", ""),
                " ".join(str(tag) for tag in tags if tag is not None),
            )
            if part is not None
        ).lower()

        if re.search(r"\bmembership\b|\bmembers?\b|\bmember\s+number\b", combined):
            return True

        return any(
            term in combined
            for term in (
                "会員",
                "会員制度",
                "会員番号",
                "利用登録",
                "會員",
                "会员",
                "회원",
                "멤버십",
            )
        )

    @staticmethod
    def _infer_entity_from_yaml_entry(entry: Dict) -> str:
        tags = entry.get("tags", [])
        tag_text = " ".join(str(tag) for tag in tags if tag is not None)
        strong_combined = " ".join(
            str(part)
            for part in (
                entry.get("id", ""),
                entry.get("title", ""),
                entry.get("title_en", ""),
                tag_text,
            )
            if part is not None
        ).lower()
        full_combined = " ".join(
            str(part)
            for part in (
                strong_combined,
                entry.get("content", ""),
                entry.get("content_en", ""),
            )
            if part is not None
        ).lower()

        if any(term.lower() in strong_combined for term in SAINO_QUERY_TERMS):
            return "saino"
        if (
            "meeting-room" in strong_combined
            or "meeting room" in strong_combined
            or "会議室" in strong_combined
        ):
            return "meeting-room"
        if (
            "engineer-cafe" in full_combined
            or "engineer cafe" in full_combined
            or "エンジニアカフェ" in full_combined
        ):
            return "engineer-cafe"
        return "general"

    def _category_matches(
        self,
        row_category: str,
        requested_category: str,
        row: Optional[Dict] = None,
        query: str = "",
    ) -> bool:
        if not requested_category:
            return True

        if requested_category == "general":
            return row_category in {
                "general",
                "hours",
                "pricing",
                "access",
                "location",
                "contact",
                "policy",
                "parking",
                "bicycle",
                "food_drink",
                "smoking",
            }

        accepted_categories = RAG_CATEGORY_ALIASES.get(requested_category, {requested_category})
        if row_category in accepted_categories:
            return True

        if not row:
            return False

        entity = self._detect_entity(row)
        if entity == "saino" and self._query_mentions_saino(query):
            if requested_category in {
                "hours",
                "saino-cafe",
                "facility-info",
                "food_drink",
                "pricing",
            }:
                return row_category in {
                    "hours",
                    "facility-info",
                    "food_drink",
                    "pricing",
                    "general",
                }

        return False
