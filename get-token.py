#!/usr/bin/env python3
"""
Minimal auth token fetcher for Minerva DPN.

No external dependencies required - uses only Python standard library.

Usage:
    python get-token.py
    python get-token.py --server https://minerva-archive.org
"""

import http.server
import argparse
import threading
import urllib.parse
import sys
import webbrowser
from pathlib import Path

# Token file is saved next to this script
SCRIPT_DIR = Path(__file__).parent
TOKEN_FILE = SCRIPT_DIR / ".minerva-dpn" / "token"


def save_token(token: str):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    print(f"\n[green]Token saved to: {TOKEN_FILE}[/green]")


def print_token(token: str):
    print("\n" + "=" * 60)
    print("YOUR TOKEN:")
    print("=" * 60)
    print(token)
    print("=" * 60)
    print(f"\nAlso saved to: {TOKEN_FILE}")


def get_token(server_url: str, save: bool = True) -> str:
    token = None
    event = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal token
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "token" in params:
                token = params["token"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Logged in! You can close this tab.</h1>")
                event.set()
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 19283), Handler)
    srv.timeout = 120

    url = f"{server_url}/auth/discord/login?worker_callback=http://127.0.0.1:19283/"

    print("\n" + "=" * 60)
    print("Minerva DPN - Token Fetcher")
    print("=" * 60)
    print("\nOpening browser for Discord login...")
    print(f"If browser doesn't open, visit:\n{url}\n")
    print("Waiting for callback...")
    sys.stdout.flush()

    webbrowser.open(url)

    while not event.is_set():
        srv.handle_request()
    srv.server_close()

    if not token:
        raise RuntimeError("Login failed - no token received")

    if save:
        save_token(token)
    else:
        print_token(token)

    return token


def main():
    parser = argparse.ArgumentParser(description="Fetch Minerva DPN auth token")
    parser.add_argument(
        "--server",
        default="https://minerva-archive.org",
        help="Minerva server URL (default: https://minerva-archive.org)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print token instead of saving to file"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show existing token from file"
    )

    args = parser.parse_args()

    if args.show:
        if TOKEN_FILE.exists():
            token = TOKEN_FILE.read_text().strip()
            print_token(token)
        else:
            print(f"[red]No token found at: {TOKEN_FILE}")
            print("Run: python get-token.py")
        return

    get_token(args.server, save=not args.no_save)


if __name__ == "__main__":
    main()
