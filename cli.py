"""
Command Line Interface for Charles Proxy Analyzer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .analyzer import CharlesAnalyzer
    from .exporter import CharlesExporter
except ImportError:
    from analyzer import CharlesAnalyzer
    from exporter import CharlesExporter


def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"


def print_terminal_summary(analyzer: CharlesAnalyzer):
    """Print clean formatted summary report in terminal with colors if TTY."""
    s = analyzer.summary()
    use_color = sys.stdout.isatty()

    CYAN = "\033[36m" if use_color else ""
    GREEN = "\033[32m" if use_color else ""
    YELLOW = "\033[33m" if use_color else ""
    RED = "\033[31m" if use_color else ""
    BOLD = "\033[1m" if use_color else ""
    RESET = "\033[0m" if use_color else ""

    p = s.get("percentiles_ms", {})

    print("\n" + "=" * 70)
    print(f" {BOLD}{CYAN}🚀 CHARLES PROXY SESSION SUMMARY REPORT{RESET}")
    print("=" * 70)
    print(f" Total Requests         : {BOLD}{s['total_requests']}{RESET}")
    print(f" Successful (2xx/3xx)   : {GREEN}{s['successful_requests']}{RESET}")
    print(f" Failed / Errors (4xx+) : {RED if s['failed_requests'] > 0 else RESET}{s['failed_requests']}{RESET}")
    print(f" Total Bandwidth        : {BOLD}{format_bytes(s['total_bytes'])}{RESET} (Sent: {format_bytes(s['total_bytes_sent'])}, Received: {format_bytes(s['total_bytes_received'])})")
    print(f" Avg Response Time      : {BOLD}{s['avg_duration_ms']} ms{RESET} (Min: {s['min_duration_ms']} ms, Max: {s['max_duration_ms']} ms)")
    if p:
        print(f" Latency Percentiles    : p50: {p.get('p50', 0)} ms | p90: {p.get('p90', 0)} ms | p95: {p.get('p95', 0)} ms | p99: {p.get('p99', 0)} ms")

    print("\n" + "-" * 70)
    print(f" {BOLD}📊 HTTP STATUS BREAKDOWN{RESET}")
    print("-" * 70)
    for code, count in sorted(s['status_codes'].items(), key=lambda x: str(x[0])):
        c_str = str(code)
        color = GREEN if c_str.startswith("2") else (YELLOW if c_str.startswith("3") else RED)
        print(f"  Status {color}{code:<10}{RESET} : {count:>4} requests")

    print("\n" + "-" * 70)
    print(f" {BOLD}🌐 TOP HOSTS / DOMAINS{RESET}")
    print("-" * 70)
    for host, count in list(s['hosts'].items())[:10]:
        print(f"  {host:<45} : {count:>4} requests")

    print("\n" + "-" * 70)
    print(f" {BOLD}⚡ TOP ENDPOINTS{RESET}")
    print("-" * 70)
    for ep in s['top_endpoints'][:8]:
        err_str = f" {RED}({ep['errors']} errors){RESET}" if ep['errors'] > 0 else ""
        print(f"  {ep['endpoint']:<45} : {ep['count']:>3} reqs | avg {ep['avg_duration_ms']:>7.2f} ms{err_str}")

    errors = analyzer.get_errors()
    if errors:
        print("\n" + "-" * 70)
        print(f" {RED}{BOLD}⚠️  FAILED / ERROR REQUESTS ({len(errors)}){RESET}")
        print("-" * 70)
        for r in errors[:10]:
            print(f"  [#{r.id}] Status {RED}{r.response_status or 'ERR'}{RESET} | {r.method} {r.url}")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Charles Proxy session files (.chlz, .chls) and HTTP Archive files (.har)"
    )
    parser.add_argument("--web", action="store_true", help="Launch interactive web application server")
    parser.add_argument("--port", type=int, default=8000, help="Port for web server (default: 8000)")
    parser.add_argument(
        "-f", "--file",
        default=None,
        help="Path to session file (.chlz, .chls, .har). Defaults to example_1.chlz"
    )
    parser.add_argument("--summary", action="store_true", help="Print summary statistics")
    parser.add_argument("--json-summary", action="store_true", help="Print summary statistics in JSON format")
    parser.add_argument("--host", help="Filter by host/domain substring")
    parser.add_argument("--status", help="Filter by status code (e.g. 200, 400, 4xx, 5xx)")
    parser.add_argument("--method", help="Filter by HTTP method (GET, POST, etc.)")
    parser.add_argument("--path", help="Filter by path substring")
    parser.add_argument("--query-param", help="Filter by query parameter substring")
    parser.add_argument("--errors-only", action="store_true", help="Show only failed/error requests")
    parser.add_argument("--search", help="Search text across URL, headers, and body")
    parser.add_argument("--sort-by", choices=["duration", "size", "status", "id", "host", "path"], help="Sort filtered requests")
    parser.add_argument("--reverse", action="store_true", help="Reverse sort direction")
    parser.add_argument("--inspect-id", type=int, help="Inspect detailed request and response payload for a specific request ID")
    parser.add_argument("--export-json", help="Path to export results to JSON file")
    parser.add_argument("--export-csv", help="Path to export results to CSV file")
    parser.add_argument("--export-html", help="Path to export interactive HTML report")
    parser.add_argument("--export-payloads", help="Directory to dump raw request/response payloads")

    args = parser.parse_args()

    if args.web:
        try:
            from .server import start_server
        except ImportError:
            from server import start_server
        start_server(port=args.port, open_browser=True)
        return

    file_path = None
    if args.file:
        candidate = Path(args.file)
        if candidate.exists():
            file_path = candidate

    if not file_path:
        # Fallback search for default example file across cwd and package location
        candidates = [
            Path("example_1.chlz"),
            Path(__file__).parent / "example_1.chlz",
            Path("charles_analizer/example_1.chlz"),
            Path(__file__).parent / "charles_analizer" / "example_1.chlz",
        ]
        for c in candidates:
            if c.exists():
                file_path = c
                break

    if not file_path or not file_path.exists():
        target_name = args.file or "example_1.chlz"
        print(f"Error: File not found at '{target_name}'", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Charles session file: {file_path}")
    analyzer = CharlesAnalyzer.from_file(file_path)

    # Filtering logic
    filtered_requests = analyzer.requests

    if args.host or args.status or args.method or args.path or args.query_param or args.errors_only or args.sort_by:
        filtered_requests = analyzer.filter(
            host=args.host,
            status=args.status,
            method=args.method,
            path=args.path,
            query_param=args.query_param,
            errors_only=args.errors_only,
            sort_by=args.sort_by,
            reverse=args.reverse,
        )
        print(f"Filtered {len(filtered_requests)} / {len(analyzer.requests)} requests.")

    if args.search:
        filtered_requests = analyzer.search(args.search)
        print(f"Found {len(filtered_requests)} requests matching search query '{args.search}'.")

    # If inspect ID requested
    if args.inspect_id is not None:
        req = analyzer.get_request_by_id(args.inspect_id)
        if not req:
            print(f"Request ID #{args.inspect_id} not found.")
        else:
            print("\n" + "=" * 70)
            print(f" INSPECTING REQUEST #{req.id}")
            print("=" * 70)
            print(f" URL            : {req.url}")
            print(f" Status         : {req.response_status} ({req.status_text})")
            print(f" Duration       : {req.duration_ms} ms (Latency: {req.latency_ms} ms)")
            print(f" Total Bytes    : {req.total_bytes} ({req.formatted_size})")
            print("\n Request Headers:")
            print(json.dumps(req.request_headers, indent=2))
            req_body = req.get_req_json() or req.get_req_body_text()
            if req_body:
                print("\n Request Body:")
                print(json.dumps(req_body, indent=2) if isinstance(req_body, (dict, list)) else req_body)
            print("\n Response Headers:")
            print(json.dumps(req.response_headers, indent=2))
            res_body = req.get_res_json() or req.get_res_body_text()
            if res_body:
                print("\n Response Body:")
                print(json.dumps(res_body, indent=2) if isinstance(res_body, (dict, list)) else res_body[:1000] + ("..." if len(str(res_body)) > 1000 else ""))
            print("=" * 70 + "\n")
        return

    if args.json_summary:
        s = CharlesAnalyzer(filtered_requests).summary()
        print(json.dumps(s, indent=2, ensure_ascii=False))
        return

    # Default action if no specific output flags provided or if --summary
    if args.summary or (not args.export_json and not args.export_csv and not args.export_html and not args.export_payloads):
        print_terminal_summary(CharlesAnalyzer(filtered_requests))

    # Exports
    if args.export_json:
        out = CharlesExporter.to_json(filtered_requests, args.export_json)
        print(f"✅ Exported JSON to: {out}")

    if args.export_csv:
        out = CharlesExporter.to_csv(filtered_requests, args.export_csv)
        print(f"✅ Exported CSV to: {out}")

    if args.export_html:
        s = analyzer.summary()
        out = CharlesExporter.to_html_report(s, filtered_requests, args.export_html)
        print(f"✅ Exported Interactive HTML Report to: {out}")

    if args.export_payloads:
        out = CharlesExporter.export_payloads(filtered_requests, args.export_payloads)
        print(f"✅ Exported Raw Payloads to directory: {out}")


if __name__ == "__main__":
    main()

