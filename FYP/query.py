from database import GetAll


QUERY_SQL = """
SELECT id, file_name, file_path, srid
FROM copc_files
WHERE bounds &&& ST_3DMakeBox(
  ST_MakePoint(%s, %s, %s),
  ST_MakePoint(%s, %s, %s)
)::geometry
ORDER BY id;
"""

UNION_BOUNDS_SQL = """
WITH selected AS (
  SELECT file_name, bounds
  FROM copc_files
  WHERE file_name = ANY(%s)
),
extent AS (
  SELECT ST_3DExtent(bounds) AS ext FROM selected
)
SELECT
  ST_XMin(ext) AS xmin,
  ST_YMin(ext) AS ymin,
  ST_ZMin(ext) AS zmin,
  ST_XMax(ext) AS xmax,
  ST_YMax(ext) AS ymax,
  ST_ZMax(ext) AS zmax,
  (SELECT array_agg(file_name) FROM selected) AS found_names
FROM extent;
"""

def query3dBox(xmin, ymin, zmin,xmax, ymax, zmax):
    return GetAll(QUERY_SQL, (xmin, ymin, zmin, xmax, ymax, zmax))

def queryMultipleFiles(fileNames):
    rows = GetAll(UNION_BOUNDS_SQL, (fileNames,))
 
    # No matching rows: the extent and found names come back as NULL
    if not rows or rows[0]["xmin"] is None:
        raise ValueError(f"No files found matching names: {fileNames}")
 
    b = rows[0]
 
    # Report any requested names that aren't in the database
    found = set(b["found_names"] or [])
    missing = sorted(set(fileNames) - found)
    if missing:
        raise ValueError(f"Files not found: {missing}")
 
    xmin, ymin, zmin = float(b["xmin"]), float(b["ymin"]), float(b["zmin"])
    xmax, ymax, zmax = float(b["xmax"]), float(b["ymax"]), float(b["zmax"])
 
    # Reuse the indexed box query with the merged bounds
    matches = query3dBox(xmin, ymin, zmin, xmax, ymax, zmax)
 
    return {
        "union_bounds": {
            "xmin": xmin, "ymin": ymin, "zmin": zmin,
            "xmax": xmax, "ymax": ymax, "zmax": zmax,
        },
        "matches": matches,
    }