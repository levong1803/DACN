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

## 6. Hướng dẫn Sử dụng

| Bước | Thao tác |
|------|----------|
| **1** | Mở trình duyệt → truy cập `http://localhost:5173` |
| **2** | Nhập URL mục tiêu vào thanh trên cùng: `http://localhost:13000` |
| **3** | Panel trái: chọn kịch bản cần test (VD: tick `WSTG-INPV-05 - SQL Injection`) |
| **4** | Nhấn nút **Run Selected Tests** |
| **5** | Theo dõi AI tác chiến realtime ở khung giữa: Planner ra lệnh → Recon đi dò → Exploit tung đòn |
| **6** | Xem kết quả ở panel phải: **PASS** (an toàn) · **ISSUE** (có lỗ hổng) · **NEEDS REVIEW** (cần xem lại) |

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
  <sub>Đồ án tốt nghiệp — Phát triển bởi <b>Lê Vòng</b></sub>
</div>
