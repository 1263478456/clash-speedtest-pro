"""
速度测试模块
通过本地代理进行下载速度、延迟测试
"""
import time
import asyncio
import httpx
import socket
import ssl
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from config import (
    MIHOMO_PROXY_PORT, MIHOMO_SOCKS_PORT,
    SPEED_TEST_TIMEOUT, SPEED_TEST_DURATION
)
from backend.utils.mihomo_manager import get_current_ports

# 测速目标 URL 列表（按优先级）
SPEED_TEST_URLS = {
    "10MB": "https://speed.cloudflare.com/__down?bytes=10485760",
    "25MB": "https://speed.cloudflare.com/__down?bytes=26214400",
    "50MB": "https://speed.cloudflare.com/__down?bytes=52428800",
    "100MB": "https://speed.cloudflare.com/__down?bytes=104857600",
}

# 延迟测试目标
PING_TARGETS = [
    ("www.gstatic.com", 443),
    ("cp.cloudflare.com", 443),
    ("connectivitycheck.gstatic.com", 443),
]


def select_test_url(initial_speed_mbps: float) -> str:
    """根据初始速度选择合适的测试文件大小"""
    if initial_speed_mbps >= 50:
        return SPEED_TEST_URLS["100MB"]
    elif initial_speed_mbps >= 20:
        return SPEED_TEST_URLS["50MB"]
    elif initial_speed_mbps >= 5:
        return SPEED_TEST_URLS["25MB"]
    else:
        return SPEED_TEST_URLS["10MB"]


async def test_tcp_ping(host: str, port: int, timeout: float = 5.0) -> Optional[float]:
    """TCP Ping 延迟测试 (ms)"""
    try:
        start = time.monotonic()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        latency = (time.monotonic() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return round(latency, 2)
    except (asyncio.TimeoutError, ConnectionError, OSError):
        return None


async def test_tls_rtt(host: str, port: int = 443, timeout: float = 5.0) -> Optional[float]:
    """TLS RTT 延迟测试 (ms)"""
    try:
        ssl_ctx = ssl.create_default_context()
        start = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_ctx),
            timeout=timeout
        )
        rtt = (time.monotonic() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return round(rtt, 2)
    except (asyncio.TimeoutError, ConnectionError, OSError, ssl.SSLError):
        return None


async def test_https_ping(url: str, timeout: float = 5.0) -> Optional[float]:
    """HTTPS Ping 延迟测试 (ms)"""
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            proxies=f"http://127.0.0.1:{MIHOMO_PROXY_PORT}"
        ) as client:
            resp = await client.head(url, follow_redirects=True)
            latency = (time.monotonic() - start) * 1000
            return round(latency, 2)
    except Exception:
        return None


async def test_download_speed(
    url: str = None,
    timeout: float = SPEED_TEST_TIMEOUT,
    duration: float = 15.0,
    dynamic: bool = True
) -> Dict[str, Any]:
    """
    下载速度测试（动态调整文件大小）
    返回: {"speed_bps": float, "speed_mbps": float, "total_bytes": int, "traffic_mb": float}
    """
    ports = get_current_ports()
    proxy_url = f"http://127.0.0.1:{ports['proxy']}"
    
    # 使用 10MB 文件进行测试
    test_url = SPEED_TEST_URLS["10MB"]
    total_bytes = 0
    start_time = time.monotonic()
    
    print(f"[SpeedTest] 开始下载测试: {test_url}")
    print(f"[SpeedTest] 使用代理: {proxy_url}")
    print(f"[SpeedTest] 代理端口状态: {ports}")
    
    # 检查端口是否开放
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            result = s.connect_ex(('127.0.0.1', ports['proxy']))
            print(f"[SpeedTest] 端口 {ports['proxy']} 连接测试: {'成功' if result == 0 else '失败 (错误码: ' + str(result) + ')'}")
    except Exception as e:
        print(f"[SpeedTest] 端口检查异常: {e}")
    
    try:
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            proxies=proxy_url,
            follow_redirects=True,
        ) as client:
            print(f"[SpeedTest] 正在建立连接...")
            async with client.stream("GET", test_url) as response:
                print(f"[SpeedTest] 收到响应: 状态码={response.status_code}")
                print(f"[SpeedTest] 响应头: {dict(response.headers)}")
                
                if response.status_code != 200:
                    print(f"[SpeedTest] 状态码不是 200, 返回 0")
                    return {"speed_bps": 0, "speed_mbps": 0, "total_bytes": 0, "traffic_mb": 0}
                
                chunk_count = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total_bytes += len(chunk)
                    chunk_count += 1
                    if chunk_count % 100 == 0:
                        print(f"[SpeedTest] 已接收 {chunk_count} 个块, 共 {total_bytes} 字节")
                    elapsed = time.monotonic() - start_time
                    if elapsed >= duration:
                        print(f"[SpeedTest] 达到时间限制 {duration}s, 停止下载")
                        break
        
        elapsed = time.monotonic() - start_time
        if elapsed <= 0:
            elapsed = 0.001
        
        speed_bps = total_bytes / elapsed  # Bytes per second
        speed_mbps = speed_bps * 8 / 1_000_000  # Mbps (保留兼容)
        speed_mb_per_sec = total_bytes / elapsed / (1024 * 1024)  # MB/s (兆字节每秒)
        traffic_mb = total_bytes / (1024 * 1024)
        
        print(f"[SpeedTest] 下载完成: {total_bytes} 字节, 耗时: {elapsed:.2f}秒, 速度: {speed_mb_per_sec:.2f} MB/s, 流量: {traffic_mb:.2f} MB")
        return {
            "speed_bps": round(speed_bps),
            "speed_mbps": round(speed_mbps, 2),
            "speed_mb_per_sec": round(speed_mb_per_sec, 2),
            "total_bytes": total_bytes,
            "traffic_mb": round(traffic_mb, 2),
            "elapsed": round(elapsed, 2),
        }
    except httpx.ConnectError as e:
        print(f"[SpeedTest] 连接失败: {type(e).__name__}: {e}", flush=True)
        print(f"[SpeedTest] 可能原因: 代理端口未开放或 mihomo 未正确启动", flush=True)
        return {"speed_bps": 0, "speed_mbps": 0, "total_bytes": 0, "traffic_mb": 0, "error": f"连接失败: {str(e)}"}
    except httpx.TimeoutException as e:
        print(f"[SpeedTest] 连接超时: {type(e).__name__}: {e}", flush=True)
        return {"speed_bps": 0, "speed_mbps": 0, "total_bytes": 0, "traffic_mb": 0, "error": f"连接超时: {str(e)}"}
    except Exception as e:
        print(f"[SpeedTest] 下载失败: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"speed_bps": 0, "speed_mbps": 0, "total_bytes": 0, "traffic_mb": 0, "error": str(e)}


async def test_latency() -> Dict[str, Any]:
    """
    综合延迟测试
    返回: {"tcp_ping": float, "tls_rtt": float, "https_ping": float}
    """
    # TCP Ping
    tcp_results = []
    for host, port in PING_TARGETS[:1]:
        result = await test_tcp_ping(host, port)
        if result is not None:
            tcp_results.append(result)

    # TLS RTT
    tls_results = []
    for host, port in PING_TARGETS[:1]:
        result = await test_tls_rtt(host, port)
        if result is not None:
            tls_results.append(result)

    # HTTPS Ping
    https_results = []
    for url in ["https://www.gstatic.com/generate_204"]:
        result = await test_https_ping(url)
        if result is not None:
            https_results.append(result)

    return {
        "tcp_ping": round(sum(tcp_results) / len(tcp_results), 2) if tcp_results else None,
        "tls_rtt": round(sum(tls_results) / len(tls_results), 2) if tls_results else None,
        "https_ping": round(sum(https_results) / len(https_results), 2) if https_results else None,
    }


async def test_node_speed(node_name: str, node_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试单个节点的完整速度数据
    """
    from backend.utils.mihomo_manager import switch_node, get_current_ports
    
    # 清理节点名称（与配置生成时一致）
    import re
    def clean_name(name: str) -> str:
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\-_.|/\\()（）【】\[\]{}]', '', name)
        return cleaned if cleaned else name
    
    clean_node_name = clean_name(node_name)
    ports = get_current_ports()
    print(f"[SpeedTest] 开始测试节点: {node_name} -> {clean_node_name}, 代理端口: {ports['proxy']}", flush=True)

    # 切换到目标节点
    switched = await switch_node(clean_node_name)
    if not switched:
        print(f"[SpeedTest] 节点切换失败: {node_name}", flush=True)
        return {
            "name": node_name,
            "type": node_info.get("type", ""),
            "server": node_info.get("server", ""),
            "speed_bps": 0,
            "speed_mbps": 0,
            "max_speed_mbps": 0,
            "tcp_ping": None,
            "tls_rtt": None,
            "https_ping": None,
            "error": "节点切换失败",
        }
    
    print(f"[SpeedTest] 节点切换成功: {node_name}", flush=True)

    # 等待连接建立
    await asyncio.sleep(1.5)

    # 测试延迟
    latency = await test_latency()
    print(f"[SpeedTest] 延迟测试完成: {latency}", flush=True)

    # 测试下载速度 (多次取最大值)
    speed_results = []
    for i in range(2):
        print(f"[SpeedTest] 开始第 {i+1} 次下载速度测试...", flush=True)
        result = await test_download_speed()
        print(f"[SpeedTest] 第 {i+1} 次测试结果: speed_mb_per_sec={result.get('speed_mb_per_sec', 0)}, traffic_mb={result.get('traffic_mb', 0)}", flush=True)
        speed_results.append(result)
        if result.get("speed_mbps", 0) > 0:
            break

    best_speed = max(speed_results, key=lambda x: x.get("speed_mb_per_sec", 0))
    print(f"[SpeedTest] 节点 {node_name} 最佳速度: {best_speed.get('speed_mb_per_sec', 0)} MB/s", flush=True)

    return {
        "name": node_name,
        "type": node_info.get("type", ""),
        "server": node_info.get("server", ""),
        "port": node_info.get("port", 0),
        "speed_bps": best_speed.get("speed_bps", 0),
        "speed_mbps": best_speed.get("speed_mbps", 0),
        "speed_mb_per_sec": best_speed.get("speed_mb_per_sec", 0),
        "max_speed_mb_per_sec": max(r.get("speed_mb_per_sec", 0) for r in speed_results),
        "traffic_mb": best_speed.get("traffic_mb", 0),
        "tcp_ping": latency.get("tcp_ping"),
        "tls_rtt": latency.get("tls_rtt"),
        "https_ping": latency.get("https_ping"),
    }
