#!/usr/bin/env python3
"""
Minerva DPN Worker — single-file volunteer download client.

Requirements:
pip install httpx rich click

Optional (faster downloads):
Install aria2c: https://aria2.github.io/

Usage:
python minerva.py login              # Authenticate with Discord
python minerva.py login-token <token> # Login with a pre-existing token
python minerva.py run                # Start downloading
python minerva.py run -c 5 -b 20     # 5 concurrent, 20 per batch
python minerva.py run --server http://...  # Custom server URL
"""

import asyncio
import http.server
import os
import shutil
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

# ── Config ──────────────────────────────────────────────────────────────────

SERVER_URL = os.environ.get("MINERVA_SERVER", "https://minerva-archive.org")
TOKEN_FILE = Path.home() / ".minerva-dpn" / "token"
TEMP_DIR = Path.home() / ".minerva-dpn" / "tmp"
MAX_RETRIES = 3
RETRY_DELAY = 5

console = Console()

# ── Auth ────────────────────────────────────────────────────────────────────


def save_token(token: str):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)


def load_token() -> str | None:
    if TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text().strip()
        return t if t else None
    return None


def do_login(server_url: str) -> str:
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
    console.print(f"[bold]Opening browser for Discord login...")
    console.print(f"[dim]If it doesn't open: {url}")
    webbrowser.open(url)

    while not event.is_set():
        srv.handle_request()
    srv.server_close()

    if not token:
        raise RuntimeError("Login failed")
    save_token(token)
    console.print("[bold green]Login successful!")
    return token


# ── Download ────────────────────────────────────────────────────────────────

HAS_ARIA2C = shutil.which("aria2c") is not None


async def download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if HAS_ARIA2C:
        proc = await asyncio.create_subprocess_exec(
            "aria2c",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M",
            "--dir", str(dest.parent),
            "--out", dest.name,
            "--auto-file-renaming=false",
            "--allow-overwrite=true",
            "--console-log-level=warn",
            "--retry-wait=3",
            "--max-tries=5",
            "--timeout=60",
            "--connect-timeout=30",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"aria2c exit {proc.returncode}: {stderr.decode()[:200]}")
    else:
        async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    async for chunk in resp.aiter_bytes(100 * 1024 * 1024):
                        f.write(chunk)
    return dest


# ── Upload ──────────────────────────────────────────────────────────────────


async def upload_file(server_url: str, token: str, file_id: int, path: Path) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=600, write=600, pool=30)) as client:
        with open(path, "rb") as f:
            resp = await client.post(
                f"{server_url}/api/upload/{file_id}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (path.name, f, "application/octet-stream")},
            )
            resp.raise_for_status()
            return resp.json()


async def report_job(server_url: str, token: str, file_id: int, status: str,
                    bytes_downloaded: int | None = None, error: str | None = None):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{server_url}/api/jobs/report",
            headers={"Authorization": f"Bearer {token}"},
            json={"file_id": file_id, "status": status,
                  "bytes_downloaded": bytes_downloaded, "error": error},
        )
        resp.raise_for_status()


# ── Main Loop ───────────────────────────────────────────────────────────────


async def process_job(server_url: str, token: str, job: dict, temp_dir: Path, progress: Progress):
    file_id = job["file_id"]
    url = job["url"]
    dest_path = job["dest_path"]
    label = dest_path[:60] if len(dest_path) <= 60 else "..." + dest_path[-57:]
    tid = progress.add_task(f"[cyan]DL {label}", total=None)

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Download
            filename = url.rsplit("/", 1)[-1]
            local_path = temp_dir / filename
            await download_file(url, local_path)
            file_size = local_path.stat().st_size

            # Upload
            progress.update(tid, description=f"[yellow]UL {label}", total=file_size)
            await upload_file(server_url, token, file_id, local_path)
            await report_job(server_url, token, file_id, "completed", bytes_downloaded=file_size)

            progress.update(tid, description=f"[green]OK {label}", completed=file_size)
            local_path.unlink(missing_ok=True)
            return  # Success
        except Exception as e:
            last_err = e
            local_path = temp_dir / url.rsplit("/", 1)[-1]
            local_path.unlink(missing_ok=True)
            if attempt < MAX_RETRIES:
                progress.update(tid, description=f"[yellow]RETRY {attempt}/{MAX_RETRIES} {label}")
                await asyncio.sleep(RETRY_DELAY * attempt)

    # All retries exhausted
    progress.update(tid, description=f"[red]FAIL {label}")
    try:
        await report_job(server_url, token, file_id, "failed", error=str(last_err)[:500])
    except Exception:
        pass
    console.print(f"[red] {dest_path}: {last_err}")


async def worker_loop(server_url: str, token: str, temp_dir: Path, concurrency: int, batch_size: int):
    console.print(f"[bold green]Minerva DPN Worker")
    console.print(f" Server: {server_url}")
    console.print(f" Concurrency: {concurrency}")
    console.print(f" Retries: {MAX_RETRIES}")
    console.print(f" aria2c: {'yes (16 connections)' if HAS_ARIA2C else 'no (using httpx)'}")
    console.print()

    temp_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)

    async def bounded(job, progress):
        async with sem:
            await process_job(server_url, token, job, temp_dir, progress)

    while True:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{server_url}/api/jobs",
                    params={"count": batch_size},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401:
                    console.print("[red]Token expired. Run: python minerva.py login")
                    return
                resp.raise_for_status()
                data = resp.json()

                jobs = data["jobs"]
                if not jobs:
                    console.print("[dim]No jobs available, waiting 30s...")
                    await asyncio.sleep(30)
                    continue

                console.print(f"[bold]Got {len(jobs)} jobs")
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(), DownloadColumn(), TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    await asyncio.gather(*(bounded(j, progress) for j in jobs))

        except httpx.HTTPError as e:
            console.print(f"[red]Server error: {e}. Retrying in 10s...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...")
            return


# ── CLI ─────────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """Minerva DPN Worker — help archive the internet."""
    pass


@cli.command()
@click.option("--server", default=SERVER_URL, help="Manager server URL")
def login(server):
    """Authenticate with Discord (opens browser)."""
    do_login(server)


@cli.command()
@click.argument("token")
def login_token(token):
    """Login with a pre-existing token.

    Get a token by running 'python minerva.py login' on any machine with
    browser access, then copy the token from the callback URL or from
    ~/.minerva-dpn/token
    """
    save_token(token)
    console.print("[bold green]Token saved!")
    console.print(f"[dim]Stored in: {TOKEN_FILE}")


@cli.command()
@click.option("--server", default=SERVER_URL, help="Manager server URL")
@click.option("-c", "--concurrency", default=3, help="Concurrent downloads")
@click.option("-b", "--batch-size", default=10, help="Files per batch")
@click.option("--temp-dir", default=str(TEMP_DIR), help="Temp download dir")
@click.option("--wait", is_flag=True, help="Wait for token file if not present")
def run(server, concurrency, batch_size, temp_dir, wait):
    """Start downloading and uploading files."""
    token = load_token()
    if not token:
        if wait:
            console.print("[yellow]No token found. Waiting for token file...")
            console.print(f"[dim]Place token at: {TOKEN_FILE}")
            import time
            while not token:
                time.sleep(5)
                token = load_token()
            console.print("[green]Token found! Starting worker...")
        else:
            console.print("[red]Not logged in. Run: python minerva.py login")
            return
    asyncio.run(worker_loop(server, token, Path(temp_dir), concurrency, batch_size))


@cli.command()
def status():
    """Show login status."""
    token = load_token()
    console.print("[green]Logged in" if token else "[red]Not logged in")
    if token:
        console.print(f"[dim]Token file: {TOKEN_FILE}")


if __name__ == "__main__":
    cli()
