from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import asyncpg
import os
import logging
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
import uuid
from datetime import datetime, timezone, timedelta
import random
import httpx  # for calling local Ollama REST API
from passlib.context import CryptContext
from jose import JWTError, jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://arunchaudhary@localhost:5432/postgres")
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

app = FastAPI()
api_router = APIRouter(prefix="/api")

# PostgreSQL Connection Pool
pool = None
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Auth Helpers
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, username FROM users WHERE username = $1", username)
        if user is None:
            raise credentials_exception
        return dict(user)

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        # Tables creation
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS emp (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                department TEXT,
                salary NUMERIC,
                joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS query_history (
                id UUID PRIMARY KEY,
                user_id UUID REFERENCES users(id),
                question TEXT NOT NULL,
                sql TEXT NOT NULL,
                explanation TEXT,
                row_count INTEGER,
                execution_time_ms INTEGER,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT
            );
        """)
        # Auto-seed emp table if empty
        count = await conn.fetchval("SELECT COUNT(*) FROM emp")
        if count == 0:
            sample_data = [
                (str(uuid.uuid4()), "Alice Smith", "Engineer", "Product", 95000),
                (str(uuid.uuid4()), "Bob Jones", "Manager", "Sales", 110000),
                (str(uuid.uuid4()), "Charlie Brown", "Designer", "Marketing", 85000)
            ]
            await conn.executemany("INSERT INTO emp (id, name, role, department, salary) VALUES ($1, $2, $3, $4, $5)", sample_data)

@app.on_event("shutdown")
async def shutdown():
    await pool.close()

# Models
class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    username: str
    password: str

class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    generated_query: Optional[dict] = None
    results: Optional[Any] = None
    error: Optional[str] = None
    explanation: Optional[str] = None
    row_count: int = 0
    execution_time_ms: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# --- Schema definition and prompt generators ---
async def get_dynamic_schema() -> dict:
    schema_def = {}
    async with pool.acquire() as conn:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        for record in tables:
            table_name = record['table_name']
            if table_name in ["query_history", "users"]: continue
            columns = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = $1 AND table_schema = 'public'", table_name)
            fields = {col['column_name']: col['data_type'] for col in columns}
            schema_def[table_name] = {"fields": fields, "description": f"Table: {table_name}"}
    return schema_def

def get_system_prompt(schema_def: dict) -> str:
    return f"""You are AskBase SQL assistant. Produce ONLY JSON:
{{
  "operation": "SELECT|INSERT|CREATE|UPDATE|DELETE",
  "sql": "valid PostgreSQL SQL statement;",
  "explanation": "text"
}}
DATABASE SCHEMA:
{json.dumps(schema_def, indent=2)}
Rules: valid SQL, gen_random_uuid() for IDs. No markdown blocks."""

# --- Routes ---
@api_router.post("/auth/register")
async def register(user: UserCreate):
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE username = $1", user.username)
        if existing: raise HTTPException(status_code=400, detail="Username already registered")
        user_id = uuid.uuid4()
        hashed = get_password_hash(user.password)
        await conn.execute("INSERT INTO users (id, username, hashed_password) VALUES ($1, $2, $3)", user_id, user.username, hashed)
        return {"message": "User created successfully"}

@api_router.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE username = $1", form_data.username)
        if not user or not verify_password(form_data.password, user['hashed_password']):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        access_token = create_access_token(data={"sub": user['username']})
        return {"access_token": access_token, "token_type": "bearer", "username": user['username']}

@api_router.get("/schema")
async def get_schema(current_user: dict = Depends(get_current_user)):
    schema_def = await get_dynamic_schema()
    counts = {}
    async with pool.acquire() as conn:
        for table_name in schema_def:
            counts[table_name] = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
    return {"schema": schema_def, "counts": counts}

@api_router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    import time
    start_time = time.time()
    try:
        schema_def = await get_dynamic_schema()
        system_prompt = get_system_prompt(schema_def)
        
        ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
        payload = {"model": ollama_model, "messages": [{"role":"system","content":system_prompt}, {"role":"user","content":request.question}], "stream": False}
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{ollama_base}/api/chat", json=payload)
            resp.raise_for_status()
            llm_text = resp.json()["message"]["content"]
        
        query_spec = json.loads(re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', llm_text).strip())
        sql = query_spec["sql"]
        
        async with pool.acquire() as conn:
            if query_spec.get("operation") == "SELECT":
                records = await conn.fetch(sql)
                results = [dict(r) for r in records]
                for r in results:
                    for k, v in r.items():
                        if isinstance(v, uuid.UUID): r[k] = str(v)
                        elif isinstance(v, datetime): r[k] = v.isoformat()
            else:
                await conn.execute(sql)
                results = [{"message": "Success"}]
            
            elapsed = int((time.time() - start_time) * 1000)
            # Save history
            await conn.execute("""
                INSERT INTO query_history (id, user_id, question, sql, explanation, row_count, execution_time_ms, session_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, uuid.uuid4(), current_user['id'], request.question, sql, query_spec.get("explanation"), len(results), elapsed, request.session_id)

        return QueryResponse(question=request.question, generated_query=query_spec, results=results, explanation=query_spec.get("explanation"), row_count=len(results), execution_time_ms=elapsed)
    except Exception as e:
        return QueryResponse(question=request.question, error=str(e), execution_time_ms=int((time.time() - start_time) * 1000))

@api_router.get("/history")
async def get_history(limit: int = 15, current_user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        records = await conn.fetch("SELECT id, question, row_count, execution_time_ms, timestamp FROM query_history WHERE user_id = $1 ORDER BY timestamp DESC LIMIT $2", current_user['id'], limit)
        return {"history": [dict(r) for r in records]}

@api_router.delete("/history")
async def clear_history(current_user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM query_history WHERE user_id = $1", current_user['id'])
    return {"message": "History cleared"}

@api_router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    schema_def = await get_dynamic_schema()
    counts = {}
    async with pool.acquire() as conn:
        for table_name in schema_def:
            counts[table_name] = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
    return {"counts": counts, "total": sum(counts.values())}

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
