#!/usr/bin/env bash
# Orquesta la inspeccion y extraccion del instalador WiX Burn.
# Uso: ./scripts/extract_bundle.sh [ruta.exe] [--out DIR]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXE="${1:-$ROOT/PBIDesktopSetup_x64.exe}"
OUT="$ROOT/extracted"
if [[ "${2:-}" == "--out" && -n "${3:-}" ]]; then OUT="$3"; fi

if [[ ! -f "$EXE" ]]; then echo "No existe: $EXE" >&2; exit 2; fi

echo "== 1/4 Verificacion =="
python3 "$ROOT/scripts/verify_bundle.py" "$EXE" || exit 1

echo
echo "== 2/4 Carve de contenedores y firmas =="
python3 "$ROOT/scripts/carve_bundle.py" "$EXE" --out "$OUT" || exit 1

echo
echo "== 3/4 Descompresion =="
shopt -s nullglob
CABS=("$OUT"/container_*.cab)
if [[ ${#CABS[@]} -eq 0 ]]; then
  echo "No se encontraron .cab para descomprimir."; exit 1
fi

if command -v dark.exe >/dev/null 2>&1; then
  echo "Usando WiX dark.exe (mas fiable, conserva estructura del bundle)"
  mkdir -p "$OUT/dark"
  dark.exe "$EXE" -x "$OUT/dark" && echo "OK -> $OUT/dark"
elif command -v cabextract >/dev/null 2>&1; then
  echo "Usando cabextract (LZX soportado por libmspack)"
  for cab in "${CABS[@]}"; do
    dest="$OUT/$(basename "${cab%.cab}")"
    mkdir -p "$dest"
    cabextract -q -d "$dest" "$cab" || echo "  aviso: fallo $cab (flags Burn 0x1503; prueba 7z/dark.exe)"
  done
elif command -v 7z >/dev/null 2>&1 || command -v 7za >/dev/null 2>&1; then
  SEVEN="$(command -v 7z || command -v 7za)"
  echo "Usando $SEVEN"
  for cab in "${CABS[@]}"; do
    dest="$OUT/$(basename "${cab%.cab}")"
    mkdir -p "$dest"
    "$SEVEN" x -y -o"$dest" "$cab" >/dev/null || echo "  aviso: fallo $cab"
  done
else
  echo "No hay cabextract, 7z ni dark.exe instalados."
  echo "Opciones:"
  echo "  - Linux:  apt install cabextract p7zip-full   (o brew install cabextract)"
  echo "  - Windows: instala WiX Toolset y ejecuta:"
  echo "      dark.exe \"$EXE\" -x \"$OUT/dark\""
  echo "  - Windows (oficial, sin descomprimir a mano):"
  echo "      \"$EXE\" /layout \"$OUT/layout\""
  echo "Los .cab crudos y las firmas ya quedaron en: $OUT"
  exit 0
fi

echo
echo "== 4/4 Resultado =="
find "$OUT" -maxdepth 2 -type f -printf '  %10s  %p\n' 2>/dev/null | sort -k2 | head -80
echo
echo "Recuerda: el contenido es propiedad de Microsoft; usalo solo para estudio/interoperabilidad."
