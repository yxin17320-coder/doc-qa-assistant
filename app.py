import os
import uuid
import html
import tempfile
import streamlit as st
from pathlib import Path

# 从 Streamlit Cloud secrets 或本地 .env 读取 API Key
if "DEEPSEEK_API_KEY" in st.secrets:
    os.environ["DEEPSEEK_API_KEY"] = st.secrets["DEEPSEEK_API_KEY"]

from rag_engine import RAGEngine

if "rag_engine" not in st.session_state:
    try:
        st.session_state.rag_engine = RAGEngine()
    except Exception as e:
        st.error(f"初始化失败: {e}")
        st.stop()

rag_engine = st.session_state.rag_engine

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
st.caption("上传文档 → 直接提问 → AI 从文档中精准找答案")

# === Sidebar ===
with st.sidebar:
    st.header("📁 上传文档")

    # 上传状态管理
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "upload_alerts" not in st.session_state:
        st.session_state.upload_alerts = []

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
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

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
        huge_files = [f for f in uploaded_files if f.size > MAX_FILE_SIZE]
        if bad_files:
            st.session_state.upload_alerts = []
            st.session_state.upload_alerts.append(
                ("error", f"不支持的格式: {', '.join(html.escape(f.name) for f in bad_files)}")
            )
            st.session_state.uploading = False
            st.session_state.uploader_key += 1
            st.rerun()

        if huge_files:
            st.session_state.upload_alerts = []
            st.session_state.upload_alerts.append(
                ("error", f"文件过大（超过50MB）: {', '.join(html.escape(f.name) for f in huge_files)}")
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
                        ext = Path(file.name).suffix
                        tmp_path = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}{ext}"
                        with open(tmp_path, "wb") as f:
                            f.write(file.getvalue())

                        chunk_count = rag_engine.add_document(
                            str(tmp_path), display_name=file.name
                        )
                        success_count += 1
                        tmp_path.unlink(missing_ok=True)
                    except Exception as e:
                        fail_errors.append(f"{html.escape(file.name)}: {html.escape(str(e))}")

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
    docs = rag_engine.get_documents()
    total_chunks = rag_engine.get_chunk_count()
    if docs:
        for doc in docs:
            st.write(f"• {doc}")
            if st.button("🗑 删除", key=f"del_{doc}"):
                rag_engine.delete_document(doc)
                st.rerun()
        st.caption(f"总计 {total_chunks} 个文档片段")
    else:
        st.caption("暂无文档，请上传")

# === Main Chat ===
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("sources"):
            with st.expander("📖 参考来源"):
                for i, src in enumerate(msg["sources"]):
                    st.caption(f"**来源 {i + 1}: {src['source']}**")
                    st.text(src["content"][:300])

if prompt := st.chat_input("输入你的问题，比如「这份文档主要讲了什么？」"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("正在检索文档并生成回答..."):
            try:
                result = rag_engine.query(prompt)
                st.write(result["answer"])
                sources = result.get("sources", [])
                if sources:
                    with st.expander("📖 参考来源"):
                        for i, src in enumerate(sources):
                            st.caption(f"**来源 {i + 1}: {src['source']}**")
                            st.text(src["content"][:300])
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": result["answer"],
                        "sources": sources,
                    }
                )
            except Exception as e:
                st.error(f"查询失败: {e}")

# 智能滚动
st.components.v1.html(
    """
    <script>
    (function() {
        var main = window.parent.document.querySelector('.main');
        if (!main) return;
        var threshold = 100;
        var atBottom = main.scrollHeight - main.scrollTop - main.clientHeight < threshold;
        if (atBottom) {
            main.scrollTo(0, main.scrollHeight);
        }
    })();
    </script>
    """,
    height=0,
)
