"""
结果图片生成模块
生成类似 MiaoSpeed 风格的测速结果表格图片
支持深色/浅色主题
"""
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path

# 深色主题颜色
DARK_COLORS = {
    "bg": (30, 30, 35),
    "header_bg": (45, 45, 55),
    "row_even": (35, 35, 42),
    "row_odd": (40, 40, 48),
    "text": (220, 220, 225),
    "text_dim": (140, 140, 150),
    "text_header": (255, 255, 255),
    "green": (76, 175, 80),
    "yellow": (255, 193, 7),
    "red": (244, 67, 54),
    "orange": (255, 152, 0),
    "blue": (33, 150, 243),
    "purple": (156, 39, 176),
    "cyan": (0, 188, 212),
    "border": (60, 60, 70),
}

# 浅色主题颜色
LIGHT_COLORS = {
    "bg": (245, 245, 247),
    "header_bg": (230, 230, 235),
    "row_even": (250, 250, 252),
    "row_odd": (245, 245, 248),
    "text": (30, 30, 40),
    "text_dim": (100, 100, 120),
    "text_header": (50, 50, 60),
    "green": (22, 163, 74),
    "yellow": (217, 119, 6),
    "red": (220, 38, 38),
    "orange": (234, 88, 12),
    "blue": (37, 99, 235),
    "purple": (147, 51, 234),
    "cyan": (8, 145, 178),
    "border": (200, 200, 210),
}

# 表格列定义
COLUMNS = [
    {"key": "index", "title": "序号", "width": 50},
    {"key": "name", "title": "节点名称", "width": 160},
    {"key": "type", "title": "类型", "width": 70},
    {"key": "speed_mbps", "title": "平均速度", "width": 90},
    {"key": "max_speed_mbps", "title": "最高速度", "width": 90},
    {"key": "traffic_mb", "title": "流量", "width": 70},
    {"key": "tls_rtt", "title": "TLS RTT", "width": 75},
    {"key": "https_ping", "title": "HTTPS延迟", "width": 80},
    {"key": "Netflix", "title": "Netflix", "width": 80},
    {"key": "YouTube", "title": "YouTube", "width": 80},
    {"key": "Bilibili", "title": "Bilibili", "width": 90},
    {"key": "Disney+", "title": "Disney+", "width": 80},
    {"key": "TikTok", "title": "TikTok", "width": 70},
    {"key": "ChatGPT", "title": "ChatGPT", "width": 80},
    {"key": "Spotify", "title": "Spotify", "width": 75},
    {"key": "Steam", "title": "Steam", "width": 80},
]


def get_colors(theme: str = "dark") -> dict:
    """根据主题返回颜色配置"""
    if theme == "light":
        return LIGHT_COLORS
    return DARK_COLORS


def get_speed_color(speed_mb_per_sec: float, colors: dict) -> tuple:
    """根据速度返回颜色 (MB/s)"""
    if speed_mb_per_sec >= 10:      # 10 MB/s = 80 Mbps
        return colors["green"]
    elif speed_mb_per_sec >= 2:     # 2 MB/s = 16 Mbps
        return colors["cyan"]
    elif speed_mb_per_sec >= 0.5:   # 0.5 MB/s = 4 Mbps
        return colors["yellow"]
    elif speed_mb_per_sec > 0:
        return colors["orange"]
    else:
        return colors["red"]


def get_unlock_color(status: str, colors: dict) -> tuple:
    """根据解锁状态返回颜色"""
    if "解锁" in status:
        return colors["green"]
    elif "未解锁" in status:
        return colors["red"]
    elif "检测失败" in status or "检测超时" in status:
        return colors["orange"]
    else:
        return colors["text_dim"]


def format_speed(speed_mbps: float) -> str:
    """格式化速度显示"""
    if speed_mbps <= 0:
        return "0.00B"
    elif speed_mbps >= 1000:
        return f"{speed_mbps/1000:.2f}GB"
    elif speed_mbps >= 1:
        return f"{speed_mbps:.2f}MB"
    else:
        return f"{speed_mbps*1000:.0f}KB"


def format_latency(ms: float) -> str:
    """格式化延迟显示"""
    if ms is None:
        return "-"
    return f"{ms:.0f}ms"


def get_font(size: int = 14):
    """获取字体"""
    font_paths = [
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        # Linux
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_result_image(
    results: List[Dict[str, Any]],
    title: str = "ClashSpeedTest",
    output_path: str = "result.png",
    theme: str = "dark"
) -> str:
    """
    生成测速结果表格图片
    
    Args:
        results: 测速结果列表
        title: 图片标题
        output_path: 输出路径
        theme: 主题 ("dark" 或 "light")
    
    Returns:
        生成的图片路径
    """
    # 获取主题颜色
    colors = get_colors(theme)
    
    # 计算总宽度
    total_width = sum(col["width"] for col in COLUMNS) + 40  # 40 = padding

    # 计算行数
    header_height = 40
    row_height = 32
    footer_height = 50
    title_height = 50
    total_height = title_height + header_height + row_height * len(results) + footer_height + 40

    # 创建图片
    img = Image.new("RGB", (total_width, total_height), colors["bg"])
    draw = ImageDraw.Draw(img)

    # 加载字体
    font_title = get_font(18)
    font_header = get_font(13)
    font_row = get_font(12)
    font_small = get_font(10)

    # 绘制标题
    y = 20
    draw.text((20, y), title, fill=colors["text_header"], font=font_title)
    y += title_height

    # 绘制表头背景
    draw.rectangle(
        [15, y, total_width - 15, y + header_height],
        fill=colors["header_bg"],
        outline=colors["border"],
    )

    # 绘制表头文字
    x = 20
    for col in COLUMNS:
        draw.text(
            (x + 5, y + 12),
            col["title"],
            fill=colors["text_header"],
            font=font_header,
        )
        x += col["width"]
    y += header_height

    # 绘制数据行
    for idx, result in enumerate(results):
        # 行背景
        row_bg = colors["row_even"] if idx % 2 == 0 else colors["row_odd"]
        draw.rectangle(
            [15, y, total_width - 15, y + row_height],
            fill=row_bg,
            outline=colors["border"],
        )

        x = 20
        for col in COLUMNS:
            key = col["key"]
            value = ""

            if key == "index":
                value = str(idx + 1)
                color = colors["text"]
            elif key == "name":
                value = result.get("name", "")
                color = colors["text"]
            elif key == "type":
                value = result.get("type", "")
                color = colors["text"]
            elif key == "speed_mbps":
                value = f"{result.get('speed_mb_per_sec', 0):.2f} MB/s"
                color = get_speed_color(result.get("speed_mb_per_sec", 0), colors)
            elif key == "max_speed_mbps":
                value = f"{result.get('max_speed_mb_per_sec', 0):.2f} MB/s"
                color = get_speed_color(result.get("max_speed_mb_per_sec", 0), colors)
            elif key == "traffic_mb":
                value = f"{result.get('traffic_mb', 0):.2f} MB"
                color = colors["text"]
            elif key == "tls_rtt":
                value = format_latency(result.get("tls_rtt"))
                color = colors["text"]
            elif key == "https_ping":
                value = format_latency(result.get("https_ping"))
                color = colors["text"]
            else:
                # 流媒体解锁状态
                value = result.get("streaming", {}).get(key, "-")
                color = get_unlock_color(value, colors)

            # 截断过长文本
            max_chars = col["width"] // 8
            if len(value) > max_chars:
                value = value[:max_chars - 1] + "..."

            draw.text(
                (x + 5, y + 9),
                value,
                fill=color,
                font=font_row,
            )
            x += col["width"]

        y += row_height

    # 绘制底部信息
    y += 10
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    theme_name = "浅色" if theme == "light" else "深色"
    total_traffic = sum(r.get("traffic_mb", 0) for r in results)
    footer_text = f"测试时间: {now} | ClashSpeedTest v1.0 | 共 {len(results)} 个节点 | 总流量: {total_traffic:.2f} MB | 主题: {theme_name}"
    draw.text((20, y), footer_text, fill=colors["text_dim"], font=font_small)

    # 保存图片
    img.save(output_path, "PNG", quality=95)
    return output_path
