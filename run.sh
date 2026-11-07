#!/bin/bash
set -e
cd "$(dirname "$0")"
pip3 install -r requirements.txt
python3 -m playwright install chromium
python3 outlook_registrator.py
