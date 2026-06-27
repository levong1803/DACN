import asyncio
import json
import os
import sys

# Đảm bảo có thể import từ thư mục app/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agent import GeminiClient
from app.db import _client as supabase_client
from app.config import settings

async def seed_rag():
    print("🚀 Bắt đầu quá trình nạp dữ liệu vào Supabase RAG (wstg_kb)...")
    
    # Kiểm tra biến môi trường
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("❌ Lỗi: Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY trong .env")
        return
        
    if not settings.gemini_api_keys:
        print("❌ Lỗi: Thiếu GEMINI_API_KEYS trong .env")
        return

    # Khởi tạo Gemini client
    gemini = GeminiClient()
    supabase = supabase_client()
    
    # Đường dẫn đến file json
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "src", "wstg_extracted.json")
    
    if not os.path.exists(json_path):
        print(f"❌ Lỗi: Không tìm thấy file {json_path}")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    total = len(data)
    print(f"📦 Đã tải {total} kịch bản từ wstg_extracted.json")
    
    success_count = 0
    error_count = 0
    
    for idx, (wstg_id, content) in enumerate(data.items(), 1):
        print(f"[{idx}/{total}] Đang xử lý {wstg_id}...", end=" ", flush=True)
        
        try:
            # 1. Kiểm tra xem đã tồn tại chưa
            existing = supabase.table("wstg_kb").select("wstg_id").eq("wstg_id", wstg_id).execute()
            if len(existing.data) > 0:
                print("Đã tồn tại (Bỏ qua)")
                continue
                
            # 2. Tạo embedding từ Gemini
            embedding = await gemini.embed_text(content)
            
            # 3. Chèn vào Supabase
            row = {
                "wstg_id": wstg_id,
                "content": content,
                "embedding": embedding,
                "metadata": {"source": "wstg_extracted.json"}
            }
            
            supabase.table("wstg_kb").insert(row).execute()
            print("✅ Thành công")
            success_count += 1
            
            # Đợi một chút để tránh rate limit
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"❌ Lỗi: {str(e)}")
            error_count += 1
            await asyncio.sleep(2)
            
    print("\n🎉 HOÀN TẤT NẠP DỮ LIỆU!")
    print(f"✅ Thành công: {success_count}")
    print(f"❌ Thất bại: {error_count}")

if __name__ == "__main__":
    asyncio.run(seed_rag())
