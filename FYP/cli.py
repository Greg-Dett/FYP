import argparse
import json
import os
import sys
import requests


def printError(msg, code=1):
    """Print an error to stderr and exit with a non-zero code."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def upload(args):
    """Upload a LAS/LAZ/COPC file to the API for ingestion."""
    url = args.base_url.rstrip("/") + "/upload"
    if not os.path.exists(args.file):
        printError(f"file not found: {args.file}")

    data = {}
    if args.srid is not None:
        data["srid"] = str(args.srid)

    # 'with' makes sure the file is closed after the upload
    with open(args.file, "rb") as fh:
        r = requests.post(url, files={"file": fh}, data=data, timeout=1800)

    if r.status_code >= 400:
        printError(f"upload failed ({r.status_code}): {r.text}")

    print(r.text)


def CMDquery(args):
    """Find files whose bounds overlap a 3D bounding box."""
    url = args.base_url.rstrip("/") + "/query"

    xmin, ymin, xmax, ymax = map(float, args.bbox)
    if xmin > xmax or ymin > ymax:
        printError("invalid bbox: mins must be less than maxs")

    zmin, zmax = map(float, args.z)
    if zmin > zmax:
        printError("invalid z range: zmin must be less than zmax")

    params = {
        "xmin": xmin, "ymin": ymin, "zmin": zmin,
        "xmax": xmax, "ymax": ymax, "zmax": zmax,
    }

    r = requests.get(url, params=params, timeout=60)
    if r.status_code >= 400:
        printError(f"query failed ({r.status_code}): {r.text}")

    payload = r.json()

    if args.raw:
        print(json.dumps(payload, indent=2))
        return

    matches = payload.get("matches", [])
    print(f"matches: {len(matches)}")
    for m in matches:
        print(f"- id={m.get('id')} name={m.get('file_name')} path={m.get('file_path')}")


def buildParser():
    p = argparse.ArgumentParser(
        prog="copc-cli",
        description="Command-line client for COPC ingestion and bounding-box queries via the Flask API",
    )
    p.add_argument(
        "--base-url",  # argparse turns this into args.base_url automatically
        default="http://localhost:5000",
        help="API base URL (default: http://localhost:5000)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="Upload and ingest a LAS/LAZ/COPC file")
    up.add_argument("file", help="Path to a .las, .laz, or .copc file")
    up.add_argument("--srid", type=int, default=None, help="Coordinate system SRID (default on server: 29902)")
    up.set_defaults(func=upload)

    q = sub.add_parser("query", help="Find files overlapping a 3D bounding box")
    q.add_argument(
        "--bbox", nargs=4, type=float, required=True,
        metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
        help="2D bounding box in the database's coordinate system (e.g. Irish Grid EPSG:29902)",
    )
    q.add_argument(
        "--z", nargs=2, type=float, required=True,
        metavar=("ZMIN", "ZMAX"),
        help="Z (height) range",
    )
    q.add_argument("--raw", action="store_true", help="Print the raw JSON response")
    q.set_defaults(func=CMDquery)

    return p


def main():
    args = buildParser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
