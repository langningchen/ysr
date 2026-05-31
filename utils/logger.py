# utils/logger.py
import sys
from loguru import logger

# 移除 Loguru 默认的基础输出格式
logger.remove()

# 1. 配置终端带颜色的美化输出 (DEBUG 及以上级别显示)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG"
)

# 2. 配置本地持久化日志存储 (INFO 及以上级别写入，自动轮转限制)
logger.add(
    "logs/hsr_automator.log",
    rotation="10 MB",      # 文件满 10MB 自动分包
    retention="1 week",    # 保留一周内的历史日志
    level="INFO",
    encoding="utf-8"
)
