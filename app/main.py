from __future__ import annotations

from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from typing import Generator
import uvicorn

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/vector_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

app = FastAPI()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
    
@app.get("/")
def read_root():
    return {"Message:": "Hello World"}

@app.get("/db-test")
def test_db(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("SELECT version();")).scalar_one()
        return { "status": "connected", "postgres_version": result }
    except Exception as e:
        return { "status": "error", "detail": str(e) }

@app.get("/vector-test")
def vector_test(db: Session = Depends(get_db)):
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        db.execute(text("""
             CREATE TABLE IF NOT EXISTS test_vectors (
                    id SERIAL PRIMARY KEY,
                    embedding VECTOR(3)      
                );           
        """))
        db.execute(text("INSERT INTO test_vectors (embedding) VALUES ('[1, 2, 3]') ON CONFLICT DO NOTHING;"))
        result = db.execute(text("SELECT * FROM test_vectors LIMIT 1")).fetchone()
        db.commit()
        return { "vector_extension": "working", "sample_row": str(result) }
    except Exception as e:
        return { "error": str(e) }
    
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)