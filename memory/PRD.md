# AskBase - PRD & Progress

## Original Problem Statement
Build a full-stack web app called AskBase with a chat interface where users type questions in plain English. A FastAPI backend receives the question, injects the database schema into a system prompt, and sends it to an LLM to generate a MongoDB query. The executor runs that query against MongoDB and returns formatted results back to the chat.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + Custom CSS (Glassmorphism theme)
- **Backend**: FastAPI (Python) with Motor (async MongoDB driver)
- **Database**: MongoDB (collections: users, orders, products)
- **LLM**: OpenAI GPT-4o via emergentintegrations library (Emergent LLM Key)

## User Personas
- **Data Analysts**: Query databases without knowing MongoDB syntax
- **Developers**: Quick data exploration without writing queries
- **Business Users**: Get answers from data using natural language

## Core Requirements
- Natural language to MongoDB query conversion
- Schema-aware query generation via prompt injection
- Query execution and formatted result display
- Chat interface with history
- Database schema viewer
- Sample data seeding

## What's Been Implemented (Jan 2026)
- Full chat interface with glassmorphism UI (Outfit, Work Sans, JetBrains Mono fonts)
- LLM-powered MongoDB query generation (GPT-4o)
- Query execution engine supporting find, aggregate, count operations
- Sidebar: Schema viewer with expandable fields, Query history
- Welcome state with 6 suggestion cards
- Database seeding with 30 users, 50 orders, 25 products (complex data)
- All backend APIs: /api/schema, /api/query, /api/seed, /api/history, /api/stats
- Responsive design

## Testing Status
- Backend: 100% pass
- Frontend: 95% pass (minor platform overlay, not app issue)
- Integration: 100% pass

## Prioritized Backlog
- **P0**: None (MVP complete)
- **P1**: Multi-turn conversations (follow-up questions), Export results to CSV
- **P2**: Schema auto-detection, Query editing before execution, Dark/Light theme toggle
- **P3**: Multiple database connections, Saved queries/bookmarks, Team sharing

## Next Tasks
- Add ability to edit generated query before execution
- Export query results to CSV/JSON
- Multi-turn conversation support (context-aware follow-ups)
