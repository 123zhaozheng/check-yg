# -*- coding: utf-8 -*-
"""
Configuration management module
Handles loading and saving configuration from ~/.check-yg/config.yaml
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for the audit system"""
    
    DEFAULT_CONFIG = {
        'mineru': {
            'url': 'http://localhost:8000',
            'timeout': 300
        },
        'llm': {
            'url': 'https://api.openai.com/v1',
            'model': 'gpt-4',
            'api_key': '',
            'batch_size': 10,
            'match_threshold': 70,  # LLM 匹配置信度阈值，高于此值视为匹配
            'system_prompt': ''  # 自定义系统提示词，为空则使用默认
        },
        'paths': {
            'input_folder': './data/input',
            'output_folder': './data/output',
            'reports_folder': './data/reports'
        },
        'search': {
            'enable_llm_judge': True,
            'fuzzy_threshold': 60
        },
        'flow_extraction': {
            'preview_rows': 10,  # 给AI看的行数
            'batch_size': 20,   # 每批处理的行数
            'confidence_threshold': 70,  # 流水表格判断的置信度阈值
            'parallelism': 4,   # 文档并行处理数
            'checkpoint_interval': 50  # 断点保存间隔（行数）
        },
        'matching': {
            'enable_exact': True,
            'enable_desensitized': True,
            'enable_fuzzy': False
        }
    }
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize configuration manager
        
        Args:
            config_dir: Path to config directory. Defaults to ~/.check-yg (user home directory)
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 使用用户根目录下的 .check-yg
            self.config_dir = Path.home() / '.check-yg'
        
        self.config_file = self.config_dir / 'config.yaml'
        self._config: Dict[str, Any] = {}
        self._ensure_config_exists()
        self.load()
    
    def _ensure_config_exists(self) -> None:
        """Ensure config directory and file exist"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.config_file.exists():
            self._config = self.DEFAULT_CONFIG.copy()
            self.save()
            logger.info("Created default config at %s", self.config_file)
    
    def load(self) -> None:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f) or {}
            
            # Merge with defaults to ensure all keys exist
            self._config = self._deep_merge(self.DEFAULT_CONFIG.copy(), loaded)
            logger.info("Configuration loaded from %s", self.config_file)
        except Exception as e:
            logger.error("Failed to load config: %s", e)
            self._config = self.DEFAULT_CONFIG.copy()
    
    def save(self) -> None:
        """Save configuration to YAML file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
            logger.info("Configuration saved to %s", self.config_file)
        except Exception as e:
            logger.error("Failed to save config: %s", e)
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key
        
        Args:
            key: Dot-notation key (e.g., 'mineru.url')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by dot-notation key
        
        Args:
            key: Dot-notation key (e.g., 'mineru.url')
            value: Value to set
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    @property
    def mineru_url(self) -> str:
        return self.get('mineru.url', 'http://localhost:8000')
    
    @property
    def mineru_timeout(self) -> int:
        return self.get('mineru.timeout', 300)
    
    @property
    def llm_url(self) -> str:
        return self.get('llm.url', 'https://api.openai.com/v1')
    
    @property
    def llm_model(self) -> str:
        return self.get('llm.model', 'gpt-4')
    
    @property
    def llm_api_key(self) -> str:
        return self.get('llm.api_key', '')
    
    @property
    def llm_batch_size(self) -> int:
        return self.get('llm.batch_size', 10)
    
    @property
    def llm_match_threshold(self) -> int:
        """LLM 匹配置信度阈值，高于此值视为匹配（默认 70）"""
        return self.get('llm.match_threshold', 70)
    
    @property
    def llm_system_prompt(self) -> str:
        """自定义 LLM 系统提示词，为空则使用默认"""
        return self.get('llm.system_prompt', '')
    
    @property
    def enable_llm_judge(self) -> bool:
        return self.get('search.enable_llm_judge', True)
    
    @property
    def fuzzy_threshold(self) -> int:
        return self.get('search.fuzzy_threshold', 60)
    
    @property
    def flow_preview_rows(self) -> int:
        """流水提取：给AI看的行数（默认 10）"""
        return self.get('flow_extraction.preview_rows', 10)
    
    @property
    def flow_batch_size(self) -> int:
        """流水提取：每批处理的行数（默认 20）"""
        return self.get('flow_extraction.batch_size', 20)
    
    @property
    def flow_confidence_threshold(self) -> int:
        """流水提取：表格判断的置信度阈值（默认 70）"""
        return self.get('flow_extraction.confidence_threshold', 70)

    @property
    def flow_parallelism(self) -> int:
        """流水提取：并行度（默认 4）"""
        return self.get('flow_extraction.parallelism', 4)

    @property
    def flow_checkpoint_interval(self) -> int:
        """流水提取：断点保存间隔（默认 50）"""
        return self.get('flow_extraction.checkpoint_interval', 50)
    
    @property
    def enable_exact_match(self) -> bool:
        """审查：是否启用精确匹配（默认 True）"""
        return self.get('matching.enable_exact', True)
    
    @property
    def enable_desensitized_match(self) -> bool:
        """审查：是否启用脱敏匹配（默认 True）"""
        return self.get('matching.enable_desensitized', True)
    
    @property
    def enable_fuzzy_match(self) -> bool:
        """审查：是否启用模糊匹配（默认 False）"""
        return self.get('matching.enable_fuzzy', False)
    
    @property
    def input_folder(self) -> Path:
        return Path(self.get('paths.input_folder', './data/input'))
    
    @property
    def output_folder(self) -> Path:
        return Path(self.get('paths.output_folder', './data/output'))
    
    @property
    def reports_folder(self) -> Path:
        return Path(self.get('paths.reports_folder', './data/reports'))
    
    @property
    def results_file(self) -> Path:
        """Path to audit results JSON file (deprecated, use audit_{id}.json instead)"""
        return self.config_dir / 'audit_results.json'
    
    def get_audit_file(self, audit_id: str) -> Path:
        """Get path to specific audit result file"""
        return self.config_dir / f'audit_{audit_id}.json'
    
    def list_audit_files(self) -> List[Path]:
        """List all audit result files for history query"""
        return sorted(self.config_dir.glob('audit_*.json'), reverse=True)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Reload configuration from file"""
    global _config
    _config = Config()
    return _config
