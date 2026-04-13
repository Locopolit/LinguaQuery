from fastapi import FastAPI, APIRouter, HTTPException
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://arunchaudhary@localhost:5432/postgres")

app = FastAPI()
api_router = APIRouter(prefix="/api")

# PostgreSQL Connection Pool
pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    # Auto-initialize 'emp' entity as requested
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS emp (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                department TEXT,
                salary NUMERIC,
                joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Check if table is empty, if so, auto-populate
        count = await conn.fetchval("SELECT COUNT(*) FROM emp")
        if count == 0:
            sample_data = [
                (str(uuid.uuid4()), "Alice Smith", "Engineer", "Product", 95000),
                (str(uuid.uuid4()), "Bob Jones", "Manager", "Sales", 110000),
                (str(uuid.uuid4()), "Charlie Brown", "Designer", "Marketing", 85000)
            ]
            await conn.executemany("""
                INSERT INTO emp (id, name, role, department, salary) 
                VALUES ($1, $2, $3, $4, $5)
            """, sample_data)

@app.on_event("shutdown")
async def shutdown():
    await pool.close()

# --- Schema definition and prompt generators (SQL version) ---
async def get_dynamic_schema() -> dict:
    """Introspect PostgreSQL to get the current schema dynamically."""
    schema_def = {}
    async with pool.acquire() as conn:
        # Get tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        for record in tables:
            table_name = record['table_name']
            if table_name == "query_history":
                continue
                
            # Get columns for this table
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = $1 AND table_schema = 'public'
            """, table_name)
            
            fields = {col['column_name']: col['data_type'] for col in columns}
            
            schema_def[table_name] = {
                "fields": fields,
                "description": f"PostgreSQL Table: {table_name}"
            }
    return schema_def

def get_system_prompt(schema_def: dict) -> str:
    return f"""You are AskBase, an advanced PostgreSQL database workbench and query generator. You receive natural language requests and produce ONLY valid PostgreSQL operations as JSON.

DATABASE SCHEMA:
{json.dumps(schema_def, indent=2)}

RULES:
1. Return ONLY a valid JSON object with these fields:
   - "operation": one of "SELECT", "INSERT", "CREATE", "UPDATE", "DELETE"
   - "sql": the raw PostgreSQL SQL string to execute
   - "explanation": a brief human-readable explanation of what the SQL does

2. DDL & DML OPERATIONS:
   - "CREATE": Use standard PostgreSQL `CREATE TABLE` syntax.
   - "INSERT": Use `INSERT INTO ... VALUES (...)`. Generate valid UUIDs for UUID columns using the 'gen_random_uuid()' function or providing a placeholder.
   - "UPDATE": Use standard `UPDATE` syntax.

3. Always terminate SQL with a semicolon.
4. Use double quotes for identifiers only if necessary (e.g. mixed case).
5. Today's date is {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
6. NEVER wrap the JSON in markdown code blocks.
7. EXAMPLES:
Q: "Show all employees"
{{"operation":"SELECT","sql":"SELECT * FROM emp;","explanation":"Fetching all records from the emp table"}}

Q: "Add a new employee named David"
{{"operation":"INSERT","sql":"INSERT INTO emp (id, name, role) VALUES (gen_random_uuid(), 'David', 'New Hire');","explanation":"Inserting a new employee record"}}
"""

# Models
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

# Helpers
def parse_llm_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match: text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace_start = text.find('{')
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == '{': depth += 1
                elif text[i] == '}': depth -= 1
                if depth == 0:
                    try: return json.loads(text[brace_start:i+1])
                    except json.JSONDecodeError: break
        raise ValueError(f"Could not parse LLM response as JSON: {text[:200]}")

async def call_ollama(question: str, system_prompt: str) -> str:
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
    payload = {
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{ollama_base}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

# Routes
@api_router.get("/")
async def root():
    return {"message": "AskBase SQL API is running"}

@api_router.get("/schema")
async def get_schema():
    schema_def = await get_dynamic_schema()
    counts = {}
    async with pool.acquire() as conn:
        for table_name in schema_def:
            counts[table_name] = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
    return {"schema": schema_def, "counts": counts}

@api_router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    import time
    start_time = time.time()
    session_id = request.session_id or str(uuid.uuid4())
    
    try:
        schema_def = await get_dynamic_schema()
        system_prompt = get_system_prompt(schema_def)
        
        # Step 1: LLM Query Generation
        llm_response = await call_ollama(request.question, system_prompt)
        query_spec = parse_llm_json(llm_response)
        sql = query_spec.get("sql", "")
        
        # Step 2: SQL Execution
        async with pool.acquire() as conn:
            if query_spec.get("operation") == "SELECT":
                records = await conn.fetch(sql)
                results = [dict(r) for r in records]
                # Convert UUIDs to strings for JSON serialization
                for res in results:
                    for k, v in res.items():
                        if isinstance(v, uuid.UUID): res[k] = str(v)
                        elif isinstance(v, datetime): res[k] = v.isoformat()
            else:
                await conn.execute(sql)
                results = [{"message": "Operation executed successfully"}]
        
        elapsed = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=request.question,
            generated_query=query_spec,
            results=results,
            explanation=query_spec.get("explanation", ""),
            row_count=len(results) if query_spec.get("operation") == "SELECT" else 1,
            execution_time_ms=elapsed
        )
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        return QueryResponse(question=request.question, error=str(e), execution_time_ms=elapsed)

@api_router.get("/stats")
async def get_stats():
    schema_def = await get_dynamic_schema()
    counts = {}
    async with pool.acquire() as conn:
        for table_name in schema_def:
            counts[table_name] = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
    return {"counts": counts, "total": sum(counts.values())}

# Middleware
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
