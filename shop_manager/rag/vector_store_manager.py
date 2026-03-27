# -*- coding: utf-8 -*-
"""
向量数据库管理模块
使用ChromaDB管理向量索引
"""

import os
import pickle
import hashlib
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings


class VectorStoreManager:
    """向量数据库管理器"""
    
    def __init__(self, persist_directory: str = None):
        """
        初始化向量数据库管理器
        
        Args:
            persist_directory: 向量数据库持久化目录
        """
        if persist_directory is None:
            # 默认使用项目根目录下的vector_store文件夹
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            persist_directory = os.path.join(project_root, "vector_store")
        
        self.persist_directory = persist_directory
        
        # 确保目录存在
        os.makedirs(persist_directory, exist_ok=True)
        
        # 初始化ChromaDB客户端
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # 集合缓存
        self.collections = {}
        
        # 文件索引记录
        self.file_index_file = os.path.join(persist_directory, "file_index.pkl")
        self.file_index = self._load_file_index()
    
    def _load_file_index(self) -> Dict[str, dict]:
        """加载文件索引记录"""
        if os.path.exists(self.file_index_file):
            try:
                with open(self.file_index_file, 'rb') as f:
                    return pickle.load(f)
            except:
                return {}
        return {}
    
    def _save_file_index(self):
        """保存文件索引记录"""
        try:
            with open(self.file_index_file, 'wb') as f:
                pickle.dump(self.file_index, f)
        except Exception as e:
            print(f"保存文件索引失败: {e}")
    
    def get_or_create_collection(self, collection_name: str = "knowledge_base"):
        """
        获取或创建集合
        
        Args:
            collection_name: 集合名称
        
        Returns:
            ChromaDB集合对象
        """
        if collection_name not in self.collections:
            try:
                self.collections[collection_name] = self.client.get_or_create_collection(
                    name=collection_name,
                    metadata={"description": "知识库向量索引"}
                )
            except Exception as e:
                print(f"创建集合失败: {e}")
                # 尝试删除旧集合并重新创建
                try:
                    self.client.delete_collection(name=collection_name)
                    self.collections[collection_name] = self.client.get_or_create_collection(
                        name=collection_name,
                        metadata={"description": "知识库向量索引"}
                    )
                except:
                    raise Exception(f"无法创建集合 {collection_name}: {e}")
        
        return self.collections[collection_name]
    
    def add_documents(self, 
                     texts: List[str], 
                     metadatas: List[Dict[str, Any]] = None,
                     ids: List[str] = None,
                     collection_name: str = "knowledge_base"):
        """
        添加文档到向量数据库
        
        Args:
            texts: 文本列表
            metadatas: 元数据列表
            ids: 文档ID列表
            collection_name: 集合名称
        """
        collection = self.get_or_create_collection(collection_name)
        
        # 生成ID
        if ids is None:
            ids = [self._generate_id(text) for text in texts]
        
        # 确保metadatas长度匹配
        if metadatas is None:
            metadatas = [{} for _ in texts]
        
        # 添加到集合
        try:
            collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
        except Exception as e:
            print(f"添加文档失败: {e}")
            raise
    
    def query(self, 
              query_texts: List[str] = None,
              query_embedding: List[float] = None,
              n_results: int = 10,
              where: Dict[str, Any] = None,
              collection_name: str = "knowledge_base") -> Dict[str, Any]:
        """
        查询向量数据库
        
        Args:
            query_texts: 查询文本列表
            query_embedding: 查询向量
            n_results: 返回结果数量
            where: 过滤条件
            collection_name: 集合名称
        
        Returns:
            查询结果
        """
        collection = self.get_or_create_collection(collection_name)
        
        try:
            results = collection.query(
                query_texts=query_texts,
                query_embeddings=[query_embedding] if query_embedding else None,
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
            return results
        except Exception as e:
            print(f"查询失败: {e}")
            return {
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
                "ids": [[]]
            }
    
    def delete_by_ids(self, ids: List[str], collection_name: str = "knowledge_base"):
        """
        根据ID删除文档
        
        Args:
            ids: 文档ID列表
            collection_name: 集合名称
        """
        collection = self.get_or_create_collection(collection_name)
        
        try:
            collection.delete(ids=ids)
        except Exception as e:
            print(f"删除文档失败: {e}")
    
    def delete_by_file(self, file_path: str, collection_name: str = "knowledge_base"):
        """
        根据文件路径删除该文件的所有文档
        
        Args:
            file_path: 文件路径
            collection_name: 集合名称
        """
        collection = self.get_or_create_collection(collection_name)
        
        try:
            collection.delete(where={"file_path": {"$eq": file_path}})
            
            # 更新索引记录
            if file_path in self.file_index:
                del self.file_index[file_path]
                self._save_file_index()
        except Exception as e:
            print(f"删除文件文档失败: {e}")
    
    def update_file_index(self, file_path: str, doc_ids: List[str], chunk_count: int):
        """
        更新文件索引记录
        
        Args:
            file_path: 文件路径
            doc_ids: 文档ID列表
            chunk_count: 块数量
        """
        import time
        self.file_index[file_path] = {
            "doc_ids": doc_ids,
            "chunk_count": chunk_count,
            "indexed_at": time.time()
        }
        self._save_file_index()
    
    def get_file_index_status(self, file_path: str) -> Optional[dict]:
        """
        获取文件索引状态
        
        Args:
            file_path: 文件路径
        
        Returns:
            索引状态信息
        """
        return self.file_index.get(file_path)
    
    def get_total_count(self, collection_name: str = "knowledge_base") -> int:
        """
        获取集合中的文档总数
        
        Args:
            collection_name: 集合名称
        
        Returns:
            文档数量
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            return collection.count()
        except Exception as e:
            print(f"获取文档总数失败: {e}")
            return 0
    
    def get_stats(self, collection_name: str = "knowledge_base") -> Dict[str, Any]:
        """
        获取集合统计信息

        Args:
            collection_name: 集合名称

        Returns:
            统计信息字典
        """
        try:
            # 先检查collection是否存在
            try:
                collection = self.client.get_collection(name=collection_name)
                count = collection.count()
                return {
                    "total_documents": count,
                    "collection_name": collection_name,
                    "persist_directory": self.persist_directory
                }
            except Exception as collection_error:
                # Collection不存在
                if "not found" in str(collection_error).lower() or "does not exist" in str(collection_error).lower():
                    return {
                        "total_documents": 0,
                        "collection_name": collection_name,
                        "persist_directory": self.persist_directory,
                        "exists": False
                    }
                raise
        except Exception as e:
            print(f"获取统计信息失败: {e}")
            return {"total_documents": 0, "error": str(e)}
    
    def clear_collection(self, collection_name: str = "knowledge_base"):
        """
        清空集合
        
        Args:
            collection_name: 集合名称
        """
        try:
            self.client.delete_collection(name=collection_name)
            if collection_name in self.collections:
                del self.collections[collection_name]
            print(f"[DEBUG] 清空集合 {collection_name} 成功", flush=True)
        except Exception as e:
            print(f"清空集合失败: {e}", flush=True)
    
    def reset(self):
        """重置整个向量数据库"""
        try:
            self.client.reset()
            self.collections = {}
            self.file_index = {}
            self._save_file_index()
        except Exception as e:
            print(f"重置数据库失败: {e}")
    
    def _generate_id(self, text: str) -> str:
        """生成文档ID"""
        # 使用文本的hash作为ID
        hash_obj = hashlib.md5(text.encode('utf-8'))
        return hash_obj.hexdigest()[:16]
