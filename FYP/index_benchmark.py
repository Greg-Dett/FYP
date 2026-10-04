import argparse
import csv
import json
import statistics
from pathlib import Path
import psycopg2
from config import settings

TABLE = "copc_files_bench"
INDEX = "copc_files_bench_bounds_idx"

SETUP_SQL = f"""
CREATE EXTENSION IF NOT EXISTS postgis;
DROP TABLE IF EXISTS {TABLE};
CREATE TABLE {TABLE} (
  id      BIGSERIAL PRIMARY KEY,
  bounds  geometry NOT NULL
);
"""

#Random 500 m x 500 m tiles, 0-100 m tall, scattered over a 30 km x 30 km area of Irish Grid.
#Tile size matches the real Dublin tiles.
INSERT_SQL = f"""
INSERT INTO {TABLE} (bounds)
SELECT ST_3DMakeBox(
         ST_MakePoint(x, y, 0),
         ST_MakePoint(x + 500, y + 500, 100)
       )::geometry
FROM (
  SELECT 300000 + random() * 30000 AS x,
         220000 + random() * 30000 AS y
  FROM generate_series(1, %s)
) AS tiles;
"""

CREATE_INDEX_SQL = f"CREATE INDEX {INDEX} ON {TABLE} USING GIST (bounds gist_geometry_ops_nd);"
DROP_INDEX_SQL = f"DROP INDEX IF EXISTS {INDEX};"

#rhe same query shape the API uses: a small 3D box (similar to benchmark Q3)
QUERY_SQL = f"""
EXPLAIN (ANALYZE, FORMAT JSON)
SELECT id FROM {TABLE}
WHERE bounds &&& ST_3DMakeBox(
  ST_MakePoint(314200, 233800, 0),
  ST_MakePoint(314600, 234100, 100)
)::geometry;
"""


def scanTypes(plan):
    """Collect the scan node types in a query plan, e.g. 'Seq Scan' or 'Bitmap Index Scan'."""
    found = []
    if "Scan" in plan.get("Node Type", ""):
        found.append(plan["Node Type"])
    for child in plan.get("Plans", []):
        found.extend(scanTypes(child))
    return found


def timeQuery(cur, runs):
    #Run EXPLAIN ANALYZE several times; returing differing sizes
    times = []
    rows = None
    scans = None
    cur.execute(QUERY_SQL)  # warm-up run so caching doesn't skew the first result
    for _ in range(runs):
        cur.execute(QUERY_SQL)
        result = cur.fetchone()[0]
        result = json.loads(result) if isinstance(result, str) else result
        top = result[0]
        times.append(top["Execution Time"])
        rows = top["Plan"].get("Actual Rows")
        scans = ", ".join(sorted(set(scanTypes(top["Plan"]))))
    return statistics.median(times), rows, scans


def main():
    parser = argparse.ArgumentParser(description="Benchmark GiST index vs sequential scan")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 10_000, 100_000, 1_000_000],
                        help="Catalogue sizes (number of tiles) to test")
    parser.add_argument("--runs", type=int, default=5, help="Timed runs per measurement")
    parser.add_argument("--out", default="results/index_benchmark.csv", help="CSV output path")
    parser.add_argument("--keep", action="store_true", help="Keep the benchmark table afterwards")
    args = parser.parse_args()

    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True  # each statement commits immediately (needed for DDL timing)
    cur = conn.cursor()

    rows_out = []
    header = (f"{'Tiles':>10} {'No index (ms)':>14} {'GiST (ms)':>10} {'Speedup':>8} "
              f"{'Matches':>8} {'Index build (ms)':>17}  Plans")
    print(header)
    print("-" * (len(header) + 30))

    try:
        for size in sorted(args.sizes):
            cur.execute(SETUP_SQL)
            cur.execute(INSERT_SQL, (size,))
            cur.execute(f"ANALYZE {TABLE};")

            # Without index: forces a sequential scan
            cur.execute(DROP_INDEX_SQL)
            seq_ms, seq_rows, seq_plan = timeQuery(cur, args.runs)

            # With index
            cur.execute("SELECT clock_timestamp();")
            start = cur.fetchone()[0]
            cur.execute(CREATE_INDEX_SQL)
            cur.execute("SELECT clock_timestamp();")
            build_ms = (cur.fetchone()[0] - start).total_seconds() * 1000
            cur.execute(f"ANALYZE {TABLE};")
            idx_ms, idx_rows, idx_plan = timeQuery(cur, args.runs)

            if seq_rows != idx_rows:
                print(f"  WARNING: row counts differ ({seq_rows} vs {idx_rows})")

            speedup = seq_ms / idx_ms if idx_ms > 0 else float("inf")
            print(f"{size:>10,} {seq_ms:>14.3f} {idx_ms:>10.3f} {speedup:>7.1f}x "
                  f"{idx_rows:>8} {build_ms:>17.1f}  {seq_plan} -> {idx_plan}")

            rows_out.append({
                "tiles": size,
                "seq_scan_ms": round(seq_ms, 3),
                "gist_ms": round(idx_ms, 3),
                "speedup": round(speedup, 1),
                "matches": idx_rows,
                "index_build_ms": round(build_ms, 1),
                "plan_without_index": seq_plan,
                "plan_with_index": idx_plan,
            })
    finally:
        if not args.keep:
            cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
        cur.close()
        conn.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"\nSaved results to {out}")


if __name__ == "__main__":
    main()
