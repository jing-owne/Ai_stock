"""
统一配置管理
支持YAML配置、fail-fast验证、环境变量覆盖
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from copy import deepcopy


@dataclass
class DataSourceConfig:
    """数据源配置"""
    provider: str = "sina"           # 数据提供商: sina/tushare/eastmoney
    api_key: Optional[str] = None    # API密钥
    api_secret: Optional[str] = None # API密钥
    timeout: int = 30               # 请求超时(秒)
    retry_times: int = 3            # 重试次数
    cache_enabled: bool = True      # 启用缓存
    cache_ttl: int = 300            # 缓存TTL(秒)


@dataclass
class StrategyConfig:
    """策略配置"""
    # 放量上涨策略
    volume_surge: Dict[str, Any] = field(default_factory=lambda: {
        "min_volume_ratio": 2.0,      # 最小放量倍数
        "min_price_change": 1.0,      # 最小涨幅%
        "min_amount": 100000000,       # 最小成交额
    })
    
    # 成交额排名策略
    turnover_rank: Dict[str, Any] = field(default_factory=lambda: {
        "top_n": 20,                  # 取前N名
        "min_amount": 500000000,      # 最小成交额
        "sort_desc": True,
    })
    
    # 多因子策略
    multi_factor: Dict[str, Any] = field(default_factory=lambda: {
        "volume_weight": 0.2,
        "price_weight": 0.3,
        "turnover_weight": 0.25,
        "tech_weight": 0.25,
        "min_score": 60,
    })
    
    # AI技术面策略
    ai_technical: Dict[str, Any] = field(default_factory=lambda: {
        "pattern_threshold": 0.75,    # 形态识别阈值
        "trend_confidence": 0.70,    # 趋势置信度
    })
    
    # 机构追踪策略
    institution: Dict[str, Any] = field(default_factory=lambda: {
        "min_inst_count": 3,          # 最少机构数
        "min_inst_ratio": 0.05,      # 最少机构持股比例
    })
    
    # 复合策略权重配置
    composite_strategy: Dict[str, Any] = field(default_factory=lambda: {
        "strategy_count_weight": 0.35,   # 策略数量权重 (25% → 35%)
        "myhhub_weight": 0.30,            # 基本面因子权重 (25% → 30%)
        "hikyuu_weight": 0.10,            # 趋势策略权重 (15% → 10%)
        "northstar_weight": 0.05,          # 北向资金权重 (10% → 5%)
        "base_win_rate": 0.50,             # 胜率基础值 (45% → 50%)
        "min_win_rate": 0.65,             # 新增胜率门槛
    })
    
    # 基本面筛选条件
    fundamental_filter: Dict[str, Any] = field(default_factory=lambda: {
        "min_roe": 0.08,                  # ROE门槛 (≥5% → ≥8%)
        "min_revenue_growth": 0.05,       # 营收增长 (≥0% → ≥5%)
        "min_profit_growth": 0.10,        # 净利润增长门槛
        "max_debt_ratio": 0.60,           # 最大负债率
    })


@dataclass
class ReportConfig:
    """报告配置"""
    format: str = "html"            # 报告格式: html/markdown/json
    template: str = "default"       # 模板名称
    include_charts: bool = True     # 包含图表
    output_dir: str = "./output"    # 输出目录
    max_stocks: int = 50           # 最大股票数


@dataclass
class EmailConfig:
    """邮件配置"""
    enabled: bool = True           # 启用邮件发送
    debug_mode: bool = False       # 调试模式（只发邮件不抄送）
    skip_money_flow: bool = True   # 跳过耗时资金流向查询
    sender_name: str = "Marcus策略师"  # 发件人名称
    smtp_server: str = "smtp.qq.com"  # QQ邮箱SMTP服务器
    smtp_port: int = 465           # SSL端口
    smtp_user: str = ""             # 发送邮箱
    smtp_password: str = ""        # SMTP授权码
    to_emails: list = field(default_factory=list)  # 收件人
    cc_emails: list = field(default_factory=list)  # 抄送
    subject_prefix: str = "[Marcus量化选股]"  # 邮件主题前缀


@dataclass
class Config:
    """统一配置类"""
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    
    # 全局设置
    log_level: str = "INFO"          # 日志级别
    max_workers: int = 4            # 最大并发数
    enable_cache: bool = True       # 启用缓存
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Config":
        """从YAML文件加载配置"""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {yaml_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """从字典加载配置"""
        config = cls()
        
        if "data_source" in data:
            for key, value in data["data_source"].items():
                if hasattr(config.data_source, key):
                    setattr(config.data_source, key, value)
        
        if "strategy" in data:
            for key, value in data["strategy"].items():
                if hasattr(config.strategy, key):
                    setattr(config.strategy, key, value)
        
        if "report" in data:
            for key, value in data["report"].items():
                if hasattr(config.report, key):
                    setattr(config.report, key, value)
        
        if "email" in data:
            for key, value in data["email"].items():
                if hasattr(config.email, key):
                    setattr(config.email, key, value)
        
        # 全局设置
        if "log_level" in data:
            config.log_level = data["log_level"]
        if "max_workers" in data:
            config.max_workers = data["max_workers"]
        if "enable_cache" in data:
            config.enable_cache = data["enable_cache"]
        
        return config
    
    def validate(self) -> None:
        """Fail-fast配置验证"""
        errors = []
        
        # 数据源验证
        if self.data_source.timeout <= 0:
            errors.append("data_source.timeout 必须大于0")
        if self.data_source.retry_times < 0:
            errors.append("data_source.retry_times 不能为负")
        
        # 策略验证
        if self.strategy.volume_surge["min_volume_ratio"] < 1.0:
            errors.append("strategy.volume_surge.min_volume_ratio 必须 >= 1.0")
        
        # 报告验证
        if self.report.format not in ["html", "markdown", "json"]:
            errors.append("report.format 必须是 html/markdown/json 之一")
        
        if errors:
            raise ValueError(f"配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors))
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "data_source": {
                "provider": self.data_source.provider,
                "api_key": self.data_source.api_key,
                "timeout": self.data_source.timeout,
                "retry_times": self.data_source.retry_times,
                "cache_enabled": self.data_source.cache_enabled,
            },
            "strategy": {
                "volume_surge": self.strategy.volume_surge,
                "turnover_rank": self.strategy.turnover_rank,
                "multi_factor": self.strategy.multi_factor,
                "ai_technical": self.strategy.ai_technical,
                "institution": self.strategy.institution,
                "composite_strategy": self.strategy.composite_strategy,
                "fundamental_filter": self.strategy.fundamental_filter,
            },
            "report": {
                "format": self.report.format,
                "template": self.report.template,
                "include_charts": self.report.include_charts,
                "output_dir": self.report.output_dir,
            },
            "email": {
                "enabled": self.email.enabled,
                "debug_mode": self.email.debug_mode,
                "skip_money_flow": self.email.skip_money_flow,
                "sender_name": self.email.sender_name,
                "smtp_server": self.email.smtp_server,
                "smtp_port": self.email.smtp_port,
                "smtp_user": self.email.smtp_user,
                "smtp_password": self.email.smtp_password,
                "to_emails": self.email.to_emails,
                "cc_emails": self.email.cc_emails,
                "subject_prefix": self.email.subject_prefix,
            },
            "log_level": self.log_level,
            "max_workers": self.max_workers,
            "enable_cache": self.enable_cache,
        }


# 全局默认配置
DEFAULT_CONFIG = Config()
