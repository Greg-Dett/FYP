import os
from flask import Flask, request, jsonify
from flask_cors import CORS

from database import runSqlFile
from ingest import getAndConvert, getRemoteCopc
from query import query3dBox, queryMultipleFiles
from pda import readPoints
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from werkzeug.utils import secure_filename
from config import settings

app = Flask(__name__)
CORS(app)


#the project has two main ways of being used. the first is uploading the file yourself and the storing it locally. the file is converted to copc if it is laz or las and then metadata extracted at which point you can then query it from local db. 
#second way is from a servr in this way one can register the server and then extract metadata and query throughhttps range requests
@app.post("/init-db")
def init_db():
    runSqlFile("schema.sql")
    return "ok"


#helper to get a float query param, raises if missing
def getFloat(name):
        v = request.args.get(name)
        if v is None:
            raise ValueError(f"missing parameter: {name}")
        return float(v)

# uploads file to the db
@app.post("/upload")
def upload():
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "missing file"}), 400

    filename = secure_filename(f.filename)  # strips things like ../ so files can't be written outside the folder
    if not filename:
        return jsonify({"error": "invalid filename"}), 400

    try:
        srid = int(request.form.get("srid", 29902))  # defaults to Irish Grid
    except ValueError:
        return jsonify({"error": "srid must be an integer"}), 400

    upload_dir = Path(settings.STORAGE_DIR) / "las_files"
    upload_dir.mkdir(parents=True, exist_ok=True)  # create the folder if it doesn't exist
    path = upload_dir / filename

    try:
        f.save(path)
        ingested = getAndConvert([str(path)], srid=srid)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ingested": ingested})

MAX_WORKERS = 8  # how many files are read at the same time



def parseBox():
    #gets bbox from command
    xmin = getFloat("xmin")
    xmax = getFloat("xmax")
    ymin = getFloat("ymin")
    ymax = getFloat("ymax")
    zmin = getFloat("zmin")
    zmax = getFloat("zmax")
    if xmin > xmax or ymin > ymax or zmin > zmax: #check mins are less than maxs
        raise ValueError("Invalid bounds ordering")
    return xmin, ymin, zmin, xmax, ymax, zmax

@app.get("/query")
def query():
    try:
        xmin, ymin, zmin, xmax, ymax, zmax = parseBox()
    except ValueError:
        return "Co-ordinate error"
    rows = query3dBox(xmin, ymin, zmin, xmax, ymax, zmax)
    return jsonify({"matches": rows})

@app.get("/points")
def getPoints():
    try:
        xmin, ymin, zmin, xmax, ymax, zmax = parseBox()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        limit = int(request.args.get("limit", 1000))  # default 1000 to avoid returning millions of points
        if limit <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "limit must be a positive integer"}), 400

    files = query3dBox(xmin, ymin, zmin, xmax, ymax, zmax)  # files whose bounds overlap the box
    if not files:
        return jsonify({"Points": [], "point_count": 0, "file_count": 0})

    errors = []
    results = []

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(files))) as pool:
        futures = {
            pool.submit(readPoints, row["file_path"], xmin, ymin, zmin, xmax, ymax, zmax, limit): row
            for row in files
        }
        for future in as_completed(futures):
            row = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                errors.append({"file": row["file_name"], "error": str(e)})

    # take points from each file in turn, so every file contributes fairly up to the limit
    points = []
    i = 0
    while len(points) < limit and any(i < len(r) for r in results):
        for r in results:
            if i < len(r) and len(points) < limit:
                points.append(r[i])
        i += 1

    result = {
        "Points": points,
        "point_count": len(points),
        "file_count": len(files),
    }
    if errors:
        result["errors"] = errors
    return jsonify(result)

#registers a remote copc file by url, pdal reads metadata via http range requests so no download needed
@app.post("/registerRemote")
def register_remote():

    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    srid = int(body.get("srid", 29902)) #defaults to irish grid if not provided
    if not url:
        return "Missing url"
    try:
        getRemoteCopc(url, srid)
    except Exception as e:
        return str(e), 500

    return f"registered {url}"


#takes a list of file names, computes their combined bbox and returns all files that overlap it
@app.get("/query")
def query():
    try:
        xmin, ymin, zmin, xmax, ymax, zmax = parseBox()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400  # bad or missing coordinates
    rows = query3dBox(xmin, ymin, zmin, xmax, ymax, zmax)
    return jsonify({"matches": rows})


if __name__ == "__main__":
    
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
