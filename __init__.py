from collections import deque
from datetime import datetime
from html import escape
import json
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Option, Source


class _RateLimiter:
    def __init__(self, max_calls, period, clock=None, sleeper=None):
        self.max_calls = max_calls
        self.period = period
        self.clock = clock or time.monotonic
        self.sleeper = sleeper or time.sleep
        self.calls = deque()
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = self.clock()
            while self.calls and now - self.calls[0] >= self.period:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                self.sleeper(self.period - (now - self.calls[0]))
                now = self.clock()
                while self.calls and now - self.calls[0] >= self.period:
                    self.calls.popleft()
            self.calls.append(now)


_API_RATE_LIMITER = _RateLimiter(max_calls=10, period=1.0)

class Yes24(Source):

    name = "Yes24 OpenAPI"
    description = "Downloads Korean book metadata and covers from Yes24 Open API."
    author = "Limeade23 <https://github.com/limeade23>"
    version = (1, 0, 1)
    minimum_calibre_version = (6, 10, 0)

    YES24_ID: str = "yes24"
    API_BASE_URL: str = "https://apis.yes24.com/v1"

    options = (
        Option(
            "api_key",
            "string",
            "",
            "API Key",
            "Yes24 Developers에서 발급받은 API 키를 입력하세요.",
        ),
    )

    capabilities = frozenset(["identify", "cover"])
    has_html_comments = True
    touched_fields = frozenset(
        [
            "title",
            "authors",
            "identifier:" + YES24_ID,
            "identifier:isbn",
            "comments",
            "publisher",
            "pubdate",
            "languages",
            "rating",
            "series",
        ]
    )

    @staticmethod
    def _normalize_isbn13(value):
        isbn = re.sub(r"[^0-9Xx]", "", value or "")
        if len(isbn) == 13 and isbn.isdigit():
            return isbn
        if len(isbn) != 10 or not isbn[:9].isdigit():
            return ""

        check_digit = 10 if isbn[-1].upper() == "X" else int(isbn[-1])
        checksum = sum((10 - index) * int(digit) for index, digit in enumerate(isbn[:9]))
        if (checksum + check_digit) % 11:
            return ""

        body = "978" + isbn[:9]
        total = sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(body))
        return body + str((10 - total % 10) % 10)

    @staticmethod
    def _is_domestic_book(item):
        if item.get("goodsType") == "국내도서":
            return True
        goods_sort = item.get("goodsSortNm") or ""
        return goods_sort == "국내도서" or goods_sort.startswith("국내도서-")

    def identify(
        self,
        log,
        result_queue,
        abort,
        title=None,
        authors=None,
        identifiers=None,
        timeout=30,
    ):
        if not self.prefs.get("api_key"):
            log.error("Yes24 API 키를 플러그인 사용자 정의에서 입력해 주세요.")
            return

        identifiers = identifiers or {}
        requested_item_id = identifiers.get(self.YES24_ID)
        isbn = self._normalize_isbn13(identifiers.get("isbn", ""))
        search_terms = [title or ""] + list(authors or [])
        query = " ".join(
            term.strip() for term in search_terms if term and term.strip()
        )
        search_params = {
            "query": query,
            "category": "BOOK",
            "sort": "RELATION",
            "page": 1,
            "pageSize": 10,
            "detail": "Y",
        }

        if not requested_item_id and not isbn and not query:
            log.error("Yes24 검색에는 제목 또는 ISBN13이 필요합니다.")
            return

        try:
            if requested_item_id:
                data = self._request_json(
                    "/goods/itemDetail",
                    {
                        "searchType": "ItemId",
                        "query": str(requested_item_id),
                        "detail": "Y",
                    },
                    timeout,
                )
            elif isbn:
                data = self._request_json(
                    "/goods/itemDetail",
                    {"searchType": "ISBN13", "query": isbn, "detail": "Y"},
                    timeout,
                )
            else:
                data = self._request_json("/goods/itemList", search_params, timeout)

            items = [
                item
                for item in data.get("items", [])
                if self._is_domestic_book(item)
            ]
            if (requested_item_id or isbn) and not items and query:
                data = self._request_json("/goods/itemList", search_params, timeout)
                items = [
                    item
                    for item in data.get("items", [])
                    if self._is_domestic_book(item)
                ]
        except Exception as error:
            log.error("Yes24 API 요청 실패: %s", error)
            return

        for relevance, item in enumerate(items):
            metadata = self._to_metadata(item)
            metadata.source_relevance = relevance
            item_id = metadata.identifiers[self.YES24_ID]
            if metadata.isbn:
                self.cache_isbn_to_identifier(metadata.isbn, item_id)
            if metadata.cover_url:
                self.cache_identifier_to_cover_url(item_id, metadata.cover_url)
            self.clean_downloaded_metadata(metadata)
            result_queue.put(metadata)

    def _request_json(self, endpoint, params, timeout=30):
        _API_RATE_LIMITER.wait()
        url = f"{self.API_BASE_URL}{endpoint}?{urlencode(params)}"
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "X-Api-Key": self.prefs["api_key"]},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
            except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
                raise RuntimeError(f"HTTP_{error.code}: {error.reason}") from error
            error_code = payload.get("errorCode") or f"HTTP_{error.code}"
            message = payload.get("message") or error.reason
            raise RuntimeError(f"{error_code}: {message}") from error
        if not payload.get("success"):
            error_code = payload.get("errorCode") or "UNKNOWN"
            message = payload.get("message") or "Yes24 API 요청에 실패했습니다."
            raise RuntimeError(f"{error_code}: {message}")
        return payload.get("data") or {}

    def _to_metadata(self, data):
        title = data.get("title", "").strip()
        subtitle = data.get("subTitle", "").strip()
        if subtitle:
            title = f"{title}: {subtitle}"

        authors = [
            author.strip()
            for author in re.split(r"\s*[,;^]\s*", data.get("author", ""))
            if author.strip()
        ]
        metadata = Metadata(title, authors)
        metadata.set_identifier(self.YES24_ID, str(data.get("itemId", "")))
        metadata.isbn = data.get("isbn13", "")
        metadata.publisher = data.get("publisher", "")
        metadata.language = "kor"
        star_score = data.get("starScore")
        metadata.rating = float(star_score) / 2 if star_score is not None else None
        metadata.cover_url = data.get("cover", "")

        publish_date = data.get("publishDate")
        if publish_date:
            date_format = "%Y-%m-%d" if "-" in publish_date else "%Y%m%d"
            metadata.pubdate = datetime.strptime(publish_date, date_format)

        series = data.get("series") or []
        if series:
            metadata.series = series[0].get("seriesName")

        content = data.get("contentDetail") or {}
        comments = []
        for field in ("bookIntroduction", "bookSummary"):
            value = content.get(field)
            if value:
                comments.append(f"<p>{escape(value)}</p>")
        table_of_contents = content.get("tableOfContents")
        if table_of_contents:
            formatted_contents = escape(table_of_contents).replace("\n", "<br/>")
            comments.append(f"<h3>목차</h3><p>{formatted_contents}</p>")
        metadata.comments = "".join(comments)

        return metadata
    
    def get_cached_cover_url(self, identifiers):
        item_id = identifiers.get(self.YES24_ID)
        if not item_id:
            isbn = self._normalize_isbn13(identifiers.get("isbn", ""))
            if isbn:
                item_id = self.cached_isbn_to_identifier(isbn)
        if item_id:
            return self.cached_identifier_to_cover_url(item_id)
        return None

    def download_cover(
        self,
        log,
        result_queue,
        abort,
        title=None,
        authors=None,
        identifiers=None,
        timeout=30,
        get_best_cover=False,
    ):
        identifiers = identifiers or {}
        cover_url = self.get_cached_cover_url(identifiers)
        isbn = self._normalize_isbn13(identifiers.get("isbn", ""))
        requested_item_id = identifiers.get(self.YES24_ID)
        search_terms = [title or ""] + list(authors or [])
        query = " ".join(
            term.strip() for term in search_terms if term and term.strip()
        )
        search_params = {
            "query": query,
            "category": "BOOK",
            "sort": "RELATION",
            "page": 1,
            "pageSize": 10,
            "detail": "N",
        }

        endpoint = None
        lookup_params = None
        if requested_item_id:
            endpoint = "/goods/itemDetail"
            lookup_params = {
                "searchType": "ItemId",
                "query": str(requested_item_id),
                "detail": "N",
            }
        elif isbn:
            endpoint = "/goods/itemDetail"
            lookup_params = {"searchType": "ISBN13", "query": isbn, "detail": "N"}
        elif query:
            endpoint = "/goods/itemList"
            lookup_params = search_params

        if not cover_url and lookup_params:
            if not self.prefs.get("api_key"):
                log.error("Yes24 API 키를 플러그인 사용자 정의에서 입력해 주세요.")
                return
            try:
                data = self._request_json(endpoint, lookup_params, timeout)
            except Exception as error:
                log.error("Yes24 API 요청 실패: %s", error)
                return
            items = [
                item
                for item in data.get("items", [])
                if self._is_domestic_book(item)
            ]
            if not items and endpoint == "/goods/itemDetail" and query:
                try:
                    data = self._request_json(
                        "/goods/itemList", search_params, timeout
                    )
                except Exception as error:
                    log.error("Yes24 API 요청 실패: %s", error)
                    return
                items = [
                    item
                    for item in data.get("items", [])
                    if self._is_domestic_book(item)
                ]
            if items:
                item = items[0]
                item_id = str(item.get("itemId", ""))
                item_isbn = self._normalize_isbn13(item.get("isbn13", "")) or isbn
                cover_url = item.get("cover", "")
                if item_id:
                    if item_isbn:
                        self.cache_isbn_to_identifier(item_isbn, item_id)
                    if cover_url:
                        self.cache_identifier_to_cover_url(item_id, cover_url)

        if not cover_url:
            log.info("No cover found")
            return

        try:
            log.info("Downloading cover from: %s", cover_url)
            with urlopen(cover_url, timeout=timeout) as response:
                result_queue.put((self, response.read()))
        except Exception:
            log.exception("Failed to download cover from: %s", cover_url)
