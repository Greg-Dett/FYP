import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/copc_db")
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./data")
    PDAL_BIN: str = os.getenv("PDAL_BIN", "pdal") 

settings = Settings()
