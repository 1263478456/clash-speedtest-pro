"""
ClashSpeedTest Pro 配置文件
"""
import os
import logging
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

# mihomo 相关配置
MIHOMO_DIR = BASE_DIR / "mihomo"
MIHOMO_CONFIG = BASE_DIR / "mihomo_config.yaml"
MIHOMO_API_URL = "http://127.0.0.1:19090"
MIHOMO_PROXY_PORT = 17890
MIHOMO_SOCKS_PORT = 17891

# 测速配置
SPEED_TEST_TIMEOUT = 30
SPEED_TEST_DURATION = 15

# 流媒体检测配置
STREAMING_TEST_TIMEOUT = 10

# 服务端口
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")

# 数据库配置
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/speedtest.db"

# JWT 配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 小时

# 日志等级配置
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

DEFAULT_LOG_LEVEL = "debug"

# 速度测试 URL
SPEED_TEST_URLS = {
    "10MB": "https://speed.cloudflare.com/__down?bytes=10485760",
    "25MB": "https://speed.cloudflare.com/__down?bytes=26214400",
    "50MB": "https://speed.cloudflare.com/__down?bytes=52428800",
    "100MB": "https://speed.cloudflare.com/__down?bytes=104857600",
}

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)
