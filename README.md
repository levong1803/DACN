<div align="center">
  <h1>OWASP WSTG AI Pentest System</h1>
  <p><b>Hệ thống Đa tác tử AI Tự động hóa Kiểm thử Xâm nhập Web theo chuẩn OWASP WSTG v4.2</b></p>
  
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00a393.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![React](https://img.shields.io/badge/React-18.0+-61dafb.svg?style=flat-square&logo=react&logoColor=black)](https://reactjs.org/)
  [![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E.svg?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com/)
  [![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-8E75B2.svg?style=flat-square&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
</div>

<br/>

## 1. Giới thiệu

Hệ thống mô phỏng tư duy của một Chuyên gia An toàn thông tin (Pentester) bằng AI. Tự động hóa hoàn toàn quá trình rà quét và khai thác lỗ hổng bảo mật trên ứng dụng Web, bao phủ **105 kịch bản** thuộc bộ tiêu chuẩn **OWASP WSTG v4.2**.

### 4 Trụ cột Công nghệ:

| # | Công nghệ | Mô tả |
|---|-----------|-------|
| 1 | **RAG** | Vector Database nhúng toàn bộ cẩm nang OWASP → AI phải "đọc sách" trước khi hành động, chống ảo giác |
| 2 | **Multi-Agent** | 4 tác tử phân quyền: Planner (chỉ huy) → Recon (trinh sát) → Exploit (khai thác) → Verifier (xác thực chống báo giả) |
| 3 | **Dynamic Knowledge Graph** | Não bộ trung tâm lưu trữ IP, API, đường dẫn xuyên suốt các bài test → Hiệu ứng quả cầu tuyết |
| 4 | **MCP Protocol** | Cầu nối an toàn để AI điều khiển trực tiếp Nmap, SQLMap, ZAP trong Terminal Linux |

---

## 2. Cấu trúc Dự án

```
DACN/
├── backend/                      # Backend FastAPI + AI Engine
│   ├── app/
│   │   ├── main.py               # API Endpoints (FastAPI)
│   │   ├── agent.py              # Lõi điều phối AI Agent
│   │   ├── multi_agent.py        # 4 Agent: Planner, Recon, Exploit, Verifier
│   │   ├── knowledge_graph.py    # Đồ thị tri thức động (DKG)
│   │   ├── rag_enhancer.py       # RAG + Vector Similarity Search
│   │   ├── mcp_bridge.py         # Cầu nối MCP (gọi tool qua stdio)
│   │   ├── recon_cache.py        # Bộ đệm trinh sát (Ghi 1 lần - Đọc nhiều lần)
│   │   ├── config.py             # Xoay vòng API Key chống Rate Limit
│   │   ├── db.py                 # Kết nối Supabase
│   │   └── prompt_logger.py      # Ghi log prompt & tool calls
│   ├── pentest_mcp_tools.py      # 19 công cụ MCP (Nmap, SQLMap, ZAP...)
│   ├── supabase_schema.sql       # Schema tạo bảng Vector DB
│   ├── requirements.txt          # Danh sách thư viện Python
│   └── .env                      # Biến môi trường (API Keys)
│
├── frontend/                     # Giao diện Web (React + Vite)
│   └── src/
│       ├── App.jsx               # Giao diện chính & Terminal Realtime
│       ├── wstgData.js           # Dữ liệu 105 kịch bản OWASP
│       └── wstg_extracted.json   # Metadata kịch bản
│
├── specialized-project/          # Mã nguồn Báo cáo LaTeX
└── README.md
```

---

## 3. Yêu cầu Hệ thống

| Thành phần | Phiên bản | Ghi chú |
|-----------|-----------|---------|
| **Python** | ≥ 3.10 | Backend AI |
| **Node.js** | ≥ 18 | Frontend React |
| **Docker** | Bất kỳ | Chạy mục tiêu Juice Shop |
| **WSL2 / Linux** | Bắt buộc | Môi trường chạy các tool bảo mật |

**Cài đặt công cụ bảo mật trên WSL2/Linux:**
```bash
sudo apt update && sudo apt install -y nmap dirb sqlmap nikto hydra wfuzz whatweb wafw00f curl
```

---

## 4. Cài đặt & Cấu hình

### Bước 1: Clone dự án
```bash
git clone https://github.com/levong1803/DACN.git
cd DACN
```

### Bước 2: Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Linux/WSL
# hoặc: venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

**Tạo file `.env`** trong thư mục `backend/`:
```env
# === Supabase (Vector Database cho RAG) ===
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>

# === Google Gemini API (hỗ trợ nhiều key xoay vòng) ===
GEMINI_API_KEYS=AIzaSy...key1,AIzaSy...key2,AIzaSy...key3

# === Model ===
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
OPENAI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=AIzaSy...key1

# === MCP (Model Context Protocol) ===
MCP_ENABLED=true
MCP_COMMAND=python
MCP_ARGS_JSON=["pentest_mcp_tools.py"]

# === Multi-Agent ===
MULTI_AGENT_ENABLED=true
PENTEST_ALLOW_ANY=true
```

### Bước 3: Frontend
```bash
cd frontend
npm install
```

---

## 5. Khởi chạy Hệ thống

Mở **3 Terminal riêng biệt**:

### Terminal 1 — Mục tiêu (OWASP Juice Shop)
```bash
docker run --rm -p 13000:3000 bkimminich/juice-shop
```
> Mục tiêu: `http://localhost:13000`

### Terminal 2 — Backend AI
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```
> API: `http://localhost:8000`

### Terminal 3 — Frontend
```bash
cd frontend
npm run dev
```
> Web UI: `http://localhost:5173`

---

## 6. Hướng dẫn Sử dụng Chi tiết

Để khai thác tối đa sức mạnh của hệ thống AI Pentest, bạn hãy làm theo luồng thao tác chuẩn sau đây:

### Bước 1: Khởi tạo Phiên làm việc
1. Mở trình duyệt Web (khuyến nghị Chrome/Edge) và truy cập vào **`http://localhost:5173`**.
2. Tại thanh địa chỉ (Target URL) nằm ở góc trên cùng, hãy nhập chính xác đường dẫn của ứng dụng mục tiêu bạn muốn kiểm thử. 
   - Ví dụ: Nhập `http://localhost:13000` nếu bạn đang chạy Juice Shop.
   - *Lưu ý: Không nên test các trang web thực tế trên Internet nếu bạn chưa có sự cho phép (Bất hợp pháp).*

### Bước 2: Lựa chọn Chiến thuật Kiểm thử (Bảng điều khiển bên trái)
- Bảng điều khiển này chứa toàn bộ 105 kịch bản phân loại theo chuẩn OWASP (như INFO: Dò quét thông tin, CONF: Lỗi cấu hình, INPV: Lỗi nhập liệu...).
- **Tìm kiếm nhanh:** Bạn có thể gõ từ khóa như `SQL`, `XSS`, `Admin` vào thanh tìm kiếm để lọc nhanh kịch bản.
- **Chọn kịch bản:** Bạn có thể tick vào một ô vuông duy nhất (ví dụ: `WSTG-INPV-05 Testing for SQL Injection`) để test lẻ, hoặc nhấn nút **"Run Group"** ở đầu mỗi nhóm để AI chạy liên hoàn toàn bộ nhóm đó.

### Bước 3: Phát lệnh Tấn công
- Sau khi đã chọn xong kịch bản, bạn kéo xuống dưới cùng và nhấn nút **"Run Selected Tests"**.
- Lúc này, Hệ thống Đa tác tử (Multi-Agent) sẽ chính thức được đánh thức.

### Bước 4: Theo dõi Radar Tác chiến (Khung màn hình trung tâm)
Đây là màn hình Terminal giả lập hiển thị suy nghĩ (Thought Process) của AI theo thời gian thực:
- Đầu tiên, bạn sẽ thấy **Planner Agent** đọc luật từ hệ thống RAG và lên kế hoạch.
- Tiếp theo, nó sẽ ủy quyền cho **Recon Agent**. Bạn sẽ thấy các dòng log báo cáo Recon đang chạy lệnh `nmap` hoặc `dirb` để tìm API/thư mục ẩn.
- Nếu tìm thấy điểm yếu, Planner sẽ gọi **Exploit Agent**. Lúc này màn hình sẽ chạy các lệnh tấn công hạng nặng (như `sqlmap` bắn payload).
- Quá trình này diễn ra hoàn toàn tự động, bạn giống như một người Chỉ huy ngồi xem lính của mình đi đánh trận.

### Bước 5: Đọc Báo cáo Cuối cùng (Bảng điều khiển bên phải)
Khi trận đánh kết thúc, hệ thống sẽ tự động tổng hợp và hiển thị kết quả sang cột bên phải:
- 🟢 **PASS (An toàn):** Công cụ đã quét cạn kiệt các trường hợp nhưng không tìm thấy lỗi.
- 🔴 **ISSUE (Có lỗ hổng):** AI đã khai thác thành công. Nếu bấm mở rộng ra, bạn sẽ thấy rõ Payload (đoạn mã độc) nào đã được AI sử dụng để xuyên thủng hệ thống.
- 🟡 **NEEDS REVIEW (Cần xem xét):** AI nghi ngờ có lỗi (ví dụ trang web trả về HTTP 500) nhưng nó không đủ bằng chứng chắc chắn 100%. Tác tử Verifier đã dán nhãn này để gọi con người vào kiểm tra thủ công.

---

## 7. Xử lý Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|-----|------------|----------|
| `429 Too Many Requests` | Hết quota Gemini API miễn phí | Thêm nhiều key vào `GEMINI_API_KEYS` (cách nhau bằng dấu phẩy). Hệ thống tự xoay vòng |
| `command not found: nmap` | Chưa cài tool trên Linux | Chạy `sudo apt install nmap sqlmap dirb nikto` trong WSL2 |
| `CORS error` trên Frontend | Backend chưa bật hoặc sai cổng | Đảm bảo Backend đang chạy trên cổng `8000` |
| `Connection refused :13000` | Docker Juice Shop chưa bật | Chạy lại `docker run --rm -p 13000:3000 bkimminich/juice-shop` |

---

<div align="center">
  <sub>Đồ án chuyên ngành — Phát triển bởi <b>Lê Vọng</b></sub>
</div>
