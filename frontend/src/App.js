import { useState, useEffect, useRef, useCallback } from "react";
import "@/App.css";
import "@/Auth.css";
import axios from "axios";
import { 
  Database, Send, Terminal, Clock, Trash2, Layers, Zap, Search, Table2, 
  Hash, ChevronRight, User, LogOut, Key, AtSign, Lock, AlertCircle
} from "lucide-react";

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

function AuthOverlay({ onLoginSuccess }) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      if (isLogin) {
        const params = new URLSearchParams();
        params.append('username', username);
        params.append('password', password);
        
        const res = await axios.post(`${API}/auth/login`, params);
        localStorage.setItem("token", res.data.access_token);
        localStorage.setItem("username", res.data.username);
        onLoginSuccess(res.data.access_token, res.data.username);
      } else {
        await axios.post(`${API}/auth/register`, { username, password });
        setIsLogin(true);
        setError("Account created! Please login.");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-overlay">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-icon">
            <Database size={28} />
          </div>
          <h2 className="auth-title">{isLogin ? "Welcome Back" : "Create Account"}</h2>
          <p className="auth-subtitle">
            {isLogin ? "Login to access your database workbench" : "Join AskBase to manage your data intuitively"}
          </p>
        </div>

        {error && (
          <div className="auth-error">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Username</label>
            <div style={{ position: "relative" }}>
              <AtSign size={16} style={{ position: "absolute", left: 14, top: 14, color: "rgba(255,255,255,0.3)" }} />
              <input 
                type="text" 
                className="auth-input" 
                placeholder="Enter username" 
                style={{ paddingLeft: 42 }}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <div style={{ position: "relative" }}>
              <Lock size={16} style={{ position: "absolute", left: 14, top: 14, color: "rgba(255,255,255,0.3)" }} />
              <input 
                type="password" 
                className="auth-input" 
                placeholder="••••••••" 
                style={{ paddingLeft: 42 }}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>
          <button type="submit" className="auth-button" disabled={loading}>
            {loading ? "Processing..." : (isLogin ? "Login to Workbench" : "Create Account")}
          </button>
        </form>

        <div className="auth-footer">
          {isLogin ? (
            <>Don't have an account? <span className="auth-link" onClick={() => setIsLogin(false)}>Sign Up</span></>
          ) : (
            <>Already have an account? <span className="auth-link" onClick={() => setIsLogin(true)}>Login</span></>
          )}
        </div>
      </div>
    </div>
  );
}

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
    <div className="results-container">
      <div className="results-header">
        <span className="results-header-text">Results</span>
        <span className="results-count">{data.length} row{data.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="results-table-wrapper">
        <table className="results-table">
          <thead>
            <tr>{keys.map((k) => <th key={k}>{k}</th>)}</tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i}>
                {keys.map((k) => <td key={k} title={formatCell(row[k])}>{formatCell(row[k])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QueryPreview({ query }) {
  if (!query) return null;
  const display = { ...query };
  delete display.explanation;
  return (
    <div className="query-preview">
      <div className="query-preview-header">
        <Terminal size={12} />
        MongoDB Query
      </div>
      <div className="query-preview-code">{query.sql}</div>
    </div>
  );
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">
        {isUser ? <Search size={16} /> : <Database size={16} />}
      </div>
      <div className="message-content">
        {isUser ? (
          <div className="message-text">{message.content}</div>
        ) : (
          <>
            {message.query_data?.explanation && <div className="message-explanation">{message.query_data.explanation}</div>}
            {message.query_data?.error && <div className="error-text">{message.query_data.error}</div>}
            {message.query_data?.generated_query && <QueryPreview query={message.query_data.generated_query} />}
            {message.query_data?.results && message.query_data.results.length > 0 && <ResultsTable data={message.query_data.results} />}
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

function Sidebar({ schema, history, username, onHistoryClick, onClearHistory, onLogout }) {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Database size={20} className="accent" />
          <span>Ask<span className="accent">Base</span></span>
        </div>
      </div>

      <div className="user-profile">
        <div className="user-avatar">
          <User size={14} />
        </div>
        <div className="user-info">
          <div className="user-name">{username}</div>
          <div className="user-status">Active Session</div>
        </div>
        <button className="logout-btn" onClick={onLogout} title="Logout">
          <LogOut size={14} />
        </button>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-title">Schema</div>
        {schema?.schema && Object.entries(schema.schema).map(([name, info]) => (
          <div key={name} className="schema-collection">
            <div className="schema-collection-name">
              <Layers size={14} />
              {name}
            </div>
            <div className="schema-fields">
              {Object.entries(info.fields || {}).map(([fname, ftype]) => (
                <div key={fname} className="schema-field">
                  <span className="field-name">{fname}</span>
                  <span className="field-type">{ftype}</span>
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
            <button className="clear-history-btn" onClick={onClearHistory}>
              <Trash2 size={12} />
            </button>
          )}
        </div>
        {history.length === 0 ? (
          <div className="no-data-msg">No queries yet</div>
        ) : (
          history.map((item, i) => (
            <div key={item.id || i} className="history-item" onClick={() => onHistoryClick(item.question)}>
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
    <div className="welcome-state">
      <div className="welcome-icon"><Database size={36} /></div>
      <h1 className="welcome-title">Ask your database anything</h1>
      <p className="welcome-subtitle">Type a question in plain English and AskBase will generate and execute MongoDB queries for you.</p>
      <div className="suggestion-grid">
        {SUGGESTIONS.map((s, i) => (
          <div key={i} className="suggestion-card" onClick={() => onSuggestionClick(s.text)}>
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
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [username, setUsername] = useState(localStorage.getItem("username"));
  const messagesEndRef = useRef(null);

  const apiHeaders = { headers: { Authorization: `Bearer ${token}` } };

  const fetchSchema = useCallback(async () => {
    if (!token) return;
    try {
      const res = await axios.get(`${API}/schema`, apiHeaders);
      setSchema(res.data);
    } catch (e) {
      if (e.response?.status === 401) handleLogout();
    }
  }, [token]);

  const fetchHistory = useCallback(async () => {
    if (!token) return;
    try {
      const res = await axios.get(`${API}/history?limit=15`, apiHeaders);
      setHistory(res.data.history || []);
    } catch (e) {
      if (e.response?.status === 401) handleLogout();
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      fetchSchema();
      fetchHistory();
    }
  }, [token, fetchSchema, fetchHistory]);

  const handleLogin = (newToken, newUsername) => {
    setToken(newToken);
    setUsername(newUsername);
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    setToken(null);
    setUsername(null);
    setMessages([]);
    setHistory([]);
    setSchema(null);
  };

  const sendQuery = async (question) => {
    if (!question.trim() || loading || !token) return;
    const userMsg = { id: crypto.randomUUID(), role: "user", content: question, timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await axios.post(`${API}/query`, { question }, apiHeaders);
      const data = res.data;
      const assistantMsg = { id: data.id || crypto.randomUUID(), role: "assistant", content: data.explanation || "", query_data: data, timestamp: data.timestamp || new Date().toISOString() };
      setMessages((prev) => [...prev, assistantMsg]);
      fetchHistory();
    } catch (e) {
      const errorMsg = { id: crypto.randomUUID(), role: "assistant", content: "Error processing query.", query_data: { error: e.response?.data?.detail || e.message }, timestamp: new Date().toISOString() };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = async () => {
    try {
      await axios.delete(`${API}/history`, apiHeaders);
      setHistory([]);
    } catch (e) { console.error(e); }
  };

  if (!token) return <AuthOverlay onLoginSuccess={handleLogin} />;

  return (
    <>
      <div className="app-background" />
      <div className="app-container">
        <Sidebar schema={schema} history={history} username={username} onHistoryClick={(q) => setInput(q)} onClearHistory={clearHistory} onLogout={handleLogout} />
        <div className="main-area">
          <div className="chat-header">
            <div className="chat-header-title">
              <span className="status-dot online" style={{ marginRight: 8 }} />
              Connected to MongoDB
            </div>
          </div>
          <div className="chat-messages">
            {messages.length === 0 ? <WelcomeState onSuggestionClick={sendQuery} /> : messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)}
            {loading && (
              <div className="message assistant">
                <div className="message-avatar"><Database size={16} /></div>
                <div className="message-content"><div className="loading-dots"><span /><span /><span /></div></div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="input-area">
            <form onSubmit={(e) => { e.preventDefault(); sendQuery(input); }} className="input-wrapper">
              <input type="text" className="input-field" placeholder="Ask your database a question..." value={input} onChange={(e) => setInput(e.target.value)} disabled={loading} />
              <button type="submit" className="send-button" disabled={loading || !input.trim()}><Send size={18} /></button>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}

export default App;
