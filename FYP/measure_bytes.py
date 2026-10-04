
##Measure how many bytes COPC queries read over HTTP, compared with downloading whole files.

import argparse
import csv
import json
from pathlib import Path

import pdal
import requests

from pda import copcMetadata, getBounds

#Same five queries as benchmark.py (Irish Grid, EPSG:29902)
QUERIES = [
    {"name": "Q1 (small)",  "xmin": 314350, "xmax": 314420, "ymin": 233900, "ymax": 233950, "zmin": 0, "zmax": 100},
    {"name": "Q2",          "xmin": 314300, "xmax": 314550, "ymin": 233900, "ymax": 234000, "zmin": 0, "zmax": 100},
    {"name": "Q3 (medium)", "xmin": 314200, "xmax": 314600, "ymin": 233800, "ymax": 234100, "zmin": 0, "zmax": 100},
    {"name": "Q4",          "xmin": 314000, "xmax": 314700, "ymin": 233500, "ymax": 234200, "zmin": 0, "zmax": 100},
    {"name": "Q5 (large)",  "xmin": 313800, "xmax": 314900, "ymin": 233300, "ymax": 234400, "zmin": 0, "zmax": 150},
]


def makeQueries(catalogue, fractions=(0.001, 0.01, 0.05, 0.25, 1.0)):
    ##Build query boxes centred on the first file, covering a fraction of its area.

    b = catalogue[0]["bounds"]
    cx, cy = (b["minx"] + b["maxx"]) / 2, (b["miny"] + b["maxy"]) / 2
    width, height = b["maxx"] - b["minx"], b["maxy"] - b["miny"]
    queries = []
    for frac in fractions:
        scale = frac ** 0.5  #scale each side so the AREA is the given fraction
        hw, hh = width * scale / 2, height * scale / 2
        queries.append({
            "name": f"{frac * 100:g}% of tile",
            "xmin": cx - hw, "xmax": cx + hw,
            "ymin": cy - hh, "ymax": cy + hh,
            "zmin": b["minz"], "zmax": b["maxz"],
        })

    if len(catalogue) > 1:
        #5%-of-tile box centred on the shared edge between the first two files' centres
        b2 = catalogue[1]["bounds"]
        mx = (cx + (b2["minx"] + b2["maxx"]) / 2) / 2
        my = (cy + (b2["miny"] + b2["maxy"]) / 2) / 2
        hw, hh = width * 0.05 ** 0.5 / 2, height * 0.05 ** 0.5 / 2
        queries.append({
            "name": "5% on boundary",
            "xmin": mx - hw, "xmax": mx + hw,
            "ymin": my - hh, "ymax": my + hh,
            "zmin": min(b["minz"], b2["minz"]), "zmax": max(b["maxz"], b2["maxz"]),
        })
    return queries


def boundsStr(q):
    return f"([{q['xmin']},{q['xmax']}],[{q['ymin']},{q['ymax']}],[{q['zmin']},{q['zmax']}])"


def overlaps(q, b):
    #True if query box q overlaps file bounds b (touching counts, like PostGIS &&&).
    return (q["xmin"] <= b["maxx"] and q["xmax"] >= b["minx"] and
            q["ymin"] <= b["maxy"] and q["ymax"] >= b["miny"] and
            q["zmin"] <= b["maxz"] and q["zmax"] >= b["minz"])


def runCount(stages):
    #Run a PDAL and return the number of points it produced.
    pipeline = pdal.Pipeline(json.dumps({"pipeline": stages}))
    pipeline.execute()
    return sum(len(a) for a in pipeline.arrays)


def remoteCount(url, q):
    #Points in the box, read from the remote COPC file using only the needed octree nodes
    return runCount([{"type": "readers.copc", "filename": url, "bounds": boundsStr(q)}])


def groundTruthCount(path, q):
    #Points in the box, from reading the ENTIRE local file and cropping (the naive approach).
    return runCount([
        {"type": "readers.copc", "filename": str(path)},
        {"type": "filters.crop", "bounds": boundsStr(q)},
    ])


def main():
    #cli
    parser = argparse.ArgumentParser(description="Measure COPC bytes read per query")
    parser.add_argument("--dir", required=True, help="Folder being served, e.g. data/copc_files")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="Range server base URL")
    parser.add_argument("--verify", action="store_true",
                        help="Also compare point counts with a full-file read + crop (completeness check)")
    parser.add_argument("--out", default="results/bytes_read.csv", help="CSV output path")
    parser.add_argument("--auto", action="store_true",
                        help="Generate queries from the loaded files' extent instead of the fixed benchmark boxes")
    parser.add_argument("--files", nargs="+",
                        help="Only use these file names from --dir (default: all COPC files)")
    args = parser.parse_args()

    server = args.server.rstrip("/")
    folder = Path(args.dir)
    files = sorted(p for p in folder.iterdir()
                   if p.name.lower().endswith((".copc", ".copc.laz")))
    if args.files:
        files = [p for p in files if p.name in args.files]
    if not files:
        raise SystemExit(f"No COPC files found in {folder}")

    #Get each file's bounds once, before measuring (this setup traffic isn't counted)
    catalogue = []
    for p in files:
        url = f"{server}/{p.name}"
        b = getBounds(copcMetadata(url))
        catalogue.append({"name": p.name, "path": p, "url": url, "size": p.stat().st_size, "bounds": b})
        print(f"Loaded {p.name}: {p.stat().st_size / 1e6:.1f} MB")

    queries = makeQueries(catalogue) if args.auto else QUERIES

    rows = []
    print()
    header = f"{'Query':<16} {'Files':>5} {'Points':>11} {'Read (MB)':>10} {'Full (MB)':>10} {'Reduction':>10} {'Requests':>9}"
    if args.verify:
        header += f" {'Complete':>9}"
    print(header)
    print("-" * len(header))

    for q in queries:
        hits = [f for f in catalogue if overlaps(q, f["bounds"])]
        if not hits:
            print(f"{q['name']:<16} no overlapping files")
            continue

        requests.get(f"{server}/__reset", timeout=10)
        points = sum(remoteCount(f["url"], q) for f in hits)
        stats = requests.get(f"{server}/__stats", timeout=10).json()

        read_bytes = stats["bytes_served"]
        full_bytes = sum(f["size"] for f in hits)
        reduction = 100 * (1 - read_bytes / full_bytes)

        row = {
            "query": q["name"],
            "files": len(hits),
            "points": points,
            "bytes_read": read_bytes,
            "full_bytes": full_bytes,
            "reduction_pct": round(reduction, 2),
            "http_requests": stats["requests"], }
        line = (f"{q['name']:<16} {len(hits):>5} {points:>11,} {read_bytes / 1e6:>10.2f} "
                f"{full_bytes / 1e6:>10.2f} {reduction:>9.1f}% {stats['requests']:>9}")

        if args.verify:
            truth = sum(groundTruthCount(f["path"], q) for f in hits)
            row["ground_truth_points"] = truth
            row["complete"] = truth == points
            line += f" {'yes' if truth == points else f'NO ({truth:,})':>9}"

        rows.append(row)
        print(line)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved results to {out}")


if __name__ == "__main__":
    main()
