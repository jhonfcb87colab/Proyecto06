#!/usr/bin/env python3
"""Inspecciona un instalador WiX Burn (p.ej. PBIDesktopSetup_x64.exe).

Solo lectura: calcula hash, parsea PE, cabecera Burn, CABs incrustados y
firma Authenticode. No extrae ni ejecuta nada.

Uso:
    python3 scripts/verify_bundle.py [ruta.exe] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

EXPECTED_SHA256 = "8ffccf627d383dcb6aa0dc8138a536b76af86246f0a730e1df103c1fe7883109"
DEFAULT_EXE = Path(__file__).resolve().parent.parent / "PBIDesktopSetup_x64.exe"

MACHINES = {0x14C: "x86 (PE32)", 0x8664: "x64 (PE32+)"}
SUBSYSTEMS = {1: "native", 2: "GUI", 3: "console"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def parse_pe(data: bytes) -> dict:
    if data[:2] != b"MZ":
        raise ValueError("No es un archivo PE (falta MZ)")
    pe = u32(data, 0x3C)
    if data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("Cabecera PE invalida")
    machine, nsec, timestamp = struct.unpack_from("<HHI", data, pe + 4)
    opt_size = u16(data, pe + 20)
    opt = pe + 24
    magic = u16(data, opt)
    ddoff = opt + (112 if magic == 0x20B else 96)
    sections = []
    sec = opt + opt_size
    for i in range(nsec):
        o = sec + i * 40
        name = data[o : o + 8].rstrip(b"\0").decode("latin1")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        sections.append(
            {
                "name": name,
                "virtual_address": vaddr,
                "virtual_size": vsize,
                "raw_offset": rawptr,
                "raw_size": rawsize,
            }
        )

    def rva_to_off(rva: int) -> int | None:
        for s in sections:
            if s["virtual_address"] <= rva < s["virtual_address"] + max(
                s["virtual_size"], s["raw_size"]
            ):
                delta = rva - s["virtual_address"]
                if delta < s["raw_size"]:
                    return s["raw_offset"] + delta
        return None

    security = {"offset": 0, "size": 0}
    if magic == 0x20B:
        ddoff = opt + 112
    else:
        ddoff = opt + 96
    if ddoff + 8 * 5 + 8 <= opt + opt_size:
        security = {
            "offset": u32(data, ddoff + 8 * 4),
            "size": u32(data, ddoff + 8 * 4 + 4),
        }
    return {
        "machine": hex(machine),
        "machine_name": MACHINES.get(machine, "desconocido"),
        "timestamp": timestamp,
        "subsystem": SUBSYSTEMS.get(u16(data, opt + 68), "desconocido"),
        "sections": sections,
        "security_directory": security,
        "rva_to_off": rva_to_off,
    }


def version_strings(data: bytes) -> dict:
    marker = "VS_VERSION_INFO".encode("utf-16-le")
    idx = data.find(marker)
    if idx < 0:
        return {}
    blob = data[idx : idx + 8192].decode("utf-16-le", "ignore")
    out = {}
    for key in ("ProductName", "FileDescription", "CompanyName", "FileVersion", "ProductVersion"):
        m = re.search(re.escape(key) + r"\x00+([^\x00]{1,120})", blob)
        if m:
            out[key] = m.group(1).strip()
    return out


def parse_cab(data: bytes, offset: int) -> dict | None:
    if data[offset : offset + 4] != b"MSCF" or offset + 36 > len(data):
        return None
    (
        _sig,
        _r1,
        cb_cabinet,
        _r2,
        coff_files,
        _r3,
        ver_minor,
        ver_major,
        n_folders,
        n_files,
        flags,
        _set_id,
        _icab,
    ) = struct.unpack_from("<4sIIIIIBBHHHHH", data, offset)
    if cb_cabinet < 36 or offset + cb_cabinet > len(data):
        return None
    if ver_major not in (1, 3) or n_folders > 64 or n_files > 100000:
        return None

    c = data[offset : offset + cb_cabinet]
    p = 36
    cb_header = cb_folder = cb_data = 0
    if flags & 0x4:
        cb_header, cb_folder, cb_data = struct.unpack_from("<HBB", c, p)
        p += 4 + cb_header
    folders = []
    for _ in range(n_folders):
        coff_start, c_cfdata, type_compress = struct.unpack_from("<IHH", c, p)
        p += 8 + cb_folder
        folders.append(
            {
                "data_offset": coff_start,
                "blocks": c_cfdata,
                "compression": {0: "none", 1: "MSZIP", 2: "Quantum", 3: "LZX"}.get(
                    type_compress & 0xFF, hex(type_compress)
                ),
                "raw_type": hex(type_compress),
            }
        )
    total = 0
    for _ in range(n_files):
        if p + 16 > len(c):
            break
        size, uoff, folder, date, time, attrs = struct.unpack_from("<IIHHHH", c, p)
        p += 16
        end = c.find(b"\0", p)
        if end < 0:
            break
        name = c[p:end].decode("latin1", "replace")
        p = end + 1
        total += size
        folders[0].setdefault("files", []).append(
            {"name": name, "size": size, "offset": uoff, "folder": folder}
        )
    return {
        "offset": offset,
        "size": cb_cabinet,
        "version": f"{ver_major}.{ver_minor}",
        "folders": folders,
        "file_count": n_files,
        "uncompressed_bytes": total,
    }


def find_cabs(data: bytes) -> list[dict]:
    cabs = []
    pos = 0
    while True:
        pos = data.find(b"MSCF", pos)
        if pos < 0:
            break
        cab = parse_cab(data, pos)
        if cab:
            cabs.append(cab)
            pos = cab["offset"] + cab["size"]
        else:
            pos += 4
    return cabs


def parse_burn(data: bytes, pe: dict) -> dict:
    for s in pe["sections"]:
        if s["name"] == ".wixburn":
            off = s["raw_offset"]
            words = [u32(data, off + i) for i in range(0, min(64, s["raw_size"]), 4)]
            return {
                "magic": hex(words[0]) if words else None,
                "version": words[1] if len(words) > 1 else None,
                "stub_size": words[6] if len(words) > 6 else None,
                "container_offset": words[8] if len(words) > 8 else None,
                "container_signature_size": words[9] if len(words) > 9 else None,
                "ux_cab_size": words[12] if len(words) > 12 else None,
                "payload_cab_size": words[13] if len(words) > 13 else None,
                "raw_words": [hex(w) for w in words],
            }
    return {}


def signature_info(data: bytes, pe: dict) -> dict:
    off = pe["security_directory"]["offset"]
    size = pe["security_directory"]["size"]
    if not off or not size or off + size > len(data):
        return {"present": False}
    wc_len, wc_rev, wc_type = struct.unpack_from("<IHH", data, off)
    der = data[off + 8 : off + min(size, wc_len)]
    info = {
        "present": True,
        "offset": off,
        "size": size,
        "certificate_type": {1: "X509", 2: "PKCS#7"}.get(wc_type, hex(wc_type)),
    }
    try:
        out = subprocess.run(
            ["openssl", "pkcs7", "-inform", "DER", "-print_certs", "-noout"],
            input=der,
            capture_output=True,
            timeout=15,
        ).stdout.decode("utf-8", "replace")
        subjects = re.findall(r"subject=(.+)", out)
        if subjects:
            info["subjects"] = subjects
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica un instalador WiX Burn")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_EXE))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"No existe: {path}", file=sys.stderr)
        return 2
    data = path.read_bytes()
    digest = sha256(path)
    pe = parse_pe(data)
    pe_wo = {k: v for k, v in pe.items() if k != "rva_to_off"}
    report = {
        "file": str(path),
        "size": len(data),
        "sha256": digest,
        "sha256_expected": EXPECTED_SHA256,
        "sha256_match": digest == EXPECTED_SHA256,
        "pe": pe_wo,
        "version_info": version_strings(data),
        "burn": parse_burn(data, pe),
        "authenticode": signature_info(data, pe),
        "containers": find_cabs(data),
    }
    cab_total = sum(c["size"] for c in report["containers"])
    report["summary"] = {
        "containers": len(report["containers"]),
        "container_bytes": cab_total,
        "overlay_bytes": len(data) - max(
            s["raw_offset"] + s["raw_size"] for s in pe["sections"]
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    v = report["version_info"]
    print(f"Archivo       : {path}")
    print(f"Tamano        : {len(data):,} bytes")
    print(f"SHA-256       : {digest}")
    print(f"Hash esperado : {'OK' if report['sha256_match'] else 'NO COINCIDE'}")
    print(f"PE            : {pe['machine_name']}, subsistema {pe['subsystem']}")
    if v:
        print(f"Producto      : {v.get('ProductName', '?')} {v.get('ProductVersion', '')}")
        print(f"Descripcion   : {v.get('FileDescription', '?')}")
    b = report["burn"]
    if b:
        print(f"Burn          : magic={b['magic']} version={b['version']} stub={b['stub_size']:,}")
    a = report["authenticode"]
    if a.get("present"):
        print(f"Firma         : {a.get('certificate_type')} ({a['size']:,} bytes)")
        for s in a.get("subjects", [])[:2]:
            print(f"  subject     : {s}")
    print(f"Contenedores  : {len(report['containers'])}")
    for c in report["containers"]:
        comp = ",".join(sorted({f["compression"] for f in c["folders"]}))
        print(
            f"  CAB @ {c['offset']:#010x}  {c['size']:>13,} bytes  "
            f"{c['file_count']} archivo(s)  {comp}"
        )
        for f in c["folders"][0].get("files", [])[:5]:
            print(f"      {f['size']:>12,}  {f['name']}")
        if c["file_count"] > 5:
            print(f"      ... {c['file_count'] - 5} mas")
    print("Nota: el payload grande suele ser el MSI; usa carve_bundle.py para extraerlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
