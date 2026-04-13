import { useState, useEffect, useRef, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import { Database, Send, Terminal, Clock, Trash2, Layers, Zap, Search, Table2, Hash, ChevronRight } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

const SUGGESTIONS = [
  { text: "Show me all active users", icon: <Search size={16} /> },
  { text: "Find products under $50 sorted by price", icon: <Table2 size={16} /> },
  { text: "How many orders are pending?", icon: <Hash size={16} /> },
  { text: "Total revenue by payment method", icon: <Layers size={16} /> },
  { text: "Find products in Electronics category with rating above 4", icon: <Search size={16} /> },
  { text: "Show orders shipped to USA", icon: <Table2 size={16} /> },
];

function ResultsTable({ data }) {
  if (!data || data.length === 0) return null;

  const keys = Object.keys(data[0]);

  const formatCell = (val) => {
    if (val === null || val === undefined) return "null";
    if (typeof val === "boolean") return val ? "true" : "false";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  };

  return (
    <div className="results-container" data-testid="query-results-table">
      <div className="results-header">
        <span className="results-header-text">Results</span>
        <span className="results-count" data-testid="results-count">{data.length} row{data.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="results-table-wrapper">
        <table className="results-table">
          <thead>
            <tr>
              {keys.map((k) => (
                <th key={k}>{k}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} data-testid={`result-row-${i}`}>
                {keys.map((k) => (
                  <td key={k} title={formatCell(row[k])}>
                    {formatCell(row[k])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="results-meta">
        <span>{data.length} document{data.length !== 1 ? "s" : ""} returned</span>
      </div>
    </div>
  );
}

function QueryPreview({ query }) {
  if (!query) return null;
  const display = { ...query };
  delete display.explanation;

  return (
    <div className="query-preview" data-testid="mongo-query-preview">
      <div className="query-preview-header">
        <Terminal size={12} />
        MongoDB Query
      </div>
      <div className="query-preview-code">{JSON.stringify(display, null, 2)}</div>
    </div>
  );
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";

  return (
    <div className={`message ${message.role}`} data-testid={`chat-message-${message.role}`}>
      <div className="message-avatar">
        {isUser ? <Search size={16} /> : <Database size={16} />}
      </div>
      <div className="message-content">
        {isUser ? (
          <div className="message-text">{message.content}</div>
        ) : (
          <>
            {message.query_data?.explanation && (
              <div className="message-explanation">{message.query_data.explanation}</div>
            )}
            {message.query_data?.error && (
              <div className="error-text" data-testid="query-error">{message.query_data.error}</div>
            )}
            {message.query_data?.generated_query && (
              <QueryPreview query={message.query_data.generated_query} />
            )}
            {message.query_data?.results && message.query_data.results.length > 0 && (
              <ResultsTable data={message.query_data.results} />
            )}
            {message.query_data?.execution_time_ms !== undefined && (
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 10, display: "flex", gap: 12 }}>
                <span><Zap size={11} style={{ display: "inline", verticalAlign: "middle" }} /> {message.query_data.execution_time_ms}ms</span>
                <span>{message.query_data.row_count} result{message.query_data.row_count !== 1 ? "s" : ""}</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Sidebar({ schema, history, activeCollection, setActiveCollection, onHistoryClick, onClearHistory }) {
  return (
    <div className="sidebar" data-testid="sidebar-container">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Database size={20} className="accent" />
          <span>Ask<span className="accent">Base</span></span>
        </div>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-title">Schema</div>
        {Object.entries(schema?.schema || {}).map(([name, collectionInfo]) => (
          <div
            key={name}
            className={`schema-collection ${activeCollection === name ? "active" : ""}`}
            onClick={() => setActiveCollection(activeCollection === name ? null : name)}
            data-testid={`schema-collection-${name}`}
          >
            <div className="schema-collection-name">
              <Layers size={14} />
              {name}
            </div>
            <div className="schema-collection-count">
              {schema?.counts?.[name] ?? 0} documents
            </div>
            <div className="schema-fields">
              {Object.entries(collectionInfo.fields || {}).map(([fieldName, fieldType]) => (
                <div key={fieldName} className="schema-field" data-testid={`schema-field-${name}-${fieldName}`}>
                  <span className="field-name">{fieldName}</span>
                  <span className="field-type">{fieldType}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="history-section">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div className="sidebar-section-title" style={{ margin: 0 }}>History</div>
          {history.length > 0 && (
            <button className="clear-history-btn" onClick={onClearHistory} data-testid="clear-history-button">
              <Trash2 size={12} />
            </button>
          )}
        </div>
        {history.length === 0 ? (
          <div className="no-data-msg">No queries yet</div>
        ) : (
          history.map((item, i) => (
            <div key={item.id || i} className="history-item" onClick={() => onHistoryClick(item.question)} data-testid={`history-item-${i}`}>
              <div className="history-item-text">{item.question}</div>
              <div className="history-item-meta">
                <span>{item.row_count} rows</span>
                <span>{item.execution_time_ms}ms</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function WelcomeState({ onSuggestionClick }) {
  return (
    <div className="welcome-state" data-testid="welcome-state">
      <div className="welcome-icon">
        <Database size={36} />
      </div>
      <h1 className="welcome-title">Ask your database anything</h1>
      <p className="welcome-subtitle">
        Type a question in plain English and AskBase will generate and execute the MongoDB query for you.
      </p>
      <div className="suggestion-grid">
        {SUGGESTIONS.map((s, i) => (
          <div key={i} className="suggestion-card" onClick={() => onSuggestionClick(s.text)} data-testid={`suggestion-card-${i}`}>
            <div className="suggestion-card-icon">{s.icon}</div>
            <div className="suggestion-card-text">{s.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [schema, setSchema] = useState(null);
  const [history, setHistory] = useState([]);
  const [activeCollection, setActiveCollection] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const [dbReady, setDbReady] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const fetchSchema = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/schema`);
      setSchema(res.data);
      const total = Object.values(res.data.counts || {}).reduce((a, b) => a + b, 0);
      setDbReady(total > 0);
    } catch (e) {
      console.error("Failed to fetch schema", e);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/history?limit=15`);
      setHistory(res.data.history || []);
    } catch (e) {
      console.error("Failed to fetch history", e);
    }
  }, []);

  useEffect(() => {
    fetchSchema();
    fetchHistory();
  }, [fetchSchema, fetchHistory]);

  const seedDatabase = async () => {
    setSeeding(true);
    try {
      await axios.post(`${API}/seed`);
      await fetchSchema();
      setDbReady(true);
    } catch (e) {
      console.error("Failed to seed database", e);
    } finally {
      setSeeding(false);
    }
  };

  const sendQuery = async (question) => {
    if (!question.trim() || loading) return;

    const userMsg = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await axios.post(`${API}/query`, { question });
      const data = res.data;

      const assistantMsg = {
        id: data.id || crypto.randomUUID(),
        role: "assistant",
        content: data.explanation || "",
        query_data: data,
        timestamp: data.timestamp || new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      fetchHistory();
    } catch (e) {
      const errorMsg = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Sorry, something went wrong.",
        query_data: { error: e.response?.data?.detail || e.message, row_count: 0, execution_time_ms: 0 },
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    sendQuery(input);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuery(input);
    }
  };

  const clearHistory = async () => {
    try {
      await axios.delete(`${API}/history`);
      setHistory([]);
    } catch (e) {
      console.error("Failed to clear history", e);
    }
  };

  return (
    <>
      <div className="app-background" />
      <div className="app-container">
        <Sidebar
          schema={schema}
          history={history}
          activeCollection={activeCollection}
          setActiveCollection={setActiveCollection}
          onHistoryClick={(q) => setInput(q)}
          onClearHistory={clearHistory}
        />

        <div className="main-area" data-testid="chat-interface">
          <div className="chat-header">
            <div className="chat-header-title">
              <span className="status-dot online" style={{ marginRight: 8 }} />
              Connected to MongoDB
            </div>
            <div className="chat-header-stats">
              {schema && Object.entries(schema.counts || {}).map(([name, count]) => (
                <div key={name} className="stat-badge" data-testid={`stat-badge-${name}`}>
                  {name}: <span className="num">{count}</span>
                </div>
              ))}
              {!dbReady && (
                <button className="seed-button" onClick={seedDatabase} disabled={seeding} data-testid="seed-database-button">
                  {seeding ? "Seeding..." : "Seed Database"}
                </button>
              )}
              {dbReady && (
                <button className="seed-button" onClick={seedDatabase} disabled={seeding} data-testid="reseed-database-button">
                  {seeding ? "Seeding..." : "Re-seed"}
                </button>
              )}
            </div>
          </div>

          <div className="chat-messages" data-testid="chat-messages-area">
            {messages.length === 0 ? (
              <WelcomeState onSuggestionClick={(text) => sendQuery(text)} />
            ) : (
              messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
            )}

            {loading && (
              <div className="message assistant" data-testid="loading-indicator">
                <div className="message-avatar">
                  <Database size={16} />
                </div>
                <div className="message-content">
                  <div className="loading-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <form onSubmit={handleSubmit} className="input-wrapper" data-testid="query-input-form">
              <input
                type="text"
                className="input-field"
                placeholder={dbReady ? "Ask your database a question..." : "Seed the database first, then ask a question..."}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                data-testid="query-input"
              />
              <button type="submit" className="send-button" disabled={loading || !input.trim()} data-testid="submit-query-button">
                <Send size={18} />
              </button>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}

export default App;
