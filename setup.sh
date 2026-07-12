#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

echo ""
echo "Setup complete. Run:"
echo "  source .venv/bin/activate"
echo "  python main.py --country India --industry \"generic medicine importers\""
