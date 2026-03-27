# -*- coding: utf-8 -*-
"""
混合检索模块
结合向量检索和BM25关键词检索
"""

import os
import re
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from rank_bm25 import BM25Okapi


class HybridRetriever:
    """混合检索器"""
    
    def __init__(self,
                 vector_weight: float = 0.7,
                 bm25_weight: float = 0.3,
                 min_relevance_score: float = 0.01):
        """
        初始化混合检索器

        Args:
            vector_weight: 向量检索权重（提高向量权重以支持语义搜索）
            bm25_weight: BM25权重
            min_relevance_score: 最小相关度阈值（设置为极低以显示所有结果）
        """
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.min_relevance_score = min_relevance_score

        # BM25模型缓存
        self._bm25_model = None
        self._bm25_corpus = None
        self._bm25_doc_ids = None
    
    def search(self, 
               query: str,
               vector_results: Dict[str, Any] = None,
               knowledge_items: List[tuple] = None,
               top_k: int = 20) -> List[Dict[str, Any]]:
        """
        执行混合检索
        
        Args:
            query: 查询文本
            vector_results: 向量检索结果
            knowledge_items: 知识库条目列表 [(id, file_path, file_name, title, content, ...), ...]
            top_k: 返回结果数量
        
        Returns:
            混合检索结果列表
        """
        results = []
        
        # 1. 向量检索结果
        vector_scores = {}
        max_vector_score = 0.0
        raw_distances = []
        
        # 计算最大距离用于归一化
        all_distances = []
        if vector_results and vector_results.get("documents"):
            for i, doc in enumerate(vector_results["documents"][0]):
                if not doc:
                    continue
                distance = vector_results.get("distances", [[1.0]])[0][i]
                all_distances.append(distance)
        
        max_distance = max(all_distances) if all_distances else 1.0
        
        if vector_results and vector_results.get("documents"):
            for i, doc in enumerate(vector_results["documents"][0]):
                if not doc:
                    continue
                metadata = vector_results.get("metadatas", [[{}]])[0][i]
                distance = vector_results.get("distances", [[1.0]])[0][i]
                raw_distances.append(distance)
                
                # 转换距离为相似度：使用 1/(1+distance) 公式
                # 距离12.64 -> 1/(1+12.64) = 0.073
                similarity = 1.0 / (1.0 + distance)
                max_vector_score = max(max_vector_score, similarity)
                
                item_id = metadata.get("item_id") or metadata.get("id", f"vec_{i}")
                
                vector_scores[item_id] = {
                    "item_id": item_id,
                    "title": metadata.get("title", ""),
                    "content": doc,
                    "file_path": metadata.get("file_path", ""),
                    "file_name": metadata.get("file_name", ""),
                    "vector_score": similarity,
                    "raw_distance": distance,
                    "source": "vector"
                }
        
        print(f"[DEBUG] 向量检索: {len(vector_scores)} 个结果, 原始距离: {raw_distances[:5]}, 转换后最高相似度: {max_vector_score:.4f}", flush=True)
        
        # 打印每个结果的详细信息用于调试重复问题
        for item_id, info in list(vector_scores.items())[:5]:
            print(f"[DEBUG] 结果详情: item_id={item_id}, distance={info.get('raw_distance', 'N/A')}, score={info.get('vector_score', 0):.4f}", flush=True)
        
        # 2. BM25检索结果
        bm25_scores = {}
        max_bm25_score = 0.0
        
        print(f"[DEBUG] BM25检索，knowledge_items数量: {len(knowledge_items) if knowledge_items else 0}", flush=True)
        
        if knowledge_items and len(knowledge_items) > 0:
            bm25_results = self._bm25_search(query, knowledge_items, top_k * 2)
            for item_id, score, item in bm25_results:
                max_bm25_score = max(max_bm25_score, score)
                bm25_scores[item_id] = {
                    "item_id": item_id,
                    "title": item[3] if len(item) > 3 else "",
                    "content": item[4] if len(item) > 4 else "",
                    "file_path": item[1] if len(item) > 1 else "",
                    "file_name": item[2] if len(item) > 2 else "",
                    "bm25_score": score,
                    "source": "bm25"
                }
        
        print(f"[DEBUG] BM25检索: {len(bm25_scores)} 个结果, 最高BM25分: {max_bm25_score}", flush=True)
        
        # 3. 合并结果
        all_item_ids = set(vector_scores.keys()) | set(bm25_scores.keys())
        
        for item_id in all_item_ids:
            vec_info = vector_scores.get(item_id, {})
            bm25_info = bm25_scores.get(item_id, {})
            
            # 获取原始分数
            vec_score = vec_info.get("vector_score", 0.0)
            bm25_score = bm25_info.get("bm25_score", 0.0)
            
            # 使用原始向量分数（已经是0-1范围的相似度）
            vec_score = vec_info.get("vector_score", 0.0)
            
            # 如果BM25有数据则归一化
            if max_bm25_score > 0:
                bm25_score = bm25_score / max_bm25_score
            
            # 计算混合分数
            if bm25_scores:
                # 如果BM25有数据，用混合权重
                hybrid_score = (self.vector_weight * vec_score + 
                              self.bm25_weight * bm25_score)
            else:
                # 如果BM25没数据，直接用向量分数
                hybrid_score = vec_score
            
            # 添加关键词匹配boost - 如果标题或内容包含查询词，大幅提升分数
            title = vec_info.get("title", "") or bm25_info.get("title", "")
            content = vec_info.get("content", "") or bm25_info.get("content", "")
            
            # 检查标题是否包含查询词（精确匹配）
            query_lower = query.lower()
            title_lower = title.lower()
            content_lower = content.lower()
            
            # 标题匹配boost
            if query_lower in title_lower:
                hybrid_score += 0.1  # 标题匹配加0.1
            # 内容匹配boost
            elif query_lower in content_lower:
                hybrid_score += 0.05  # 内容匹配加0.05
            
            # 合并信息
            result = {
                "item_id": item_id,
                "title": title,
                "content": content,
                "file_path": vec_info.get("file_path") or bm25_info.get("file_path", ""),
                "file_name": vec_info.get("file_name") or bm25_info.get("file_name", ""),
                "vector_score": vec_score,
                "bm25_score": bm25_score,
                "hybrid_score": hybrid_score,
                "source": "hybrid"
            }
            
            results.append(result)
        
        # 4. 按混合分数排序
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        print(f"[DEBUG] 混合检索排序后: {len(results)} 个结果, 阈值: {self.min_relevance_score}")
        if results:
            print(f"[DEBUG] 最高分: {results[0]['hybrid_score']}, 最低分: {results[-1]['hybrid_score']}")

        # 5. 过滤低相关度结果
        results = [r for r in results if r["hybrid_score"] >= self.min_relevance_score]
        print(f"[DEBUG] 过滤后剩余: {len(results)} 个结果")
        
        # 6. 去重（同一item_id只保留一个，保留最高分）
        best_by_id = {}
        for r in results:
            item_id = r.get("item_id", "")
            if item_id:
                if item_id not in best_by_id:
                    best_by_id[item_id] = r
                else:
                    # 如果已存在，保留分数更高的
                    if r["hybrid_score"] > best_by_id[item_id]["hybrid_score"]:
                        best_by_id[item_id] = r
        
        deduplicated = list(best_by_id.values())
        
        # 重新按分数排序
        deduplicated.sort(key=lambda x: x["hybrid_score"], reverse=True)
        
        print(f"[DEBUG] 去重前: {len(results)} 个结果, 去重后: {len(deduplicated)} 个结果")
        
        return deduplicated[:top_k]
    
    def _bm25_search(self, 
                    query: str, 
                    knowledge_items: List[tuple], 
                    top_k: int) -> List[Tuple[str, float, tuple]]:
        """
        执行BM25检索
        
        Args:
            query: 查询文本
            knowledge_items: 知识库条目列表
            top_k: 返回结果数量
        
        Returns:
            BM25检索结果 [(item_id, score, item), ...]
        """
        # 准备语料库
        corpus = []
        doc_ids = []
        
        for item in knowledge_items:
            if len(item) >= 5:
                item_id = item[0]
                title = item[3] if len(item) > 3 else ""
                content = item[4] if len(item) > 4 else ""
                
                # 组合标题和内容
                text = f"{title} {content}"
                corpus.append(text)
                doc_ids.append(item_id)
        
        if not corpus:
            return []
        
        # 预处理查询
        query = query.lower()
        query_terms = self._tokenize(query)
        
        # 构建BM25模型
        tokenized_corpus = [self._tokenize(doc) for doc in corpus]
        
        try:
            bm25 = BM25Okapi(tokenized_corpus)
        except:
            return []
        
        # 获取BM25分数
        scores = bm25.get_scores(query_terms)
        
        # 排序并返回top_k
        results = []
        for i, score in enumerate(scores):
            # BM25分数可能是0或负数，需要保留所有非负分数
            if score >= 0:
                results.append((doc_ids[i], score, knowledge_items[i]))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def _tokenize(self, text: str) -> List[str]:
        """
        文本分词
        
        Args:
            text: 输入文本
        
        Returns:
            分词结果列表
        """
        # 转换为小写
        text = text.lower()
        
        # 简单分词：按空格和标点分割
        # 保留中文和英文单词
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|\d+', text)
        
        # 过滤空字符串
        tokens = [t for t in tokens if t]
        
        return tokens
    
    def set_weights(self, vector_weight: float, bm25_weight: float):
        """
        设置检索权重
        
        Args:
            vector_weight: 向量检索权重
            bm25_weight: BM25权重
        """
        total = vector_weight + bm25_weight
        if total > 0:
            self.vector_weight = vector_weight / total
            self.bm25_weight = bm25_weight / total
    
    def set_min_relevance(self, min_score: float):
        """
        设置最小相关度阈值
        
        Args:
            min_score: 最小相关度分数
        """
        self.min_relevance_score = min_score
