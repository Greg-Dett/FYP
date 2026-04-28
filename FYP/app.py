import os
from flask import Flask, request, jsonify
from flask_cors import CORS

from database import runSqlFile
from ingest import getAndConvert, getRemoteCopc
from query import query3dBox, queryMultipleFiles
from pda import readPoints

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
    srid = int(request.form.get("srid")) #going to be 29902 for our dataset however have not kept it as that for adaptability
    f = request.files["file"]
    storage = r"C:\Users\Greg\FYP\las_files"
    path = storage + "\\" + f.filename

    try:
        f.save(str(path))
        ingested = getAndConvert([str(path)], srid=srid)
    except Exception as e:
        print(str(e))
        return str(e), 500

    return "uploaded"




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
    except ValueError:
        return "Co-ordinate error"

    pointLimit = request.args.get("limit")
    if (pointLimit):
         limit = int(pointLimit) 
    else: limit =1000 #default to 1000 to stop too much data coming through, possibility of millions of points

    files = query3dBox(xmin, ymin, zmin, xmax, ymax, zmax) #get files whose bounds overlap the query box
    if not files:
        return "No files found"
    #creating points and errors lists to prevent total failure from single point retrieval failure
    points = []
    errors = []
    per_file_limit = limit // len(files) #spread limit evenly across files so points come from each
    for row in files:
        try:
            geojson = readPoints(row["file_path"], xmin, ymin, zmin, xmax, ymax, zmax, limit=per_file_limit)
            points.extend(geojson.get("features", []))
        except Exception as e:
            errors.append({"file": row["file_name"], "error": str(e)}) #store error but continue with other files

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
@app.post("/queryMany")
def query_between():

    body = request.get_json(silent=True) or {}
    file_names = body.get("files", [])

    if not isinstance(file_names, list) or len(file_names) < 2:
        return "Provide at least 2 file names in 'files'"

    try:
        result = queryMultipleFiles(file_names)
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        return str(e), 500

    return jsonify(result)


if __name__ == "__main__":
    
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
