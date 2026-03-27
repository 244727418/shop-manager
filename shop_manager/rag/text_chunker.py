# -*- coding: utf-8 -*-
"""
文本分块处理模块
负责将长文本分割成较小的块，便于向量检索
"""

import re
import os
from typing import List, Dict, Any, Optional


class TextChunker:
    """文本分块处理器"""
    
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        """
        初始化分块器
        
        Args:
            chunk_size: 每个块的字符数
            chunk_overlap: 块之间的重叠字符数
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        将文本分割成块
        
        Args:
            text: 要分割的文本
            metadata: 关联的元数据
        
        Returns:
            分块后的文本块列表
        """
        if not text or not text.strip():
            return []
        
        chunks = []
        text = text.strip()
        
        # 按段落分割
        paragraphs = self._split_by_paragraph(text)
        
        current_chunk = ""
        chunk_id = 0
        
        for para in paragraphs:
            # 如果单个段落就超过了块大小，需要进一步分割
            if len(para) > self.chunk_size:
                # 先保存当前累积的块
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk, chunk_id, metadata))
                    chunk_id += 1
                    current_chunk = ""
                
                # 对长段落进行分割
                sub_chunks = self._split_long_paragraph(para)
                for sub_chunk in sub_chunks:
                    chunks.append(self._create_chunk(sub_chunk, chunk_id, metadata))
                    chunk_id += 1
            
            # 如果加上这个段落会超过块大小，先保存当前块
            elif len(current_chunk) + len(para) + 1 > self.chunk_size:
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk, chunk_id, metadata))
                    chunk_id += 1
                
                # 保留最后一部分作为新块的开头（重叠部分）
                if self.chunk_overlap > 0 and len(current_chunk) > self.chunk_overlap:
                    current_chunk = current_chunk[-(self.chunk_overlap):] + "\n" + para
                else:
                    current_chunk = para
            else:
                # 添加到当前块
                if current_chunk:
                    current_chunk += "\n" + para
                else:
                    current_chunk = para
        
        # 保存最后一个块
        if current_chunk:
            chunks.append(self._create_chunk(current_chunk, chunk_id, metadata))
        
        return chunks
    
    def _split_by_paragraph(self, text: str) -> List[str]:
        """按段落分割文本"""
        # 先按换行分割
        lines = text.split('\n')
        paragraphs = []
        current_para = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_para:
                    paragraphs.append(current_para)
                    current_para = ""
            else:
                if current_para:
                    current_para += " " + line
                else:
                    current_para = line
        
        if current_para:
            paragraphs.append(current_para)
        
        return paragraphs
    
    def _split_long_paragraph(self, text: str) -> List[str]:
        """分割过长的段落"""
        chunks = []
        
        # 按句子分割
        sentences = re.split(r'([。！？.!?])', text)
        
        current_chunk = ""
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i]
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]  # 保留句号
            
            if len(current_chunk) + len(sentence) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                
                # 保留重叠
                if self.chunk_overlap > 0 and len(current_chunk) > self.chunk_overlap:
                    current_chunk = current_chunk[-(self.chunk_overlap):] + sentence
                else:
                    current_chunk = sentence
            else:
                current_chunk += sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _create_chunk(self, text: str, chunk_id: int, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """创建文本块"""
        chunk = {
            "chunk_id": chunk_id,
            "text": text.strip(),
            "char_count": len(text)
        }
        
        if metadata:
            chunk["metadata"] = metadata
        
        return chunk
    
    def chunk_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        将文件内容分割成块
        
        Args:
            file_path: 文件路径
        
        Returns:
            分块后的文本块列表
        """
        if not os.path.exists(file_path):
            return []
        
        # 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"读取文件失败 {file_path}: {e}")
            return []
        
        # 提取文件名作为元数据
        file_name = os.path.basename(file_path)
        
        metadata = {
            "file_path": file_path,
            "file_name": file_name
        }
        
        return self.chunk_text(content, metadata)
    
    def chunk_knowledge_items(self, items: List[tuple]) -> List[Dict[str, Any]]:
        """
        将知识库条目分割成块
        
        Args:
            items: 知识库条目列表 [(id, file_path, file_name, title, content, ...), ...]
        
        Returns:
            分块后的文本块列表
        """
        chunks = []
        
        for item in items:
            if len(item) >= 5:
                item_id = item[0]
                file_path = item[1] if len(item) > 1 else ""
                file_name = item[2] if len(item) > 2 else ""
                title = item[3] if len(item) > 3 else ""
                content = item[4] if len(item) > 4 else ""
                
                # 组合标题和内容
                full_text = f"【{title}】\n{content}"
                
                metadata = {
                    "item_id": item_id,
                    "file_path": file_path,
                    "file_name": file_name,
                    "title": title
                }
                
                item_chunks = self.chunk_text(full_text, metadata)
                chunks.extend(item_chunks)
        
        return chunks
