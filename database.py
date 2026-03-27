import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions
import os
import re
import logging

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, db_path: str = "./my_vectordb", collection_name: str = "research_data_cn"):
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name=collection_name,
                                                               embedding_function=self.embedding_function)
        logger.info(f"📚 知识库引擎启动，挂载集合: {collection_name}")

    def ingest_pdf(self, pdf_path: str, chunk_size: int = 400, overlap: int = 50) -> None:
        if not os.path.exists(pdf_path): return
        try:
            doc = fitz.open(pdf_path)
            paragraphs = []
            for page in doc:
                text = page.get_text()
                paragraphs.extend([p for p in re.split(r'\n\s*\n', text) if p.strip()])

            chunks, current_chunk, current_size = [], [], 0
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if not paragraph: continue
                if current_size + len(paragraph) <= chunk_size:
                    current_chunk.append(paragraph)
                    current_size += len(paragraph)
                else:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [paragraph]
                    current_size = len(paragraph)
            if current_chunk: chunks.append(" ".join(current_chunk))

            docs, metadatas, ids = [], [], []
            file_name = os.path.splitext(os.path.basename(pdf_path))[0]
            for idx, chunk in enumerate(chunks):
                docs.append(chunk)
                metadatas.append({"source": pdf_path, "file_name": file_name, "type": "pdf_document"})
                ids.append(f"{file_name}_chunk_{idx}")

            self.collection.upsert(documents=docs, metadatas=metadatas, ids=ids)
            logger.info(f"✅ {file_name} 的 {len(chunks)} 个碎片已吞噬！")
        except Exception as e:
            logger.error(f"处理PDF出错: {str(e)}")

    def query(self, question: str, top_k: int = 3) -> str:
        try:
            results = self.collection.query(query_texts=[question], n_results=top_k)
            if not results['documents'] or len(results['documents'][0]) == 0:
                return "本地数据库暂无相关资料。"
            return "\n".join(results['documents'][0])
        except Exception:
            return "本地数据库查询失败。"