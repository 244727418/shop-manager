# -*- coding: utf-8 -*-
"""
搜索UI适配层
将RAG搜索引擎集成到现有UI
"""

import time
import os
import sys
from typing import List, Dict, Any, Optional, Callable

# 直接导入，避免相对导入问题
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from rag_search_engine import RAGSearchEngine, get_search_engine, RAGSearchConfig


class SearchUIAdapter:
    """搜索UI适配器"""

    def __init__(self, db=None):
        """
        初始化适配器

        Args:
            db: 数据库实例
        """
        self.db = db
        self.engine = None
        self._is_indexing = False
        self._last_index_time = 0
        self._index_cooldown = 60  # 索引冷却时间（秒）

    def initialize(self, model_name: str = None, timeout: int = 30) -> bool:
        """
        初始化搜索引擎

        Args:
            model_name: 嵌入模型名称
            timeout: 超时时间

        Returns:
            是否初始化成功
        """
        self.engine = get_search_engine(model_name=model_name, db=self.db)

        # 应用配置
        if self.db:
            config = RAGSearchConfig.get_config_from_db(self.db)
            RAGSearchConfig.apply_config_to_engine(self.engine, config)

        return self.engine.initialize(timeout=timeout)

    def build_index(self, knowledge_items: List[tuple], force: bool = False) -> Dict[str, Any]:
        """
        构建搜索索引

        Args:
            knowledge_items: 知识库条目列表
            force: 是否强制重建索引

        Returns:
            索引结果
        """
        if self._is_indexing:
            return {"status": "indexing", "message": "索引正在构建中..."}

        # 检查冷却时间
        current_time = time.time()
        if not force and (current_time - self._last_index_time) < self._index_cooldown:
            remaining = int(self._index_cooldown - (current_time - self._last_index_time))
            return {"status": "cooldown", "message": f"请等待{remaining}秒后再重建索引"}

        self._is_indexing = True

        try:
            if force:
                result = self.engine.rebuild_index(knowledge_items)
            else:
                result = self.engine.add_documents(knowledge_items)

            self._last_index_time = time.time()
            result["status"] = "success"
            return result

        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            self._is_indexing = False

    def search(self,
              query: str,
              top_k: int = 10,
              knowledge_items: List[tuple] = None,
              selected_files: List[str] = None,
              use_rag: bool = True,
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
            use_rag: 是否使用RAG搜索
            min_relevance: 最小相关度阈值
            use_rewrite: 是否使用查询改写（None则使用配置）
            use_hybrid: 是否使用混合检索（None则使用配置）
            use_rerank: 是否使用重排序（None则使用配置）

        Returns:
            搜索结果列表
        """
        if not query or not query.strip():
            return []

        if not self.engine:
            self.initialize()

        try:
            if use_rag and self.engine and self.engine._is_initialized:
                # 使用RAG混合搜索（支持查询改写、混合检索、重排序）
                results = self.engine.search(
                    query=query,
                    top_k=top_k,
                    knowledge_items=knowledge_items,
                    selected_files=selected_files,
                    min_relevance=min_relevance,
                    use_rewrite=use_rewrite,
                    use_hybrid=use_hybrid,
                    use_rerank=use_rerank
                )

                # 格式化结果
                formatted = []
                for i, r in enumerate(results):
                    formatted.append({
                        "rank": i + 1,
                        "item_id": r.get("item_id"),
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "file_name": r.get("file_name", ""),
                        "file_path": r.get("file_path", ""),
                        "hybrid_score": r.get("hybrid_score", 0),
                        "vector_score": r.get("vector_score", 0),
                        "bm25_score": r.get("bm25_score", 0),
                        "rerank_score": r.get("rerank_score", 0),
                        "match_snippet": r.get("match_snippet", ""),
                        "search_time": r.get("search_time", 0),
                        "original_query": r.get("original_query", query),
                        "rewritten_query": r.get("rewritten_query", query)
                    })

                return formatted
            else:
                # 降级到纯BM25搜索
                if knowledge_items:
                    return self._simple_search(query, knowledge_items, top_k)
                return []

        except Exception as e:
            print(f"搜索失败: {e}")
            # 降级到简单搜索
            if knowledge_items:
                return self._simple_search(query, knowledge_items, top_k)
            return []

    def reload_config(self):
        """重新加载配置"""
        if self.engine and self.db:
            config = RAGSearchConfig.get_config_from_db(self.db)
            RAGSearchConfig.apply_config_to_engine(self.engine, config)

    def set_feature_flags(self, use_rewrite: bool = None, use_hybrid: bool = None, use_rerank: bool = None):
        """
        设置功能开关

        Args:
            use_rewrite: 是否启用查询改写
            use_hybrid: 是否启用混合检索
            use_rerank: 是否启用重排序
        """
        if self.engine:
            if use_rewrite is not None:
                self.engine.use_query_rewrite = use_rewrite
            if use_hybrid is not None:
                self.engine.use_hybrid_search = use_hybrid
            if use_rerank is not None:
                self.engine.use_rerank = use_rerank

    def _simple_search(self,
                      query: str,
                      knowledge_items: List[tuple],
                      top_k: int) -> List[Dict[str, Any]]:
        """简单的关键词搜索（降级方案）"""
        query_lower = query.lower()
        results = []

        for item in knowledge_items:
            if len(item) >= 5:
                item_id = item[0]
                file_path = item[1] if len(item) > 1 else ""
                file_name = item[2] if len(item) > 2 else ""
                title = item[3] if len(item) > 3 else ""
                content = item[4] if len(item) > 4 else ""

                # 计算简单相关度
                score = 0
                if query_lower in title.lower():
                    score = 100
                elif query_lower in content.lower():
                    score = 50

                if score > 0:
                    results.append({
                        "rank": 0,
                        "item_id": item_id,
                        "title": title,
                        "content": content,
                        "file_name": file_name,
                        "file_path": file_path,
                        "hybrid_score": score / 100.0,
                        "vector_score": 0,
                        "bm25_score": score / 100.0,
                        "rerank_score": 0,
                        "match_snippet": content[:100],
                        "search_time": 0,
                        "original_query": query,
                        "rewritten_query": query
                    })

        # 排序
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        # 添加排名
        for i, r in enumerate(results[:top_k]):
            r["rank"] = i + 1

        return results[:top_k]

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引状态"""
        if self.engine:
            return self.engine.get_index_stats()
        return {"total_vectors": 0, "model_name": "", "status": "not_initialized"}

    def clear_index(self):
        """清空索引"""
        if self.engine:
            self.engine.clear_index()

    def warm_up(self):
        """预热引擎"""
        if self.engine:
            self.engine.warm_up()


# 全局适配器实例
_global_adapter = None


def get_search_adapter(db=None) -> SearchUIAdapter:
    """
    获取全局搜索适配器

    Args:
        db: 数据库实例

    Returns:
        SearchUIAdapter实例
    """
    global _global_adapter

    if _global_adapter is None:
        _global_adapter = SearchUIAdapter(db)

    return _global_adapter
