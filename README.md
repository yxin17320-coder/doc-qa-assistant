# 智能文档问答助手

上传文档，用自然语言提问，AI 从文档里找答案。

支持 PDF、Word、TXT、Markdown 格式。

## 技术栈

- **RAG 框架**：LangChain + ChromaDB
- **后端**：FastAPI
- **前端**：Streamlit
- **大模型**：DeepSeek V4
- **向量化**：all-MiniLM-L6-v2 (本地)

## 本地运行

```bash
pip install -r requirements.txt

# 在 .env 里填入 DEEPSEEK_API_KEY

uvicorn api:app --host 0.0.0.0 --port 8000

streamlit run app.py
```

打开 http://localhost:8501 使用。
