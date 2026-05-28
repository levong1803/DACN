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
  const [showLogs, setShowLogs] = useState({});
  const [wstgDetails, setWstgDetails] = useState({});

  // Run All state
  const [runAllActive, setRunAllActive] = useState(false);
  const [runAllProgress, setRunAllProgress] = useState({ current: 0, total: 0, currentTest: null });
  const [runAllResults, setRunAllResults] = useState({ pass: 0, issue: 0, needs_review: 0, error: 0 });
  const [runAllLog, setRunAllLog] = useState([]);
  const runAllStopRef = useRef(false);
  const [showReport, setShowReport] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [reportLogs, setReportLogs] = useState({});
  const [promptLogs, setPromptLogs] = useState({});

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
        body: JSON.stringify({
          message: prompt,
          session_id: sessionIdRef.current,
          wstg_id: test.wstgId
        }),
      });
      sessionIdRef.current = data.session_id;
      setSessionId(data.session_id);
      setWstgResult({ wstgId: test.wstgId, reply: data.reply });

      // Đọc lại status mới nhất từ DB (Backend đã tự parse [CONCLUSION])
      await loadWstgStatus();
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

  // ── Run All Tests ──
  const runAllTests = async () => {
    const t = targetUrl.trim();
    if (!t) { alert("Vui l\u00f2ng nh\u1eadp URL m\u1ee5c ti\u00eau tr\u01b0\u1edbc!"); return; }
    if (runAllActive) return;

    const allTests = wstgCategories.flatMap(cat => cat.tests);
    setRunAllActive(true);
    runAllStopRef.current = false;
    setRunAllProgress({ current: 0, total: allTests.length, currentTest: null });
    setRunAllResults({ pass: 0, issue: 0, needs_review: 0, error: 0 });
    setRunAllLog([]);

    const results = { pass: 0, issue: 0, needs_review: 0, error: 0 };

    for (let i = 0; i < allTests.length; i++) {
      if (runAllStopRef.current) {
        setRunAllLog(prev => [...prev, { wstgId: "STOPPED", status: "info", msg: `D\u1eebng t\u1ea1i test #${i + 1}` }]);
        break;
      }

      // B\u1ecf qua test \u0111\u00e3 pass ho\u1eb7c issue
      const existing = wstgStatus[allTests[i].wstgId]?.status;
      if (existing === "pass" || existing === "issue") {
        setRunAllLog(prev => [...prev, { wstgId: allTests[i].wstgId, status: existing, msg: "\u0110\u00e3 c\u00f3 k\u1ebft qu\u1ea3, b\u1ecf qua" }]);
        results[existing]++;
        setRunAllResults({ ...results });
        setRunAllProgress({ current: i + 1, total: allTests.length, currentTest: allTests[i].wstgId });
        continue;
      }

      const test = allTests[i];
      const prompt = test.promptTemplate.replace(/\{target\}/g, t);
      setRunAllProgress({ current: i + 1, total: allTests.length, currentTest: test.wstgId });
      setWstgRunning(prev => ({ ...prev, [test.wstgId]: true }));

      try {
        const data = await fetchJSON("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: prompt, session_id: sessionIdRef.current, wstg_id: test.wstgId }),
        });
        sessionIdRef.current = data.session_id;
        setSessionId(data.session_id);

        // Parse conclusion
        const m = (data.reply || "").match(/\[CONCLUSION\]:\s*\[?(PASS|ISSUE|NEEDS_REVIEW)\]?/i);
        const status = m ? m[1].toLowerCase() : "needs_review";
        results[status]++;
        setRunAllResults({ ...results });
        setRunAllLog(prev => [...prev, { wstgId: test.wstgId, status, msg: (data.reply || "").substring(0, 150) }]);
        await loadWstgStatus();
      } catch (e) {
        const errMsg = e.message || String(e);
        results.error++;
        setRunAllResults({ ...results });
        setRunAllLog(prev => [...prev, { wstgId: test.wstgId, status: "error", msg: errMsg }]);
        
        if (errMsg.includes("429") || errMsg.toLowerCase().includes("quota")) {
          setRunAllLog(prev => [...prev, { wstgId: "STOPPED", status: "error", msg: "\u26A0\uFE0F H\u1ebft API Quota! T\u1ef1 \u0111\u1ed9ng d\u1eebng to\u00e0n b\u1ed9 quy tr\u00ecnh." }]);
          runAllStopRef.current = true;
          break;
        }
      } finally {
        setWstgRunning(prev => { const n = { ...prev }; delete n[test.wstgId]; return n; });
      }

      // Delay 5s gi\u1eefa c\u00e1c test
      if (i < allTests.length - 1 && !runAllStopRef.current) {
        await new Promise(r => setTimeout(r, 5000));
      }
    }

    setRunAllActive(false);
    setRunAllProgress(prev => ({ ...prev, currentTest: null }));
  };

  const stopRunAll = () => { runAllStopRef.current = true; };

  const loadReport = async () => {
    try {
      const data = await fetchJSON("/api/run-all-report");
      setReportData(data);
      setShowReport(true);
    } catch { setReportData(null); }
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

  const toggleDetails = async (wstgId) => {
    if (showLogs[wstgId]) {
      setShowLogs(p => ({ ...p, [wstgId]: false }));
      return;
    }
    try {
      const logs = await fetchJSON(`/api/wstg-logs?wstg_id=${wstgId}&session_id=${sessionId || ""}`);
      setWstgDetails(p => ({ ...p, [wstgId]: logs }));
      setShowLogs(p => ({ ...p, [wstgId]: true }));
    } catch (e) {
      alert("Lỗi khi tải bằng chứng: " + e.message);
    }
  };

  useEffect(() => {
    if (tab === "history") loadHistory();
    if (tab === "wstg") loadWstgStatus();
  }, [tab, loadHistory, loadWstgStatus]);

  const statusIcon = (wstgId) => {
    const s = wstgStatus[wstgId]?.status;
    if (s === "pass") return "✅";
    if (s === "issue") return "⚠️";
    if (s === "needs_review") return "🟦";
    return "⬜";
  };

  const handlePrint = () => {
    // Ép mở tất cả details trong report trước khi in
    const details = document.querySelectorAll('.report-cat-group');
    details.forEach(d => d.setAttribute('open', 'true'));
    
    window.print();
    
    // Đóng lại (chỉ giữ mở mục INFO như ban đầu)
    details.forEach(d => {
      const isInfo = d.querySelector('.report-cat-summary')?.textContent.includes('1. Information Gathering');
      if (!isInfo) d.removeAttribute('open');
    });
  };

  const escapeHtml = (str) => {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  };

  const printPromptLog = (wstgId, roundIdx = null) => {
    const logs = promptLogs[wstgId];
    if (!logs || !Array.isArray(logs) || logs.length === 0) return;
    
    const printWindow = window.open('', '_blank', 'width=1000,height=800');
    let html = `<html><head><title>Prompt Log - ${escapeHtml(wstgId)}</title><style>
      body { font-family: sans-serif; line-height: 1.5; padding: 20px; }
      h2 { color: #2563eb; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 20px; page-break-inside: avoid; }
      th, td { border: 1px solid #ccc; padding: 10px; text-align: left; vertical-align: top; }
      th { background-color: #f3f4f6; }
      pre { white-space: pre-wrap; word-wrap: break-word; background: #f8fafc; padding: 10px; border-radius: 4px; font-size: 13px; }
    </style></head><body>`;
    
    html += `<h2>Prompt Log: ${escapeHtml(wstgId)}${roundIdx !== null ? ` (Lượt gọi #${roundIdx + 1})` : ''}</h2>`;
    
    let filteredLogs = logs.filter(p => p.direction === 'TO_LLM');
    if (roundIdx !== null && filteredLogs[roundIdx]) {
      filteredLogs = [filteredLogs[roundIdx]];
    }

    filteredLogs.forEach((prompt, loopIdx) => {
      const displayIdx = roundIdx !== null ? roundIdx : loopIdx;
      html += `<table>
        <thead><tr><th colSpan="2">Lượt gọi LLM #${displayIdx + 1} (${new Date(prompt.timestamp).toLocaleTimeString()})</th></tr></thead>
        <tbody>
          <tr><td style="width:150px; font-weight:bold;">User Message</td><td><pre>${escapeHtml(prompt.user_message)}</pre></td></tr>
          <tr><td style="font-weight:bold;">RAG Context</td><td><pre style="color: #9333ea;">${escapeHtml(prompt.rag_context) || 'Không có'}</pre></td></tr>
          <tr><td style="font-weight:bold;">Endpoint Hints</td><td><pre style="color: #dc2626;">${escapeHtml(prompt.endpoint_hints) || 'Không có'}</pre></td></tr>
          <tr><td style="font-weight:bold;">Chain of Evidence</td><td><pre style="color: #b45309;">${escapeHtml(prompt.chain_of_evidence) || 'Không có'}</pre></td></tr>
          <tr><td style="font-weight:bold;">Recon Cache</td><td><pre style="color: #0d9488;">${escapeHtml(prompt.recon_cache_data) || 'Không có'}</pre></td></tr>
          <tr><td style="font-weight:bold;">System Prompt</td><td><pre>${escapeHtml(prompt.system_prompt)}</pre></td></tr>
        </tbody>
      </table>`;
    });
    
    html += `</body></html>`;
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
    }, 500);
  };

  const renderStructuredReport = () => {
    if (!reportData || !reportData.data) return <p className="muted">Chưa có kết quả.</p>;
    const data = reportData.data;
    const total = data.length;
    if (total === 0) return <p className="muted">Chưa có kết quả test nào.</p>;

    const grouped = {};
    let passed = 0, issues = 0, needs_review = 0, errors = 0;
    
    data.forEach(r => {
      if (r.status === 'pass') passed++;
      if (r.status === 'issue') issues++;
      if (r.status === 'needs_review') needs_review++;
      if (r.status === 'error') errors++;

      const cat = r.wstg_id.split('-')[1] || "OTHER";
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(r);
    });

    const catNames = {
      "INFO": "1. Information Gathering", "CONF": "2. Configuration and Deploy",
      "IDNT": "3. Identity Management", "ATHN": "4. Authentication",
      "ATHZ": "5. Authorization", "SESS": "6. Session Management",
      "INPV": "7. Data Validation (Input)", "ERRH": "8. Error Handling",
      "CRYP": "9. Cryptography", "BUSL": "10. Business Logic",
      "CLNT": "11. Client-Side", "APIT": "12. API Testing",
    };

    return (
      <div className="report-structured">
        <div className="report-summary-box">
          <p><strong>Mục tiêu:</strong> {data[0]?.target_url}</p>
          <p><strong>Tổng số test:</strong> {total}/105</p>
          <div className="progress-stats">
            <span className="stat-pass">✅ {passed} PASS</span>
            <span className="stat-issue">⚠️ {issues} ISSUE</span>
            <span className="stat-review">🟦 {needs_review} REVIEW</span>
            <span className="stat-error">❌ {errors} ERROR</span>
          </div>
        </div>
        
        {Object.entries(grouped).sort().map(([cat, tests]) => {
          const cPassed = tests.filter(t => t.status === 'pass').length;
          const cIssues = tests.filter(t => t.status === 'issue').length;
          return (
            <details key={cat} className="report-cat-group">
              <summary className="report-cat-summary">
                <strong>{catNames[cat] || cat}</strong> 
                <span className="cat-stats">({cPassed} PASS / {cIssues} ISSUE / {tests.length} Tổng)</span>
              </summary>
              <div className="report-cat-content">
                {tests.map(t => (
                  <div key={t.wstg_id} className={`report-item status-${t.status}`}>
                    <h4 className="report-item-title">{t.wstg_id} - {t.status.toUpperCase()}</h4>
                    <div className="report-item-desc">{t.result_summary || "Chưa có chi tiết."}</div>
                    
                    <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
                      <button 
                        className="btn-outline-small"
                        onClick={async () => {
                          if (reportLogs[t.wstg_id]) {
                            setReportLogs(prev => ({ ...prev, [t.wstg_id]: null }));
                          } else {
                            setReportLogs(prev => ({ ...prev, [t.wstg_id]: "loading" }));
                            try {
                              const res = await fetchJSON(`/api/wstg-logs?wstg_id=${t.wstg_id}`);
                              setReportLogs(prev => ({ ...prev, [t.wstg_id]: res }));
                            } catch (err) {
                              setReportLogs(prev => ({ ...prev, [t.wstg_id]: [] }));
                            }
                          }
                        }}
                      >
                        {reportLogs[t.wstg_id] ? "Ẩn Log" : "📄 Xem Log Tool"}
                      </button>

                      <button 
                        className="btn-outline-small"
                        style={{ color: '#16a34a', borderColor: '#bbf7d0' }}
                        onClick={async () => {
                          if (promptLogs[t.wstg_id]) {
                            setPromptLogs(prev => ({ ...prev, [t.wstg_id]: null }));
                          } else {
                            setPromptLogs(prev => ({ ...prev, [t.wstg_id]: "loading" }));
                            try {
                              const res = await fetchJSON(`/api/prompt-logs?wstg_id=${t.wstg_id}`);
                              setPromptLogs(prev => ({ ...prev, [t.wstg_id]: res.entries || [] }));
                            } catch (err) {
                              setPromptLogs(prev => ({ ...prev, [t.wstg_id]: [] }));
                            }
                          }
                        }}
                      >
                        {promptLogs[t.wstg_id] ? "Ẩn Prompt" : "Prompt LLM"}
                      </button>
                    </div>

                    {reportLogs[t.wstg_id] === "loading" && <div className="muted mt-2">Đang tải log...</div>}
                    {Array.isArray(reportLogs[t.wstg_id]) && (
                      <div className="wstg-details-panel" style={{ marginTop: '10px' }}>
                        {reportLogs[t.wstg_id].length === 0 ? (
                          <p className="muted">Không có log nào cho bài test này.</p>
                        ) : (
                          <table className="wstg-details-table">
                            <thead>
                              <tr>
                                <th>Nguồn</th>
                                <th>Tool</th>
                                <th>Nội dung / Tham số</th>
                                <th>Kết quả</th>
                              </tr>
                            </thead>
                            <tbody>
                              {reportLogs[t.wstg_id].map((log) => (
                                <tr key={log.id}>
                                  <td className="td-role">
                                    {log.role === 'assistant' && '🤖 AI'}
                                    {log.role === 'tool' && '🛠️ Tool'}
                                    {log.role === 'user' && '👤 User'}
                                  </td>
                                  <td className="td-tool"><strong>{log.tool_name || '-'}</strong></td>
                                  <td className="td-args">
                                    {log.tool_args ? <pre className="small-pre">{log.tool_args}</pre> : '-'}
                                    {log.content && <div className="log-content-text">{log.content}</div>}
                                  </td>
                                  <td className="td-res">
                                    {log.tool_result ? <pre className="result-pre">{log.tool_result}</pre> : '-'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    )}

                    {/* PROMPT LOGS */}
                    {promptLogs[t.wstg_id] === "loading" && <div className="muted mt-2">Đang tải prompt...</div>}
                    {Array.isArray(promptLogs[t.wstg_id]) && (
                      <div className="wstg-details-panel" style={{ marginTop: '10px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                          <h4 style={{ margin: 0 }}>Lịch sử giao tiếp LLM</h4>
                          {promptLogs[t.wstg_id].length > 0 && (
                            <button className="btn-print" style={{ padding: '4px 10px', fontSize: '13px' }} onClick={() => printPromptLog(t.wstg_id)}>
                              🖨️ Xuất PDF Log
                            </button>
                          )}
                        </div>
                        {promptLogs[t.wstg_id].length === 0 ? (
                          <p className="muted">Không có prompt log nào cho bài test này.</p>
                        ) : (
                          promptLogs[t.wstg_id].filter(p => p.direction === 'TO_LLM').map((prompt, idx) => (
                            <table key={idx} className="wstg-details-table" style={{ marginBottom: '15px' }}>
                              <thead>
                                <tr>
                                  <th colSpan="2">
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                      <span>Lượt gọi LLM #{idx + 1} ({new Date(prompt.timestamp).toLocaleTimeString()})</span>
                                      <button className="btn-print" style={{ padding: '2px 8px', fontSize: '11px', cursor: 'pointer' }} onClick={() => printPromptLog(t.wstg_id, idx)}>
                                        🖨️ Xuất Lượt Này
                                      </button>
                                    </div>
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <td style={{ width: '150px', fontWeight: 'bold' }}>User Message</td>
                                  <td><pre className="result-pre" style={{ maxHeight: '100px' }}>{prompt.user_message}</pre></td>
                                </tr>
                                <tr>
                                  <td style={{ fontWeight: 'bold' }}>RAG Context</td>
                                  <td><pre className="result-pre" style={{ maxHeight: '150px', color: '#9333ea' }}>{prompt.rag_context || "Không có"}</pre></td>
                                </tr>
                                <tr>
                                  <td style={{ fontWeight: 'bold' }}>Endpoint Hints</td>
                                  <td><pre className="result-pre" style={{ maxHeight: '100px', color: '#dc2626' }}>{prompt.endpoint_hints || "Không có"}</pre></td>
                                </tr>
                                <tr>
                                  <td style={{ fontWeight: 'bold' }}>Chain of Evidence</td>
                                  <td><pre className="result-pre" style={{ maxHeight: '150px', color: '#b45309' }}>{prompt.chain_of_evidence || "Không có"}</pre></td>
                                </tr>
                                <tr>
                                  <td style={{ fontWeight: 'bold' }}>Recon Cache</td>
                                  <td><pre className="result-pre" style={{ maxHeight: '150px', color: '#0d9488' }}>{prompt.recon_cache_data || "Không có"}</pre></td>
                                </tr>
                                <tr>
                                  <td style={{ fontWeight: 'bold' }}>System Prompt</td>
                                  <td>
                                    <details>
                                      <summary style={{ cursor: 'pointer', color: '#3b82f6', outline: 'none' }}>Hiện / Ẩn chi tiết System Prompt ({prompt.system_prompt_length} chars)</summary>
                                      <pre className="result-pre" style={{ maxHeight: '200px', marginTop: '8px' }}>{prompt.system_prompt}</pre>
                                    </details>
                                  </td>
                                </tr>
                              </tbody>
                            </table>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </details>
          );
        })}
      </div>
    );
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

          {/* ═══ RUN ALL CONTROLS ═══ */}
          <div className="run-all-section">
            <div className="run-all-buttons">
              {!runAllActive ? (
                <button className="btn-run-all" onClick={runAllTests} disabled={!targetUrl.trim()}>
                  run all ({wstgCategories.reduce((s, c) => s + c.tests.length, 0)} mục)
                </button>
              ) : (
                <button className="btn-stop-all" onClick={stopRunAll}>
                  ⏹ Dừng
                </button>
              )}
              <button className="btn-report" onClick={loadReport}>
                📋 Xem báo cáo
              </button>
            </div>

            {runAllActive && (
              <div className="run-all-progress">
                <div className="progress-bar-bg">
                  <div className="progress-bar-fill" style={{ width: `${(runAllProgress.current / runAllProgress.total * 100) || 0}%` }} />
                </div>
                <div className="progress-text">
                  {runAllProgress.current}/{runAllProgress.total}
                  {runAllProgress.currentTest && <span> — Đang chạy: <strong>{runAllProgress.currentTest}</strong></span>}
                </div>
                <div className="progress-stats">
                  <span className="stat-pass">✅ {runAllResults.pass}</span>
                  <span className="stat-issue">⚠️ {runAllResults.issue}</span>
                  <span className="stat-review">🟦 {runAllResults.needs_review}</span>
                  <span className="stat-error">❌ {runAllResults.error}</span>
                </div>
              </div>
            )}

            {runAllLog.length > 0 && (
              <div className="run-all-log">
                <details>
                  <summary>Log chạy ({runAllLog.length} tests)</summary>
                  <div className="log-entries">
                    {runAllLog.map((entry, i) => (
                      <div key={i} className={`log-entry log-${entry.status}`}>
                        <span className="log-id">{entry.wstgId}</span>
                        <span className="log-status">{entry.status.toUpperCase()}</span>
                        <span className="log-msg">{entry.msg}</span>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </div>

          {/* ═══ REPORT MODAL ═══ */}
          {showReport && reportData && (
            <div className="report-overlay" onClick={() => setShowReport(false)}>
              <div className="report-modal" onClick={e => e.stopPropagation()}>
                <div className="report-header">
                  <h3>📋 Báo cáo tổng hợp</h3>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="btn-print" onClick={handlePrint}>🖨️ Xuất PDF</button>
                    <button className="btn-close" onClick={() => setShowReport(false)}>✕</button>
                  </div>
                </div>
                <div className="report-body">
                  {renderStructuredReport()}
                </div>
              </div>
            </div>
          )}

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
                            <option value="needs_review">Needs review</option>
                          </select>
                          <button
                            className="btn-run"
                            disabled={!!wstgRunning[test.wstgId]}
                            onClick={() => runWstgTest(test)}
                          >
                            {wstgRunning[test.wstgId] ? "⏳ Đang chạy" : "▶ Chạy"}
                          </button>
                          <button
                            className={`btn-details ${showLogs[test.wstgId] ? "active" : ""}`}
                            onClick={() => toggleDetails(test.wstgId)}
                          >
                            {showLogs[test.wstgId] ? "📁 Đóng" : "📄 Chi tiết"}
                          </button>
                        </div>

                        {showLogs[test.wstgId] && (
                          <div className="wstg-detail-report">
                            <div className="report-synthesis">
                              <h4>📝 Tóm tắt kết quả (Bởi AI Agent)</h4>
                              <div className="synthesis-box">
                                {wstgStatus[test.wstgId]?.result_summary || "Chưa có kết luận tổng hợp từ Agent cho mục này."}
                              </div>
                            </div>

                            <h4>🛡️ Bằng chứng thực thi ({test.wstgId})</h4>
                            <div className="detail-table-wrap">
                              <table className="detail-table">
                                <thead>
                                  <tr><th>Tool</th><th>Tham số (Command)</th><th>Kết quả quét</th></tr>
                                </thead>
                                <tbody>
                                  {(wstgDetails[test.wstgId] || []).filter(log => log.tool_name).map((log, idx) => (
                                    <tr key={idx}>
                                      <td className="td-tool"><strong>{log.tool_name}</strong></td>
                                      <td className="td-args"><pre className="small-pre">{log.tool_args}</pre></td>
                                      <td className="td-res"><pre className="result-pre">{log.tool_result}</pre></td>
                                    </tr>
                                  ))}
                                  {(wstgDetails[test.wstgId] || []).filter(log => log.tool_name).length === 0 && (
                                    <tr><td colSpan="3" className="muted center">Chưa có bằng chứng chạy tool cho mục này.</td></tr>
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
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
                      {row.tool_result && <pre className="history-result-pre">{row.tool_result}</pre>}
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
