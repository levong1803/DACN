import { useCallback, useEffect, useState } from "react";

async function fetchJSON(url, options) {
  const r = await fetch(url, options);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json();
}

export default function App() {
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [lines, setLines] = useState([]);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState("chat");
  const [clearBusy, setClearBusy] = useState(false);

  const pushLine = useCallback((role, text) => {
    setLines((prev) => [...prev, { role, text, t: new Date().toISOString() }]);
  }, []);

  const send = async () => {
    const m = message.trim();
    if (!m || busy) return;
    setBusy(true);
    pushLine("user", m);
    setMessage("");
    try {
      const data = await fetchJSON("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: m, session_id: sessionId }),
      });
      setSessionId(data.session_id);
      pushLine("assistant", data.reply);
    } catch (e) {
      pushLine("error", e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const loadHistory = useCallback(async () => {
    try {
      const rows = await fetchJSON("/api/history?limit=200");
      setHistory(rows);
    } catch {
      setHistory([]);
    }
  }, []);

  const clearHistory = useCallback(async () => {
    if (!window.confirm("CẢNH BÁO: Hành động này sẽ xóa sập toàn bộ CSDL Log của Hệ thống Pentest!\nBạn có chắc chắn muốn dọn sạch không?")) return;
    setClearBusy(true);
    try {
      await fetchJSON("/api/history", { method: "DELETE" });
      setHistory([]);
    } catch (e) {
      alert("Lỗi khi dọn rác: " + e.message);
    } finally {
      setClearBusy(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "history") loadHistory();
  }, [tab, loadHistory]);

  return (
    <div style={styles.layout}>
      <header style={styles.header}>
        <h1 style={styles.title}>Pentest</h1>
        <nav style={styles.tabs}>
          <button
            type="button"
            style={tab === "chat" ? styles.tabOn : styles.tabOff}
            onClick={() => setTab("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            style={tab === "history" ? styles.tabOn : styles.tabOff}
            onClick={() => setTab("history")}
          >
            Lịch sử lệnh
          </button>
        </nav>
      </header>

      {tab === "chat" && (
        <main style={styles.main}>
          <div style={styles.log}>
            {lines.length === 0 && (
              <p style={styles.muted}>Nội dung</p>
            )}
            {lines.map((l, i) => (
              <div key={i} style={styles.lineWrap}>
                <span style={styles.badge(l.role)}>{l.role}</span>
                <pre style={styles.pre}>{l.text}</pre>
                <span style={styles.time}>{l.t}</span>
              </div>
            ))}
          </div>
          <div style={styles.inputRow}>
            <textarea
              style={styles.textarea}
              rows={3}
              placeholder="Nhập nội dung"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button type="button" style={styles.send} disabled={busy} onClick={send}>
              {busy ? "Đang chạy" : "Gửi"}
            </button>
          </div>
          {sessionId && (
            <p style={styles.mutedSmall}>Session: {sessionId}</p>
          )}
        </main>
      )}

      {tab === "history" && (
        <main style={styles.main}>
          <div style={{ display: "flex", gap: "10px" }}>
            <button type="button" style={styles.refresh} onClick={loadHistory}>
              Tải lại
            </button>
            <button type="button" style={styles.clearBtn} disabled={clearBusy} onClick={clearHistory}>
              {clearBusy ? "Đang xóa..." : "Xóa lịch sử"}
            </button>
          </div>
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Thời gian (UTC)</th>
                  <th>Role</th>
                  <th>Nội dung / tool</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td style={styles.tdTime}>{row.created_at}</td>
                    <td>{row.role}</td>
                    <td style={styles.tdContent}>
                      {row.tool_name && (
                        <strong>{row.tool_name}</strong>
                      )}
                      {row.tool_args && (
                        <pre style={styles.smallPre}>{row.tool_args}</pre>
                      )}
                      {row.content && <pre style={styles.smallPre}>{row.content}</pre>}
                      {row.tool_result && (
                        <pre style={styles.resultPre}>{row.tool_result}</pre>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </main>
      )}
    </div>
  );
}

const styles = {
  layout: { maxWidth: 920, margin: "0 auto", padding: "1.25rem" },
  header: { marginBottom: "1rem" },
  title: { fontSize: "1.35rem", margin: "0 0 0.35rem" },
  sub: { color: "#9aa0a6", margin: "0 0 0.75rem", fontSize: "0.95rem" },
  tabs: { display: "flex", gap: 8 },
  tabOn: {
    padding: "6px 14px",
    borderRadius: 8,
    border: "1px solid #3c4043",
    background: "#1a2332",
    color: "#e8eaed",
    cursor: "pointer",
  },
  tabOff: {
    padding: "6px 14px",
    borderRadius: 8,
    border: "1px solid #30343a",
    background: "transparent",
    color: "#9aa0a6",
    cursor: "pointer",
  },
  main: { display: "flex", flexDirection: "column", gap: 12 },
  log: {
    minHeight: 200,
    maxHeight: "42vh",
    overflow: "auto",
    padding: 12,
    background: "#1a1f26",
    borderRadius: 10,
    border: "1px solid #2d333b",
  },
  muted: { color: "#6b7280", margin: 0 },
  mutedSmall: { color: "#6b7280", fontSize: "0.8rem", margin: 0 },
  lineWrap: { marginBottom: 14 },
  badge: (role) => ({
    display: "inline-block",
    fontSize: "0.7rem",
    textTransform: "uppercase",
    padding: "2px 8px",
    borderRadius: 4,
    marginBottom: 4,
    background:
      role === "user"
        ? "#1e3a5f"
        : role === "assistant"
          ? "#1a3d2e"
          : "#4a2c2c",
    color: "#cbd5e1",
  }),
  pre: {
    margin: "4px 0 0",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontSize: "0.92rem",
  },
  time: { fontSize: "0.7rem", color: "#6b7280" },
  inputRow: { display: "flex", gap: 10, alignItems: "flex-end" },
  textarea: {
    flex: 1,
    resize: "vertical",
    padding: 10,
    borderRadius: 10,
    border: "1px solid #3c4043",
    background: "#161b22",
    color: "#e8eaed",
  },
  send: {
    padding: "12px 20px",
    borderRadius: 10,
    border: "none",
    background: "#2563eb",
    color: "#fff",
    cursor: "pointer",
    fontWeight: 600,
  },
  refresh: {
    alignSelf: "flex-start",
    padding: "8px 16px",
    borderRadius: 8,
    border: "1px solid #3c4043",
    background: "#1a2332",
    color: "#e8eaed",
    cursor: "pointer",
  },
  clearBtn: {
    alignSelf: "flex-start",
    padding: "8px 16px",
    borderRadius: 8,
    border: "1px solid #7f1d1d",
    background: "#450a0a",
    color: "#fca5a5",
    cursor: "pointer",
    fontWeight: "bold",
  },
  tableWrap: { overflow: "auto", maxHeight: "65vh" },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "0.85rem",
  },
  tdTime: { whiteSpace: "nowrap", verticalAlign: "top" },
  tdContent: { verticalAlign: "top", maxWidth: 480 },
  smallPre: {
    margin: "4px 0",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontSize: "0.8rem",
    color: "#cbd5e1",
  },
  resultPre: {
    margin: "4px 0 0",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontSize: "0.78rem",
    color: "#94a3b8",
    maxHeight: 120,
    overflow: "auto",
  },
};
