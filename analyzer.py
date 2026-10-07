"""
Charles Session Analyzer.
Provides aggregation, filtering, search, and performance reporting.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from .models import CharlesRequest
    from .parser import CharlesSessionParser
except ImportError:
    from models import CharlesRequest
    from parser import CharlesSessionParser


class CharlesAnalyzer:
    """Analyzer for Charles Proxy sessions."""

    def __init__(self, requests: List[CharlesRequest]):
        self.requests = requests

    @classmethod
    def from_file(cls, file_source: Any) -> CharlesAnalyzer:
        """Load and parse session file or bytes directly into an analyzer instance."""
        parser = CharlesSessionParser(file_source)
        requests = parser.parse()
        return cls(requests)

    def _calc_percentiles(self, values: List[int]) -> Dict[str, float]:
        """Calculate p50, p90, p95, p99 percentiles."""
        if not values:
            return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def _p(pct: float) -> float:
            k = (n - 1) * (pct / 100.0)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return float(sorted_vals[int(k)])
            d0 = sorted_vals[int(f)] * (c - k)
            d1 = sorted_vals[int(c)] * (k - f)
            return round(d0 + d1, 2)

        return {
            "p50": _p(50),
            "p90": _p(90),
            "p95": _p(95),
            "p99": _p(99),
        }

    def summary(self) -> Dict[str, Any]:
        """Compute comprehensive statistical summary of the session."""
        if not self.requests:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_bytes_sent": 0,
                "total_bytes_received": 0,
                "total_bytes": 0,
                "avg_duration_ms": 0.0,
                "min_duration_ms": 0,
                "max_duration_ms": 0,
                "percentiles_ms": {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0},
                "status_codes": {},
                "status_categories": {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "ERR": 0},
                "methods": {},
                "hosts": {},
                "content_types": {},
                "top_endpoints": [],
            }

        total_requests = len(self.requests)
        successful_requests = sum(1 for r in self.requests if r.is_success)
        failed_requests = sum(1 for r in self.requests if r.is_error)

        status_counter = Counter(r.response_status if r.response_status is not None else "No Response" for r in self.requests)
        category_counter = Counter(r.status_category for r in self.requests)
        method_counter = Counter(r.method for r in self.requests)
        host_counter = Counter(r.host for r in self.requests)
        mime_counter = Counter(r.response_mime_type or "Unknown" for r in self.requests)

        durations = [r.duration_ms for r in self.requests]
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        percentiles = self._calc_percentiles(durations)

        bytes_sent = sum(r.request_sizes.get("body", 0) or 0 for r in self.requests)
        bytes_received = sum(r.response_sizes.get("body", 0) or 0 for r in self.requests)

        # Top endpoints breakdown
        endpoints_data = defaultdict(lambda: {"count": 0, "total_duration": 0, "errors": 0})
        for r in self.requests:
            path_base = (r.path or "").split("?")[0]
            key = f"{r.method or 'GET'} {path_base}"
            endpoints_data[key]["count"] += 1
            endpoints_data[key]["total_duration"] += r.duration_ms
            if r.is_error:
                endpoints_data[key]["errors"] += 1

        top_endpoints = []
        for ep, data in endpoints_data.items():
            top_endpoints.append({
                "endpoint": ep,
                "count": data["count"],
                "avg_duration_ms": round(data["total_duration"] / data["count"], 2),
                "errors": data["errors"],
            })
        top_endpoints.sort(key=lambda x: x["count"], reverse=True)

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "total_bytes_sent": bytes_sent,
            "total_bytes_received": bytes_received,
            "total_bytes": bytes_sent + bytes_received,
            "avg_duration_ms": round(avg_duration, 2),
            "min_duration_ms": min_duration,
            "max_duration_ms": max_duration,
            "percentiles_ms": percentiles,
            "status_codes": dict(status_counter),
            "status_categories": dict(category_counter),
            "methods": dict(method_counter),
            "hosts": dict(host_counter.most_common(15)),
            "content_types": dict(mime_counter.most_common(10)),
            "top_endpoints": top_endpoints[:10],
        }

    def filter(
        self,
        host: Optional[str] = None,
        status: Optional[Union[int, str]] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        min_duration: Optional[int] = None,
        max_duration: Optional[int] = None,
        errors_only: bool = False,
        mime_type: Optional[str] = None,
        query_param: Optional[str] = None,
        sort_by: Optional[str] = None,
        reverse: bool = False,
    ) -> List[CharlesRequest]:
        """
        Filter and sort requests using specified criteria.
        """
        results = []
        host_lower = host.lower() if host else None
        method_upper = method.upper() if method else None
        path_lower = path.lower() if path else None
        query_lower = query_param.lower() if query_param else None
        mime_lower = mime_type.lower() if mime_type else None

        status_prefix = None
        status_exact = None
        if status is not None:
            if isinstance(status, int):
                status_exact = status
            elif isinstance(status, str):
                s_str = status.lower()
                if s_str.endswith("xx") and s_str[0].isdigit():
                    status_prefix = int(s_str[0])
                elif s_str.isdigit():
                    status_exact = int(s_str)

        for req in self.requests:
            if errors_only and not req.is_error:
                continue

            if host_lower and host_lower not in req.host.lower():
                continue

            if method_upper and method_upper != req.method.upper():
                continue

            if path_lower and path_lower not in req.path.lower():
                continue

            if query_lower and query_lower not in req.query.lower():
                continue

            if mime_lower and (not req.response_mime_type or mime_lower not in req.response_mime_type.lower()):
                continue

            if min_duration is not None and req.duration_ms < min_duration:
                continue

            if max_duration is not None and req.duration_ms > max_duration:
                continue

            if status_exact is not None and req.response_status != status_exact:
                continue

            if status_prefix is not None:
                if req.response_status is None or req.response_status // 100 != status_prefix:
                    continue

            results.append(req)

        if sort_by:
            sort_key_map = {
                "duration": lambda r: r.duration_ms,
                "size": lambda r: r.total_bytes,
                "status": lambda r: r.response_status or 0,
                "id": lambda r: r.id,
                "host": lambda r: r.host.lower(),
                "path": lambda r: r.path.lower(),
            }
            key_func = sort_key_map.get(sort_by.lower())
            if key_func:
                results.sort(key=key_func, reverse=reverse)

        return results

    def search(
        self,
        query: str,
        in_url: bool = True,
        in_headers: bool = True,
        in_body: bool = True,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> List[CharlesRequest]:
        """
        Perform text or regex search across URL, method, status, headers, and request/response body.
        """
        if not query:
            return []

        pattern = None
        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(query, flags)
            except re.error:
                return []

        q = query if case_sensitive else query.lower()
        results = []

        for req in self.requests:
            matched = False

            # Check URL / Method / Status / Host / Path
            if in_url:
                url_str = req.url or ""
                method_str = req.method or ""
                status_str = str(req.response_status) if req.response_status is not None else ""
                status_text = req.status_text or ""
                host_str = req.host or ""
                path_str = req.path or ""

                if pattern:
                    if (
                        pattern.search(url_str)
                        or pattern.search(method_str)
                        or pattern.search(status_str)
                        or pattern.search(status_text)
                        or pattern.search(host_str)
                        or pattern.search(path_str)
                    ):
                        matched = True
                else:
                    targets = [url_str, method_str, status_str, status_text, host_str, path_str]
                    if not case_sensitive:
                        targets = [t.lower() for t in targets]
                    if any(q in t for t in targets):
                        matched = True

            # Check Headers
            if not matched and in_headers:
                headers_items = list(req.request_headers.items()) + list(req.response_headers.items())
                headers_text = " ".join(f"{k}: {v}" for k, v in headers_items)
                if pattern:
                    if pattern.search(headers_text):
                        matched = True
                else:
                    target = headers_text if case_sensitive else headers_text.lower()
                    if q in target:
                        matched = True

            # Check Body
            if not matched and in_body:
                req_body = req.get_req_body_text() or ""
                res_body = req.get_res_body_text() or ""
                if pattern:
                    if pattern.search(req_body) or pattern.search(res_body):
                        matched = True
                else:
                    if case_sensitive:
                        if q in req_body or q in res_body:
                            matched = True
                    else:
                        if q in req_body.lower() or q in res_body.lower():
                            matched = True

            if matched:
                results.append(req)

        return results

    def get_slowest(self, limit: int = 10) -> List[CharlesRequest]:
        """Get the N slowest requests sorted by total duration descending."""
        return sorted(self.requests, key=lambda r: r.duration_ms, reverse=True)[:limit]

    def get_largest(self, limit: int = 10) -> List[CharlesRequest]:
        """Get the N largest requests sorted by total payload size descending."""
        return sorted(self.requests, key=lambda r: r.total_bytes, reverse=True)[:limit]

    def get_errors(self) -> List[CharlesRequest]:
        """Get all failed/error requests (status >= 400 or missing status)."""
        return [r for r in self.requests if r.is_error]

    def get_request_by_id(self, req_id: int) -> Optional[CharlesRequest]:
        """Retrieve specific request by ID."""
        for r in self.requests:
            if r.id == req_id:
                return r
        return None

