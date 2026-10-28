#!/usr/bin/env python3
"""Extrae (carve) los contenedores CAB y firmas de un instalador WiX Burn.

No necesita 7-Zip ni WiX: localiza los CAB por su firma MSCF, valida su
cabecera y los escribe tal cual en disco. La descompresion LZX posterior se
delega a cabextract/7-Zip/dark.exe (ver extract_bundle.sh).

Uso:
    python3 scripts/carve_bundle.py [ruta.exe] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_bundle import (  # noqa: E402
    DEFAULT_EXE,
    find_cabs,
    parse_burn,
    parse_pe,
    sha256,
)


def carve_cabs(data: bytes, out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for cab in find_cabs(data):
        name = f"container_{cab['offset']:08x}.cab"
        target = out / name
        target.write_bytes(data[cab["offset"] : cab["offset"] + cab["size"]])
        cab["carved"] = str(target)
        results.append(cab)
        files = ", ".join(f["name"] for f in cab["folders"][0].get("files", [])[:6])
        print(f"  -> {target}  ({cab['size']:,} bytes, {cab['file_count']} archivo(s))")
        if files:
            print(f"     {files}")
    return results


def carve_authenticode(data: bytes, pe: dict, out: Path) -> str | None:
    off = pe["security_directory"]["offset"]
    size = pe["security_directory"]["size"]
    if not off or not size or off + size > len(data):
        return None
    wc_len = struct.unpack_from("<I", data, off)[0]
    total = min(size, wc_len)
    target = out / "authenticode.p7b"
    target.write_bytes(data[off : off + total])
    print(f"  -> {target}  ({total:,} bytes)")
    return str(target)


def carve_pkcs7_blobs(data: bytes, out: Path) -> list[str]:
    """Localiza estructuras PKCS#7 SignedData sueltas (firmas de contenedor)."""
    oid = bytes.fromhex("06092a864886f70d010702")
    found = []
    pos = 0
    while True:
        idx = data.find(oid, pos)
        if idx < 0:
            break
        start = idx - 12
        if (
            start >= 0
            and data[start + 4 : start + 8] == b"\x00\x02\x02\x00"
            and data[start + 8 : start + 10] == b"\x30\x82"
        ):
            length = struct.unpack_from("<I", data, start)[0]
            der_len = struct.unpack_from(">H", data, start + 10)[0] + 4
            if 64 <= length <= 1 << 20 and start + length <= len(data) and der_len <= length:
                target = out / f"pkcs7_{start:08x}.p7b"
                target.write_bytes(data[start + 8 : start + 8 + der_len])
                found.append(str(target))
                print(f"  -> {target}  ({der_len:,} bytes DER)")
                pos = start + length
                continue
        pos = idx + len(oid)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Carve de contenedores WiX Burn")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_EXE))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    path = Path(args.path)
    out_arg = args.out
    if not path.exists():
        print(f"No existe: {path}", file=sys.stderr)
        return 2

    out = Path(out_arg) if out_arg else path.resolve().parent / "extracted"
    data = path.read_bytes()
    pe = parse_pe(data)
    digest = sha256(path)

    print(f"Archivo: {path}")
    print(f"SHA-256: {digest}")
    print(f"Salida : {out}")
    print("Contenedores:")
    cabs = carve_cabs(data, out)
    print("Firmas:")
    auth = carve_authenticode(data, pe, out)
    blobs = carve_pkcs7_blobs(data, out)

    manifest = {
        "source": str(path),
        "sha256": digest,
        "size": len(data),
        "burn": parse_burn(data, pe),
        "containers": cabs,
        "authenticode": auth,
        "pkcs7_blobs": blobs,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Manifiesto: {manifest_path}")
    print(
        "\nSiguiente paso: descomprimir los .cab con cabextract/7-Zip o, en Windows, "
        "usar 'dark.exe <setup.exe> -x <dir>' del WiX Toolset."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
