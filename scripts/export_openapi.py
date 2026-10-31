"""Generate the committed specification from the executable API contracts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.main import create_app  # noqa: E402
from backend import Settings  # noqa: E402

if __name__ == "__main__":
    target = ROOT / "docs" / "swagger.json"
    specification = create_app(settings=Settings()).openapi()
    target.write_text(json.dumps(specification, indent=2, ensure_ascii=False) + "\n")
    print(f"Generated {target.relative_to(ROOT)}")
