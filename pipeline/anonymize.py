"""pipeline/anonymize.py — replace employee names with stable opaque IDs.

Run AFTER build_v2.py + build_dashboard.py and BEFORE git commit if you want to
publish the dashboard to a public repo without exposing employee names.

Mapping is deterministic and stable across runs (sha256-truncated). It's stored
at cache/operator_map.json (gitignored) so internal users can de-anonymize.

Usage:
    python3 pipeline/anonymize.py        # rewrites docs/* in place
    python3 pipeline/anonymize.py --check # show what would change, no writes

Files touched:
    docs/data/loss_records.csv          operator column
    docs/data/store_benchmark.csv       top_operator column
    docs/data/dashboard_payload.json    operators[].name + top_operator
    docs/index.html                     re-rendered from anonymized payload
"""
import argparse, csv, hashlib, json, os, sys
from collections import OrderedDict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS_DATA = os.path.join(REPO_ROOT, "docs", "data")
INDEX_HTML = os.path.join(REPO_ROOT, "docs", "index.html")
CACHE = os.path.join(REPO_ROOT, "cache", "operator_map.json")

def anon_id(name):
    """Stable 4-hex-char ID — collision risk acceptable for ≤24 employees."""
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:4]
    return f"OP-{h.upper()}"

def collect_names():
    names = set()
    with open(os.path.join(DOCS_DATA, "loss_records.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["operator"]: names.add(r["operator"])
    return sorted(names)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report without writing")
    args = ap.parse_args()

    names = collect_names()
    mapping = OrderedDict((n, anon_id(n)) for n in names)
    print(f"Found {len(names)} distinct operator names. Mapping preview:")
    for n, a in list(mapping.items())[:5]:
        print(f"  {n!r:<28} -> {a}")
    if len(mapping) > 5: print(f"  ... and {len(mapping)-5} more")
    if args.check:
        print("\n--check: no files modified.")
        return

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(mapping, open(CACHE, "w"), ensure_ascii=False, indent=2)
    print(f"\nwrote mapping to {CACHE}")

    # 1. loss_records.csv
    p = os.path.join(DOCS_DATA, "loss_records.csv")
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    fields = list(rows[0].keys())
    for r in rows: r["operator"] = mapping.get(r["operator"], r["operator"])
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"rewrote {p}")

    # 2. store_benchmark.csv (top_operator column)
    p = os.path.join(DOCS_DATA, "store_benchmark.csv")
    with open(p, encoding="utf-8") as f: lines = list(csv.reader(f))
    hdr = lines[0]; ti = hdr.index("top_operator")
    for row in lines[1:]:
        if row[ti] in mapping: row[ti] = mapping[row[ti]]
    with open(p, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(lines)
    print(f"rewrote {p}")

    # 3. dashboard_payload.json
    p = os.path.join(DOCS_DATA, "dashboard_payload.json")
    payload = json.load(open(p, encoding="utf-8"))
    def fix_store_list(lst):
        for s in lst:
            if s.get("top_operator") in mapping:
                s["top_operator"] = mapping[s["top_operator"]]
            for op in s.get("operators", []):
                if op.get("name") in mapping: op["name"] = mapping[op["name"]]
    fix_store_list(payload.get("stores_all", []))
    for sp, lst in payload.get("stores_by_spec", {}).items():
        fix_store_list(lst)
    fix_store_list(payload.get("non_stores", []))
    json.dump(payload, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"rewrote {p}")

    # 4. re-render index.html from anonymized payload
    # Easiest: swap the payload in docs/index.html by regex.
    html = open(INDEX_HTML, encoding="utf-8").read()
    import re
    new = re.sub(
        r"const DATA = \{.+?\};\s*\n\s*const fmtN",
        "const DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n\nconst fmtN",
        html, count=1, flags=re.DOTALL,
    )
    if new == html:
        print(f"WARNING: failed to swap payload in {INDEX_HTML}")
    else:
        open(INDEX_HTML, "w", encoding="utf-8").write(new)
        print(f"rewrote {INDEX_HTML}")

if __name__ == "__main__":
    main()
