#!/usr/bin/env bash
# scripts/rasterize_svg.sh
# Rasterize assets/peloton.svg to prepared_logos at multiple sizes.
# Uses inkscape if available, otherwise cairosvg (which requires libcairo installed).
# If neither is available the script will print instructions to install dependencies.

set -euo pipefail
mkdir -p prepared_logos
SVG=assets/peloton.svg
OUT_DIR=prepared_logos

render_with_inkscape() {
  echo "Using inkscape to render..."
  inkscape "$SVG" --export-type=png --export-filename="$OUT_DIR/peloton_64x64.png" --export-width=64 --export-height=64
  inkscape "$SVG" --export-type=png --export-filename="$OUT_DIR/peloton_64x32.png" --export-width=64 --export-height=32
}

render_with_cairosvg() {
  echo "Using cairosvg to render..."
  python3 - <<PY
from cairosvg import svg2png
svg='$SVG'
svg2png(url=svg, write_to='$OUT_DIR/peloton_64x64.png', output_width=64, output_height=64)
svg2png(url=svg, write_to='$OUT_DIR/peloton_64x32.png', output_width=64, output_height=32)
print('Rendered with cairosvg')
PY
}

if command -v inkscape >/dev/null 2>&1; then
  render_with_inkscape
  exit 0
fi

if python3 -c "import cairosvg" >/dev/null 2>&1; then
  render_with_cairosvg
  exit 0
fi

cat <<EOF
Neither inkscape nor cairosvg are available. To generate crisp PNGs from the SVG install one of the following:

macOS (Homebrew):
  brew install --cask inkscape
  # or
  brew install cairo pango libpng jpeg librsvg
  python3 -m pip install --user cairosvg

Debian / Raspberry Pi:
  sudo apt update
  sudo apt install inkscape libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0
  # or (for cairosvg):
  sudo apt install libcairo2 libpango-1.0-0
  python3 -m pip install cairosvg

After installing, re-run this script:
  bash scripts/rasterize_svg.sh
EOF
exit 1
