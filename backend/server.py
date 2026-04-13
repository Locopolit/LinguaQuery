from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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
import httpx
from passlib.context import CryptContext
from jose import JWTError, jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "askbase")
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

app = FastAPI()
api_router = APIRouter(prefix="/api")

# MongoDB client
client = None
db = None
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Auth Helpers
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except JWTError: raise credentials_exception
    
    user = await db.users.find_one({"username": username})
    if user is None: raise credentials_exception
    return {"id": str(user["_id"]), "username": user["username"]}

@app.on_event("startup")
async def startup():
    global client, db
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # Initialize collections/indexes if needed
    await db.users.create_index("username", unique=True)
    
    # Seed emp table if empty
    count = await db.emp.count_documents({})
    if count == 0:
        sample_data = [
            {"_id": str(uuid.uuid4()), "name": "Alice Smith", "role": "Engineer", "department": "Product", "salary": 95000, "joined_at": datetime.now(timezone.utc)},
            {"_id": str(uuid.uuid4()), "name": "Bob Jones", "role": "Manager", "department": "Sales", "salary": 110000, "joined_at": datetime.now(timezone.utc)},
            {"_id": str(uuid.uuid4()), "name": "Charlie Brown", "role": "Designer", "department": "Marketing", "salary": 85000, "joined_at": datetime.now(timezone.utc)}
        ]
        await db.emp.insert_many(sample_data)

@app.on_event("shutdown")
async def shutdown():
    client.close()

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
    collections = await db.list_collection_names()
    for coll_name in collections:
        if coll_name in ["query_history", "users", "system.indexes"]: continue
        
        # Sample a document to infer fields
        doc = await db[coll_name].find_one()
        if doc:
            fields = {}
            for k, v in doc.items():
                if k == "_id": continue
                fields[k] = type(v).__name__
            schema_def[coll_name] = {"fields": fields, "description": f"Collection: {coll_name}"}
        else:
            schema_def[coll_name] = {"fields": {}, "description": f"Empty collection: {coll_name}"}
    return schema_def

def get_system_prompt(schema_def: dict) -> str:
    return f"""You are AskBase MongoDB assistant. Produce ONLY JSON for motor (async MongoDB driver):
{{
  "collection": "collection_name",
  "operation": "find|aggregate|count_documents",
  "query": {{ "key": "value" }},
  "projection": {{ "field": 1 }},
  "sort": [[ "field", 1 ]],
  "limit": 10,
  "pipeline": [ ... ],
  "explanation": "text"
}}
DATABASE SCHEMA:
{json.dumps(schema_def, indent=2)}
Rules: valid MQL. No markdown blocks."""

# --- Routes ---
@api_router.post("/auth/register")
async def register(user: UserCreate):
    existing = await db.users.find_one({"username": user.username})
    if existing: raise HTTPException(status_code=400, detail="Username already registered")
    hashed = get_password_hash(user.password)
    await db.users.insert_one({"username": user.username, "hashed_password": hashed, "created_at": datetime.now(timezone.utc)})
    return {"message": "User created successfully"}

@api_router.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.users.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user['hashed_password']):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user['username']})
    return {"access_token": access_token, "token_type": "bearer", "username": user['username']}

@api_router.get("/schema")
async def get_schema(current_user: dict = Depends(get_current_user)):
    schema_def = await get_dynamic_schema()
    counts = {}
    for coll_name in schema_def:
        counts[coll_name] = await db[coll_name].count_documents({})
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
        
        async with httpx.AsyncClient(timeout=120.0) as client_httpx:
            resp = await client_httpx.post(f"{ollama_base}/api/chat", json=payload)
            resp.raise_for_status()
            llm_text = resp.json()["message"]["content"]
        
        query_spec = json.loads(re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', llm_text).strip())
        coll = db[query_spec["collection"]]
        op = query_spec.get("operation", "find")
        
        results = []
        if op == "find":
            cursor = coll.find(query_spec.get("query", {}), query_spec.get("projection"))
            if "sort" in query_spec: cursor = cursor.sort(query_spec["sort"])
            if "limit" in query_spec: cursor = cursor.limit(query_spec["limit"])
            results = await cursor.to_list(length=100)
        elif op == "aggregate":
            results = await coll.aggregate(query_spec.get("pipeline", [])).to_list(length=100)
        elif op == "count_documents":
            count = await coll.count_documents(query_spec.get("query", {}))
            results = [{"count": count}]
        
        # Cleanup results for JSON
        for r in results:
            if "_id" in r: r["_id"] = str(r["_id"])
            for k, v in r.items():
                if isinstance(v, datetime): r[k] = v.isoformat()

        elapsed = int((time.time() - start_time) * 1000)
        # Save history
        await db.query_history.insert_one({
            "user_id": current_user['id'],
            "question": request.question,
            "query": query_spec,
            "row_count": len(results),
            "execution_time_ms": elapsed,
            "session_id": request.session_id,
            "timestamp": datetime.now(timezone.utc)
        })

        return QueryResponse(question=request.question, generated_query=query_spec, results=results, explanation=query_spec.get("explanation"), row_count=len(results), execution_time_ms=elapsed)
    except Exception as e:
        return QueryResponse(question=request.question, error=str(e), execution_time_ms=int((time.time() - start_time) * 1000))

@api_router.get("/history")
async def get_history(limit: int = 15, current_user: dict = Depends(get_current_user)):
    records = await db.query_history.find({"user_id": current_user['id']}).sort("timestamp", -1).limit(limit).to_list(length=limit)
    for r in records: 
        r["id"] = str(r["_id"])
        del r["_id"]
        if "timestamp" in r: r["timestamp"] = r["timestamp"].isoformat()
    return {"history": records}

@api_router.delete("/history")
async def clear_history(current_user: dict = Depends(get_current_user)):
    await db.query_history.delete_many({"user_id": current_user['id']})
    return {"message": "History cleared"}

@api_router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    schema_def = await get_dynamic_schema()
    counts = {}
    for coll_name in schema_def:
        counts[coll_name] = await db[coll_name].count_documents({})
    return {"counts": counts, "total": sum(counts.values())}

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
