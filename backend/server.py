from fastapi import FastAPI, APIRouter, HTTPException
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
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Schema definition for the LLM
SCHEMA_DEFINITION = {
    "users": {
        "fields": {
            "user_id": "string (UUID)",
            "name": "string",
            "email": "string",
            "role": "string (admin, editor, viewer)",
            "department": "string",
            "is_active": "boolean",
            "created_at": "ISO datetime string",
            "last_login": "ISO datetime string or null"
        },
        "description": "User accounts in the system"
    },
    "orders": {
        "fields": {
            "order_id": "string (UUID)",
            "user_id": "string (references users.user_id)",
            "items": "array of objects with {product_name, quantity, unit_price}",
            "total_amount": "number",
            "status": "string (pending, processing, shipped, delivered, cancelled)",
            "payment_method": "string (credit_card, paypal, bank_transfer, crypto)",
            "shipping_address": "object with {city, state, country}",
            "created_at": "ISO datetime string",
            "updated_at": "ISO datetime string"
        },
        "description": "Customer orders with line items"
    },
    "products": {
        "fields": {
            "product_id": "string (UUID)",
            "name": "string",
            "price": "number",
            "category": "string (Electronics, Clothing, Books, Home, Sports, Food)",
            "stock": "integer",
            "rating": "number (1-5)",
            "tags": "array of strings",
            "supplier": "string",
            "is_available": "boolean",
            "created_at": "ISO datetime string"
        },
        "description": "Product catalog with categories and inventory"
    }
}

SYSTEM_PROMPT = """You are AskBase, an expert MongoDB query generator. You receive natural language questions and produce ONLY valid MongoDB query operations as JSON.

DATABASE SCHEMA:
""" + json.dumps(SCHEMA_DEFINITION, indent=2) + """

RULES:
1. Return ONLY a valid JSON object with these fields:
   - "collection": the collection name (users, orders, products)
   - "operation": one of "find", "aggregate", "count"
   - "query": the MongoDB filter/pipeline (as a JSON object or array for aggregations)
   - "projection": (optional) fields to include/exclude
   - "sort": (optional) sort specification
   - "limit": (optional) max documents to return (default 20)
   - "explanation": a brief human-readable explanation of what the query does

2. For date comparisons, use ISO date strings like "2025-01-15T00:00:00Z"
3. For aggregations, "query" should be an array of pipeline stages
4. NEVER wrap the JSON in markdown code blocks
5. NEVER include explanatory text outside the JSON
6. Always limit results to a reasonable number (max 50)
7. Use $regex for text search with "i" flag for case-insensitive
8. Today's date is """ + datetime.now(timezone.utc).strftime("%Y-%m-%d") + """

EXAMPLES:
Q: "Show me all active users"
{"collection":"users","operation":"find","query":{"is_active":true},"projection":{"_id":0},"limit":20,"explanation":"Find all users where is_active is true"}

Q: "How many orders are pending?"
{"collection":"orders","operation":"count","query":{"status":"pending"},"explanation":"Count orders with pending status"}

Q: "Find products under $50 sorted by price"
{"collection":"products","operation":"find","query":{"price":{"$lt":50}},"projection":{"_id":0},"sort":{"price":1},"limit":20,"explanation":"Find products with price less than 50, sorted ascending"}

Q: "Total revenue by payment method"
{"collection":"orders","operation":"aggregate","query":[{"$group":{"_id":"$payment_method","total_revenue":{"$sum":"$total_amount"},"order_count":{"$sum":1}}},{"$sort":{"total_revenue":-1}}],"explanation":"Aggregate total revenue grouped by payment method"}
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

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # user or assistant
    content: str
    query_data: Optional[dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Helpers
def sanitize_doc(doc):
    """Remove _id and convert non-serializable types."""
    if isinstance(doc, dict):
        return {k: sanitize_doc(v) for k, v in doc.items() if k != '_id'}
    if isinstance(doc, list):
        return [sanitize_doc(i) for i in doc]
    return doc


def parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown blocks."""
    text = text.strip()
    # Remove markdown code blocks
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        text = match.group(1).strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        brace_start = text.find('{')
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i+1])
                    except json.JSONDecodeError:
                        break
        raise ValueError(f"Could not parse LLM response as JSON: {text[:200]}")


async def execute_mongo_query(query_spec: dict) -> tuple:
    """Execute a MongoDB query and return (results, count)."""
    collection_name = query_spec.get("collection")
    operation = query_spec.get("operation", "find")
    query = query_spec.get("query", {})
    projection = query_spec.get("projection", {"_id": 0})
    sort_spec = query_spec.get("sort")
    limit = min(query_spec.get("limit", 20), 50)

    collection = db[collection_name]

    if operation == "find":
        cursor = collection.find(query, projection)
        if sort_spec:
            cursor = cursor.sort(list(sort_spec.items()))
        cursor = cursor.limit(limit)
        results = await cursor.to_list(limit)
        results = [sanitize_doc(r) for r in results]
        return results, len(results)

    elif operation == "aggregate":
        pipeline = query if isinstance(query, list) else [query]
        # Ensure _id exclusion in final projection if not specified
        cursor = collection.aggregate(pipeline)
        results = await cursor.to_list(50)
        results = [sanitize_doc(r) for r in results]
        return results, len(results)

    elif operation == "count":
        count = await collection.count_documents(query)
        return [{"count": count}], 1

    else:
        raise ValueError(f"Unsupported operation: {operation}")


# Routes
@api_router.get("/")
async def root():
    return {"message": "AskBase API is running"}


@api_router.get("/schema")
async def get_schema():
    """Return the database schema definition."""
    # Also get live counts
    counts = {}
    for coll_name in SCHEMA_DEFINITION:
        counts[coll_name] = await db[coll_name].count_documents({})
    return {"schema": SCHEMA_DEFINITION, "counts": counts}


@api_router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process a natural language query."""
    import time
    start_time = time.time()

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key not configured")

    session_id = request.session_id or str(uuid.uuid4())

    try:
        # Generate MongoDB query using LLM
        chat = LlmChat(
            api_key=api_key,
            session_id=f"askbase-{session_id}-{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT
        )
        chat.with_model("openai", "gpt-4o")

        user_msg = UserMessage(text=request.question)
        llm_response = await chat.send_message(user_msg)

        # Parse the LLM response
        query_spec = parse_llm_json(llm_response)

        # Validate collection
        if query_spec.get("collection") not in SCHEMA_DEFINITION:
            raise ValueError(f"Unknown collection: {query_spec.get('collection')}")

        # Execute the query
        results, row_count = await execute_mongo_query(query_spec)
        elapsed = int((time.time() - start_time) * 1000)

        response = QueryResponse(
            question=request.question,
            generated_query=query_spec,
            results=results,
            explanation=query_spec.get("explanation", ""),
            row_count=row_count,
            execution_time_ms=elapsed
        )

        # Save to history
        history_doc = {
            "id": response.id,
            "question": request.question,
            "generated_query": query_spec,
            "row_count": row_count,
            "execution_time_ms": elapsed,
            "timestamp": response.timestamp,
            "session_id": session_id
        }
        await db.query_history.insert_one(history_doc)

        return response

    except ValueError as e:
        elapsed = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=request.question,
            error=str(e),
            execution_time_ms=elapsed
        )
    except Exception as e:
        logger.error(f"Query processing error: {e}")
        elapsed = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=request.question,
            error=f"Failed to process query: {str(e)}",
            execution_time_ms=elapsed
        )


@api_router.get("/history")
async def get_history(limit: int = 20):
    """Get recent query history."""
    history = await db.query_history.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"history": history}


@api_router.delete("/history")
async def clear_history():
    """Clear query history."""
    await db.query_history.delete_many({})
    return {"message": "History cleared"}


@api_router.post("/seed")
async def seed_database():
    """Seed the database with sample data."""
    # Clear existing data
    for coll in ["users", "orders", "products"]:
        await db[coll].delete_many({})

    # --- USERS ---
    departments = ["Engineering", "Marketing", "Sales", "Finance", "HR", "Design", "Operations", "Legal"]
    roles = ["admin", "editor", "viewer"]
    first_names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank", "Iris", "Jack",
                   "Karen", "Leo", "Mona", "Nick", "Olivia", "Paul", "Quinn", "Rachel", "Sam", "Tina",
                   "Uma", "Victor", "Wendy", "Xander", "Yara", "Zane", "Amara", "Blake", "Chloe", "Derek"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                  "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee"]

    users = []
    for i in range(30):
        fname = first_names[i]
        lname = random.choice(last_names)
        created = datetime.now(timezone.utc) - timedelta(days=random.randint(30, 730))
        last_login = created + timedelta(days=random.randint(1, 60)) if random.random() > 0.15 else None
        users.append({
            "user_id": str(uuid.uuid4()),
            "name": f"{fname} {lname}",
            "email": f"{fname.lower()}.{lname.lower()}@example.com",
            "role": random.choice(roles),
            "department": random.choice(departments),
            "is_active": random.random() > 0.2,
            "created_at": created.isoformat(),
            "last_login": last_login.isoformat() if last_login else None
        })
    await db.users.insert_many(users)

    # --- PRODUCTS ---
    product_data = [
        ("Wireless Headphones", 79.99, "Electronics", ["audio", "wireless", "bluetooth"], "TechFlow"),
        ("Mechanical Keyboard", 149.99, "Electronics", ["gaming", "typing", "rgb"], "KeyMasters"),
        ("Running Shoes", 119.99, "Sports", ["running", "fitness", "outdoor"], "SprintX"),
        ("Yoga Mat", 34.99, "Sports", ["yoga", "fitness", "home"], "ZenGear"),
        ("Python Cookbook", 42.99, "Books", ["programming", "python", "learning"], "CodePress"),
        ("Data Science Handbook", 54.99, "Books", ["data", "science", "analytics"], "DataPub"),
        ("Ergonomic Chair", 399.99, "Home", ["office", "ergonomic", "comfort"], "ComfortPlus"),
        ("Standing Desk", 549.99, "Home", ["office", "standing", "health"], "DeskCo"),
        ("Protein Powder", 29.99, "Food", ["nutrition", "protein", "fitness"], "NutriMax"),
        ("Green Tea Pack", 14.99, "Food", ["tea", "organic", "healthy"], "TeaLeaf"),
        ("4K Monitor", 329.99, "Electronics", ["display", "4k", "ultrawide"], "VisionTech"),
        ("USB-C Hub", 39.99, "Electronics", ["usb", "hub", "connectivity"], "PortAll"),
        ("Winter Jacket", 189.99, "Clothing", ["winter", "warm", "outdoor"], "NorthStyle"),
        ("Cotton T-Shirt", 24.99, "Clothing", ["casual", "cotton", "summer"], "BasicWear"),
        ("Hiking Boots", 159.99, "Sports", ["hiking", "outdoor", "waterproof"], "TrailBlaze"),
        ("Basketball", 29.99, "Sports", ["basketball", "outdoor", "team"], "HoopStar"),
        ("Machine Learning Book", 49.99, "Books", ["ml", "ai", "deep-learning"], "AIPress"),
        ("JavaScript Guide", 37.99, "Books", ["javascript", "web", "programming"], "WebDev"),
        ("Smart Watch", 249.99, "Electronics", ["wearable", "fitness", "smart"], "WristTech"),
        ("Noise Cancelling Earbuds", 199.99, "Electronics", ["audio", "anc", "wireless"], "SoundPro"),
        ("Desk Lamp", 45.99, "Home", ["lighting", "led", "office"], "BrightLife"),
        ("Coffee Maker", 89.99, "Home", ["coffee", "kitchen", "morning"], "BrewMaster"),
        ("Whey Protein Bar", 19.99, "Food", ["protein", "snack", "fitness"], "FitBite"),
        ("Organic Honey", 12.99, "Food", ["organic", "natural", "sweet"], "PureHive"),
        ("Denim Jeans", 69.99, "Clothing", ["denim", "casual", "everyday"], "DenimCraft"),
    ]

    products = []
    for name, price, category, tags, supplier in product_data:
        products.append({
            "product_id": str(uuid.uuid4()),
            "name": name,
            "price": price,
            "category": category,
            "stock": random.randint(0, 500),
            "rating": round(random.uniform(2.5, 5.0), 1),
            "tags": tags,
            "supplier": supplier,
            "is_available": random.random() > 0.1,
            "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(10, 365))).isoformat()
        })
    await db.products.insert_many(products)

    # --- ORDERS ---
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    payment_methods = ["credit_card", "paypal", "bank_transfer", "crypto"]
    cities = [
        {"city": "New York", "state": "NY", "country": "USA"},
        {"city": "San Francisco", "state": "CA", "country": "USA"},
        {"city": "London", "state": "England", "country": "UK"},
        {"city": "Tokyo", "state": "Tokyo", "country": "Japan"},
        {"city": "Berlin", "state": "Berlin", "country": "Germany"},
        {"city": "Sydney", "state": "NSW", "country": "Australia"},
        {"city": "Toronto", "state": "ON", "country": "Canada"},
        {"city": "Mumbai", "state": "MH", "country": "India"},
        {"city": "Paris", "state": "IDF", "country": "France"},
        {"city": "Seoul", "state": "Seoul", "country": "South Korea"},
    ]

    orders = []
    for _ in range(50):
        user = random.choice(users)
        num_items = random.randint(1, 4)
        items = []
        total = 0
        for _ in range(num_items):
            prod = random.choice(products)
            qty = random.randint(1, 3)
            items.append({
                "product_name": prod["name"],
                "quantity": qty,
                "unit_price": prod["price"]
            })
            total += prod["price"] * qty
        created = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180))
        orders.append({
            "order_id": str(uuid.uuid4()),
            "user_id": user["user_id"],
            "items": items,
            "total_amount": round(total, 2),
            "status": random.choice(statuses),
            "payment_method": random.choice(payment_methods),
            "shipping_address": random.choice(cities),
            "created_at": created.isoformat(),
            "updated_at": (created + timedelta(hours=random.randint(1, 72))).isoformat()
        })
    await db.orders.insert_many(orders)

    counts = {
        "users": await db.users.count_documents({}),
        "orders": await db.orders.count_documents({}),
        "products": await db.products.count_documents({})
    }
    return {"message": "Database seeded successfully", "counts": counts}


@api_router.get("/stats")
async def get_stats():
    """Get database statistics."""
    counts = {}
    for coll_name in SCHEMA_DEFINITION:
        counts[coll_name] = await db[coll_name].count_documents({})
    return {"counts": counts, "total": sum(counts.values())}


# Include router and middleware
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
