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


def kind(url, content_type="", body=b""):
    path = urlsplit(url).path.lower()
    ct = content_type.lower().split(";")[0].strip()
    if path.endswith(".m3u8") or "mpegurl" in ct:
        text = body.decode("utf-8", "ignore") if isinstance(body, bytes) else body
        if "#EXT-X-STREAM-INF" in text or "#EXT-X-I-FRAME-STREAM-INF" in text:
            return "HLS master"
        if "#EXTINF:" in text or "#EXT-X-TARGETDURATION:" in text:
            return "HLS media"
        return "HLS"
    if path.endswith(".mpd") or ct == "application/dash+xml":
        return "DASH"
    if MEDIA_EXT.search(url) or ct in MEDIA_TYPES:
        return "VIDEO"
    return None


def yt_command(url, referer=None, output=None, cookies_browser=None, list_formats=False):
    cmd = ["yt-dlp", "--no-playlist", "--quiet", "--progress"]
    if list_formats:
        cmd.append("--list-formats")
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
                    if detected == "HLS":
                        try:
                            detected = kind(u, ct, response.body())
                        except Exception:
                            pass
                    if detected and u not in candidates:
                        candidates[u] = (detected, response.request.headers.get("referer", args.url))
                        print(f"  [{len(candidates)}] {detected} from {urlsplit(u).hostname or 'unknown host'}", flush=True)
                except Exception:
                    pass

            context.on("response", inspect)
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                print(f"Navigation warning: {type(exc).__name__}")
            print(f"Listening for up to {args.timeout}s. Play or change quality, then close the browser window to finish.", flush=True)
            for _ in range(max(1, args.timeout)):
                if not browser.is_connected() or page.is_closed():
                    break
                try:
                    page.wait_for_timeout(1000)
                except Exception:
                    if not browser.is_connected() or page.is_closed():
                        break
                    raise
            if browser.is_connected():
                browser.close()
    except Exception as exc:
        print(f"Browser error: {type(exc).__name__}", file=sys.stderr)
        print("For Chromium install: python -m playwright install chromium", file=sys.stderr)
        return 2

    if not candidates:
        print("No supported media URLs detected. Check if video played, or if it uses DRM.")
        return 1
    priority = {"HLS master": 0, "HLS": 1, "HLS media": 1, "DASH": 2, "VIDEO": 3}
    entries = sorted(candidates.items(), key=lambda item: priority[item[1][0]])
    print("\nDiscovered media:")
    for i, (url, (media_kind, _)) in enumerate(entries, 1):
        print(f"  {i}. [{media_kind}] {urlsplit(url).hostname or 'unknown host'}")
    while True:
        choice = input(f"Select 1-{len(entries)} (Enter=1, q=quit): ").strip().lower()
        if choice == "q":
            return 0
        if not choice:
            choice = "1"
        if choice.isdigit() and 1 <= int(choice) <= len(entries):
            break
        print("Invalid selection.")
    selected_url, (media_kind, referer) = entries[int(choice)-1]
    print("Checking available formats with yt-dlp...", flush=True)
    cmd = yt_command(selected_url, referer=referer or args.url, cookies_browser=args.cookies_browser, list_formats=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("yt-dlp could not verify this media source.", file=sys.stderr)
        return result.returncode
    if media_kind == "HLS media":
        print("This is a media playlist; higher qualities may exist but cannot be inferred safely.")
    print("Downloading with yt-dlp...", flush=True)
    cmd = yt_command(selected_url, referer=referer or args.url, output=args.output, cookies_browser=args.cookies_browser)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
