"""
Data models for representing Charles Proxy session requests and responses.
"""

from __future__ import annotations

import gzip
import json
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CharlesRequest:
    id: int
    status_text: str = ""
    method: str = "GET"
    scheme: str = "http"
    host: str = ""
    port: int = 80
    path: str = ""
    query: str = ""

    response_status: Optional[int] = None

    times: Dict[str, Any] = field(default_factory=dict)
    durations: Dict[str, Any] = field(default_factory=dict)
    speeds: Dict[str, Any] = field(default_factory=dict)

    request_sizes: Dict[str, int] = field(default_factory=dict)
    response_sizes: Dict[str, int] = field(default_factory=dict)

    request_mime_type: Optional[str] = None
    response_mime_type: Optional[str] = None

    request_headers: Dict[str, str] = field(default_factory=dict)
    response_headers: Dict[str, str] = field(default_factory=dict)

    req_filename: Optional[str] = None
    res_filename: Optional[str] = None

    req_body_bytes: bytes = b""
    res_body_bytes: bytes = b""

    raw_meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        """Construct full URL."""
        port_str = ""
        if (self.scheme == "http" and self.port != 80) or (self.scheme == "https" and self.port != 443):
            port_str = f":{self.port}"
        query_str = f"?{self.query}" if self.query else ""
        return f"{self.scheme}://{self.host}{port_str}{self.path}{query_str}"

    @property
    def duration_ms(self) -> int:
        """Get total duration in milliseconds."""
        return self.durations.get("total", 0) or 0

    @property
    def latency_ms(self) -> int:
        """Get latency in milliseconds."""
        return self.durations.get("latency", 0) or 0

    @property
    def is_success(self) -> bool:
        """Check if request returned 2xx or 3xx status code."""
        return self.response_status is not None and 200 <= self.response_status < 400

    @property
    def is_error(self) -> bool:
        """Check if request returned 4xx or 5xx status code, or failed."""
        if self.response_status is None:
            return True
        return self.response_status >= 400

    @property
    def is_2xx(self) -> bool:
        """Check if response status is 2xx."""
        return self.response_status is not None and 200 <= self.response_status < 300

    @property
    def is_3xx(self) -> bool:
        """Check if response status is 3xx."""
        return self.response_status is not None and 300 <= self.response_status < 400

    @property
    def is_4xx(self) -> bool:
        """Check if response status is 4xx."""
        return self.response_status is not None and 400 <= self.response_status < 500

    @property
    def is_5xx(self) -> bool:
        """Check if response status is 5xx."""
        return self.response_status is not None and 500 <= self.response_status < 600

    @property
    def status_category(self) -> str:
        """Get status code category string (2xx, 3xx, 4xx, 5xx, or ERR)."""
        if self.response_status is None:
            return "ERR"
        if 200 <= self.response_status < 300:
            return "2xx"
        if 300 <= self.response_status < 400:
            return "3xx"
        if 400 <= self.response_status < 500:
            return "4xx"
        if 500 <= self.response_status < 600:
            return "5xx"
        return "ERR"

    @property
    def total_bytes(self) -> int:
        """Total size in bytes (request + response body and headers)."""
        req_b = (self.request_sizes.get("headers", 0) or 0) + (self.request_sizes.get("body", 0) or 0)
        res_b = (self.response_sizes.get("headers", 0) or 0) + (self.response_sizes.get("body", 0) or 0)
        return req_b + res_b

    @property
    def formatted_size(self) -> str:
        """Format total_bytes to human readable string."""
        size = self.total_bytes
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        else:
            return f"{size / (1024 * 1024):.2f} MB"

    def get_header(self, name: str, default: Optional[str] = None, response: bool = False) -> Optional[str]:
        """Case-insensitive lookup for request or response headers."""
        headers = self.response_headers if response else self.request_headers
        target_key = name.lower()
        for k, v in headers.items():
            if k.lower() == target_key:
                return v
        return default

    def _decode_bytes(self, raw_bytes: bytes, encoding_header: Optional[str] = None) -> Optional[str]:
        """Decompress and decode bytes into UTF-8 string cleanly."""
        if not raw_bytes:
            return None

        decompressed = raw_bytes
        encoding = (encoding_header or "").lower()

        if "gzip" in encoding or raw_bytes.startswith(b"\x1f\x8b"):
            try:
                decompressed = gzip.decompress(raw_bytes)
            except Exception:
                pass
        elif "deflate" in encoding:
            try:
                decompressed = zlib.decompress(raw_bytes, -zlib.MAX_WBITS)
            except Exception:
                try:
                    decompressed = zlib.decompress(raw_bytes)
                except Exception:
                    pass
        elif "br" in encoding:
            try:
                import brotli
                decompressed = brotli.decompress(raw_bytes)
            except Exception:
                pass

        try:
            return decompressed.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return decompressed.decode("latin-1")
            except Exception:
                return None

    def get_req_body_text(self) -> Optional[str]:
        """Decode request body as UTF-8 string."""
        enc = self.get_header("Content-Encoding", response=False)
        return self._decode_bytes(self.req_body_bytes, enc)

    def get_res_body_text(self) -> Optional[str]:
        """Decode response body as UTF-8 string."""
        enc = self.get_header("Content-Encoding", response=True)
        return self._decode_bytes(self.res_body_bytes, enc)

    def get_req_json(self) -> Any:
        """Parse request body as JSON."""
        text = self.get_req_body_text()
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return None

    def get_res_json(self) -> Any:
        """Parse response body as JSON."""
        text = self.get_res_body_text()
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return None

    def to_dict(self, include_bodies: bool = False) -> Dict[str, Any]:
        """Convert request model to dictionary."""
        d = {
            "id": self.id,
            "status_text": self.status_text,
            "method": self.method,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "query": self.query,
            "url": self.url,
            "response_status": self.response_status,
            "duration_ms": self.duration_ms,
            "latency_ms": self.latency_ms,
            "request_mime_type": self.request_mime_type,
            "response_mime_type": self.response_mime_type,
            "request_sizes": self.request_sizes,
            "response_sizes": self.response_sizes,
            "total_bytes": self.total_bytes,
            "formatted_size": self.formatted_size,
            "status_category": self.status_category,
            "is_success": self.is_success,
            "is_error": self.is_error,
            "request_headers": self.request_headers,
            "response_headers": self.response_headers,
            "times": self.times,
        }
        if include_bodies:
            d["request_body"] = self.get_req_json() or self.get_req_body_text()
            d["response_body"] = self.get_res_json() or self.get_res_body_text()
        return d

