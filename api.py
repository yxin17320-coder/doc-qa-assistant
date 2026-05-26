import uuid
import traceback
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rag_engine import rag_engine

app = FastAPI(title="文档问答助手 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class QueryRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {"message": "文档问答助手 API 运行中", "version": "1.0.0"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "未提供文件")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".docx", ".doc", ".txt", ".md"]:
        raise HTTPException(400, f"不支持的文件格式: {ext}，支持 PDF/Word/TXT/Markdown")

    # 防止同名文件覆盖，加 UUID 前缀
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = UPLOAD_DIR / safe_name
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        chunk_count = rag_engine.add_document(str(file_path), display_name=file.filename)

        return {
            "filename": file.filename,
            "chunks": chunk_count,
            "message": f"文档已上传并处理，共切割为 {chunk_count} 个文本片段",
        }
    except Exception as e:
        print(f"[UPLOAD ERROR] {file.filename}: {e}")
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.post("/query")
async def query_document(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")
    try:
        result = rag_engine.query(req.question)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/documents")
async def list_documents():
    docs = rag_engine.get_documents()
    return {
        "documents": docs,
        "total_chunks": rag_engine.get_chunk_count(),
    }


@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    success = rag_engine.delete_document(filename)
    if not success:
        raise HTTPException(404, f"文档不存在: {filename}")
    return {"message": f"文档已删除: {filename}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
