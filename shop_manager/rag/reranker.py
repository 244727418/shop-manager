# -*- coding: utf-8 -*-
"""
重排序模块
使用交叉编码器对召回结果进行精排
"""

import os
import time
from typing import List, Dict, Any, Optional
import numpy as np


class Reranker:
    """重排序器"""

    DEFAULT_MODEL = "BAAI/bge-reranker-base"

    def __init__(self, model_name: str = None, device: str = "cpu"):
        """
        初始化重排序器

        Args:
            model_name: 重排序模型名称
            device: 设备类型 "cpu" 或 "cuda"
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device
        self._model = None
        self._tokenizer = None
        self._model_loading = False
        self._model_loaded = False

    def _load_model(self):
        """延迟加载模型"""
        if self._model_loaded or self._model_loading:
            return

        self._model_loading = True

        try:
            import os
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'

            print(f"[DEBUG] Reranker: 正在加载模型 {self.model_name}...")

            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            # 查找本地模型
            local_model_path = self._find_local_model()
            if local_model_path:
                print(f"[DEBUG] Reranker: 从本地加载模型: {local_model_path}")
                self._tokenizer = AutoTokenizer.from_pretrained(local_model_path)
                self._model = AutoModelForSequenceClassification.from_pretrained(local_model_path)
            else:
                print(f"[DEBUG] Reranker: 尝试在线加载模型（可能需要网络）...")
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)

            if self.device == "cuda" and hasattr(self._model, 'to'):
                self._model = self._model.to("cuda")

            self._model.eval()
            self._model_loaded = True
            print("[DEBUG] Reranker: 模型加载完成")

        except Exception as e:
            print(f"[ERROR] Reranker: 模型加载失败: {e}")
            self._model = None
            self._tokenizer = None
        finally:
            self._model_loading = False

    def _find_local_model(self) -> Optional[str]:
        """查找本地模型路径"""
        import os

        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "shop_manager", "bge-reranker-base"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bge-reranker-base"),
            os.path.expanduser("~/.cache/huggingface/hub/models--BAAI--bge-reranker-base"),
        ]

        for path in possible_paths:
            normalized = os.path.normpath(path)
            if os.path.exists(normalized) and os.path.isdir(normalized):
                has_model = any(f.endswith('.bin') or f.endswith('.safetensors') or f.endswith('.pt') for f in os.listdir(normalized) if os.path.isfile(os.path.join(normalized, f)))
                if has_model:
                    return normalized

        return None

    def rerank(self,
               query: str,
               results: List[Dict[str, Any]],
               top_k: int = 10) -> List[Dict[str, Any]]:
        """
        对检索结果进行重排序

        Args:
            query: 查询文本
            results: 检索结果列表
            top_k: 返回结果数量

        Returns:
            重排序后的结果列表
        """
        if not results:
            return []

        if not self._model_loaded:
            self._load_model()

        if self._model is None or self._tokenizer is None:
            print("[DEBUG] Reranker: 模型未加载，返回原始结果")
            return results[:top_k]

        start_time = time.time()

        # 准备查询-文档对
        pairs = []
        for result in results:
            content = result.get("content", "")
            title = result.get("title", "")
            # 组合标题和内容
            doc_text = f"{title} {content}" if title else content
            pairs.append([query, doc_text[:512]])  # 限制文档长度

        try:
            # 编码
            with np.no_grad():
                inputs = self._tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")

                if self.device == "cuda" and hasattr(inputs, 'to'):
                    inputs = {k: v.to("cuda") for k, v in inputs.items()}

                # 获取分数
                outputs = self._model(**inputs)
                scores = outputs.logits.squeeze(-1).cpu().numpy()

            # 更新结果分数
            for i, result in enumerate(results):
                result["rerank_score"] = float(scores[i])
                result["original_score"] = result.get("hybrid_score", result.get("vector_score", 0))

            # 按重排序分数排序
            results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

            elapsed = time.time() - start_time
            print(f"[DEBUG] Reranker: 重排序完成，耗时 {elapsed:.2f}s，处理 {len(results)} 个结果")

            # 打印前后变化
            if len(results) >= 3:
                print(f"[DEBUG] Reranker - Top3变化:")
                for i, r in enumerate(results[:3]):
                    print(f"  {i+1}. score={r.get('rerank_score', 0):.4f} title={r.get('title', '')[:30]}")

            return results[:top_k]

        except Exception as e:
            print(f"[ERROR] Reranker: 重排序失败: {e}")
            return results[:top_k]

    def is_ready(self) -> bool:
        """检查模型是否已加载"""
        return self._model_loaded and self._model is not None

    def unload(self):
        """卸载模型释放内存"""
        if self._model:
            del self._model
            self._model = None
        if self._tokenizer:
            del self._tokenizer
            self._tokenizer = None
        self._model_loaded = False
        print("[DEBUG] Reranker: 模型已卸载")


def create_reranker(model_name: str = None, device: str = "cpu") -> Reranker:
    """
    创建重排序器实例

    Args:
        model_name: 模型名称
        device: 设备类型

    Returns:
        Reranker实例
    """
    return Reranker(model_name, device)
