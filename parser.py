"""
Parser for Charles Proxy trace/session files (.chlz, .chls) and HTTP Archive files (.har).
"""

from __future__ import annotations

import base64
import io
import json
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
from urllib.parse import urlparse

try:
    from .models import CharlesRequest
except ImportError:
    from models import CharlesRequest


CHLZ_FILE_PATTERN = re.compile(r"(?:^|/)(?P<id>\d+)-(?P<kind>meta|req|res)(?:\..+)?$")
REQ_LINE_PATTERN = re.compile(r"^(GET|POST|PUT|DELETE|HEAD|OPTIONS|CONNECT|PATCH)\s+([^\s]+)", re.IGNORECASE)


def _to_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _java_body_to_bytes(obj: Any) -> bytes:
    """Safely convert javaobj JavaByteArray or sequence of signed bytes to Python bytes."""
    if obj is None:
        return b""
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    if hasattr(obj, "_data") and isinstance(obj._data, (list, tuple, bytes, bytearray)):
        return bytes([b & 0xFF for b in obj._data])
    if hasattr(obj, "data") and isinstance(obj.data, (list, tuple, bytes, bytearray)):
        return bytes([b & 0xFF for b in obj.data])
    try:
        return bytes([b & 0xFF for b in obj])
    except Exception:
        return b""


class CharlesSessionParser:
    """
    Parses Charles Proxy session files (.chlz zip archives, .chls JSON/XML/Binary)
    and HTTP Archive files (.har).
    """

    def __init__(self, file_source: Union[str, Path, bytes, io.BytesIO]):
        self.file_path: Path | None = None
        if isinstance(file_source, (str, Path)):
            self.file_path = Path(file_source)
            if not self.file_path.exists():
                raise FileNotFoundError(f"File not found: {self.file_path}")
            with open(self.file_path, "rb") as f:
                self.data_bytes = f.read()
        elif isinstance(file_source, bytes):
            self.data_bytes = file_source
        elif hasattr(file_source, "read"):
            self.data_bytes = file_source.read()
        else:
            raise TypeError("Unsupported file_source type")

    def parse(self) -> List[CharlesRequest]:
        """
        Auto-detect format (.chlz zip, .har JSON, .chls JSON/XML/Binary) and return parsed requests.
        """
        # 1. Check if ZIP archive (.chlz)
        if zipfile.is_zipfile(io.BytesIO(self.data_bytes)):
            return self._parse_chlz()

        stripped = self.data_bytes.strip()

        # 2. Check if HAR (.har) or CHLS JSON format
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            try:
                json_data = json.loads(self.data_bytes.decode("utf-8", errors="replace"))
                if isinstance(json_data, dict) and "log" in json_data and "entries" in json_data.get("log", {}):
                    return self._parse_har(json_data)
                return self._parse_chls_json(json_data)
            except Exception:
                pass

        # 3. Check if CHLS XML format
        if stripped.startswith(b"<") or b"<charles-session" in stripped or b"<session" in stripped:
            try:
                return self._parse_chls_xml(self.data_bytes)
            except Exception:
                pass

        # 4. Check if CHLS Java Binary format (0xACED 0005) or binary trace
        if self.data_bytes.startswith(b"\xac\xed") or b"com.xk72.charles" in self.data_bytes:
            return self._parse_chls_binary(self.data_bytes)

        raise ValueError(
            f"Unsupported or invalid session format for file: {self.file_path or 'bytes data'}. "
            "Supported formats are .chlz (zip), .chls (JSON/XML/Binary), and .har (JSON)."
        )

    def _parse_chlz(self) -> List[CharlesRequest]:
        """Parse .chlz zip session file."""
        requests_dict: Dict[int, CharlesRequest] = {}

        with zipfile.ZipFile(io.BytesIO(self.data_bytes), "r") as z:
            namelist = z.namelist()

            file_index_map: Dict[int, Dict[str, str]] = {}

            for filename in namelist:
                match = CHLZ_FILE_PATTERN.search(filename)
                if match:
                    req_id = int(match.group("id"))
                    kind = match.group("kind")
                    if req_id not in file_index_map:
                        file_index_map[req_id] = {}
                    file_index_map[req_id][kind] = filename

            for req_id in sorted(file_index_map.keys()):
                files = file_index_map[req_id]
                if "meta" not in files:
                    continue

                meta_data = self._read_json_from_zip(z, files["meta"])
                if not meta_data:
                    continue

                req_obj = self._build_request_object(req_id, meta_data, files)

                if "req" in files:
                    req_obj.req_filename = files["req"]
                    req_obj.req_body_bytes = z.read(files["req"])

                if "res" in files:
                    req_obj.res_filename = files["res"]
                    req_obj.res_body_bytes = z.read(files["res"])

                requests_dict[req_id] = req_obj

        return [requests_dict[k] for k in sorted(requests_dict.keys())]

    def _parse_har(self, har_data: Dict[str, Any]) -> List[CharlesRequest]:
        """Parse HTTP Archive (.har v1.2) JSON format."""
        log = har_data.get("log", {})
        entries = log.get("entries", [])

        requests: List[CharlesRequest] = []
        for idx, entry in enumerate(entries):
            req_data = entry.get("request", {}) or {}
            res_data = entry.get("response", {}) or {}
            timings = entry.get("timings", {}) or {}

            url_str = req_data.get("url", "")
            parsed_url = urlparse(url_str)

            scheme = parsed_url.scheme or "http"
            host = parsed_url.hostname or ""
            port = parsed_url.port or (443 if scheme == "https" else 80)
            path = parsed_url.path or ""
            query = parsed_url.query or ""

            req_headers = {
                str(h.get("name", "")): str(h.get("value", ""))
                for h in req_data.get("headers", [])
                if isinstance(h, dict) and "name" in h
            }
            res_headers = {
                str(h.get("name", "")): str(h.get("value", ""))
                for h in res_data.get("headers", [])
                if isinstance(h, dict) and "name" in h
            }

            # Request Body
            post_data = req_data.get("postData", {}) or {}
            req_text = post_data.get("text", "")
            req_body_bytes = req_text.encode("utf-8") if isinstance(req_text, str) else b""

            # Response Body
            res_content = res_data.get("content", {}) or {}
            res_text = res_content.get("text", "")
            res_encoding = res_content.get("encoding", "")

            if res_encoding == "base64" and res_text:
                try:
                    res_body_bytes = base64.b64decode(res_text)
                except Exception:
                    res_body_bytes = res_text.encode("utf-8")
            elif isinstance(res_text, str):
                res_body_bytes = res_text.encode("utf-8")
            else:
                res_body_bytes = b""

            status = res_data.get("status")
            status_int = _to_int(status, default=0) if status is not None else None
            if status_int == 0 and status is None:
                status_int = None

            total_time = _to_int(entry.get("time", 0))
            latency = _to_int(timings.get("wait", 0))
            if latency < 0:
                latency = 0

            req_headers_sz = _to_int(req_data.get("headersSize"), len(str(req_headers)))
            req_body_sz = _to_int(req_data.get("bodySize"), len(req_body_bytes))
            res_headers_sz = _to_int(res_data.get("headersSize"), len(str(res_headers)))
            res_body_sz = _to_int(res_data.get("bodySize"), len(res_body_bytes))

            if req_headers_sz < 0:
                req_headers_sz = len(str(req_headers))
            if req_body_sz < 0:
                req_body_sz = len(req_body_bytes)
            if res_headers_sz < 0:
                res_headers_sz = len(str(res_headers))
            if res_body_sz < 0:
                res_body_sz = len(res_body_bytes)

            req_obj = CharlesRequest(
                id=idx,
                status_text=str(res_data.get("statusText") or ""),
                method=str(req_data.get("method") or "GET").upper(),
                scheme=scheme,
                host=host,
                port=port,
                path=path,
                query=query,
                response_status=status_int,
                durations={"total": total_time, "latency": latency},
                request_sizes={
                    "headers": req_headers_sz,
                    "body": req_body_sz,
                },
                response_sizes={
                    "headers": res_headers_sz,
                    "body": res_body_sz,
                },
                request_mime_type=post_data.get("mimeType"),
                response_mime_type=res_content.get("mimeType"),
                request_headers=req_headers,
                response_headers=res_headers,
                req_body_bytes=req_body_bytes,
                res_body_bytes=res_body_bytes,
                raw_meta=entry,
            )
            requests.append(req_obj)

        return requests

    def _parse_chls_json(self, json_data: Union[Dict[str, Any], List[Any]]) -> List[CharlesRequest]:
        """Parse Charles Session (.chls / .chlsj) JSON export format."""
        if isinstance(json_data, list):
            items = json_data
        elif isinstance(json_data, dict):
            items = json_data.get("session", {}).get("transactions", json_data.get("transactions", [json_data]))
        else:
            items = []

        requests: List[CharlesRequest] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            req_data = item.get("request", {}) or {}
            res_data = item.get("response", {}) or {}

            scheme = item.get("scheme") or req_data.get("scheme", "http")
            host = item.get("host") or req_data.get("host", "")
            port = item.get("port") or req_data.get("port", 443 if scheme == "https" else 80)
            path = item.get("path") or req_data.get("path", "")
            query = item.get("query") or req_data.get("query", "")

            url_str = item.get("url") or req_data.get("url")
            if url_str and not host:
                pu = urlparse(url_str)
                scheme = pu.scheme or scheme
                host = pu.hostname or host
                port = pu.port or port
                path = pu.path or path
                query = pu.query or query

            req_headers = self._extract_headers(req_data.get("header") or req_data.get("headers"))
            res_headers = self._extract_headers(res_data.get("header") or res_data.get("headers"))

            # Body parsing
            req_body = req_data.get("body", "")
            if isinstance(req_body, str):
                req_body_bytes = req_body.encode("utf-8")
            elif isinstance(req_body, dict):
                if "text" in req_body:
                    req_body_bytes = str(req_body["text"]).encode("utf-8")
                elif "encoded" in req_body:
                    try:
                        req_body_bytes = base64.b64decode(req_body["encoded"])
                    except Exception:
                        req_body_bytes = b""
                else:
                    req_body_bytes = json.dumps(req_body).encode("utf-8")
            elif isinstance(req_body, list):
                req_body_bytes = json.dumps(req_body).encode("utf-8")
            else:
                req_body_bytes = b""

            res_body = res_data.get("body", "")
            if isinstance(res_body, str):
                res_body_bytes = res_body.encode("utf-8")
            elif isinstance(res_body, dict):
                if "text" in res_body:
                    res_body_bytes = str(res_body["text"]).encode("utf-8")
                elif "encoded" in res_body:
                    try:
                        res_body_bytes = base64.b64decode(res_body["encoded"])
                    except Exception:
                        res_body_bytes = b""
                else:
                    res_body_bytes = json.dumps(res_body).encode("utf-8")
            elif isinstance(res_body, list):
                res_body_bytes = json.dumps(res_body).encode("utf-8")
            else:
                res_body_bytes = b""

            status = item.get("status") or res_data.get("status")
            if status is not None:
                try:
                    status = int(status)
                except (ValueError, TypeError):
                    status = None

            durations = item.get("durations", {}) or {}
            dur_dict = durations if isinstance(durations, dict) else {"total": durations}

            req_obj = CharlesRequest(
                id=item.get("id", idx),
                status_text=str(item.get("status_text", res_data.get("statusText", ""))),
                method=str(item.get("method") or req_data.get("method", "GET")).upper(),
                scheme=scheme,
                host=host,
                port=port,
                path=path,
                query=query,
                response_status=status,
                durations=dur_dict,
                request_sizes=item.get("request_sizes", {}) or {"headers": 0, "body": len(req_body_bytes)},
                response_sizes=item.get("response_sizes", {}) or {"headers": 0, "body": len(res_body_bytes)},
                request_mime_type=req_data.get("mimeType"),
                response_mime_type=res_data.get("mimeType"),
                request_headers=req_headers,
                response_headers=res_headers,
                req_body_bytes=req_body_bytes,
                res_body_bytes=res_body_bytes,
                raw_meta=item,
            )
            requests.append(req_obj)

        return requests

    def _parse_chls_xml(self, data_bytes: bytes) -> List[CharlesRequest]:
        """Parse Charles Session (.chls) XML export format."""
        root = ET.fromstring(data_bytes.decode("utf-8", errors="replace"))
        transactions = root.findall(".//transaction") or root.findall("transaction")
        if not transactions and root.tag == "transaction":
            transactions = [root]

        requests: List[CharlesRequest] = []
        for idx, tx in enumerate(transactions):
            attrs = tx.attrib
            method = attrs.get("method") or "GET"
            scheme = attrs.get("scheme") or "http"
            host = attrs.get("host") or ""
            port = int(attrs.get("port", 443 if scheme == "https" else 80))
            path = attrs.get("path") or ""
            query = attrs.get("query") or ""

            req_el = tx.find("request")
            res_el = tx.find("response")

            req_headers: Dict[str, str] = {}
            if req_el is not None:
                for h in req_el.findall(".//header"):
                    name = h.attrib.get("name") or h.findtext("name")
                    val = h.attrib.get("value") or h.findtext("value") or h.text
                    if name:
                        req_headers[str(name)] = str(val or "")

            res_headers: Dict[str, str] = {}
            status: int | None = None
            if res_el is not None:
                st_str = res_el.attrib.get("status") or tx.attrib.get("status")
                if st_str:
                    try:
                        status = int(st_str)
                    except (ValueError, TypeError):
                        pass
                for h in res_el.findall(".//header"):
                    name = h.attrib.get("name") or h.findtext("name")
                    val = h.attrib.get("value") or h.findtext("value") or h.text
                    if name:
                        res_headers[str(name)] = str(val or "")

            if status is None:
                st_str = attrs.get("status")
                if st_str and st_str.isdigit():
                    status = int(st_str)

            req_body_text = req_el.findtext("body") if req_el is not None else ""
            res_body_text = res_el.findtext("body") if res_el is not None else ""

            req_obj = CharlesRequest(
                id=idx,
                status_text=attrs.get("status", ""),
                method=method.upper(),
                scheme=scheme,
                host=host,
                port=port,
                path=path,
                query=query,
                response_status=status,
                request_headers=req_headers,
                response_headers=res_headers,
                req_body_bytes=(req_body_text or "").encode("utf-8"),
                res_body_bytes=(res_body_text or "").encode("utf-8"),
                raw_meta=attrs,
            )
            requests.append(req_obj)

        return requests

    def _extract_javaobj_headers(self, http_fields: Any) -> Tuple[Dict[str, str], str]:
        """Extract headers dictionary and first HTTP line from javaobj HttpFields object."""
        headers: Dict[str, str] = {}
        first_line_str = ""

        if not http_fields:
            return headers, first_line_str

        annotations = getattr(http_fields, "annotations", []) or []
        for ann in annotations:
            if isinstance(ann, str) and ("HTTP/" in ann or any(m in ann for m in ["GET ", "POST ", "PUT ", "DELETE ", "HEAD "])):
                first_line_str = ann
                break
            elif isinstance(ann, list):
                for item in ann:
                    if isinstance(item, str) and ("HTTP/" in item or any(m in item for m in ["GET ", "POST ", "PUT ", "DELETE ", "HEAD "])):
                        first_line_str = item
                        break

        field_names = getattr(http_fields, "fieldNames", []) or []
        field_values = getattr(http_fields, "fieldValues", []) or []

        for k, v in zip(field_names, field_values):
            if k is not None and v is not None:
                headers[str(k)] = str(v)

        return headers, first_line_str

    def _collect_javaobj_transactions(
        self, node: Any, current_host: str = "", current_protocol: str = "http", current_port: int = 80
    ) -> List[Tuple[Any, str, str, int]]:
        """Recursively walk Java object tree nodes (Session, Host, Path, Transaction) to collect all transactions."""
        tx_list: List[Tuple[Any, str, str, int]] = []
        if not node:
            return tx_list

        host_name = str(getattr(node, "hostName", "") or current_host)
        protocol = str(getattr(node, "protocol", "") or current_protocol or "http")
        port = getattr(node, "actualPort", None)
        if port == -1 or port == 0 or port is None:
            port = getattr(node, "port", None)
        if port is None or port == -1 or port == 0:
            port = current_port

        cls_name = getattr(getattr(node, "classdesc", None), "name", "")
        if "Transaction" in cls_name or hasattr(node, "requestHeader") or hasattr(node, "responseHeader"):
            tx_list.append((node, host_name, protocol, int(port) if isinstance(port, int) else 80))

        children = getattr(node, "children", None)
        if children and isinstance(children, list):
            for child in children:
                tx_list.extend(self._collect_javaobj_transactions(child, host_name, protocol, int(port) if isinstance(port, int) else 80))

        return tx_list

    def _parse_chls_binary_javaobj(self, data_bytes: bytes) -> List[CharlesRequest]:
        """Parse Java Object Serialization .chls using javaobj-py3 library."""
        try:
            import javaobj
        except ImportError:
            return []

        try:
            session = javaobj.loads(data_bytes)
        except Exception:
            return []

        raw_txs = self._collect_javaobj_transactions(session)
        if not raw_txs:
            return []

        requests: List[CharlesRequest] = []
        req_id = 1

        for tx, host_name, protocol, port in raw_txs:
            req_hdr_obj = getattr(tx, "requestHeader", None)
            res_hdr_obj = getattr(tx, "responseHeader", None)

            req_headers, req_first_line = self._extract_javaobj_headers(req_hdr_obj)
            res_headers, res_first_line = self._extract_javaobj_headers(res_hdr_obj)

            raw_scheme = getattr(tx, "scheme", None)
            if not req_first_line and not req_headers and not res_first_line and not res_headers and not raw_scheme:
                continue

            method = str(raw_scheme or "GET").upper()
            path = "/"
            query = ""

            if req_first_line:
                parts = req_first_line.split()
                if len(parts) >= 2:
                    m_cand = parts[0].upper()
                    if m_cand in ("GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "CONNECT", "PATCH"):
                        method = m_cand
                    full_path = parts[1]
                    parsed = urlparse(full_path)
                    path = parsed.path or "/"
                    query = parsed.query or ""

            res_status = None
            status_text = ""
            if res_first_line:
                parts = res_first_line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    res_status = int(parts[1])
                    status_text = " ".join(parts[2:]) if len(parts) > 2 else ""

            if res_status is None:
                raw_status = getattr(tx, "status", None)
                if isinstance(raw_status, int) and raw_status > 0:
                    res_status = raw_status

            req_body = getattr(tx, "requestBody", None)
            res_body = getattr(tx, "responseBody", None)

            req_body_bytes = _java_body_to_bytes(req_body)
            res_body_bytes = _java_body_to_bytes(res_body)

            req_mime = req_headers.get("Content-Type") or req_headers.get("content-type")
            res_mime = res_headers.get("Content-Type") or res_headers.get("content-type")

            req_model = CharlesRequest(
                id=req_id,
                method=method,
                scheme=protocol,
                host=host_name or req_headers.get("Host", "unknown"),
                port=int(port) if isinstance(port, int) else 80,
                path=path,
                query=query,
                response_status=res_status,
                status_text=status_text,
                request_headers=req_headers,
                response_headers=res_headers,
                request_mime_type=req_mime,
                response_mime_type=res_mime,
                req_body_bytes=req_body_bytes,
                res_body_bytes=res_body_bytes,
            )
            requests.append(req_model)
            req_id += 1

        return requests

    def _parse_chls_binary(self, data_bytes: bytes) -> List[CharlesRequest]:
        """Parse Charles Session (.chls) Java Object Serialization stream."""
        # 1. Attempt javaobj-py3 native deserialization if available
        javaobj_results = self._parse_chls_binary_javaobj(data_bytes)
        if javaobj_results:
            return javaobj_results

        # 2. Fallback to binary scanner loop
        f = io.BytesIO(data_bytes)
        if data_bytes.startswith(b"\xac\xed"):
            f.seek(4)
        else:
            f.seek(0)

        data_len = len(data_bytes)
        strings: List[Tuple[int, str]] = []

        while f.tell() < data_len - 3:
            pos = f.tell()
            b = f.read(1)
            if not b:
                break
            t = b[0]
            if t in (0x74, 0x7C):
                try:
                    l = struct.unpack(">H", f.read(2))[0] if t == 0x74 else struct.unpack(">Q", f.read(8))[0]
                    if 0 < l < 100000 and f.tell() + l <= data_len:
                        s_bytes = f.read(l)
                        s = s_bytes.decode("utf-8", errors="replace")
                        strings.append((pos, s))
                except Exception:
                    pass

        def clean_target(target: str) -> str:
            # Cut off at Java serialization tags or binary noise if appended
            for tag in ["sq~", "uq~", "xsq~", "sq\x00", "uq\x00", "xsq\x00"]:
                if tag in target:
                    target = target.split(tag)[0]
            clean_chars = []
            for ch in target:
                if 32 <= ord(ch) <= 126:
                    clean_chars.append(ch)
                else:
                    break
            return "".join(clean_chars).strip()

        def is_valid_clean_str(s: str) -> bool:
            if not s or not s.isprintable():
                return False
            if any(tag in s for tag in ["sq~", "uq~", "xsq~", "\ufffd"]):
                return False
            return True

        tx_indices: List[Tuple[int, str, str]] = []

        for idx, (pos, s) in enumerate(strings):
            s_clean = s.strip()
            m = REQ_LINE_PATTERN.match(s_clean)
            if m:
                method = m.group(1).upper()
                target = clean_target(m.group(2))
                if target and not target.startswith(("1.1", "1.0", "2.0", "http/1.")):
                    tx_indices.append((idx, method, target))
            elif s_clean.startswith(("http://", "https://")):
                target = clean_target(s_clean)
                if target:
                    tx_indices.append((idx, "GET", target))
            elif s_clean.startswith("/") and not s_clean.startswith(("//", "/1.1", "/1.0", "/2.0", "/http")):
                if "?" in s_clean or len(s_clean) > 3:
                    target = clean_target(s_clean)
                    if target and is_valid_clean_str(target):
                        tx_indices.append((idx, "GET", target))

        unique_txs: List[Tuple[int, str, str]] = []
        seen = set()
        for idx, method, target in tx_indices:
            key = (method, target)
            if key not in seen:
                seen.add(key)
                unique_txs.append((idx, method, target))

        requests: List[CharlesRequest] = []
        for req_id, (s_idx, method, target) in enumerate(unique_txs):
            scheme = "http"
            host = ""
            port = 80
            path = ""
            query = ""

            if target.startswith("http://") or target.startswith("https://"):
                pu = urlparse(target)
                scheme = pu.scheme or "http"
                host = pu.hostname or ""
                port = pu.port or (443 if scheme == "https" else 80)
                path = pu.path or ""
                query = pu.query or ""
            elif method == "CONNECT":
                parts = target.split(":")
                host = parts[0]
                port = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 443
                scheme = "https"
            else:
                if "?" in target:
                    path, query = target.split("?", 1)
                else:
                    path = target
                    query = ""

            if not host:
                window_strs = [st[1] for st in strings[max(0, s_idx - 15) : min(len(strings), s_idx + 25)]]
                for ws in window_strs:
                    ws_clean = clean_target(ws)
                    if is_valid_clean_str(ws_clean) and "." in ws_clean and "/" not in ws_clean and not ws_clean.startswith(("{", "[")):
                        if any(tld in ws_clean for tld in [".com", ".net", ".org", ".tv", ".googleapis", ".co", ".io"]):
                            host = ws_clean.strip()
                            break

            if not host:
                host = "localhost"

            status = 200
            window_strs = [st[1] for st in strings[max(0, s_idx - 5) : min(len(strings), s_idx + 25)]]
            for ws in window_strs:
                if ws in ("200", "201", "204", "301", "302", "304", "400", "401", "403", "404", "500", "502", "503"):
                    status = int(ws)
                    break

            req_headers: Dict[str, str] = {}
            for ws in window_strs:
                ws_clean = clean_target(ws)
                if is_valid_clean_str(ws_clean) and ":" in ws_clean and not ws_clean.startswith("http") and not ws_clean.startswith("{") and len(ws_clean) < 200:
                    k, _, v = ws_clean.partition(":")
                    k_clean = k.strip()
                    v_clean = v.strip()
                    if k_clean and v_clean and not k_clean.isdigit() and "DigiCert" not in k_clean:
                        req_headers[k_clean] = v_clean

            req_obj = CharlesRequest(
                id=req_id,
                method=method,
                scheme=scheme,
                host=host,
                port=port,
                path=path,
                query=query,
                response_status=status,
                request_headers=req_headers,
                raw_meta={"binary_pos": strings[s_idx][0]},
            )
            requests.append(req_obj)

        return requests

    def _read_json_from_zip(self, z: zipfile.ZipFile, filename: str) -> Dict[str, Any]:
        try:
            content = z.read(filename).decode("utf-8")
            return json.loads(content)
        except Exception:
            return {}

    def _extract_headers(self, header_data: Any) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if not header_data:
            return headers
        if isinstance(header_data, list):
            for item in header_data:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    headers[str(item["name"])] = str(item["value"])
        elif isinstance(header_data, dict):
            header_list = header_data.get("headers", [])
            if isinstance(header_list, list):
                for item in header_list:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        headers[str(item["name"])] = str(item["value"])
            else:
                headers = {str(k): str(v) for k, v in header_data.items() if not str(k).startswith("_")}
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
