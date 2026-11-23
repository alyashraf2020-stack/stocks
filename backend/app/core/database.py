from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import LEGACY_DATABASE, RUNTIME_DATABASE, settings
from app.core.sqlite_backup import backup_database

def create_database_engine(database_url: str):
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True)
    if url.database and Path(url.database).resolve() == LEGACY_DATABASE:
        url = url.set(database=RUNTIME_DATABASE.as_posix())
    if url.database and Path(url.database).resolve() == RUNTIME_DATABASE and not RUNTIME_DATABASE.exists():
        try:
            backup_database(LEGACY_DATABASE, RUNTIME_DATABASE)
        except FileExistsError:
            pass  # Another process published its verified backup first.
    return create_engine(url, connect_args={"check_same_thread": False})


engine = create_database_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
