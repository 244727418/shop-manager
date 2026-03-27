# -*- coding: utf-8 -*-
"""
RAG搜索核心引擎
整合向量检索、BM25混合检索、查询改写、重排序能力
"""

import os
import sys
import time
import threading
from typing import List, Dict, Any, Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from sentence_transformers import SentenceTransformer
import numpy as np

from vector_store_manager import VectorStoreManager
from text_chunker import TextChunker
from hybrid_retriever import HybridRetriever
from query_rewriter import QueryRewriter
from reranker import Reranker


class RAGSearchEngine:
    """RAG搜索核心引擎"""

    # 模型名称
    DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self,
                 model_name: str = None,
                 persist_directory: str = None,
                 chunk_size: int = 512,
                 chunk_overlap: int = 50,
                 vector_weight: float = 0.6,
                 bm25_weight: float = 0.4,
                 min_relevance: float = 0.01,
                 db=None):
        """
        初始化RAG搜索引擎

        Args:
            model_name: 嵌入模型名称
            persist_directory: 向量数据库持久化目录
            chunk_size: 文本分块大小
            chunk_overlap: 块重叠大小
            vector_weight: 向量检索权重
            bm25_weight: BM25权重
            min_relevance: 最小相关度阈值
            db: 数据库实例（用于查询改写）
        """
        self.model_name = model_name or self.DEFAULT_MODEL_NAME
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.db = db

        # 初始化组件
        self.vector_store = VectorStoreManager(persist_directory)
        self.text_chunker = TextChunker(chunk_size, chunk_overlap)
        self.hybrid_retriever = HybridRetriever(
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            min_relevance_score=min_relevance
        )

        # 查询改写器
        self.query_rewriter = QueryRewriter(db)

        # 重排序器
        self.reranker = Reranker()

        # 功能开关
        self.use_query_rewrite = True
        self.use_hybrid_search = True
        self.use_rerank = False

        # 模型和缓存
        self._model = None
        self._model_lock = threading.Lock()

        # 搜索缓存
        self._search_cache = {}
        self._cache_max_size = 100

        # 状态标志
        self._is_initialized = False
        self._init_error = None
    
    def initialize(self, timeout: int = 30) -> bool:
        """
        初始化引擎（加载模型）
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            是否初始化成功
        """
        if self._is_initialized:
            return True
        
        def _load_model():
            try:
                with self._model_lock:
                    if self._model is None:
                        print(f"正在加载嵌入模型: {self.model_name}...")
                        # 设置离线模式，避免联网下载
                        import os
                        os.environ['HF_HUB_OFFLINE'] = '1'
                        os.environ['TRANSFORMERS_OFFLINE'] = '1'
                        
                        # 先尝试导入 sentence_transformers
                        try:
                            from sentence_transformers import SentenceTransformer
                        except ImportError as ie:
                            print(f"[ERROR] 导入 sentence_transformers 失败: {ie}")
                            # 尝试安装缺失的依赖
                            import subprocess
                            import sys
                            print("[INFO] 尝试安装缺失模块...")
                            subprocess.check_call([sys.executable, "-m", "pip", "install", "regex", "-q"])
                            from sentence_transformers import SentenceTransformer
                        
                        # 尝试从本地缓存加载
                        local_model_path = self._find_local_model()
                        if local_model_path:
                            print(f"从本地加载模型: {local_model_path}")
                            self._model = SentenceTransformer(local_model_path)
                        else:
                            print("警告: 未找到本地模型，尝试在线下载...")
                            self._model = SentenceTransformer(self.model_name)
                        print("模型加载完成")
            except Exception as e:
                self._init_error = str(e)
                print(f"模型加载失败: {e}")
        
        # 在后台线程加载模型
        thread = threading.Thread(target=_load_model)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if self._model is not None:
            self._is_initialized = True
            return True
        return False
    
    def _find_local_model(self) -> str:
        """查找本地模型路径"""
        import os
        
        # 可能的本地模型路径
        possible_paths = [
            # 项目内路径 - 先检查 shop_manager 目录下
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "shop_manager", "sentence-transformers", "paraphrase-multilingual-MiniLM-L12-v2"),
            # 备用路径
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "sentence-transformers", "paraphrase-multilingual-MiniLM-L12-v2"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "minilm_model"),
            # Hugging Face缓存路径
            os.path.expanduser("~/.cache/torch/sentence_transformers/sentence-transformers_paraphrase-multilingual-MiniLM-L12-v2"),
            os.path.expanduser("~/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"),
        ]
        
        for path in possible_paths:
            normalized = os.path.normpath(path)
            print(f"[DEBUG] Checking model path: {normalized}, exists: {os.path.exists(normalized)}")
            if os.path.exists(normalized) and os.path.isdir(normalized):
                # 检查是否包含模型文件
                has_model = any(f.endswith('.bin') or f.endswith('.safetensors') for f in os.listdir(normalized) if os.path.isfile(os.path.join(normalized, f)))
                print(f"[DEBUG] Path has model files: {has_model}")
                if has_model:
                    return normalized
        
        return None
    
    def add_documents(self, 
                    knowledge_items: List[tuple],
                    show_progress: bool = True) -> Dict[str, Any]:
        """
        添加文档到索引
        
        Args:
            knowledge_items: 知识库条目列表
            show_progress: 是否显示进度
        
        Returns:
            索引结果统计
        """
        if not self._is_initialized:
            self.initialize()
        
        start_time = time.time()
        total_chunks = 0
        indexed_files = set()
        
        # 按文件分组
        file_items = {}
        for item in knowledge_items:
            if len(item) >= 5:
                file_path = item[1] if len(item) > 1 else ""
                if file_path not in file_items:
                    file_items[file_path] = []
                file_items[file_path].append(item)

        total_files = len(file_items)
        pbar = None
        if tqdm and show_progress:
            pbar = tqdm(total=total_files, desc="正在重建索引", unit="文件")

        # 索引每个文件
        for file_path, items in file_items.items():
            file_name = os.path.basename(file_path) if file_path else "unknown"
            indexed_files.add(file_name)

            if pbar:
                pbar.set_description(f"处理: {file_name[:20]}")
                pbar.update(1)
            
            # 分块
            chunks = self.text_chunker.chunk_knowledge_items(items)
            total_chunks += len(chunks)
            
            if not chunks:
                continue
            
            # 生成嵌入
            texts = [chunk["text"] for chunk in chunks]
            try:
                embeddings = self._model.encode(texts, show_progress_bar=False)
            except Exception as e:
                print(f"生成嵌入失败: {e}")
                continue
            
            # 准备元数据
            metadatas = []
            ids = []
            for i, chunk in enumerate(chunks):
                metadata = chunk.get("metadata", {})
                metadata["chunk_id"] = chunk["chunk_id"]
                metadata["char_count"] = chunk["char_count"]
                metadata["text_preview"] = chunk["text"][:100]
                metadatas.append(metadata)
                
                # 生成ID
                chunk_id = f"{file_name}_{chunk['chunk_id']}_{i}"
                ids.append(chunk_id)
            
            # 添加到向量数据库
            try:
                self.vector_store.add_documents(
                    texts=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                
                # 更新文件索引
                self.vector_store.update_file_index(file_path, ids, len(chunks))
                
            except Exception as e:
                print(f"添加到向量数据库失败: {e}")

        if pbar:
            pbar.close()

        elapsed = time.time() - start_time
        
        return {
            "total_items": len(knowledge_items),
            "total_chunks": total_chunks,
            "indexed_files": len(indexed_files),
            "elapsed_time": elapsed
        }
    
    def search(self,
              query: str,
              top_k: int = 20,
              knowledge_items: List[tuple] = None,
              selected_files: List[str] = None,
              use_cache: bool = True,
              min_relevance: float = None,
              use_rewrite: bool = None,
              use_hybrid: bool = None,
              use_rerank: bool = None) -> List[Dict[str, Any]]:
        """
        执行搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            knowledge_items: 知识库条目列表（用于BM25）
            selected_files: 选中的文件列表（用于向量检索过滤）
            use_cache: 是否使用缓存
            min_relevance: 最小相关度阈值（可选，不传则使用默认值）
            use_rewrite: 是否使用查询改写（默认使用类属性）
            use_hybrid: 是否使用混合检索（默认使用类属性）
            use_rerank: 是否使用重排序（默认使用类属性）

        Returns:
            搜索结果列表
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        # 确定各功能开关状态
        do_rewrite = use_rewrite if use_rewrite is not None else self.use_query_rewrite
        do_hybrid = use_hybrid if use_hybrid is not None else self.use_hybrid_search
        do_rerank = use_rerank if use_rerank is not None else self.use_rerank

        # 更新阈值（如果传入了新值）
        if min_relevance is not None and hasattr(self, 'hybrid_retriever'):
            self.hybrid_retriever.min_relevance_score = min_relevance

        # 构建缓存键（包含所有开关状态）
        if use_cache:
            current_threshold = self.hybrid_retriever.min_relevance_score if hasattr(self, 'hybrid_retriever') else 0.01
            cache_key = f"{query}_{top_k}_{current_threshold}_{do_rewrite}_{do_hybrid}_{do_rerank}"
            if cache_key in self._search_cache:
                return self._search_cache[cache_key]

        if not self._is_initialized:
            self.initialize()

        start_time = time.time()

        # ===== 1. 查询改写 =====
        original_query = query
        rewritten_query = query

        if do_rewrite:
            print(f"[DEBUG] Search: 启用查询改写，原查询: '{query}'")
            rewritten_query = self.query_rewriter.rewrite(query)
            if rewritten_query != query:
                print(f"[DEBUG] Search: 查询改写后: '{rewritten_query}'")
        else:
            print(f"[DEBUG] Search: 跳过查询改写")

        # ===== 2. 向量检索 =====
        try:
            query_embedding = self._model.encode([rewritten_query])[0].tolist()
            print(f"[DEBUG] Search: 查询向量生成成功: {rewritten_query}")
        except Exception as e:
            print(f"生成查询向量失败: {e}")
            query_embedding = None

        vector_results = None
        if query_embedding:
            try:
                # 混合检索需要更多候选
                candidate_k = top_k * 5 if do_rerank else top_k * 2
                # 添加文件过滤
                where_filter = {"file_name": {"$in": selected_files}} if selected_files else None
                vector_results = self.vector_store.query(
                    query_embedding=query_embedding,
                    n_results=candidate_k,
                    where=where_filter
                )
                if vector_results and vector_results.get("documents"):
                    doc_count = len([d for d in vector_results["documents"][0] if d])
                    print(f"[DEBUG] Search: 向量检索返回 {doc_count} 个结果")
                else:
                    print(f"[DEBUG] Search: 向量检索无结果")
            except Exception as e:
                print(f"向量检索失败: {e}")

        # ===== 3. 混合检索或纯向量检索 =====
        print(f"[DEBUG] Search: 混合检索={do_hybrid}, min_relevance: {self.hybrid_retriever.min_relevance_score}")

        if do_hybrid:
            results = self.hybrid_retriever.search(
                query=rewritten_query,
                vector_results=vector_results,
                knowledge_items=knowledge_items,
                top_k=top_k * 5 if do_rerank else top_k
            )
        else:
            # 纯向量检索
            results = self._vector_only_search(vector_results, top_k * 5 if do_rerank else top_k)

        print(f"[DEBUG] Search: 检索阶段返回 {len(results)} 个结果")

        # ===== 4. 重排序 =====
        if do_rerank and results:
            print(f"[DEBUG] Search: 启用重排序，候选数量: {len(results)}")
            results = self.reranker.rerank(
                query=rewritten_query,
                results=results,
                top_k=top_k
            )
        else:
            print(f"[DEBUG] Search: 跳过重排序")

        # ===== 5. 后处理：添加匹配片段 =====
        for result in results:
            content = result.get("content", "")
            query_lower = rewritten_query.lower()

            # 查找最佳匹配片段
            best_match = self._find_best_match_snippet(content, query_lower)
            result["match_snippet"] = best_match

            # 记录原始查询和改写后的查询
            result["original_query"] = original_query
            result["rewritten_query"] = rewritten_query

        elapsed = time.time() - start_time

        # 添加耗时信息
        for result in results:
            result["search_time"] = elapsed

        # 更新缓存
        if use_cache and results:
            if len(self._search_cache) >= self._cache_max_size:
                self._search_cache.pop(next(iter(self._search_cache)))
            self._search_cache[cache_key] = results

        print(f"[DEBUG] Search: 搜索完成，总耗时 {elapsed:.2f}s，返回 {len(results)} 个结果")

        return results

    def _vector_only_search(self, vector_results, top_k: int) -> List[Dict[str, Any]]:
        """纯向量检索（不使用BM25）"""
        results = []

        if vector_results and vector_results.get("documents"):
            for i, doc in enumerate(vector_results["documents"][0]):
                if not doc:
                    continue
                metadata = vector_results.get("metadatas", [[{}]])[0][i]
                distance = vector_results.get("distances", [[1.0]])[0][i]

                similarity = 1.0 / (1.0 + distance)

                item_id = metadata.get("item_id") or metadata.get("id", f"vec_{i}")

                results.append({
                    "item_id": item_id,
                    "title": metadata.get("title", ""),
                    "content": doc,
                    "file_path": metadata.get("file_path", ""),
                    "file_name": metadata.get("file_name", ""),
                    "vector_score": similarity,
                    "hybrid_score": similarity,
                    "source": "vector"
                })

        # 按分数排序
        results.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        return results[:top_k]
    
    def _find_best_match_snippet(self, content: str, query: str, context_len: int = 50) -> str:
        """查找最佳匹配片段"""
        content_lower = content.lower()
        
        # 查找查询词在内容中的位置
        pos = content_lower.find(query)
        
        if pos >= 0:
            # 找到匹配，返回周围上下文
            start = max(0, pos - context_len)
            end = min(len(content), pos + len(query) + context_len)
            snippet = content[start:end]
            
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."
            
            return snippet
        
        # 如果没有精确匹配，返回开头
        return content[:context_len * 2] + ("..." if len(content) > context_len * 2 else "")
    
    def delete_file_index(self, file_path: str):
        """
        删除文件索引
        
        Args:
            file_path: 文件路径
        """
        self.vector_store.delete_by_file(file_path)
    
    def rebuild_index(self, knowledge_items: List[tuple], show_progress: bool = True) -> Dict[str, Any]:
        """
        重建索引
        
        Args:
            knowledge_items: 知识库条目列表
            show_progress: 是否显示进度
        
        Returns:
            重建结果统计
        """
        # 清空现有索引
        print(f"[DEBUG] 重建索引: 开始清空旧数据...", flush=True)
        self.clear_index()
        print(f"[DEBUG] 重建索引: 旧数据已清空", flush=True)
        
        # 重新添加
        return self.add_documents(knowledge_items, show_progress)
    
    def clear_index(self):
        """清空所有索引"""
        self.vector_store.clear_collection()
        self._search_cache.clear()
    
    def get_index_stats(self) -> Dict[str, Any]:
        """
        获取索引统计信息
        
        Returns:
            统计信息
        """
        return {
            "total_vectors": self.vector_store.get_total_count(),
            "model_name": self.model_name,
            "chunk_size": self.chunk_size,
            "cache_size": len(self._search_cache)
        }
    
    def warm_up(self):
        """预热引擎"""
        # 触发模型加载
        if not self._is_initialized:
            self.initialize()
    
    def clear_cache(self):
        """清除搜索缓存"""
        self._search_cache.clear()


# 全局单例
_global_engine = None


def get_search_engine(**kwargs) -> RAGSearchEngine:
    """
    获取全局搜索引擎实例

    Args:
        **kwargs: 引擎初始化参数

    Returns:
        RAGSearchEngine实例
    """
    global _global_engine

    if _global_engine is None:
        _global_engine = RAGSearchEngine(**kwargs)

    return _global_engine


def reset_search_engine():
    """重置全局搜索引擎"""
    global _global_engine

    if _global_engine:
        _global_engine.clear_index()
        _global_engine = None


class RAGSearchConfig:
    """RAG搜索配置类"""

    DEFAULT_CONFIG = {
        "use_query_rewrite": True,
        "use_hybrid_search": True,
        "use_rerank": False,
        "vector_weight": 0.6,
        "bm25_weight": 0.4,
        "min_relevance": 0.01,
        "rerank_candidate_count": 50,
    }

    @staticmethod
    def get_config_from_db(db) -> Dict[str, Any]:
        """
        从数据库获取配置

        Args:
            db: 数据库实例

        Returns:
            配置字典
        """
        config = RAGSearchConfig.DEFAULT_CONFIG.copy()

        if db is None:
            return config

        try:
            # 读取各配置项
            config["use_query_rewrite"] = db.get_setting("rag_use_query_rewrite", "true").lower() == "true"
            config["use_hybrid_search"] = db.get_setting("rag_use_hybrid_search", "true").lower() == "true"
            config["use_rerank"] = db.get_setting("rag_use_rerank", "false").lower() == "true"

            # 权重设置
            vector_weight = db.get_setting("rag_vector_weight", None)
            if vector_weight:
                config["vector_weight"] = float(vector_weight)
                config["bm25_weight"] = 1.0 - config["vector_weight"]

            # 相关度阈值
            min_relevance = db.get_setting("rag_min_relevance", None)
            if min_relevance:
                config["min_relevance"] = float(min_relevance)

            # 重排序候选数量
            rerank_count = db.get_setting("rag_rerank_candidate_count", None)
            if rerank_count:
                config["rerank_candidate_count"] = int(rerank_count)

        except Exception as e:
            print(f"[DEBUG] 读取RAG配置失败: {e}")

        return config

    @staticmethod
    def apply_config_to_engine(engine: RAGSearchEngine, config: Dict[str, Any]):
        """
        将配置应用到搜索引擎

        Args:
            engine: RAGSearchEngine实例
            config: 配置字典
        """
        if "use_query_rewrite" in config:
            engine.use_query_rewrite = config["use_query_rewrite"]
        if "use_hybrid_search" in config:
            engine.use_hybrid_search = config["use_hybrid_search"]
        if "use_rerank" in config:
            engine.use_rerank = config["use_rerank"]
        if "vector_weight" in config:
            engine.hybrid_retriever.vector_weight = config["vector_weight"]
        if "bm25_weight" in config:
            engine.hybrid_retriever.bm25_weight = config["bm25_weight"]
        if "min_relevance" in config:
            engine.hybrid_retriever.min_relevance_score = config["min_relevance"]

        print(f"[DEBUG] RAG配置已应用: 查询改写={config.get('use_query_rewrite')}, "
              f"混合检索={config.get('use_hybrid_search')}, "
              f"重排序={config.get('use_rerank')}, "
              f"向量权重={config.get('vector_weight')}")
