# Multi-File Point Cloud Query System

My final year project for the BSc in Computer Science at UCD. It lets you query a 3D box across many large LiDAR files and only read the parts of each file you actually need, whether the files are stored locally or on a remote server.
On the 2015 Dublin LiDAR dataset (about 90 million points per tile), small queries read around 95% less data than downloading the whole files.

## How it works

There are two levels of indexing:

1. **Which files?** Each file's 3D bounding box is stored in PostgreSQL/PostGIS with a GiST index, so finding the files that overlap a query stays fast even with a very large number of files.
2. **Which parts of each file?** Files are stored as COPC (Cloud Optimized Point Cloud), which organises points in an octree. PDAL reads only the octree nodes that intersect the query. Because COPC supports HTTP range requests, this also works for files on a remote server without downloading them.

Overlapping files are read in parallel, and results are returned as GeoJSON through a Flask REST API. There's also a small command-line client.

```mermaid
flowchart LR
    C[Client / CLI] --> A[Flask API]
    A -->|which files?| DB[(PostGIS)]
    A -->|read only needed parts| P[PDAL]
    P --> L[Local COPC files]
    P -->|HTTP range requests| R[Remote COPC files]
```

Built with Python, Flask, PostgreSQL/PostGIS, PDAL (python-pdal), and Docker.

## Setup

You'll need Miniconda and Docker.

```bash
git clone https://github.com/Greg-Dett/<repo-name>.git
cd <repo-name>
conda env create -f environment.yml
conda activate copc

docker run --name copc-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=copc_db \
  -p 127.0.0.1:5433:5432 -d postgis/postgis
```

Create a `.env` file:

```
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/copc_db
STORAGE_DIR=./data
PDAL_BIN=pdal
```

Then start the API and create the table:

```bash
python app.py
curl -X POST http://127.0.0.1:5000/init-db
```

I used conda rather than pip because PDAL is a C++ library, and conda installs it along with the Python bindings.

## Usage

```bash
python cli.py upload las_files/T_315000_233500.laz --srid 29902
python cli.py query --bbox 315200 233700 315300 233800 --z -100 400
```

Or call the API directly:

| Endpoint | What it does |
|---|---|
| `POST /init-db` | Creates the table and index |
| `POST /upload` | Uploads a LAS/LAZ/COPC file (converted to COPC if needed) |
| `POST /registerRemote` | Registers a remote COPC file by URL |
| `GET /query` | Lists files overlapping a 3D box |
| `GET /points` | Returns points inside a 3D box (optional `limit`) |
| `POST /queryMany` | Finds files overlapping the combined area of two or more files |

Coordinates are in Irish Grid (EPSG:29902).

## Data

The data comes from the [2015 Dublin LiDAR survey](https://doi.org/10.17609/N8MQ0N/) by NYU and isn't included here. I used tiles [T_315000_233500](https://archive.nyu.edu/handle/2451/38594) and [T_315500_233500](https://archive.nyu.edu/handle/2451/38600). Download the "LAZ (Point-cloud)" file for each.

## Results

All results can be reproduced with the scripts in the repo and are saved in `results/`.

**Data read per query** (measured by serving the files over HTTP and counting bytes, `measure_bytes.py`):

| Query size (share of a 472 MB tile) | Data read | Reduction |
|---|---|---|
| 0.1% | 20.1 MB | 95.7% |
| 1% | 22.9 MB | 95.1% |
| 5% | 42.2 MB | 91.1% |
| 25% | 180.4 MB | 61.8% |
| 100% | 471.8 MB | 0% |

Small queries always read about 20 MB, which is the file header, the octree index, and the top levels of the octree.

**Spatial index** (`index_benchmark.py`): at 1 million files, finding overlapping files took 0.43 ms with the GiST index versus 59.5 ms without it, about 139× faster.

**Correctness:** every returned point is inside the query box (`benchmark.py`), and the results match a full read of each file exactly, so no points are missed (`measure_bytes.py --verify`).

## What I learned

- My benchmark showed every query taking about 4 seconds no matter how big it was, which meant the time wasn't going into the query itself. It turned out Windows tries IPv6 first for `localhost`, and waits about 2 seconds before falling back. Using `127.0.0.1` brought queries down to around 0.13 seconds.
- My first version of the database had no actual spatial index. With only a few files it made no difference, so I only noticed when I tested with a much bigger catalogue.
- COPC only helps when files are large and queries are small. On my small sample files it saved very little, which is why I tested on full-size tiles.

## Next steps

- Deploy it on AWS (files in S3, the API on Lambda or Fargate, the database on RDS)
- Add automated tests and a CI pipeline
- Use COPC's level of detail for quick previews

---

Gregory Dettling · [LinkedIn](https://linkedin.com/in/gregory-dettling) · AWS Certified Solutions Architect – Associate
