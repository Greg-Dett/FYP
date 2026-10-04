from pathlib import Path
from urllib.parse import urlparse

from config import settings
from database import execute
from pda import lasToCopc, copcMetadata, getBounds

#insert file metadata into db
INSERT_SQL = """
INSERT INTO copc_files (file_name, file_path, bounds, srid)
VALUES (
  %s,
  %s,
  ST_3DMakeBox(
    ST_MakePoint(%s, %s, %s),
    ST_MakePoint(%s, %s, %s)
  )::geometry,
  %s
)
ON CONFLICT (file_path) DO UPDATE SET
  file_name = EXCLUDED.file_name,
  bounds = EXCLUDED.bounds,
  srid = EXCLUDED.srid;
"""

def getCopc(path, srid): #extracts metadata from local copc file and stores in db
    meta = copcMetadata(path)
    b = getBounds(meta)

    p = Path(path)
    execute(
        INSERT_SQL,
        (
            p.name,
            str(p.resolve()),
            b["minx"], b["miny"], b["minz"],
            b["maxx"], b["maxy"], b["maxz"],
            srid,
        )
    )

def getRemoteCopc(url: str, srid: int): #fetches metadata from remote copc file via http range requests so no full download needed
    meta = copcMetadata(url)
    b = getBounds(meta)
    file_name = Path(urlparse(url).path).name #extract filename from url
    execute(
        INSERT_SQL,
        (
            file_name,
            url, #url stored as file_path so /points can read it remotely later
            b["minx"], b["miny"], b["minz"],
            b["maxx"], b["maxy"], b["maxz"],
            srid,
        )
    )

def getAndConvert(inputs: list[str], srid: int = 29902): #converts las/laz to copc and ingests, or ingests copc directly
    out_dir = Path(settings.STORAGE_DIR) / "copc_files"
    out_dir.mkdir(parents=True, exist_ok=True)
    ingested = []

    for in_path in inputs:
        p = Path(in_path)
        if not p.exists():
            raise FileNotFoundError(str(p))

        if p.name.lower().endswith((".copc", ".copc.laz")):  #already COPC, ingest directly
            getCopc(str(p), srid=srid)
            ingested.append(str(p.resolve()))
            continue

        if p.suffix.lower() in [".las", ".laz"]: #convert to copc first then ingest
            out_path = out_dir / f"{p.stem}.copc"
            lasToCopc(str(p), str(out_path))
            getCopc(str(out_path), srid=srid)
            ingested.append(str(out_path.resolve()))
            continue

        raise ValueError(f"Unsupported file type: {p.name}")

    return ingested
