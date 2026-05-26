import os
from typing import List, Dict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_community.vectorstores import Chroma

CHROMA_DIR = "./chroma_db"
DEEPSEEK_BASE = "https://api.deepseek.com"

# DeepSeek 目前不提供独立的 Embedding 服务
# 使用本地的 sentence-transformers 模型做向量化（免费，无需联网）
from langchain_community.embeddings import HuggingFaceEmbeddings


class RAGEngine:
    def __init__(self):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY。本地运行请在 .env 文件中设置；"
                "Streamlit Cloud 部署请在 Manage app → Secrets 中添加：\n"
                'DEEPSEEK_API_KEY = "sk-your-key-here"'
            )

        # 本地轻量 Embedding 模型，80MB，免费无需 API
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        # DeepSeek 对话模型，兼容 OpenAI SDK
        self.llm = ChatOpenAI(
            model="deepseek-chat",
            api_key=api_key,
            base_url=DEEPSEEK_BASE,
            temperature=0.3,
            max_tokens=2048,
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
        )

        os.makedirs(CHROMA_DIR, exist_ok=True)
        self.vectorstore = Chroma(
            embedding_function=self.embeddings,
            persist_directory=CHROMA_DIR,
        )
        self.uploaded_docs: Dict[str, int] = {}

    def load_document(self, file_path: str) -> List:
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            loader = PyPDFLoader(file_path)
        elif ext in [".docx", ".doc"]:
            loader = Docx2txtLoader(file_path)
        elif ext in [".txt", ".md"]:
            for enc in ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]:
                try:
                    return TextLoader(file_path, encoding=enc).load()
                except UnicodeDecodeError:
                    continue
            raise RuntimeError(f"无法识别文件编码: {file_path}")
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
        return loader.load()

    def add_document(self, file_path: str, display_name: str = None) -> int:
        docs = self.load_document(file_path)
        chunks = self.text_splitter.split_documents(docs)

        if not chunks:
            raise ValueError("文档内容为空或无法解析，可能是不支持的内容格式（如扫描件PDF、图片等）")

        filename = display_name or Path(file_path).name
        for chunk in chunks:
            chunk.metadata["source"] = filename

        self.vectorstore.add_documents(chunks)

        self.uploaded_docs[filename] = len(chunks)
        return len(chunks)

    def query(self, question: str, k: int = 4) -> Dict:
        docs = self.vectorstore.similarity_search(question, k=k)

        if docs:
            context_parts = []
            for i, doc in enumerate(docs):
                source = doc.metadata.get("source", "未知来源")
                context_parts.append(f"[来源{i + 1}: {source}]\n{doc.page_content}")
            context = "\n\n".join(context_parts)

            prompt = f"""你是一个智能助手。你的首要任务是基于用户上传的文档回答问题，但如果文档无法回答，就用自己的知识正常回复。

## 参考文档
{context}

## 用户问题
{question}

## 回答规则
- 文档相关内容优先：如果文档能回答问题，引用文档原文回答
- 自由对话：如果文档与问题无关，无视文档，用自己的知识正常回答，不要提及文档"""
        else:
            prompt = f"""你是一个智能助手。

## 用户问题
{question}

当前没有上传任何文档，请用自己的知识正常回答问题。"""

        response = self.llm.invoke(prompt)
        answer = response.content

        sources = []
        seen = set()
        for doc in docs:
            source = doc.metadata.get("source", "未知来源")
            if source not in seen:
                seen.add(source)
                sources.append(
                    {
                        "content": doc.page_content[:200],
                        "source": source,
                    }
                )

        return {
            "question": question,
            "answer": answer,
            "sources": sources,
        }

    def delete_document(self, filename: str) -> bool:
        if filename not in self.uploaded_docs:
            return False
        self.vectorstore._collection.delete(where={"source": filename})
        del self.uploaded_docs[filename]
        # 同时删除 uploads 目录下的原始文件
        for f in Path("./uploads").glob(f"*_{filename}"):
            f.unlink()
        return True

    def get_documents(self) -> List[str]:
        return list(self.uploaded_docs.keys())

    def get_chunk_count(self) -> int:
        return sum(self.uploaded_docs.values())
