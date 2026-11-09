"""Paths and settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POLICIES_PDF = DATA_DIR / "store_policies.pdf"
CSV_TABLES = ("categories", "customers", "orders", "order_items", "products", "promotions")
