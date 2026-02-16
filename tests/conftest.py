"""Test configuration and path setup."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTROL_PLANE = ROOT / "control-plane" / "api"
if str(CONTROL_PLANE) not in sys.path:
    sys.path.insert(0, str(CONTROL_PLANE))

EVENT_PROCESSOR = ROOT / "control-plane" / "event-processor"
if str(EVENT_PROCESSOR) not in sys.path:
    sys.path.insert(0, str(EVENT_PROCESSOR))
