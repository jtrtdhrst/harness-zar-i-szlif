"""Read-only folder selector for non-source-ready Harness services."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "ops/service-deployment-roots.json"
def select(paths):
    records = json.loads(MANIFEST.read_text())["resources"]
    paths = [p.removeprefix("./").replace("\\\\","/") for p in paths]
    return sorted({r["id"] for r in records for p in paths if
                   any(p.startswith(w) for w in r["watched_paths"])})
if __name__ == "__main__":
    print(json.dumps({"candidate_services":select(sys.argv[1:]),"deploy":False},sort_keys=True))
