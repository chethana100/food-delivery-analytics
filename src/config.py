"""Central configuration (paths, timezone, generation defaults)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "food_delivery.db"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"

# All timestamps are stored as naive ISO strings in this timezone, and all
# "current week / month / year" logic uses it as well.
REPORTING_TZ = "Asia/Kolkata"
CURRENCY = "₹"

# Synthetic data generation defaults (fixed so the dataset is reproducible).
SEED = 42
DATA_START = "2025-01-01"
DATA_END = "2026-10-17"
