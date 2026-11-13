#!/usr/bin/env bash
set -euo pipefail
font_path="${RUNNER_TEMP:-/tmp}/NotoSansKR.ttf"
curl --fail --location --retry 2 --connect-timeout 15 --max-time 30 'https://raw.githubusercontent.com/google/fonts/b38c5c93af322c45f633e17ac440ec1e6c94d489/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf' -o "$font_path"
echo "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252  $font_path" | sha256sum --check
mkdir -p "$HOME/.local/share/fonts"
cp "$font_path" "$HOME/.local/share/fonts/NotoSansKR.ttf"
fc-cache -f "$HOME/.local/share/fonts"
