from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.utility.envvalues import get_env_value

DATABASE_URL = get_env_value("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine,autoflush=False,autocommit=False)


def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()