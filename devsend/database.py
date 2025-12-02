from sqlalchemy.orm import Session
from devsend.config import settings

engine = None
SessionLocal = None


def get_db_engine():
    global engine
    if engine is None:
        from devsend.models import get_engine
        engine = get_engine(settings.database_url)
    return engine


def get_db():
    global SessionLocal
    if SessionLocal is None:
        from sqlalchemy.orm import sessionmaker
        engine = get_db_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
