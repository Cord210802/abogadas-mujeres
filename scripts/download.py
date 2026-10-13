#!/usr/bin/env python3
"""
Descarga idempotente y reanudable de las fuentes crudas.

Garantias (segun el encargo):
  - Idempotente: si el archivo final ya existe y su sha256 coincide con el
    manifest, no se vuelve a bajar. Para los "acumulado" (cuyo hash cambia con
    cada refresh del portal) se compara el Content-Length via HEAD.
  - Reanudable: descarga por streaming a un archivo .part; si el .part existe y el
    servidor acepta Range, se reanuda desde donde quedo. Nunca se carga el
    contenido a memoria.
  - Manifest: cada descarga exitosa escribe una fila en logs/manifest.csv con
    url, filename, sha256, size_bytes, timestamp_utc, period, group, source_page.
  - Fallos ruidosos: status != 200/206 -> excepcion. Archivo truncado
    (bytes recibidos != Content-Length) -> excepcion. Nunca se continua en
    silencio ni se renombra un .part incompleto.

Uso:
  python scripts/download.py                 # nucleo completo
  python scripts/download.py --list          # solo listar que haria
  python scripts/download.py --only carpetasFGJ_acumulado
  python scripts/download.py --optional pgj_carpetas_archivo
  python scripts/download.py --force --only resageburb_09csv20
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import Source, core_sources, all_known, OPTIONAL, BLOCKED  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOGS = ROOT / "logs"
MANIFEST = LOGS / "manifest.csv"
RUNLOG = LOGS / "download_runs.log"

CHUNK = 1 << 20  # 1 MiB
TIMEOUT = (30, 120)  # (connect, read) segundos
USER_AGENT = "caso-itam-pipeline/1.0 (+adquisicion de datos; contacto: jupacord2108@gmail.com)"

MANIFEST_COLS = [
    "timestamp_utc", "key", "group", "filename", "url", "sha256",
    "size_bytes", "expected_bytes", "period", "http_status", "source_page", "notes",
]


class DownloadError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# utilidades
# --------------------------------------------------------------------------- #
def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"{utcnow()}  {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with RUNLOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def last_manifest_row(key: str) -> Optional[dict]:
    rows = [r for r in read_manifest() if r.get("key") == key]
    return rows[-1] if rows else None


def append_manifest(row: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with MANIFEST.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in MANIFEST_COLS})


def head(session: requests.Session, url: str) -> requests.Response:
    r = session.head(url, allow_redirects=True, timeout=TIMEOUT)
    return r


# --------------------------------------------------------------------------- #
# decision de si hay que descargar
# --------------------------------------------------------------------------- #
def needs_download(src: Source, session: requests.Session, force: bool) -> tuple[bool, str]:
    dest = RAW / src.group / src.filename
    if force:
        return True, "forzado (--force)"
    if not dest.exists():
        return True, "no existe en disco"

    prev = last_manifest_row(src.key)
    if src.checksum_check:
        if prev and prev.get("sha256"):
            actual = sha256_file(dest)
            if actual == prev["sha256"]:
                return False, f"ya existe, sha256 coincide ({actual[:12]}...)"
            return True, "existe pero sha256 NO coincide con el manifest"
        return True, "existe pero no hay sha256 previo en el manifest"
    else:
        # acumulados: el hash cambia con cada refresh -> comparar tamano via HEAD
        try:
            h = head(session, src.url)
            remote_len = int(h.headers.get("Content-Length", "0"))
        except Exception as exc:  # noqa: BLE001
            return False, f"existe; no se pudo hacer HEAD ({exc}); se conserva lo local"
        local_len = dest.stat().st_size
        if remote_len and remote_len == local_len:
            return False, f"ya existe, tamano coincide con el remoto ({local_len} B)"
        return True, f"existe ({local_len} B) pero el remoto reporta {remote_len} B"


# --------------------------------------------------------------------------- #
# descarga
# --------------------------------------------------------------------------- #
def stream_download(src: Source, session: requests.Session) -> Path:
    dest = RAW / src.group / src.filename
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)

    resume_from = part.stat().st_size if part.exists() else 0
    headers = {}
    mode = "wb"
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
        mode = "ab"
        log(f"  .part previo de {resume_from} B -> intento reanudar con Range")

    with session.get(src.url, stream=True, timeout=TIMEOUT, headers=headers) as r:
        status = r.status_code
        if resume_from and status == 200:
            # el servidor ignoro el Range: empezar de cero
            log("  el servidor ignoro Range (200); se descarga desde cero")
            resume_from = 0
            mode = "wb"
        elif resume_from and status == 206:
            log("  reanudando (206 Partial Content)")
        elif status != 200:
            raise DownloadError(f"{src.key}: HTTP {status} en GET {src.url}")

        total = r.headers.get("Content-Length")
        expected_total = None
        if total is not None:
            expected_total = int(total) + (resume_from if status == 206 else 0)

        written = resume_from
        t0 = time.time()
        last_report = t0
        with open(part, mode) as fh:
            for chunk in r.iter_content(chunk_size=CHUNK):
                if not chunk:
                    continue
                fh.write(chunk)
                written += len(chunk)
                now = time.time()
                if now - last_report > 5:
                    mb = written / 1e6
                    rate = (written - resume_from) / 1e6 / max(now - t0, 1e-6)
                    tail = f" / {expected_total/1e6:.1f} MB" if expected_total else ""
                    log(f"  {src.key}: {mb:.1f} MB{tail}  ({rate:.1f} MB/s)")
                    last_report = now

    if expected_total is not None and written != expected_total:
        raise DownloadError(
            f"{src.key}: archivo truncado. Recibidos {written} B, esperados {expected_total} B. "
            f"Se conserva {part.name} para reanudar."
        )

    os.replace(part, dest)  # rename atomico
    return dest


def process(src: Source, session: requests.Session, force: bool, dry_run: bool) -> str:
    need, why = needs_download(src, session, force)
    if not need:
        log(f"SKIP  {src.key}: {why}")
        return "skip"
    if dry_run:
        log(f"PLAN  {src.key}: {why} -> descargaria {src.url}")
        return "plan"

    log(f"GET   {src.key}: {why}")
    dest = stream_download(src, session)
    size = dest.stat().st_size
    sha = sha256_file(dest)

    if src.expected_bytes and abs(size - src.expected_bytes) / src.expected_bytes > 0.5:
        log(f"  AVISO: {src.key} pesa {size} B; esperado ~{src.expected_bytes} B (diferencia >50%)")

    append_manifest({
        "timestamp_utc": utcnow(),
        "key": src.key,
        "group": src.group,
        "filename": src.filename,
        "url": src.url,
        "sha256": sha,
        "size_bytes": size,
        "expected_bytes": src.expected_bytes or "",
        "period": src.period,
        "http_status": "200",
        "source_page": src.source_page,
        "notes": src.notes,
    })
    log(f"OK    {src.key}: {size} B  sha256={sha}")
    return "downloaded"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="listar fuentes y salir")
    ap.add_argument("--dry-run", action="store_true", help="mostrar plan sin descargar")
    ap.add_argument("--force", action="store_true", help="re-descargar aunque ya exista")
    ap.add_argument("--only", action="append", default=[], metavar="KEY",
                    help="descargar solo esta(s) key(s) (repetible)")
    ap.add_argument("--optional", action="append", default=[], metavar="KEY",
                    help="incluir esta fuente OPCIONAL (repetible)")
    args = ap.parse_args()

    catalog = {s.key: s for s in all_known()}

    if args.list:
        print("== NUCLEO (se descarga por defecto) ==")
        for s in core_sources():
            print(f"  {s.key:38s} {s.group:14s} {s.kind:8s} {s.period}")
        print("\n== OPCIONAL (--optional KEY) ==")
        for s in OPTIONAL:
            print(f"  {s.key:38s} {s.group:14s} {s.kind:8s} {s.period}")
        print("\n== BLOQUEADO (sin URL verificable) ==")
        for k, v in BLOCKED.items():
            print(f"  {k:38s} {v['descripcion']}")
        return 0

    if args.only:
        unknown = [k for k in args.only if k not in catalog]
        if unknown:
            raise SystemExit(f"key(s) desconocida(s): {unknown}. Usa --list.")
        selected = [catalog[k] for k in args.only]
    else:
        selected = core_sources()
        for k in args.optional:
            if k not in catalog:
                raise SystemExit(f"key opcional desconocida: {k}. Usa --list.")
            selected.append(catalog[k])

    log(f"=== corrida de descarga: {len(selected)} fuente(s); force={args.force} dry_run={args.dry_run}")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    summary: dict[str, list[str]] = {"downloaded": [], "skip": [], "plan": [], "error": []}
    for src in selected:
        try:
            res = process(src, session, args.force, args.dry_run)
            summary[res].append(src.key)
        except Exception as exc:  # noqa: BLE001
            summary["error"].append(src.key)
            log(f"ERROR {src.key}: {exc}")
            raise  # fallo ruidoso: abortar la corrida

    log(f"=== resumen: {', '.join(f'{k}={len(v)}' for k, v in summary.items() if v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
