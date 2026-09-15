import json
from pathlib import Path
from datetime import datetime
import streamlit as st

from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from chat import run_model_tool_loop
from versioning import build_artifact_version

ROOT = Path(__file__).parent
load_lab_env(ROOT)

# Cấu hình trang cơ bản
st.set_page_config(
    page_title="Northstar Labs - IT Helpdesk",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# CUSTOM CSS STYLE (UI/UX Tối Ưu)
# ---------------------------------------------------------
st.markdown("""
<style>
    /* Tổng quan nền tối và font chữ */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgba(20, 20, 32, 1) 0%, rgba(10, 10, 15, 1) 90%);
        color: #E2E8F0;
    }

    /* Tiêu đề chính */
    .main-title {
        background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    .sub-title {
        color: #94A3B8;
        font-size: 1.1rem;
        font-weight: 300;
        margin-bottom: 2rem;
    }

    /* Sidebar glassmorphism */
    [data-testid="stSidebar"] {
        background: rgba(30, 30, 46, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }

    /* Tùy chỉnh chat box */
    .stChatMessage {
        background: rgba(255,255,255,0.02);
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid rgba(255,255,255,0.05);
        margin-bottom: 1rem;
    }
    
    /* Box hiển thị Tool Traces (Đẹp hơn JSON thường) */
    .tool-box {
        background: #1E293B;
        border-left: 4px solid #3B82F6;
        border-radius: 6px;
        padding: 12px;
        margin-top: 10px;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.85rem;
    }
    .tool-header {
        font-weight: bold;
        color: #60A5FA;
        margin-bottom: 6px;
    }
    .tool-success { border-left-color: #10B981; }
    .tool-success .tool-header { color: #34D399; }
    
    /* Expander style */
    .streamlit-expanderHeader {
        font-size: 0.9rem !important;
        color: #94A3B8 !important;
        background: rgba(0,0,0,0.2) !important;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# LOAD DATA & ARTIFACTS
# ---------------------------------------------------------
SYSTEM_PROMPT_PATH = ROOT / "artifacts" / "system_prompt.md"
TOOLS_PATH = ROOT / "artifacts" / "tools.yaml"

system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
tool_decls = load_tool_declarations(TOOLS_PATH)
openai_tools = to_openai_tools(tool_decls)

artifact_ver = build_artifact_version("v3", SYSTEM_PROMPT_PATH, TOOLS_PATH)

# ---------------------------------------------------------
# SIDEBAR CONFIGURATION
# ---------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2082/2082875.png", width=60)
    st.markdown("### ⚙️ Cài đặt Agent")
    st.caption("IT Helpdesk System Config")
    
    provider_choice = st.selectbox("Provider", ["openrouter", "openai", "anthropic", "gemini"], index=0)
    
    st.divider()
    st.markdown("#### 📦 Trạng Thái Phiên Bản")
    st.markdown(f"**Version Label:** `{artifact_ver.artifact_version}`")
    st.caption(f"**Prompt Hash:** {artifact_ver.prompt_hash[:8]}")
    st.caption(f"**Tools Hash:** {artifact_ver.tools_hash[:8]}")
    
    st.divider()
    st.markdown("#### 🛠️ Các Công Cụ Có Sẵn")
    for t in tool_decls:
        st.markdown(f"- 🔧 `{t['name']}`")
        
    st.divider()
    if st.button("🗑️ Xóa Lịch Sử Trò Chuyện", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------
# MAIN INTERFACE
# ---------------------------------------------------------
st.markdown('<div class="main-title">IT Helpdesk Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Hỗ trợ kỹ thuật tự động cho nhân viên Northstar Labs ✦ Nhanh chóng & Bảo mật</div>', unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "👋 Xin chào! Tôi là trợ lý IT Helpdesk của Northstar Labs. Tôi có thể giúp bạn kiểm tra VPN, Wi-Fi, trạng thái thiết bị hoặc tìm hướng dẫn sử dụng. Bạn cần hỗ trợ gì hôm nay?"}
    ]

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👨‍💻" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])
        
        # Nếu có gọi tools, hiển thị UI đẹp thay vì st.json
        if "tools" in msg and msg["tools"]:
            with st.expander("🛠️ Xem chi tiết các tiến trình hệ thống (Traces)"):
                for t_event in msg["tools"]:
                    t_name = t_event.get("tool", "unknown")
                    t_args = t_event.get("args", {})
                    t_res = t_event.get("result", {})
                    
                    is_error = isinstance(t_res, dict) and "error" in t_res
                    box_class = "tool-box" if is_error else "tool-box tool-success"
                    icon = "⚠️" if is_error else "✅"
                    
                    st.markdown(f"""
                    <div class="{box_class}">
                        <div class="tool-header">{icon} Gọi công cụ: {t_name}</div>
                        <b>Tham số (Args):</b><br/> {json.dumps(t_args, ensure_ascii=False, indent=2)}<br/><br/>
                        <b>Kết quả trả về:</b><br/> {json.dumps(t_res, ensure_ascii=False, indent=2)}
                    </div>
                    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# CHAT INPUT & LOGIC
# ---------------------------------------------------------
if prompt := st.chat_input("Ví dụ: 'Kiểm tra VPN giúp tôi' hoặc 'Tạo ticket máy in'..."):
    
    # Thêm tin nhắn user vào UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👨‍💻"):
        st.markdown(prompt)

    # Chuẩn bị context gửi cho Agent
    provider = make_provider(provider_choice)
    chat_history = [{"role": "system", "content": system_prompt}]
    
    # Chỉ lấy các tin nhắn text, bỏ qua cấu trúc hiển thị tools để tránh nhiễu model
    for m in st.session_state.messages:
        chat_history.append({"role": m["role"], "content": m["content"]})

    # Agent xử lý
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Đang chẩn đoán hệ thống và truy xuất dữ liệu..."):
            result = run_model_tool_loop(
                provider=provider,
                messages=chat_history,
                tools=openai_tools,
                model=None,
                max_tool_rounds=4,
            )
            
            reply = result["assistant_text"]
            tool_events = result.get("tool_events", [])
            
            st.markdown(reply)
            
            # Render tool events nếu có
            if tool_events:
                with st.expander("🛠️ Xem chi tiết các tiến trình hệ thống (Traces)"):
                    for t_event in tool_events:
                        t_name = t_event.get("tool", "unknown")
                        t_args = t_event.get("args", {})
                        t_res = t_event.get("result", {})
                        
                        is_error = isinstance(t_res, dict) and "error" in t_res
                        box_class = "tool-box" if is_error else "tool-box tool-success"
                        icon = "⚠️" if is_error else "✅"
                        
                        st.markdown(f"""
                        <div class="{box_class}">
                            <div class="tool-header">{icon} Gọi công cụ: {t_name}</div>
                            <b>Tham số (Args):</b><br/> {json.dumps(t_args, ensure_ascii=False, indent=2)}<br/><br/>
                            <b>Kết quả trả về:</b><br/> {json.dumps(t_res, ensure_ascii=False, indent=2)}
                        </div>
                        """, unsafe_allow_html=True)

    # Lưu lại lịch sử
    st.session_state.messages.append({
        "role": "assistant",
        "content": reply,
        "tools": tool_events,
    })
