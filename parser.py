"""
Parser for Charles Proxy trace/session files (.chlz, zip archive).
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Union

try:
    from .models import CharlesRequest
except ImportError:
    from models import CharlesRequest


class CharlesSessionParser:
    """Parses Charles Proxy session files (.chlz)."""

    def __init__(self, file_source: Union[str, Path, bytes, io.BytesIO]):
        if isinstance(file_source, (str, Path)):
            self.file_path = Path(file_source)
            if not self.file_path.exists():
                raise FileNotFoundError(f"File not found: {self.file_path}")
            self.zip_source = self.file_path
        elif isinstance(file_source, bytes):
            self.zip_source = io.BytesIO(file_source)
        else:
            self.zip_source = file_source

    def parse(self) -> List[CharlesRequest]:
        """
        Parse the .chlz zip file and return a list of CharlesRequest objects sorted by ID.
        """
        if not zipfile.is_zipfile(self.zip_source):
            raise ValueError("Provided file is not a valid zip archive (.chlz)")

        requests_dict: Dict[int, CharlesRequest] = {}

        with zipfile.ZipFile(self.zip_source, "r") as z:
            namelist = z.namelist()

            # Map filenames by request ID and type (meta, req, res)
            # Handles root files like "0-meta.json" and nested paths like "session/0-meta.json"
            file_index_map: Dict[int, Dict[str, str]] = {}
            pattern = re.compile(r"(?:^|/)(?P<id>\d+)-(?P<kind>meta|req|res)(?:\..+)?$")

            for filename in namelist:
                match = pattern.search(filename)
                if match:
                    req_id = int(match.group("id"))
                    kind = match.group("kind")
                    if req_id not in file_index_map:
                        file_index_map[req_id] = {}
                    file_index_map[req_id][kind] = filename

            # Process metadata and payloads
            for req_id in sorted(file_index_map.keys()):
                files = file_index_map[req_id]
                if "meta" not in files:
                    continue

                meta_data = self._read_json_from_zip(z, files["meta"])
                if not meta_data:
                    continue

                req_obj = self._build_request_object(req_id, meta_data, files)

                # Read request body if present
                if "req" in files:
                    req_obj.req_filename = files["req"]
                    req_obj.req_body_bytes = z.read(files["req"])

                # Read response body if present
                if "res" in files:
                    req_obj.res_filename = files["res"]
                    req_obj.res_body_bytes = z.read(files["res"])

                requests_dict[req_id] = req_obj

        return [requests_dict[k] for k in sorted(requests_dict.keys())]

    def _read_json_from_zip(self, z: zipfile.ZipFile, filename: str) -> Dict[str, Any]:
        try:
            content = z.read(filename).decode("utf-8")
            return json.loads(content)
        except Exception:
            return {}

    def _extract_headers(self, header_data: Dict[str, Any]) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if not header_data:
            return headers
        header_list = header_data.get("headers", [])
        if isinstance(header_list, list):
            for item in header_list:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    headers[str(item["name"])] = str(item["value"])
        elif isinstance(header_list, dict):
            headers = {str(k): str(v) for k, v in header_list.items()}
        return headers

    def _build_request_object(self, req_id: int, meta: Dict[str, Any], files: Dict[str, str]) -> CharlesRequest:
        req_info = meta.get("request", {})
        res_info = meta.get("response", {})

        req_headers = self._extract_headers(req_info.get("header", {}))
        res_headers = self._extract_headers(res_info.get("header", {}))

        req_mime = req_info.get("mimeType")
        res_mime = res_info.get("mimeType")

        status_code = res_info.get("status")
        if status_code is not None:
            try:
                status_code = int(status_code)
            except (ValueError, TypeError):
                status_code = None

        return CharlesRequest(
            id=req_id,
            status_text=meta.get("status") or "",
            method=meta.get("method") or "GET",
            scheme=meta.get("scheme") or "http",
            host=meta.get("host") or "",
            port=meta.get("actualPort") or meta.get("port") or (443 if meta.get("scheme") == "https" else 80),
            path=meta.get("path") or "",
            query=meta.get("query") or "",
            response_status=status_code,
            times=meta.get("times", {}) or {},
            durations=meta.get("durations", {}) or {},
            speeds=meta.get("speeds", {}) or {},
            request_sizes=req_info.get("sizes", {}) or {},
            response_sizes=res_info.get("sizes", {}) or {},
            request_mime_type=req_mime,
            response_mime_type=res_mime,
            request_headers=req_headers,
            response_headers=res_headers,
            raw_meta=meta,
        )

