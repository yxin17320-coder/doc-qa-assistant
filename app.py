import requests
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="智能文档问答助手",
    page_icon="📚",
    layout="wide",
)

# 自动滚动到底部
st.markdown(
    """
    <script>
    const observer = new MutationObserver(() => {
        const chatContainer = window.parent.document.querySelector('.stChatFloatingInputContainer');
        if (chatContainer) chatContainer.scrollIntoView({behavior: 'smooth'});
    });
    observer.observe(document.body, {childList: true, subtree: true});
    </script>
    """,
    unsafe_allow_html=True,
)

st.title("📚 智能文档问答助手")
st.caption("上传文档 → 自然语言提问 → AI 从文档中精准找答案")

# === Sidebar ===
with st.sidebar:
    st.header("📁 上传文档")

    # 上传状态管理
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "upload_alerts" not in st.session_state:
        st.session_state.upload_alerts = []  # [(type, msg), ...]

    uploaded_files = st.file_uploader(
        "支持 PDF / Word / TXT / Markdown",
        type=["pdf", "docx", "doc", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
    )

    # 渲染消息
    has_success = any(a[0] == "success" for a in st.session_state.upload_alerts)
    if has_success:
        st.markdown(
            """
            <style>
            @keyframes fadeSlide {
                to { opacity: 0; max-height: 0; padding: 0; margin: 0; overflow: hidden; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    for idx, alert in enumerate(st.session_state.upload_alerts[:]):
        atype, msg = alert
        if atype == "success":
            st.markdown(
                f"""
                <div style="background:#d4edda;color:#155724;padding:10px 14px;border-radius:6px;
                            margin:4px 0;font-size:13px;
                            animation: fadeSlide 0.5s ease 2s forwards;">
                    ✅ {msg}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.error(msg)
            if st.button("✕ 关闭", key=f"dismiss_{idx}"):
                st.session_state.upload_alerts.pop(idx)
                st.rerun()

    ALLOWED_TYPES = {"pdf", "docx", "doc", "txt", "md"}

    # 处理中则禁用上传按钮
    if "uploading" not in st.session_state:
        st.session_state.uploading = False

    upload_btn = st.button(
        "确认上传并处理", type="primary",
        disabled=st.session_state.uploading or not uploaded_files,
    )

    if upload_btn and uploaded_files:
        st.session_state.uploading = True
        st.rerun()

    if st.session_state.uploading and uploaded_files:
        bad_files = [f for f in uploaded_files if f.name.split(".")[-1].lower() not in ALLOWED_TYPES]
        if bad_files:
            st.session_state.upload_alerts = []
            st.session_state.upload_alerts.append(
                ("error", f"不支持的格式: {', '.join(f.name for f in bad_files)}")
            )
            st.session_state.uploading = False
            st.session_state.uploader_key += 1
            st.rerun()
        else:
            with st.spinner(f"正在处理 {len(uploaded_files)} 个文件..."):
                success_count = 0
                fail_errors = []
                for file in uploaded_files:
                    try:
                        resp = requests.post(
                            f"{API_BASE}/upload",
                            files={"file": (file.name, file.getvalue())},
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            success_count += 1
                        else:
                            detail = resp.json().get("detail", "未知错误")
                            fail_errors.append(f"{file.name}: {detail}")
                    except requests.ConnectionError:
                        fail_errors.append("无法连接后端，请先启动 API 服务")
                        break
                    except Exception as e:
                        fail_errors.append(f"{file.name}: {str(e)}")

                st.session_state.upload_alerts = []
                if success_count > 0:
                    st.session_state.upload_alerts.append(
                        ("success", f"成功上传 {success_count} 个文件")
                    )
                for err in fail_errors:
                    st.session_state.upload_alerts.append(("error", err))
                st.session_state.uploading = False
                st.session_state.uploader_key += 1
                st.rerun()

    st.divider()

    st.header("📋 已上传文档")
    try:
        resp = requests.get(f"{API_BASE}/documents", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("documents", [])
            if docs:
                for doc in docs:
                    st.write(f"• {doc}")
                    if st.button("🗑 删除", key=f"del_{doc}"):
                        try:
                            del_resp = requests.delete(
                                f"{API_BASE}/documents/{doc}", timeout=5
                            )
                            if del_resp.status_code == 200:
                                st.rerun()
                        except requests.ConnectionError:
                            st.error("删除失败")
                st.caption(f"总计 {data['total_chunks']} 个文档片段")
            else:
                st.caption("暂无文档，请上传")
    except requests.ConnectionError:
        st.caption("等待后端服务启动...")

# === Main Chat ===
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("sources"):
            with st.expander("📖 参考来源"):
                for i, src in enumerate(msg["sources"]):
                    st.caption(f"**来源 {i + 1}: {src['source']}**")
                    st.text(src["content"][:300])

# Handle input
if prompt := st.chat_input("输入你的问题，比如「这份文档主要讲了什么？」"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("正在检索文档并生成回答..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/query",
                    json={"question": prompt},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.write(data["answer"])
                    sources = data.get("sources", [])
                    if sources:
                        with st.expander("📖 参考来源"):
                            for i, src in enumerate(sources):
                                st.caption(f"**来源 {i + 1}: {src['source']}**")
                                st.text(src["content"][:300])
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": data["answer"],
                            "sources": sources,
                        }
                    )
                else:
                    st.error(f"查询失败: {resp.json().get('detail', '')}")
            except requests.ConnectionError:
                st.error("❌ 无法连接后端服务，请先运行: uvicorn api:app --reload")

# 智能滚动：只在用户处于底部时才自动滚，手动上翻时不抢
st.components.v1.html(
    """
    <script>
    (function() {
        var main = window.parent.document.querySelector('.main');
        if (!main) return;
        var threshold = 100;  // 距底部100px以内视为"在底部"
        var atBottom = main.scrollHeight - main.scrollTop - main.clientHeight < threshold;
        if (atBottom) {
            main.scrollTo(0, main.scrollHeight);
        }
    })();
    </script>
    """,
    height=0,
)
