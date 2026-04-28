from database import GetAll

QUERY_SQL = """
SELECT id, file_name, file_path, srid
FROM copc_files
WHERE bounds &&& ST_3DMakeBox(
  ST_MakePoint(%s, %s, %s),
  ST_MakePoint(%s, %s, %s)
)::box3d
ORDER BY id;
"""

UNION_BOUNDS_SQL = """
SELECT
  ST_XMin(ST_3DExtent(bounds::geometry)::geometry) AS xmin,
  ST_YMin(ST_3DExtent(bounds::geometry)::geometry) AS ymin,
  ST_ZMin(ST_3DExtent(bounds::geometry)::geometry) AS zmin,
  ST_XMax(ST_3DExtent(bounds::geometry)::geometry) AS xmax,
  ST_YMax(ST_3DExtent(bounds::geometry)::geometry) AS ymax,
  ST_ZMax(ST_3DExtent(bounds::geometry)::geometry) AS zmax
FROM copc_files
WHERE file_name = ANY(%s);
"""

def query3dBox(xmin, ymin, zmin,xmax, ymax, zmax):
    return GetAll(QUERY_SQL, (xmin, ymin, zmin, xmax, ymax, zmax))

def queryMultipleFiles(fileNames): #takes file names, merges their bounds, returns all files that overlap the merged area
    rows = GetAll(UNION_BOUNDS_SQL, (fileNames,))
    if not rows or rows[0]["xmin"] is None: #none means no matching files found in db
        raise ValueError(f"No files found matching names: {fileNames}")

    b = rows[0]
    xmin, ymin, zmin = float(b["xmin"]), float(b["ymin"]), float(b["zmin"])
    xmax, ymax, zmax = float(b["xmax"]), float(b["ymax"]), float(b["zmax"])

    matches = query3dBox(xmin, ymin, zmin, xmax, ymax, zmax) #reuse existing query with the merged bounds
    return {
         "union_bounds": { #return the merged bounds so caller knows what area was searched
            "xmin": xmin, "ymin": ymin, "zmin": zmin,
            "xmax": xmax, "ymax": ymax, "zmax": zmax,
        },
        "matches": matches,
    }
