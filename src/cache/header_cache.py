# -*- coding: utf-8 -*-
"""
Header mapping cache management
Caches AI-analyzed header mappings to avoid repeated API calls
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from ..parsers.base import HeaderMapping

logger = logging.getLogger(__name__)


class HeaderCache:
    """
    表头映射缓存管理器
    
    缓存结构：~/.check-yg/cache/{task_id}/{document_hash}.json
    支持增量提取：通过文件hash检测文件是否变化
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存根目录，默认 ~/.check-yg/cache/
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / '.check-yg' / 'cache'
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_task_dir(self, task_id: str) -> Path:
        """获取任务缓存目录"""
        task_dir = self.cache_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir
    
    def _get_cache_path(self, task_id: str, document_name: str) -> Path:
        """获取缓存文件路径"""
        # 使用文档名的hash作为缓存文件名（避免特殊字符问题）
        name_hash = hashlib.md5(document_name.encode('utf-8')).hexdigest()[:16]
        return self._get_task_dir(task_id) / f"{name_hash}.json"
    
    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """计算文件内容hash（用于检测文件变化）"""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                # 只读取前1MB用于hash计算（大文件优化）
                chunk = f.read(1024 * 1024)
                hasher.update(chunk)
                # 加上文件大小
                f.seek(0, 2)
                hasher.update(str(f.tell()).encode())
        except Exception as e:
            logger.warning("Failed to compute file hash: %s", e)
            return ""
        return hasher.hexdigest()
    
    def get(
        self, 
        task_id: str, 
        document_name: str, 
        file_path: Optional[Path] = None
    ) -> Optional[HeaderMapping]:
        """
        获取缓存的表头映射
        
        Args:
            task_id: 任务ID
            document_name: 文档名称
            file_path: 文档路径（用于验证文件是否变化）
            
        Returns:
            HeaderMapping if cache hit and valid, None otherwise
        """
        cache_path = self._get_cache_path(task_id, document_name)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证文件是否变化
            if file_path and file_path.exists():
                cached_hash = data.get('document_hash', '')
                current_hash = self.compute_file_hash(file_path)
                if cached_hash and current_hash and cached_hash != current_hash:
                    logger.info("File changed, cache invalidated: %s", document_name)
                    return None
            
            # 解析缓存数据
            mapping_data = data.get('header_mapping', {})
            return HeaderMapping.from_dict(mapping_data)
            
        except Exception as e:
            logger.warning("Failed to read cache: %s - %s", cache_path, e)
            return None
    
    def set(
        self,
        task_id: str,
        document_name: str,
        mapping: HeaderMapping,
        file_path: Optional[Path] = None
    ) -> bool:
        """
        保存表头映射到缓存
        
        Args:
            task_id: 任务ID
            document_name: 文档名称
            mapping: 表头映射结果
            file_path: 文档路径（用于计算hash）
            
        Returns:
            True if saved successfully
        """
        cache_path = self._get_cache_path(task_id, document_name)
        
        try:
            data = {
                'document_name': document_name,
                'document_hash': '',
                'created_at': datetime.now().isoformat(),
                'header_mapping': mapping.to_dict(),
            }
            
            if file_path and file_path.exists():
                data['document_hash'] = self.compute_file_hash(file_path)
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("Cache saved: %s", cache_path)
            return True
            
        except Exception as e:
            logger.error("Failed to save cache: %s - %s", cache_path, e)
            return False
    
    def has_cache(self, task_id: str, document_name: str) -> bool:
        """检查是否存在缓存"""
        cache_path = self._get_cache_path(task_id, document_name)
        return cache_path.exists()
    
    def invalidate(self, task_id: str, document_name: str) -> bool:
        """使缓存失效（删除）"""
        cache_path = self._get_cache_path(task_id, document_name)
        try:
            if cache_path.exists():
                cache_path.unlink()
                logger.info("Cache invalidated: %s", cache_path)
            return True
        except Exception as e:
            logger.error("Failed to invalidate cache: %s", e)
            return False
    
    def clear_task(self, task_id: str) -> int:
        """清除任务的所有缓存"""
        task_dir = self._get_task_dir(task_id)
        count = 0
        try:
            for cache_file in task_dir.glob('*.json'):
                cache_file.unlink()
                count += 1
            logger.info("Cleared %d cache files for task: %s", count, task_id)
        except Exception as e:
            logger.error("Failed to clear task cache: %s", e)
        return count
    
    def list_cached_documents(self, task_id: str) -> Dict[str, str]:
        """
        列出任务中已缓存的文档
        
        Returns:
            Dict[document_name, created_at]
        """
        task_dir = self._get_task_dir(task_id)
        result = {}
        
        for cache_file in task_dir.glob('*.json'):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                doc_name = data.get('document_name', cache_file.stem)
                created_at = data.get('created_at', '')
                result[doc_name] = created_at
            except Exception:
                pass
        
        return result
