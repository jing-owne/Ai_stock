"""
测试配置模块
"""
import pytest
import tempfile
import os
from src.core.config import Config, DataSourceConfig, StrategyConfig


class TestConfig:
    """测试Config类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = Config()
        
        assert config.data_source.provider == "sina"
        assert config.data_source.timeout == 30
        assert config.log_level == "INFO"
    
    def test_config_validation(self):
        """测试配置验证"""
        config = Config()
        
        # 有效配置应该通过验证
        config.validate()  # 不抛出异常
    
    def test_invalid_timeout(self):
        """测试无效超时值"""
        config = Config()
        config.data_source.timeout = -1
        
        with pytest.raises(ValueError):
            config.validate()
    
    def test_invalid_format(self):
        """测试无效的报告格式"""
        config = Config()
        config.report.format = "invalid"
        
        with pytest.raises(ValueError):
            config.validate()
    
    def test_from_dict(self):
        """测试从字典创建配置"""
        data = {
            "data_source": {
                "provider": "tushare",
                "timeout": 60,
            },
            "log_level": "DEBUG",
        }
        
        config = Config.from_dict(data)
        
        assert config.data_source.provider == "tushare"
        assert config.data_source.timeout == 60
        assert config.log_level == "DEBUG"
    
    def test_from_yaml(self):
        """测试从YAML加载配置"""
        yaml_content = """
data_source:
  provider: eastmoney
  timeout: 45

strategy:
  volume_surge:
    min_volume_ratio: 2.5

log_level: WARNING
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            config = Config.from_yaml(temp_path)
            
            assert config.data_source.provider == "eastmoney"
            assert config.data_source.timeout == 45
            assert config.strategy.volume_surge["min_volume_ratio"] == 2.5
            assert config.log_level == "WARNING"
        finally:
            os.unlink(temp_path)
    
    def test_to_dict(self):
        """测试转换为字典"""
        config = Config()
        
        d = config.to_dict()
        
        assert "data_source" in d
        assert "strategy" in d
        assert "report" in d
        assert d["log_level"] == "INFO"


class TestDataSourceConfig:
    """测试数据源配置"""
    
    def test_default_values(self):
        """测试默认值"""
        ds_config = DataSourceConfig()
        
        assert ds_config.provider == "sina"
        assert ds_config.timeout == 30
        assert ds_config.retry_times == 3
        assert ds_config.cache_enabled is True
    
    def test_custom_values(self):
        """测试自定义值"""
        ds_config = DataSourceConfig(
            provider="tushare",
            api_key="test_key",
            timeout=60,
            retry_times=5,
        )
        
        assert ds_config.provider == "tushare"
        assert ds_config.api_key == "test_key"
        assert ds_config.timeout == 60
        assert ds_config.retry_times == 5


class TestStrategyConfig:
    """测试策略配置"""
    
    def test_volume_surge_params(self):
        """测试放量上涨策略参数"""
        config = StrategyConfig()
        
        vs = config.volume_surge
        assert vs["min_volume_ratio"] == 2.0
        assert vs["min_price_change"] == 1.0
        assert vs["min_amount"] == 100_000_000
    
    def test_turnover_rank_params(self):
        """测试成交额排名策略参数"""
        config = StrategyConfig()
        
        tr = config.turnover_rank
        assert tr["top_n"] == 20
        assert tr["min_amount"] == 500_000_000
