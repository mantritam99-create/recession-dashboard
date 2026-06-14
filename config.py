"""Config + path resolution. Import this anywhere; it finds project root."""
import os, yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

with open(os.path.join(ROOT, "config.yaml"), "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

# Optional local-only overrides (gitignored) — keeps secrets out of the committed
# config.yaml. Currently used only to supply fred.api_key for local runs; the CI
# build instead reads the key from the FRED_API_KEY environment / repo secret.
_LOCAL = os.path.join(ROOT, "config.local.yaml")
if os.path.exists(_LOCAL):
    with open(_LOCAL, "r", encoding="utf-8") as f:
        _ov = yaml.safe_load(f) or {}
    if _ov.get("fred", {}).get("api_key"):
        CFG.setdefault("fred", {})["api_key"] = _ov["fred"]["api_key"]


def fred_key() -> str:
    """Key from config.yaml, else FRED_API_KEY env var, else ''."""
    return (CFG.get("fred", {}).get("api_key") or os.environ.get("FRED_API_KEY") or "").strip()


def has_fred() -> bool:
    return len(fred_key()) >= 32  # FRED keys are 32-char alphanumeric
