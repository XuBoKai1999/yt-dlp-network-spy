#!/usr/bin/env python3
"""Browser-assisted media URL discovery; yt-dlp performs all downloads.

Requires: pip install playwright ; installed Edge or Chromium; yt-dlp on PATH.
Only download media you are authorized to save. Does not bypass DRM.
"""
import argparse
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

MEDIA_EXT = re.compile(r"\.(?:m3u8|mpd|mp4|webm|mov)(?:$|[?#])", re.I)
MEDIA_TYPES = ("application/vnd.apple.mpegurl", "application/x-mpegurl", "application/dash+xml", "video/mp4", "video/webm", "video/quicktime")


def kind(url, content_type=""):
    path = urlsplit(url).path.lower()
    ct = content_type.lower().split(";")[0].strip()
    if path.endswith(".m3u8") or "mpegurl" in ct:
        return "HLS"
    if path.endswith(".mpd") or ct == "application/dash+xml":
        return "DASH"
    if MEDIA_EXT.search(url) or ct in MEDIA_TYPES:
        return "VIDEO"
    return None


def yt_command(url, referer=None, output=None, cookies_browser=None):
    cmd = ["yt-dlp", "--no-playlist"]
    if output:
        cmd += ["-P", output]
    if referer:
        cmd += ["--referer", referer]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd.append(url)
    return cmd


def main():
    ap = argparse.ArgumentParser(description="yt-dlp downloader with browser network sniffing fallback")
    ap.add_argument("url", help="Webpage URL")
    ap.add_argument("--spy", action="store_true", help="Skip direct yt-dlp and open browser immediately")
    ap.add_argument("--browser", choices=["edge", "chrome", "chromium"], default="edge")
    ap.add_argument("-P", "--output", help="Download directory (passed to yt-dlp)")
    ap.add_argument("--timeout", type=int, default=90, help="Maximum browser listening time in seconds (default: 90)")
    ap.add_argument("--cookies-browser", choices=["edge", "chrome", "firefox"], help="Optional: use your own browser cookies for yt-dlp")
    args = ap.parse_args()
    if not shutil.which("yt-dlp"):
        ap.error("yt-dlp not found in PATH")
    if not args.spy:
        print("[1/2] Trying yt-dlp on the webpage first...", flush=True)
        result = subprocess.run(yt_command(args.url, output=args.output, cookies_browser=args.cookies_browser))
        if result.returncode == 0:
            print("Download complete.")
            return 0
        print("Direct download failed. Starting browser network inspection.", flush=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install Playwright: python -m pip install playwright", file=sys.stderr)
        return 2

    candidates = {}
    print("[2/2] Opening browser. Play the video; network requests will be detected.", flush=True)
    try:
        with sync_playwright() as p:
            kwargs = {"headless": False}
            if args.browser in ("edge", "chrome"):
                kwargs["channel"] = "msedge" if args.browser == "edge" else "chrome"
            browser = p.chromium.launch(**kwargs)
            context = browser.new_context()
            page = context.new_page()

            def inspect(response):
                try:
                    u = response.url
                    ct = response.headers.get("content-type", "")
                    detected = kind(u, ct)
                    if detected and u not in candidates:
                        candidates[u] = (detected, response.request.headers.get("referer", args.url))
                        print(f"  [{len(candidates)}] {detected}: {u[:180]}", flush=True)
                except Exception:
                    pass

            context.on("response", inspect)
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                print(f"Navigation warning: {exc}")
            print(f"Listening for up to {args.timeout}s. Play video now...", flush=True)
            # Playwright event loop pumps response events while waiting.
            # Stop shortly after detecting media; otherwise allow time to click Play.
            quiet_ticks = 0
            previous_count = 0
            for _ in range(max(1, args.timeout)):
                page.wait_for_timeout(1000)
                if candidates:
                    quiet_ticks = quiet_ticks + 1 if len(candidates) == previous_count else 0
                    if quiet_ticks >= 5:
                        break
                previous_count = len(candidates)
            browser.close()
    except Exception as exc:
        print(f"Browser error: {exc}", file=sys.stderr)
        print("For Chromium install: python -m playwright install chromium", file=sys.stderr)
        return 2

    if not candidates:
        print("No supported media URLs detected. Check if video played, or if it uses DRM.")
        return 1
    entries = sorted(candidates.items(), key=lambda item: {"HLS": 0, "DASH": 1, "VIDEO": 2}[item[1][0]])
    print("\nDiscovered media:")
    for i, (url, (media_kind, _)) in enumerate(entries, 1):
        print(f"  {i}. [{media_kind}] {url[:160]}")
    while True:
        choice = input(f"Select 1-{len(entries)} (Enter=1, q=quit): ").strip().lower()
        if choice == "q":
            return 0
        if not choice:
            choice = "1"
        if choice.isdigit() and 1 <= int(choice) <= len(entries):
            break
        print("Invalid selection.")
    selected_url, (_, referer) = entries[int(choice)-1]
    print("Downloading with yt-dlp...", flush=True)
    cmd = yt_command(selected_url, referer=referer or args.url, output=args.output, cookies_browser=args.cookies_browser)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
