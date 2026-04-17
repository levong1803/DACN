import { useCallback, useEffect, useState, useRef } from "react";
import { wstgCategories } from "./wstgData";

async function fetchJSON(url, options) {
  const r = await fetch(url, options);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json();
}

export default function App() {
  const MAX_CONCURRENT_CHAT = 3;
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [lines, setLines] = useState([]);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState("chat");
  const [clearBusy, setClearBusy] = useState(false);
  const [queue, setQueue] = useState([]);
  const [activeWorkers, setActiveWorkers] = useState(0);

  // WSTG state
  const [targetUrl, setTargetUrl] = useState("");
  const [openCat, setOpenCat] = useState(null);
  const [wstgStatus, setWstgStatus] = useState({});
  const [wstgRunning, setWstgRunning] = useState({});
  const [wstgResult, setWstgResult] = useState(null);

  const queueRef = useRef([]);
  const activeWorkersRef = useRef(0);
  const sessionIdRef = useRef(null);

  const pushLine = useCallback((role, text) => {
    setLines((prev) => [...prev, { role, text, t: new Date().toISOString() }]);
  }, []);

  // ── Queue system (parallel workers) ──
  const processQueue = useCallback(() => {
    while (activeWorkersRef.current < MAX_CONCURRENT_CHAT && queueRef.current.length > 0) {
      const nextMsg = queueRef.current[0];
      queueRef.current = queueRef.current.slice(1);
      setQueue([...queueRef.current]);

      activeWorkersRef.current += 1;
      setActiveWorkers(activeWorkersRef.current);
      setBusy(true);
      pushLine("user", nextMsg.text);

      fetchJSON("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: nextMsg.text, session_id: sessionIdRef.current }),
      })
        .then((data) => {
          sessionIdRef.current = data.session_id;
          setSessionId(data.session_id);
          pushLine("assistant", data.reply);
        })
        .catch((e) => {
          pushLine("error", e.message || String(e));
        })
        .finally(() => {
          activeWorkersRef.current -= 1;
          setActiveWorkers(activeWorkersRef.current);
          if (activeWorkersRef.current === 0 && queueRef.current.length === 0) {
            setBusy(false);
          }
          processQueue();
        });
    }
  }, [pushLine]);

  const enqueueMessage = () => {
    const m = message.trim();
    if (!m) return;
    setMessage("");
    queueRef.current.push({ id: Date.now() + Math.random(), text: m });
    setQueue([...queueRef.current]);
    processQueue();
  };

  const removeFromQueue = (id) => {
    queueRef.current = queueRef.current.filter((item) => item.id !== id);
    setQueue([...queueRef.current]);
  };

  // ── History ──
  const loadHistory = useCallback(async () => {
    try {
      const rows = await fetchJSON("/api/history?limit=200");
      setHistory(rows);
    } catch {
      setHistory([]);
    }
  }, []);

  const clearHistory = useCallback(async () => {
    if (!window.confirm("CẢNH BÁO: Bạn có chắc muốn xóa dữ liệu không?")) return;
    setClearBusy(true);
    try {
      await fetchJSON("/api/history", { method: "DELETE" });
      setHistory([]);
    } catch (e) {
      alert("Lỗi khi xóa: " + e.message);
    } finally {
      setClearBusy(false);
    }
  }, []);

  // ── WSTG ──
  const loadWstgStatus = useCallback(async () => {
    try {
      const rows = await fetchJSON("/api/wstg-status");
      const map = {};
      rows.forEach((r) => { map[r.wstg_id] = r; });
      setWstgStatus(map);
    } catch {
      /* bảng chưa tạo thì bỏ qua */
    }
  }, []);

  const runWstgTest = async (test) => {
    const t = targetUrl.trim();
    if (!t) {
      alert("Vui lòng nhập URL mục tiêu trước khi chạy!");
      return;
    }
    
    // Giới hạn chạy song song tối đa 3 test case
    if (Object.keys(wstgRunning).length >= 3) {
      alert("Hệ thống đang chạy tối đa 3 Test Case song song. Vui lòng đợi!");
      return;
    }

    const prompt = test.promptTemplate.replace(/\{target\}/g, t);
    setWstgRunning(prev => ({ ...prev, [test.wstgId]: true }));
    setWstgResult(null);
    try {
      const data = await fetchJSON("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: prompt, session_id: sessionIdRef.current }),
      });
      sessionIdRef.current = data.session_id;
      setSessionId(data.session_id);
      setWstgResult({ wstgId: test.wstgId, reply: data.reply });

      const currentStatus = wstgStatus[test.wstgId]?.status || "not_started";
      await fetchJSON("/api/wstg-status", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wstg_id: test.wstgId,
          status: currentStatus,
          target_url: t,
          result_summary: data.reply.slice(0, 4000),
        }),
      });
      setWstgStatus((prev) => ({
        ...prev,
        [test.wstgId]: {
          ...prev[test.wstgId],
          wstg_id: test.wstgId,
          status: currentStatus,
          target_url: t,
          result_summary: data.reply.slice(0, 4000),
        },
      }));
    } catch (e) {
      setWstgResult({ wstgId: test.wstgId, reply: "Lỗi: " + e.message });
    } finally {
      setWstgRunning(prev => {
        const next = { ...prev };
        delete next[test.wstgId];
        return next;
      });
    }
  };

  const updateStatus = async (wstgId, newStatus) => {
    const prev = wstgStatus[wstgId] || {};
    try {
      await fetchJSON("/api/wstg-status", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wstg_id: wstgId,
          status: newStatus,
          target_url: prev.target_url || targetUrl || null,
          result_summary: prev.result_summary || null,
        }),
      });
      setWstgStatus((p) => ({ ...p, [wstgId]: { ...prev, wstg_id: wstgId, status: newStatus } }));
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (tab === "history") loadHistory();
    if (tab === "wstg") loadWstgStatus();
  }, [tab, loadHistory, loadWstgStatus]);

  const statusIcon = (wstgId) => {
    const s = wstgStatus[wstgId]?.status;
    if (s === "pass") return "✅";
    if (s === "issue") return "⚠️";
    return "⬜";
  };

  return (
    <div className="app-layout">
      <header className="app-header">
        <h1 className="app-title">Pentest</h1>
        <nav className="app-tabs">
          {["chat", "wstg", "history"].map((t) => (
            <button
              key={t}
              type="button"
              className={tab === t ? "tab-btn active" : "tab-btn"}
              onClick={() => setTab(t)}
            >
              {t === "chat" ? "Chat" : t === "wstg" ? "WSTG Checklist" : "Lịch sử lệnh"}
            </button>
          ))}
        </nav>
      </header>

      {/* ═══════ TAB CHAT ═══════ */}
      {tab === "chat" && (
        <main className="main-area">
          <div className="chat-log">
            {lines.length === 0 && <p className="muted">Nội dung</p>}
            {lines.map((l, i) => (
              <div key={i} className="line-wrap">
                <span className={`badge badge-${l.role}`}>{l.role}</span>
                <pre className="line-pre">{l.text}</pre>
                <span className="line-time">{l.t}</span>
              </div>
            ))}
          </div>
          {queue.length > 0 && (
            <div className="queue-box">
              <p className="queue-label">Đang chờ xử lý ({queue.length}):</p>
              {queue.map((item) => (
                <div key={item.id} className="queue-item">
                  <span className="queue-text" title={item.text}>{item.text}</span>
                  <button className="queue-rm" onClick={() => removeFromQueue(item.id)}>Xóa</button>
                </div>
              ))}
            </div>
          )}
          <div className="input-row">
            <textarea
              className="chat-input"
              rows={3}
              placeholder="Nhập nội dung"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enqueueMessage(); } }}
            />
            <button type="button" className="btn-send" onClick={enqueueMessage}>
              {busy ? `Đang chạy (${activeWorkers}/${MAX_CONCURRENT_CHAT}) • chờ ${queue.length}` : "Gửi"}
            </button>
          </div>
          {sessionId && <p className="muted-small">Session: {sessionId}</p>}
        </main>
      )}

      {/* ═══════ TAB WSTG ═══════ */}
      {tab === "wstg" && (
        <main className="main-area">
          <div className="wstg-target-row">
            <label className="wstg-label">🎯 URL mục tiêu:</label>
            <input
              className="wstg-input"
              type="text"
              placeholder="VD: testphp.vulnweb.com hoặc http://testphp.vulnweb.com/listproducts.php?cat=1"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
            />
          </div>

          <div className="wstg-categories">
            {wstgCategories.map((cat) => (
              <div key={cat.id} className="wstg-cat">
                <button
                  className={`wstg-cat-header ${openCat === cat.id ? "open" : ""}`}
                  onClick={() => setOpenCat(openCat === cat.id ? null : cat.id)}
                >
                  <span className="wstg-cat-icon">{cat.icon}</span>
                  <span className="wstg-cat-name">{cat.id}. {cat.name}</span>
                  <span className="wstg-cat-count">
                    {cat.tests.filter((t) => wstgStatus[t.wstgId]?.status === "pass").length}/{cat.tests.length}
                  </span>
                  <span className="wstg-arrow">{openCat === cat.id ? "▼" : "▶"}</span>
                </button>

                {openCat === cat.id && (
                  <div className="wstg-tests">
                    {cat.tests.map((test) => (
                      <div key={test.id} className="wstg-test-row">
                        <span className="wstg-status-icon">{statusIcon(test.wstgId)}</span>
                        <div className="wstg-test-info">
                          <span className="wstg-test-id">{test.wstgId}</span>
                          <span className="wstg-test-name">{test.name}</span>
                          <span className="wstg-test-tools">{test.tools}</span>
                        </div>
                        <div className="wstg-test-actions">
                          <select
                            className="wstg-status-select"
                            value={wstgStatus[test.wstgId]?.status || "not_started"}
                            onChange={(e) => updateStatus(test.wstgId, e.target.value)}
                          >
                            <option value="not_started">Not started</option>
                            <option value="pass">Pass</option>
                            <option value="issue">Issue</option>
                          </select>
                          <button
                            className="btn-run"
                            disabled={!!wstgRunning[test.wstgId]}
                            onClick={() => runWstgTest(test)}
                          >
                            {wstgRunning[test.wstgId] ? "⏳ Đang chạy" : "▶ Chạy"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {wstgResult && (
            <div className="wstg-result-box">
              <div className="wstg-result-header">
                Kết quả: <strong>{wstgResult.wstgId}</strong>
              </div>
              <pre className="wstg-result-content">{wstgResult.reply}</pre>
            </div>
          )}
        </main>
      )}

      {/* ═══════ TAB HISTORY ═══════ */}
      {tab === "history" && (
        <main className="main-area">
          <div className="history-actions">
            <button type="button" className="btn-refresh" onClick={loadHistory}>Tải lại</button>
            <button type="button" className="btn-clear" disabled={clearBusy} onClick={clearHistory}>
              {clearBusy ? "Đang xóa..." : "Xóa lịch sử"}
            </button>
          </div>
          <div className="table-wrap">
            <table className="history-table">
              <thead>
                <tr><th>ID</th><th>Thời gian (UTC)</th><th>Role</th><th>Nội dung / tool</th></tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td className="td-time">{row.created_at}</td>
                    <td>{row.role}</td>
                    <td className="td-content">
                      {row.tool_name && <strong>{row.tool_name}</strong>}
                      {row.tool_args && <pre className="small-pre">{row.tool_args}</pre>}
                      {row.content && <pre className="small-pre">{row.content}</pre>}
                      {row.tool_result && <pre className="result-pre">{row.tool_result}</pre>}
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
