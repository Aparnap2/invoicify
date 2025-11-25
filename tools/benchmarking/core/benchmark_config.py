"""
Configuration management for benchmarking operations.
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path

from .benchmark_types import BenchmarkConfig


class BenchmarkConfigManager:
    """Manages benchmark configuration with environment-specific overrides."""

    DEFAULT_CONFIG_PATHS = [
        "tools/benchmarking/config/default.json",
        "tools/benchmarking/config/{environment}.json",
        "tools/benchmarking/config/local.json",
        "~/.ap_intake/benchmarking/config.json",
    ]

    def __init__(self, environment: str = "development"):
        """Initialize config manager for specific environment."""
        self.environment = environment
        self._config_cache: Optional[BenchmarkConfig] = None

    def load_config(self, config_path: Optional[str] = None) -> BenchmarkConfig:
        """Load benchmark configuration from file or use defaults."""
        if self._config_cache and not config_path:
            return self._config_cache

        # Start with default configuration
        config_data = self._get_default_config()

        # Load configuration from files
        config_data = self._load_config_from_files(config_data)

        # Override with environment variables
        config_data = self._apply_env_overrides(config_data)

        # Override with explicit config file if provided
        if config_path:
            config_data = self._merge_config_from_file(config_data, config_path)

        # Create and cache config object
        config = BenchmarkConfig(**config_data)
        self._config_cache = config

        return config

    def save_config(self, config: BenchmarkConfig, config_path: str) -> None:
        """Save benchmark configuration to file."""
        config_dict = {
            "environment": config.environment,
            "api_base_url": config.api_base_url,
            "database_url": config.database_url,
            "load_test_duration_seconds": config.load_test_duration_seconds,
            "load_test_virtual_users": config.load_test_virtual_users,
            "load_test_ramp_up_seconds": config.load_test_ramp_up_seconds,
            "profiling_duration_seconds": config.profiling_duration_seconds,
            "profiling_sampling_rate": config.profiling_sampling_rate,
            "memory_profiling_enabled": config.memory_profiling_enabled,
            "cpu_profiling_enabled": config.cpu_profiling_enabled,
            "monitoring_interval_seconds": config.monitoring_interval_seconds,
            "monitoring_duration_seconds": config.monitoring_duration_seconds,
            "industry_benchmarks_enabled": config.industry_benchmarks_enabled,
            "comparison_industry": config.comparison_industry,
            "report_format": config.report_format,
            "include_charts": config.include_charts,
            "save_raw_data": config.save_raw_data,
            "response_time_threshold_ms": config.response_time_threshold_ms,
            "error_rate_threshold": config.error_rate_threshold,
            "cpu_usage_threshold": config.cpu_usage_threshold,
            "memory_usage_threshold": config.memory_usage_threshold,
        }

        # Ensure directory exists
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(config_dict, f, indent=2)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "environment": self.environment,
            "api_base_url": "http://localhost:8000",
            "database_url": "",
            "load_test_duration_seconds": 300,
            "load_test_virtual_users": 10,
            "load_test_ramp_up_seconds": 30,
            "profiling_duration_seconds": 120,
            "profiling_sampling_rate": 100.0,
            "memory_profiling_enabled": True,
            "cpu_profiling_enabled": True,
            "monitoring_interval_seconds": 5,
            "monitoring_duration_seconds": 300,
            "industry_benchmarks_enabled": True,
            "comparison_industry": "fintech_ap_automation",
            "report_format": "json",
            "include_charts": True,
            "save_raw_data": True,
            "response_time_threshold_ms": 500.0,
            "error_rate_threshold": 0.01,
            "cpu_usage_threshold": 0.8,
            "memory_usage_threshold": 0.85,
        }

    def _load_config_from_files(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """Load configuration from standard config file paths."""
        for path_template in self.DEFAULT_CONFIG_PATHS:
            path = path_template.format(environment=self.environment)
            path = os.path.expanduser(path)

            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        file_config = json.load(f)
                        base_config.update(file_config)
                except Exception as e:
                    print(f"Warning: Failed to load config from {path}: {e}")

        return base_config

    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides."""
        env_mappings = {
            "BENCHMARK_API_BASE_URL": "api_base_url",
            "BENCHMARK_DATABASE_URL": "database_url",
            "BENCHMARK_LOAD_TEST_DURATION": "load_test_duration_seconds",
            "BENCHMARK_LOAD_TEST_USERS": "load_test_virtual_users",
            "BENCHMARK_PROFILING_DURATION": "profiling_duration_seconds",
            "BENCHMARK_REPORT_FORMAT": "report_format",
            "BENCHMARK_RESPONSE_TIME_THRESHOLD": "response_time_threshold_ms",
        }

        for env_var, config_key in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value:
                # Type conversion based on key
                if "threshold" in config_key or "duration" in config_key or "users" in config_key:
                    try:
                        config[config_key] = float(env_value)
                    except ValueError:
                        pass
                elif config_key.endswith("_enabled"):
                    config[config_key] = env_value.lower() in ("true", "1", "yes")
                else:
                    config[config_key] = env_value

        return config

    def _merge_config_from_file(self, base_config: Dict[str, Any], config_path: str) -> Dict[str, Any]:
        """Merge configuration from a specific file."""
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                file_config = json.load(f)
                base_config.update(file_config)
        return base_config


# Global config manager instance
_config_manager: Optional[BenchmarkConfigManager] = None


def get_config_manager(environment: str = None) -> BenchmarkConfigManager:
    """Get global config manager instance."""
    global _config_manager
    if _config_manager is None or (environment and _config_manager.environment != environment):
        env = environment or os.getenv("BENCHMARK_ENV", "development")
        _config_manager = BenchmarkConfigManager(env)
    return _config_manager


def load_config(config_path: Optional[str] = None, environment: Optional[str] = None) -> BenchmarkConfig:
    """Load benchmark configuration."""
    manager = get_config_manager(environment)
    return manager.load_config(config_path)


def save_config(config: BenchmarkConfig, config_path: str) -> None:
    """Save benchmark configuration."""
    manager = get_config_manager()
    manager.save_config(config, config_path)