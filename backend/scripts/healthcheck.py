#!/usr/bin/env python3
"""
Docker Healthcheck Script for Engineer Cafe Navigator Backend

Usage:
    python scripts/healthcheck.py                    # Basic health check
    python scripts/healthcheck.py --verbose          # Detailed output
    python scripts/healthcheck.py --timeout 10       # Custom timeout
    python scripts/healthcheck.py --check-services   # Check VoiceVox + Kokoro too

Exit codes:
    0 - Healthy
    1 - Unhealthy
"""

import argparse
import sys
import urllib.request
import urllib.error


def check_url(url: str, timeout: int = 5, verbose: bool = False) -> bool:
    """Check if a URL returns a successful response."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                if verbose:
                    print(f"  OK: {url} (status={response.status})")
                return True
            if verbose:
                print(f"  FAIL: {url} (status={response.status})")
            return False
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        if verbose:
            print(f"  FAIL: {url} ({e})")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Backend healthcheck")
    parser.add_argument("--timeout", type=int, default=5, help="Request timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--check-services", action="store_true", help="Also check VoiceVox and Kokoro"
    )
    args = parser.parse_args()

    if args.verbose:
        print("Running healthcheck...")

    # Primary health check
    healthy = check_url("http://localhost:8000/health", timeout=args.timeout, verbose=args.verbose)
    if not healthy:
        if args.verbose:
            print("UNHEALTHY: Backend health endpoint failed")
        return 1

    # Optional service checks
    if args.check_services:
        services = {
            "VoiceVox": "http://localhost:50021/version",
            "Kokoro TTS": "http://localhost:8880/v1/audio/voices",
        }
        for name, url in services.items():
            ok = check_url(url, timeout=args.timeout, verbose=args.verbose)
            if not ok and args.verbose:
                print(f"  WARNING: {name} is not available")

    if args.verbose:
        print("HEALTHY: All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
