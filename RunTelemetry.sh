#!/bin/bash

echo " -> Starting Live Telemetry"

# old commands pre-ESC 2026 - not in use post 2026 onwards

# cd DUSC/TELEMETRYR/LINUXGRAFANA/
# python3 Live-Telem-05-09-2024-WIP.py

# new commands - ESC 2026 onwards
# unchanged since ESC 2024 version (TPB)

cd "Receiver"
python3 ./Live-Telem-05-09-2024-WIP.py

