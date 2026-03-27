# -*- coding: utf-8 -*-
"""
查询改写模块
使用LLM将用户口语化问题改写成更适合向量检索的精炼查询
"""

import os
import re
import json
import time
from typing import Optional, Dict, Any


class QueryRewriter:
    """查询改写器"""

    def __init__(self, db=None):
        """
        初始化查询改写器

        Args:
            db: 数据库实例，用于获取API配置
        """
        self.db = db
        self._cache = {}
        self._cache_max_size = 100

    def _get_api_config(self) -> Dict[str, Any]:
        """获取API配置"""
        api_key = None
        if self.db:
            api_key = self.db.get_setting("ai_api_key", "")

        if not api_key:
            return {"available": False, "error": "未配置API Key"}

        api_type = "deepseek" if ("sk-" in api_key or api_key.startswith("deepseek-")) else "openai"

        return {
            "available": True,
            "api_key": api_key,
            "api_type": api_type,
            "url": "https://api.deepseek.com/v1/chat/completions" if api_type == "deepseek" else "https://api.openai.com/v1/chat/completions",
            "model": "deepseek-chat" if api_type == "deepseek" else "gpt-3.5-turbo"
        }

    def rewrite(self, query: str) -> str:
        """
        改写查询

        Args:
            query: 用户原始查询

        Returns:
            改写后的查询，如果失败则返回原始查询
        """
        if not query or not query.strip():
            return query

        query = query.strip()

        # 检查缓存
        if query in self._cache:
            return self._cache[query]

        # 获取API配置
        config = self._get_api_config()

        if not config.get("available"):
            print(f"[DEBUG] QueryRewriter: {config.get('error')}, 使用原始查询")
            return query

        # 调用LLM进行改写
        try:
            rewritten = self._call_llm_rewrite(query, config)
            if rewritten and rewritten.strip():
                rewritten = rewritten.strip()
                # 更新缓存
                if len(self._cache) >= self._cache_max_size:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[query] = rewritten
                print(f"[DEBUG] QueryRewriter: '{query}' -> '{rewritten}'")
                return rewritten
        except Exception as e:
            print(f"[DEBUG] QueryRewriter LLM调用失败: {e}")

        # 失败时返回原始查询
        return query

    def _call_llm_rewrite(self, query: str, config: Dict[str, Any]) -> Optional[str]:
        """
        调用LLM进行查询改写

        Args:
            query: 原始查询
            config: API配置

        Returns:
            改写后的查询
        """
        import requests

        prompt = self._build_prompt(query)

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json"
        }

        data = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": "你是一个查询改写专家，专门将用户的口语化问题改写成适合向量检索的精炼查询。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }

        try:
            response = requests.post(
                config["url"],
                headers=headers,
                json=data,
                timeout=15
            )

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    # 提取改写后的查询（去掉可能的引号或前缀）
                    return self._extract_rewritten_query(content)
            else:
                print(f"[DEBUG] QueryRewriter API错误: {response.status_code} - {response.text[:200]}")
        except requests.exceptions.Timeout:
            print("[DEBUG] QueryRewriter API超时")
        except Exception as e:
            print(f"[DEBUG] QueryRewriter API异常: {e}")

        return None

    def _build_prompt(self, query: str) -> str:
        """构建改写提示词"""
        return f"""你是一个查询改写专家。用户输入的问题可能口语化、模糊，请将其改写成适合向量检索的精炼查询。

要求：
- 去除口语化表达（如"怎么办"、"怎么弄"、"麻烦帮我查一下"等）
- 保留核心术语、错误码、产品名、数量词等关键信息
- 如果用户问题本身已经清晰简洁，保持原样
- 输出只返回改写后的查询语句，不要任何解释、不要任何引号包裹

用户问题：{query}
改写后："""

    def _extract_rewritten_query(self, content: str) -> str:
        """从LLM输出中提取改写后的查询"""
        # 去除可能的引号包裹
        content = content.strip()

        # 如果有"改写后："或"结果："等前缀，取冒号后面的内容
        for prefix in ["改写后：", "改写后:", "结果：", "结果:", "查询：", "查询:"]:
            if prefix in content:
                content = content.split(prefix)[-1].strip()
                break

        # 去除可能的引号
        if (content.startswith('"') and content.endswith('"')) or \
           (content.startswith("'") and content.endswith("'")):
            content = content[1:-1].strip()

        return content

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()

    def set_db(self, db):
        """设置数据库实例"""
        self.db = db


def create_query_rewriter(db=None) -> QueryRewriter:
    """
    创建查询改写器实例

    Args:
        db: 数据库实例

    Returns:
        QueryRewriter实例
    """
    return QueryRewriter(db)
