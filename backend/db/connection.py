from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# Render and other cloud Postgres need postgresql:// and often SSL
_url = DATABASE_URL.strip()
if _url.startswith("postgres://"):
    _url = "postgresql://" + _url[11:]
if "render.com" in _url and "sslmode=" not in _url:
    _url += "?sslmode=require" if "?" not in _url else "&sslmode=require"

engine = create_engine(
    _url,
    pool_pre_ping=True,
    pool_size=5,
    echo=False
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

def get_db():
    """
    FastAPI dependency — yields a session per request, always closes it.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_connection():
    """Ping DB on startup."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Database connection OK")