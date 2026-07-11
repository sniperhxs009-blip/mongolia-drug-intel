"""
统一日志模块
============
全局 logging 配置，支持文件按天分割、控制台输出、多级别日志。
所有模块通过 get_logger(__name__) 获取日志实例。
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_loggers: dict[str, logging.Logger] = {}
_initialized = False


def _mask_key(s: str) -> str:
    """脱敏 API Key：保留前4后4位"""
    if len(s) <= 8:
        return "****"
    return s[:4] + "*" * (len(s) - 8) + s[-4:]


def init_logging(level: str = "INFO"):
    """初始化全局日志配置（只需调用一次）"""
    global _initialized
    if _initialized:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(fmt)

    # 文件输出（按天分割，保留 30 天）
    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "app.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    _initialized = True

    # 启动时打印环境信息（密钥脱敏）
    dsk = os.environ.get("DEEPSEEK_API_KEY", "")
    log = logging.getLogger("init")
    log.info("日志系统初始化完成，级别=%s", level)
    if dsk:
        log.info("DeepSeek API Key 已配置: %s", _mask_key(dsk))
    else:
        log.warning("DeepSeek API Key 未配置，将使用规则引擎")


def get_logger(name: str) -> logging.Logger:
    """获取模块日志实例"""
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]
