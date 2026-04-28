import json
import subprocess
import tempfile
from pathlib import Path

from config import settings


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

    bounds = f"([{xmin},{xmax}],[{ymin},{ymax}],[{zmin},{zmax}])"

    stages= [
        {
        "type": "readers.copc",
        "filename": str(Path(file).resolve()),
        "bounds": bounds,
        }
    ]
    #limit to not crash by retrieving all points as files can be massive
    if limit is not None:
        stages.append({"type": "filters.head", "count": limit})
    #temp file for pdal pipeline usage
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "out.geojson"
        stages.append({
        "type": "writers.text",
        "format": "geojson",
        "filename": str(out_path),
        })

        pipePath = Path(tmpdir) / "pipeline.json"
        pipePath.write_text(json.dumps({"pipeline": stages}), encoding="utf-8")

        runCommand([settings.PDAL_BIN, "pipeline", str(pipePath)])

        return json.loads(out_path.read_text(encoding="utf-8"))
    
def getPointCount(metaData): #gets number of points from Metadata
    md = metaData.get("metadata", {})
    
    count = md.get("count") or md.get("summary", {}).get("num_points")
    try:
        return int(count) if count is not None else None
    except Exception:
        return None


    


