import time
import statistics
import requests

BASE = "http://127.0.0.1:5000"
RUNS = 5 #number of runs per query to get median

#5 queries of increasing bounding box size, centred on the dataset
#coords in irish grid (epsg:29902)
QUERIES = [
    {"name": "Q1 (small)",  "xmin": 314350, "xmax": 314420, "ymin": 233900, "ymax": 233950, "zmin": 0, "zmax": 100},
    {"name": "Q2",          "xmin": 314300, "xmax": 314550, "ymin": 233900, "ymax": 234000, "zmin": 0, "zmax": 100},
    {"name": "Q3 (medium)", "xmin": 314200, "xmax": 314600, "ymin": 233800, "ymax": 234100, "zmin": 0, "zmax": 100},
    {"name": "Q4",          "xmin": 314000, "xmax": 314700, "ymin": 233500, "ymax": 234200, "zmin": 0, "zmax": 100},
    {"name": "Q5 (large)",  "xmin": 313800, "xmax": 314900, "ymin": 233300, "ymax": 234400, "zmin": 0, "zmax": 150},
]

def approx_area(q):
    return (q["xmax"] - q["xmin"]) * (q["ymax"] - q["ymin"])

def check_correctness(q, features):
    #verify every returned point falls within the query bounds
    violations = 0
    for f in features:
        coords = f.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 3:
            x, y, z = coords[0], coords[1], coords[2]
            if not (q["xmin"] <= x <= q["xmax"] and
                    q["ymin"] <= y <= q["ymax"] and
                    q["zmin"] <= z <= q["zmax"]):
                violations += 1
    return violations

print("=" * 60)
print("BENCHMARK RESULTS")
print("=" * 60)

print("\n7.2.2 Query Performance\n")
print(f"{'Query':<15} {'Area (m2)':>12} {'Median (s)':>12} {'Points':>8}")
print("-" * 52)

for q in QUERIES:
    params = {k: q[k] for k in ["xmin","xmax","ymin","ymax","zmin","zmax"]}
    params["limit"] = 5000

    times = []
    last_payload = None
    for _ in range(RUNS):
        start = time.time()
        r = requests.get(f"{BASE}/points", params=params, timeout=120)
        elapsed = time.time() - start
        times.append(elapsed)
        if r.status_code == 200:
            last_payload = r.json()

    median_t = statistics.median(times)
    point_count = last_payload.get("point_count", 0) if last_payload else 0
    area = approx_area(q)
    print(f"{q['name']:<15} {area:>12,.0f} {median_t:>12.3f} {point_count:>8}")

    #correctness check
    if last_payload:
        features = last_payload.get("Points", [])
        violations = check_correctness(q, features)
        if violations == 0:
            print(f"  correctness: all {len(features)} points within bounds")
        else:
            print(f"  correctness: {violations} VIOLATIONS FOUND")

print("\n7.2.3 Data Transfer Efficiency\n")
#run Q3 and report transfer stats
q = QUERIES[2]
params = {k: q[k] for k in ["xmin","xmax","ymin","ymax","zmin","zmax"]}
params["limit"] = 5000
r = requests.get(f"{BASE}/points", params=params, timeout=120)
if r.status_code == 200:
    payload = r.json()
    response_mb = len(r.content) / (1024 * 1024)
    point_count = payload.get("point_count", 0)
    file_count = payload.get("file_count", 0)
    print(f"Query: {q['name']}")
    print(f"Points returned: {point_count:,}")
    print(f"Response size: {response_mb:.2f} MB")
    print(f"Files queried: {file_count}")
