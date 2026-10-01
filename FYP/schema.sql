CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS copc_files (
  id         BIGSERIAL PRIMARY KEY,
  file_name  TEXT NOT NULL,
  file_path  TEXT NOT NULL UNIQUE,
  srid       INTEGER NOT NULL DEFAULT 29902,
  bounds     geometry NOT NULL   -- 3D box stored as geometry so it can be indexed
);

CREATE INDEX IF NOT EXISTS copc_files_bounds_idx
  ON copc_files USING GIST (bounds gist_geometry_ops_nd);