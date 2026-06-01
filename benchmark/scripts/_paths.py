"""benchmark/ path constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parents[1]
RESULTS = BENCH / "results"
SAMPLES = BENCH / "samples"
LOGS = BENCH / "logs"
