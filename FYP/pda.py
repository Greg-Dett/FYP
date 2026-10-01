import json
import subprocess
import tempfile
from pathlib import Path
from config import settings
import pdal

def isRemote(path):
    return str(path).startswith(("http://", "https://"))

def toPdalPath(path):
    # URLs must be passed through unchanged; only local paths get resolved
    return str(path) if isRemote(path) else str(Path(path).resolve())


def runCommand(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stderr)
    return proc.stdout



    
def lasToCopc(inPath, outPath): #conversion from las to copc 
    if not Path(outPath).parent.exists():
        Path(outPath).parent.mkdir() #creates out path if not available
    #creating pdal pipeline
    pipeline = {"pipeline": [str(inPath), {"type": "writers.copc", "filename": str(outPath)}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f: #temporary file for pdal pipeline as JSON cannot be passed to PDAL
        json.dump(pipeline, f)
        pipePath = f.name  #temp file path 
    proc = subprocess.run([settings.PDAL_BIN, "pipeline", pipePath], capture_output=True, text=True)
    print(proc.stderr)

def copcMetadata(path): #gets metadata from file
    stdout = runCommand([settings.PDAL_BIN, "info", "--metadata", path])
    #print(stdout)
    return json.loads(stdout)

def getBounds(metaData):
    #returns bounding box from metadata
    md = metaData.get("metadata", {})
    needed = ["minx", "miny", "minz", "maxx", "maxy", "maxz"]
    if all(k in md for k in needed):
        result = {k: float(md[k]) for k in needed}
        print(result)
        return result

    raise ValueError(f"Could not find bounds in metadata: {md}")

#gets actual point data from files
def readPoints(file, xmin, ymin, zmin, xmax, ymax, zmax, limit=None):
    stages = [{
        "type": "readers.copc",
        "filename": toPdalPath(file),  # fixes remote URLs being mangled by Path().resolve()
        "bounds": f"([{xmin},{xmax}],[{ymin},{ymax}],[{zmin},{zmax}])",
    }]
    if limit is not None:
        stages.append({"type": "filters.head", "count": limit})  # cap points so huge files don't flood the response

    # run the pipeline in memory: no temp files, no separate PDAL process
    pipeline = pdal.Pipeline(json.dumps({"pipeline": stages}))
    pipeline.execute()

    if not pipeline.arrays:
        return []
    pts = pipeline.arrays[0]  # NumPy structured array with X, Y, Z columns

    return [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y, z]}}
        for x, y, z in zip(pts["X"].tolist(), pts["Y"].tolist(), pts["Z"].tolist())
    ]
    
def getPointCount(metaData): #gets number of points from Metadata
    md = metaData.get("metadata", {})
    
    count = md.get("count") or md.get("summary", {}).get("num_points")
    try:
        return int(count) if count is not None else None
    except Exception:
        return None


    


