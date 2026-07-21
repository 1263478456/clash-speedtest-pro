"""
mihomo 进程管理模块
负责启动/停止 mihomo 进程、切换节点、生成配置
"""
import os
import sys
import time
import yaml
import signal
import asyncio
import httpx
import socket
import random
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import MIHOMO_DIR, MIHOMO_CONFIG, MIHOMO_API_URL, MIHOMO_PROXY_PORT, MIHOMO_SOCKS_PORT


# 当前使用的端口
_current_api_port = None
_current_proxy_port = None
_current_socks_port = None
_mihomo_process = None


def check_port_available(port: int) -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False


def find_available_port(start_port: int, max_attempts: int = 100) -> int:
    """查找可用端口"""
    port = start_port
    for _ in range(max_attempts):
        if check_port_available(port):
            return port
        port = random.randint(10000, 60000)
    raise RuntimeError(f"无法找到可用端口 (起始: {start_port})")


def get_available_ports() -> tuple:
    """获取三个可用端口: api, proxy, socks"""
    global _current_api_port, _current_proxy_port, _current_socks_port
    
    api_port = find_available_port(19090)
    proxy_port = find_available_port(17890)
    socks_port = find_available_port(17891)
    
    # 确保 socks_port 不与 proxy_port 相同
    while socks_port == proxy_port:
        socks_port = find_available_port(17891)
    
    _current_api_port = api_port
    _current_proxy_port = proxy_port
    _current_socks_port = socks_port
    
    return api_port, proxy_port, socks_port


def get_current_ports() -> Dict[str, int]:
    """获取当前使用的端口"""
    return {
        "api": _current_api_port,
        "proxy": _current_proxy_port,
        "socks": _current_socks_port,
    }


def get_mihomo_binary() -> Path:
    """获取 mihomo 可执行文件路径"""
    if sys.platform == "win32":
        return MIHOMO_DIR / "mihomo.exe"
    return MIHOMO_DIR / "mihomo"


def generate_mihomo_config(nodes: List[Dict[str, Any]], current_node: str = None) -> str:
    """生成 mihomo 配置文件"""
    
    def clean_name(name: str) -> str:
        """清理节点名称中的特殊字符，只保留中文、英文、数字、常见符号"""
        import re
        # 移除 emoji 和特殊 unicode 字符，只保留安全字符
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\-_.|/\\()（）【】\[\]{}]', '', name)
        # 如果清理后为空，使用原始名称
        return cleaned if cleaned else name
    
    # 获取可用端口
    api_port, proxy_port, socks_port = get_available_ports()
    print(f"[Config] 使用端口 - API: {api_port}, Proxy: {proxy_port}, SOCKS: {socks_port}")
    
    # 构建 proxies 列表
    proxies = []
    for node in nodes:
        raw = node.get("raw", {})
        proxy_type = raw.get("type", "").lower()
        node_name = clean_name(node.get("name", "unknown"))
        
        print(f"[Config] 处理节点: {node_name}, 类型: {proxy_type}")

        if proxy_type == "ss":
            proxy = {
                "name": node_name,
                "type": "ss",
                "server": node["server"],
                "port": node["port"],
                "cipher": raw.get("cipher", "aes-256-gcm"),
                "password": raw.get("password", ""),
            }
            if raw.get("plugin"):
                proxy["plugin"] = raw["plugin"]
                proxy["plugin-opts"] = raw.get("plugin-opts", {})
            proxies.append(proxy)

        elif proxy_type == "vmess":
            proxy = {
                "name": node_name,
                "type": "vmess",
                "server": node["server"],
                "port": node["port"],
                "uuid": raw.get("uuid", ""),
                "alterId": raw.get("alterId", 0),
                "cipher": raw.get("cipher", "auto"),
                "network": raw.get("network", "tcp"),
            }
            if raw.get("tls"):
                proxy["tls"] = True
            if raw.get("ws-opts"):
                proxy["ws-opts"] = raw["ws-opts"]
            proxies.append(proxy)

        elif proxy_type == "trojan":
            proxy = {
                "name": node_name,
                "type": "trojan",
                "server": node["server"],
                "port": node["port"],
                "password": raw.get("password", ""),
            }
            if raw.get("sni"):
                proxy["sni"] = raw["sni"]
            proxies.append(proxy)

        elif proxy_type == "vless":
            proxy = {
                "name": node_name,
                "type": "vless",
                "server": node["server"],
                "port": node["port"],
                "uuid": raw.get("uuid", ""),
                "network": raw.get("network", "tcp"),
                "tls": raw.get("tls", False),
            }
            proxies.append(proxy)

        elif proxy_type == "ssr":
            # ShadowsocksR 协议
            proxy = {
                "name": node_name,
                "type": "ssr",
                "server": node["server"],
                "port": node["port"],
                "cipher": raw.get("cipher", "aes-256-cfb"),
                "password": raw.get("password", ""),
                "obfs": raw.get("obfs", "plain"),
                "obfs-param": raw.get("obfs-param", ""),
                "protocol": raw.get("protocol", "origin"),
                "protocol-param": raw.get("protocol-param", ""),
            }
            proxies.append(proxy)

        elif proxy_type == "anytls":
            # AnyTLS 协议 (较新的协议)
            proxy = {
                "name": node_name,
                "type": "anytls",
                "server": node["server"],
                "port": node["port"],
                "password": raw.get("password", ""),
            }
            if raw.get("sni"):
                proxy["sni"] = raw["sni"]
            if raw.get("fingerprint"):
                proxy["fingerprint"] = raw["fingerprint"]
            proxies.append(proxy)

        elif proxy_type in ["hysteria", "hysteria2"]:
            # Hysteria / Hysteria2 协议
            proxy = {
                "name": node_name,
                "type": proxy_type,
                "server": node["server"],
                "port": node["port"],
                "password": raw.get("password", ""),
            }
            if raw.get("sni"):
                proxy["sni"] = raw["sni"]
            if raw.get("obfs"):
                proxy["obfs"] = raw["obfs"]
            proxies.append(proxy)

        else:
            print(f"[Config] 未知类型: {proxy_type}, 跳过节点: {node_name}")

    print(f"[Config] 生成了 {len(proxies)} 个代理配置")

    # 清理 proxy-groups 中的名称
    cleaned_node_names = [clean_name(n["name"]) for n in nodes]

    # 构建完整配置
    config = {
        "mixed-port": proxy_port,
        "socks-port": socks_port,
        "allow-lan": False,
        "mode": "global",
        "log-level": "warning",
        "external-controller": f"127.0.0.1:{api_port}",
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "GLOBAL",
                "type": "select",
                "proxies": ["DIRECT"] + cleaned_node_names,
            }
        ],
        "rules": ["MATCH,GLOBAL"],
    }

    if current_node:
        config["proxy-groups"][0]["proxies"].insert(0, clean_name(current_node))

    return yaml.dump(config, allow_unicode=True, default_flow_style=False)


async def start_mihomo(nodes: List[Dict[str, Any]]) -> bool:
    """启动 mihomo 进程"""
    global _mihomo_process
    
    binary = get_mihomo_binary()
    if not binary.exists():
        raise FileNotFoundError(
            f"mihomo 二进制文件不存在: {binary}\n"
            f"请从 https://github.com/MetaCubeX/mihomo/releases 下载对应版本并放入 mihomo 目录"
        )

    # 检查节点列表
    if not nodes:
        raise ValueError("节点列表为空，无法启动 mihomo")

    # 生成配置 (会自动检测可用端口)
    config_content = generate_mihomo_config(nodes)
    MIHOMO_CONFIG.write_text(config_content, encoding="utf-8")
    
    # 获取当前使用的端口
    ports = get_current_ports()
    api_url = f"http://127.0.0.1:{ports['api']}"
    
    print(f"[mihomo] 配置已生成: {MIHOMO_CONFIG}", flush=True)
    print(f"[mihomo] 节点数量: {len(nodes)}", flush=True)
    print(f"[mihomo] 使用端口 - API: {ports['api']}, Proxy: {ports['proxy']}", flush=True)

    # 先停止已有的 mihomo 进程
    await stop_mihomo()
    await asyncio.sleep(1)

    # 启动进程
    cmd = [str(binary), "-d", str(MIHOMO_DIR), "-f", str(MIHOMO_CONFIG)]
    print(f"[mihomo] 启动命令: {' '.join(cmd)}")
    print(f"[mihomo] 配置文件内容:")
    try:
        config_content = MIHOMO_CONFIG.read_text(encoding="utf-8")
        for i, line in enumerate(config_content.split('\n')[:15]):
            print(f"  {line}")
        if len(config_content.split('\n')) > 15:
            print(f"  ... (共 {len(config_content.split(chr(10)))} 行)")
    except Exception as e:
        print(f"  读取配置失败: {e}")

    try:
        if sys.platform == "win32":
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid,
            )
        
        _mihomo_process = process
        print(f"[mihomo] 进程已启动, PID: {process.pid}", flush=True)

        # 等待启动
        print(f"[mihomo] 等待 5 秒让进程启动...", flush=True)
        await asyncio.sleep(5)

        # 检查进程是否还在运行
        returncode = process.returncode
        print(f"[mihomo] 进程状态: returncode={returncode}", flush=True)
        
        if returncode is not None:
            # 进程已退出，读取错误信息
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "未知错误"
                stdout_msg = stdout.decode('utf-8', errors='ignore') if stdout else ""
                print(f"[mihomo] 进程已退出，返回码: {returncode}", flush=True)
                print(f"[mihomo] 错误信息: {error_msg[:1000]}", flush=True)
                print(f"[mihomo] 标准输出: {stdout_msg[:1000]}", flush=True)
            except Exception as e:
                print(f"[mihomo] 读取进程输出失败: {e}", flush=True)
            _mihomo_process = None
            return False

        # 读取启动日志
        try:
            stdout_data = await asyncio.wait_for(process.stdout.read(1024), timeout=2)
            stderr_data = await asyncio.wait_for(process.stderr.read(1024), timeout=2)
            if stdout_data:
                print(f"[mihomo] 标准输出: {stdout_data.decode('utf-8', errors='ignore')[:500]}", flush=True)
            if stderr_data:
                print(f"[mihomo] 标准错误: {stderr_data.decode('utf-8', errors='ignore')[:500]}", flush=True)
        except asyncio.TimeoutError:
            print(f"[mihomo] 读取日志超时（正常）", flush=True)
        except Exception as e:
            print(f"[mihomo] 读取日志异常: {e}", flush=True)

        # 检查是否启动成功
        print(f"[mihomo] 检查 API: {api_url}/version", flush=True)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{api_url}/version", timeout=10)
                if resp.status_code == 200:
                    version_info = resp.json()
                    print(f"[mihomo] 启动成功! 版本: {version_info.get('version', 'unknown')}", flush=True)
                    
                    # 检查代理组
                    try:
                        resp = await client.get(f"{api_url}/proxies", timeout=5)
                        if resp.status_code == 200:
                            proxies_data = resp.json()
                            print(f"[mihomo] 代理组: {list(proxies_data.get('proxies', {}).keys())}", flush=True)
                    except Exception as e:
                        print(f"[mihomo] 获取代理信息失败: {e}", flush=True)
                    
                    return True
                else:
                    print(f"[mihomo] API 返回非 200: {resp.status_code}", flush=True)
        except httpx.ConnectError as e:
            print(f"[mihomo] API 连接失败: {e}", flush=True)
        except Exception as e:
            print(f"[mihomo] API 检查失败: {type(e).__name__}: {e}", flush=True)

        return False
    except Exception as e:
        print(f"[mihomo] 启动异常: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False


async def stop_mihomo():
    """停止 mihomo 进程"""
    global _mihomo_process
    
    ports = get_current_ports()
    api_url = f"http://127.0.0.1:{ports['api']}" if ports['api'] else None
    
    # 尝试通过 API 优雅关闭
    if api_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(f"{api_url}/configs", timeout=5)
                print("[mihomo] 通过 API 发送关闭信号")
        except Exception:
            pass
    
    # 关闭本地进程
    if _mihomo_process:
        try:
            _mihomo_process.terminate()
            print("[mihomo] 进程已终止")
        except Exception:
            pass
        _mihomo_process = None
    
    # 强制结束所有 mihomo 进程 (只结束我们启动的，不影响其他 mihomo)
    # 注意：不在 Docker 容器中使用 pkill，因为 slim 镜像没有这个命令
    # 我们已经通过 _mihomo_process.terminate() 终止了主进程


async def switch_node(node_name: str) -> bool:
    """切换 mihomo 到指定节点"""
    ports = get_current_ports()
    if not ports['api']:
        print("[Switch] API 端口未设置")
        return False
    
    api_url = f"http://127.0.0.1:{ports['api']}"
    print(f"[Switch] 尝试切换节点: {node_name} -> {api_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            # 通过 API 切换代理组
            resp = await client.put(
                f"{api_url}/proxies/GLOBAL",
                json={"name": node_name},
                timeout=5,
            )
            print(f"[Switch] API 响应: {resp.status_code}")
            return resp.status_code == 200 or resp.status_code == 204
    except Exception as e:
        print(f"[Switch] 切换失败: {e}")
        return False


async def get_current_node() -> Optional[str]:
    """获取当前使用的节点名称"""
    ports = get_current_ports()
    if not ports['api']:
        return None
    
    api_url = f"http://127.0.0.1:{ports['api']}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{api_url}/proxies/GLOBAL", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("now")
    except Exception:
        pass
    return None


async def get_proxy_delay(node_name: str) -> Dict[str, Any]:
    """获取节点延迟信息"""
    ports = get_current_ports()
    if not ports['api']:
        return {}
    
    api_url = f"http://127.0.0.1:{ports['api']}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/proxies/{node_name}/delay",
                params={"timeout": 5000, "url": "http://www.gstatic.com/generate_204"},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


async def is_mihomo_running() -> bool:
    """检查 mihomo 是否运行"""
    ports = get_current_ports()
    if not ports['api']:
        return False
    
    api_url = f"http://127.0.0.1:{ports['api']}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{api_url}/version", timeout=3)
            return resp.status_code == 200
    except Exception:
        return False
