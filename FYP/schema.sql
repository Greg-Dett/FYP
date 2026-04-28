CREATE EXTENSION IF NOT EXISTS postgis;
--this i s table for storing copc files
CREATE TABLE IF NOT EXISTS copc_files (
  id              BIGSERIAL PRIMARY KEY,  --uncrementing number
  file_name       TEXT NOT NULL,
  file_path       TEXT NOT NULL UNIQUE, 
  srid            INTEGER NOT NULL DEFAULT 29902, --29902 is the coordinate system used in the dataset provided. it represents the irish national grid
  bounds          box3d NOT NULL --3d bounding box represent the entire area that the file contains the points of
);

