"""Local web server for searching, previewing, and copying files."""

from __future__ import annotations

import ctypes
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import heapq
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import string
import sys
import threading
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
import zipfile

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PRESETS_FILE = BASE_DIR / "presets.json"
HOST = "127.0.0.1"
PORT = 8765
MAX_SCAN_RESULTS = 2000
MAX_TEXT_PREVIEW_BYTES = 200_000
DEFAULT_SOURCE = str(Path.home() / "Downloads")
DEFAULT_DEST = str(BASE_DIR.parent)

DEFAULT_PRESETS = [
    {
        "id": "preset-notulensi",
        "name": "File Notulensi (Downloads -> tes5)",
        "source_dir": DEFAULT_SOURCE,
        "dest_dir": DEFAULT_DEST,
        "keywords": "Notulensi",
        "extensions": "",
        "date_field": "either",
        "date_mode": "none",
        "specific_dates": "",
        "date_from": "",
        "date_to": "",
        "recursive": True,
        "conflict_policy": "skip",
    },
    {
        "id": "preset-nov-17-25",
        "name": "Download 17 & 25 Nov 2026",
        "source_dir": DEFAULT_SOURCE,
        "dest_dir": DEFAULT_DEST,
        "keywords": "",
        "extensions": "",
        "date_field": "either",
        "date_mode": "specific",
        "specific_dates": "2026-11-17, 2026-11-25",
        "date_from": "",
        "date_to": "",
        "recursive": False,
        "conflict_policy": "rename",
    },
]


def get_file_times(stat_res: os.stat_result) -> tuple[datetime, datetime]:
    """Return local (created, modified) datetimes across Python versions."""
    created_ts = getattr(stat_res, "st_birthtime", stat_res.st_ctime)
    created_dt = datetime.fromtimestamp(created_ts)
    modified_dt = datetime.fromtimestamp(stat_res.st_mtime)
    return created_dt, modified_dt


def list_windows_drives() -> list[str]:
    """Return available drive root paths on Windows, or '/' on POSIX."""
    if os.name != "nt":
        return ["/"]
    drives: list[str] = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for idx, letter in enumerate(string.ascii_uppercase):
        if bitmask & (1 << idx):
            drives.append(f"{letter}:\\")
    return drives


def load_presets() -> list[dict]:
    """Load saved filter presets, seeding the defaults once.

    The file stores {"seeded": true, "presets": [...]}, so deleting every
    preset is remembered and the defaults do not come back. An older bare
    list is migrated; an empty bare list counts as never seeded.
    """
    try:
        data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = None
    except (OSError, json.JSONDecodeError):
        return [dict(p) for p in DEFAULT_PRESETS]

    if isinstance(data, dict) and isinstance(data.get("presets"), list):
        return data["presets"]
    if isinstance(data, list) and data:
        save_presets(data)
        return data

    presets = [dict(p) for p in DEFAULT_PRESETS]
    save_presets(presets)
    return presets


def save_presets(presets: list[dict]) -> None:
    """Persist presets to JSON on disk."""
    PRESETS_FILE.write_text(
        json.dumps({"seeded": True, "presets": presets}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_keywords(raw: str) -> list[str]:
    """Split comma- or newline-separated keywords into lowercase tokens."""
    parts = [p.strip().lower() for p in re.split(r"[,;\n]+", raw or "") if p.strip()]
    return parts


def parse_extensions(raw: str) -> set[str]:
    """Normalize extension filter strings like 'pdf, .docx'."""
    exts: set[str] = set()
    for token in re.split(r"[,;\s]+", raw or ""):
        cleaned = token.strip().lower()
        if not cleaned:
            continue
        if not cleaned.startswith("."):
            cleaned = f".{cleaned}"
        exts.add(cleaned)
    return exts


def parse_specific_dates(raw: str) -> tuple[set[str], list[str]]:
    """Split comma/space-separated input into valid YYYY-MM-DD dates and invalid tokens."""
    dates: set[str] = set()
    invalid: list[str] = []
    for token in re.split(r"[,;\s]+", raw or ""):
        cleaned = token.strip()
        if not cleaned:
            continue
        try:
            datetime.strptime(cleaned, "%Y-%m-%d")
            dates.add(cleaned)
        except ValueError:
            invalid.append(cleaned)
    return dates, invalid


def matches_date_filter(
    created_dt: datetime,
    modified_dt: datetime,
    date_field: str,
    date_mode: str,
    specific_dates: set[str],
    date_from: str,
    date_to: str,
) -> bool:
    """Evaluate whether file timestamps match the requested date criteria."""
    if date_mode == "none":
        return True

    candidates: list[str] = []
    if date_field in ("created", "either"):
        candidates.append(created_dt.strftime("%Y-%m-%d"))
    if date_field in ("modified", "either"):
        candidates.append(modified_dt.strftime("%Y-%m-%d"))

    if not candidates:
        return True

    if date_mode == "specific":
        if not specific_dates:
            return True
        return any(day in specific_dates for day in candidates)

    if date_mode == "range":
        for day in candidates:
            if date_from and day < date_from:
                continue
            if date_to and day > date_to:
                continue
            return True
        return False

    return True


def scan_files(payload: dict) -> dict:
    """Scan source directory and return matching file entries and warnings."""
    source_raw = str(payload.get("source_dir", "")).strip()
    if not source_raw:
        raise ValueError("Folder sumber wajib diisi.")

    source_path = Path(source_raw).expanduser()
    if not source_path.exists() or not source_path.is_dir():
        raise ValueError(f"Folder sumber tidak ditemukan: {source_raw}")

    keywords = parse_keywords(str(payload.get("keywords", "")))
    use_regex = bool(payload.get("use_regex", False))
    regex_pattern = None
    if use_regex and payload.get("keywords", "").strip():
        try:
            regex_pattern = re.compile(str(payload["keywords"]).strip(), re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Pola regex tidak valid: {exc}") from exc

    extensions = parse_extensions(str(payload.get("extensions", "")))
    date_field = str(payload.get("date_field", "either"))
    date_mode = str(payload.get("date_mode", "none"))
    specific_dates, invalid_dates = parse_specific_dates(str(payload.get("specific_dates", "")))
    if date_mode == "specific" and not specific_dates:
        raise ValueError(
            "Mode 'Tanggal Tertentu' dipilih, tetapi tidak ada tanggal valid (format YYYY-MM-DD)."
        )
    date_from = str(payload.get("date_from", "")).strip()
    date_to = str(payload.get("date_to", "")).strip()
    recursive = bool(payload.get("recursive", False))

    # Min-heap of (mtime, seq, entry) holding the newest MAX_SCAN_RESULTS matches.
    newest: list[tuple[float, int, dict]] = []
    warnings: list[str] = []
    if date_mode == "specific" and invalid_dates:
        warnings.append(f"Tanggal tidak valid diabaikan: {', '.join(invalid_dates)}")
    scanned_count = 0
    matched_count = 0

    def walk_dir(directory: Path) -> None:
        nonlocal scanned_count, matched_count
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError as exc:
            warnings.append(f"Tidak dapat mengakses {directory}: {exc}")
            return

        for entry in entries:
            try:
                if entry.is_dir():
                    if recursive:
                        walk_dir(Path(entry.path))
                    continue
                if not entry.is_file():
                    continue

                scanned_count += 1
                name = entry.name
                name_lower = name.lower()

                if extensions and Path(name).suffix.lower() not in extensions:
                    continue

                if regex_pattern is not None:
                    if not regex_pattern.search(name):
                        continue
                elif keywords:
                    if not any(kw in name_lower for kw in keywords):
                        continue

                stat_res = entry.stat()
                created_dt, modified_dt = get_file_times(stat_res)

                if not matches_date_filter(
                    created_dt,
                    modified_dt,
                    date_field,
                    date_mode,
                    specific_dates,
                    date_from,
                    date_to,
                ):
                    continue

                item = {
                        "name": name,
                        "path": entry.path,
                        "extension": Path(name).suffix.lower() or "(tanpa ekstensi)",
                        "size": stat_res.st_size,
                        "created_at": created_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "created_date": created_dt.strftime("%Y-%m-%d"),
                        "modified_at": modified_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "modified_date": modified_dt.strftime("%Y-%m-%d"),
                        "dates_differ": (
                            created_dt.strftime("%Y-%m-%d")
                            != modified_dt.strftime("%Y-%m-%d")
                        ),
                }
                matched_count += 1
                heap_item = (stat_res.st_mtime, matched_count, item)
                if len(newest) < MAX_SCAN_RESULTS:
                    heapq.heappush(newest, heap_item)
                else:
                    heapq.heappushpop(newest, heap_item)
            except OSError as exc:
                warnings.append(f"Gagal membaca {entry.path}: {exc}")

    walk_dir(source_path)
    results = [item for _, _, item in sorted(newest, key=lambda t: (t[0], t[1]), reverse=True)]
    truncated = matched_count > MAX_SCAN_RESULTS
    if truncated:
        warnings.append(
            f"Ditemukan {matched_count} file cocok; hanya {MAX_SCAN_RESULTS} file terbaru "
            "(berdasarkan tanggal diubah) yang ditampilkan. Persempit filter untuk hasil lebih spesifik."
        )
    return {
        "files": results,
        "total_matched": matched_count,
        "total_scanned": scanned_count,
        "truncated": truncated,
        "warnings": warnings,
    }


def resolve_destination_path(dest_dir: Path, filename: str, policy: str) -> tuple[Path | None, str]:
    """Determine final target file path according to conflict policy."""
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate, "ok"

    if policy == "skip":
        return None, "skipped"
    if policy == "overwrite":
        return candidate, "overwritten"

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        renamed = dest_dir / f"{stem} ({counter}){suffix}"
        if not renamed.exists():
            return renamed, "renamed"
        counter += 1


def transfer_files(payload: dict) -> dict:
    """Copy or move selected files to the destination folder."""
    files = payload.get("files", [])
    dest_raw = str(payload.get("dest_dir", "")).strip()
    mode = str(payload.get("mode", "copy")).lower()
    policy = str(payload.get("conflict_policy", "skip")).lower()
    create_dest = bool(payload.get("create_dest", True))

    if not dest_raw:
        raise ValueError("Folder tujuan wajib diisi.")
    if mode not in ("copy", "move"):
        raise ValueError("Mode harus 'copy' atau 'move'.")
    if policy not in ("skip", "overwrite", "rename"):
        raise ValueError("Kebijakan konflik harus 'skip', 'overwrite', atau 'rename'.")
    if not isinstance(files, list) or not files:
        raise ValueError("Pilih minimal 1 file untuk diproses.")

    dest_dir = Path(dest_raw).expanduser()
    if not dest_dir.exists():
        if create_dest:
            dest_dir.mkdir(parents=True, exist_ok=True)
        else:
            raise ValueError(f"Folder tujuan tidak ditemukan: {dest_raw}")
    elif not dest_dir.is_dir():
        raise ValueError(f"Target tujuan bukan folder: {dest_raw}")

    items_log: list[dict] = []
    summary = {"succeeded": 0, "skipped": 0, "failed": 0, "total_bytes": 0}

    for raw_path in files:
        src = Path(str(raw_path))
        if not src.exists() or not src.is_file():
            summary["failed"] += 1
            items_log.append(
                {"source": str(src), "status": "failed", "message": "File sumber tidak ditemukan."}
            )
            continue

        try:
            target, action_note = resolve_destination_path(dest_dir, src.name, policy)
            if target is None:
                summary["skipped"] += 1
                items_log.append(
                    {
                        "source": str(src),
                        "dest": str(dest_dir / src.name),
                        "status": "skipped",
                        "message": "File sudah ada di folder tujuan (dilewati).",
                    }
                )
                continue

            if src.resolve() == target.resolve():
                summary["skipped"] += 1
                items_log.append(
                    {
                        "source": str(src),
                        "dest": str(target),
                        "status": "skipped",
                        "message": "Sumber dan tujuan sama.",
                    }
                )
                continue

            file_size = src.stat().st_size
            if mode == "move":
                shutil.move(str(src), str(target))
            else:
                shutil.copy2(str(src), str(target))

            summary["succeeded"] += 1
            summary["total_bytes"] += file_size
            items_log.append(
                {
                    "source": str(src),
                    "dest": str(target),
                    "status": "succeeded",
                    "note": action_note,
                    "message": (
                        f"Berhasil {'dipindah' if mode == 'move' else 'disalin'}"
                        + (f" ({action_note})" if action_note != "ok" else "")
                    ),
                }
            )
        except OSError as exc:
            summary["failed"] += 1
            items_log.append(
                {"source": str(src), "status": "failed", "message": str(exc)}
            )

    return {"summary": summary, "results": items_log}


def extract_docx_text(file_path: Path) -> str:
    """Extract plain paragraph text from a .docx archive using stdlib only."""
    with zipfile.ZipFile(file_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return "(Dokumen Word tidak memiliki word/document.xml)"
        xml_bytes = zf.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", ns):
        texts = [node.text for node in para.findall(".//w:t", ns) if node.text]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs) if paragraphs else "(Dokumen tidak berisi teks)"


def build_preview(file_path: Path) -> dict:
    """Return metadata and preview payload for text, docx, image, or PDF files."""
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError("File tidak ditemukan.")

    stat_res = file_path.stat()
    created_dt, modified_dt = get_file_times(stat_res)
    ext = file_path.suffix.lower()

    meta = {
        "name": file_path.name,
        "path": str(file_path),
        "size": stat_res.st_size,
        "extension": ext,
        "created_at": created_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "modified_at": modified_dt.strftime("%Y-%m-%d %H:%M:%S"),
    }

    text_exts = {".txt", ".md", ".csv", ".json", ".log", ".xml", ".yaml", ".yml", ".py", ".js", ".html", ".css", ".ps1"}
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

    if ext in text_exts:
        raw = file_path.read_bytes()[:MAX_TEXT_PREVIEW_BYTES]
        text = raw.decode("utf-8", errors="replace")
        truncated = stat_res.st_size > MAX_TEXT_PREVIEW_BYTES
        return {**meta, "kind": "text", "content": text, "truncated": truncated}

    if ext == ".docx":
        try:
            text = extract_docx_text(file_path)
            truncated = len(text) > MAX_TEXT_PREVIEW_BYTES
            return {
                **meta,
                "kind": "text",
                "content": text[:MAX_TEXT_PREVIEW_BYTES],
                "truncated": truncated,
            }
        except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
            return {**meta, "kind": "unsupported", "message": f"Gagal membaca isi DOCX: {exc}"}

    if ext in image_exts:
        url = f"/api/raw?path={urllib.parse.quote(str(file_path))}"
        return {**meta, "kind": "image", "url": url}

    if ext == ".pdf":
        url = f"/api/raw?path={urllib.parse.quote(str(file_path))}"
        return {**meta, "kind": "pdf", "url": url}

    return {
        **meta,
        "kind": "unsupported",
        "message": f"Preview langsung belum tersedia untuk tipe file {ext or 'ini'}.",
    }


def browse_directory(path_str: str) -> dict:
    """List drives or child directories for the folder picker modal."""
    if not path_str:
        drives = list_windows_drives()
        return {
            "current": "",
            "parent": "",
            "folders": [{"name": d, "path": d} for d in drives],
        }

    current = Path(path_str).expanduser()
    if not current.exists() or not current.is_dir():
        raise ValueError(f"Folder tidak ditemukan: {path_str}")

    folders: list[dict] = []
    try:
        with os.scandir(current) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append({"name": entry.name, "path": entry.path})
                except OSError:
                    continue
    except OSError as exc:
        raise PermissionError(f"Akses ditolak: {exc}") from exc

    folders.sort(key=lambda item: item["name"].lower())
    parent_str = "" if current.parent == current else str(current.parent)
    return {
        "current": str(current),
        "parent": parent_str,
        "folders": folders,
    }


class AppHandler(SimpleHTTPRequestHandler):
    """Serve static frontend files and JSON API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:
        # Keep console output concise.
        return

    def send_json(self, status: int, data: dict | list) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def allowed_hosts(self) -> set[str]:
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def request_is_trusted(self, require_json: bool) -> bool:
        """Reject requests coming from other websites open in the browser.

        - Host must be this server (blocks DNS-rebinding).
        - Origin, when sent, must be this server (blocks cross-site POST/DELETE).
        - JSON Content-Type on POST forces a CORS preflight that this server
          never approves, so other sites cannot send a "simple" form request.
        """
        hosts = self.allowed_hosts()
        if self.headers.get("Host", "") not in hosts:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in hosts}:
            return False
        if require_json:
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return False
        return True

    def reject_untrusted(self) -> None:
        self.send_json(
            HTTPStatus.FORBIDDEN,
            {"error": "Permintaan ditolak: hanya boleh dari halaman aplikasi ini."},
        )

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        if not self.request_is_trusted(require_json=False):
            self.reject_untrusted()
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/health":
            self.send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "default_source": DEFAULT_SOURCE,
                    "default_dest": DEFAULT_DEST,
                },
            )
            return

        if parsed.path == "/api/browse":
            target = query.get("path", [""])[0]
            try:
                self.send_json(HTTPStatus.OK, browse_directory(target))
            except (ValueError, PermissionError) as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if parsed.path == "/api/presets":
            self.send_json(HTTPStatus.OK, {"presets": load_presets()})
            return

        if parsed.path == "/api/preview":
            raw_path = query.get("path", [""])[0]
            try:
                self.send_json(HTTPStatus.OK, build_preview(Path(raw_path)))
            except FileNotFoundError as exc:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except OSError as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if parsed.path == "/api/raw":
            raw_path = query.get("path", [""])[0]
            file_path = Path(raw_path)
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "File tidak ditemukan")
                return
            mime, _ = mimetypes.guess_type(str(file_path))
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                self.send_error(HTTPStatus.FORBIDDEN, str(exc))
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        if not self.request_is_trusted(require_json=True):
            self.reject_untrusted()
            return
        parsed = urllib.parse.urlparse(self.path)
        try:
            payload = self.read_json_body()
        except (ValueError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Payload JSON tidak valid."})
            return

        if parsed.path == "/api/scan":
            try:
                self.send_json(HTTPStatus.OK, scan_files(payload))
            except ValueError as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if parsed.path == "/api/transfer":
            try:
                self.send_json(HTTPStatus.OK, transfer_files(payload))
            except ValueError as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if parsed.path == "/api/presets":
            name = str(payload.get("name", "")).strip()
            if not name:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Nama preset wajib diisi."})
                return
            presets = load_presets()
            preset_id = str(payload.get("id") or f"preset-{int(datetime.now().timestamp())}")
            new_preset = {**payload, "id": preset_id, "name": name}
            presets = [p for p in presets if p.get("id") != preset_id]
            presets.insert(0, new_preset)
            save_presets(presets)
            self.send_json(HTTPStatus.OK, {"preset": new_preset, "presets": presets})
            return

        if parsed.path == "/api/open-folder":
            folder_raw = str(payload.get("path", "")).strip()
            folder = Path(folder_raw)
            if not folder.exists() or not folder.is_dir():
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Folder tidak ditemukan."})
                return
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            self.send_json(HTTPStatus.OK, {"ok": True})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint tidak ditemukan."})

    def do_DELETE(self) -> None:
        if not self.request_is_trusted(require_json=False):
            self.reject_untrusted()
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/presets":
            preset_id = query.get("id", [""])[0]
            presets = [p for p in load_presets() if p.get("id") != preset_id]
            save_presets(presets)
            self.send_json(HTTPStatus.OK, {"presets": presets})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint tidak ditemukan."})


def main() -> None:
    args = [arg for arg in sys.argv[1:] if arg != "--no-browser"]
    no_browser = "--no-browser" in sys.argv[1:]
    port = int(args[0]) if args else PORT
    server = ThreadingHTTPServer((HOST, port), AppHandler)
    url = f"http://{HOST}:{port}"
    print(f"File Finder & Copier Web App berjalan di {url}")
    print("Tekan Ctrl+C untuk menghentikan server.")
    if not no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
