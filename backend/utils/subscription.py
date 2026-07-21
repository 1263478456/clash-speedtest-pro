"""
订阅链接解析模块
支持 Clash/SSR/V2Ray 订阅格式
"""
import base64
import yaml
import httpx
import re
from typing import List, Dict, Any
from urllib.parse import urlparse, parse_qs


async def fetch_subscription(url: str) -> str:
    """拉取订阅内容"""
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        resp = await client.get(url, headers={
            "User-Agent": "mihomo/v1.19.28"
        })
        resp.raise_for_status()
        return resp.text


def decode_base64_urlsafe(data: str) -> str:
    """解码 base64 (urlsafe)"""
    # 补齐 padding
    missing = len(data) % 4
    if missing:
        data += "=" * (4 - missing)
    # 替换 urlsafe 字符
    data = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(data).decode("utf-8", errors="ignore")


def parse_clash_yaml(content: str) -> List[Dict[str, Any]]:
    """解析 Clash YAML 格式订阅"""
    try:
        config = yaml.safe_load(content)
    except yaml.YAMLError:
        return []

    proxies = config.get("proxies", [])
    nodes = []
    
    # 过滤掉非代理节点（订阅信息等）
    invalid_server_patterns = ["www.baidu.com", "baidu.com", "example.com", "localhost"]
    invalid_name_patterns = ["官网", "剩余流量", "套餐时间", "到期", "续费", "余额", "剩余", "流量", "时间", "地址", "信息"]
    
    filtered_count = 0
    for p in proxies:
        name = p.get("name", "unknown")
        server = p.get("server", "")
        
        # 检查是否是无效节点
        is_invalid = False
        
        # 检查服务器地址
        for pattern in invalid_server_patterns:
            if pattern in server.lower():
                is_invalid = True
                break
        
        # 检查节点名称
        if not is_invalid:
            for pattern in invalid_name_patterns:
                if pattern in name:
                    is_invalid = True
                    break
        
        if is_invalid:
            filtered_count += 1
            print(f"[Subscription] 跳过无效节点: {name} (服务器: {server})", flush=True)
            continue
        
        node = {
            "name": name,
            "type": p.get("type", "").upper(),
            "server": server,
            "port": p.get("port", 0),
            "raw": p,
        }
        nodes.append(node)
    
    print(f"[Subscription] 过滤了 {filtered_count} 个无效节点, 剩余 {len(nodes)} 个有效节点", flush=True)
    return nodes


def parse_v2ray_links(content: str) -> List[Dict[str, Any]]:
    """解析 V2Ray/SS/VMess 链接"""
    nodes = []
    lines = content.strip().split("\n")
    
    # 过滤掉非代理节点（订阅信息等）
    invalid_server_patterns = ["www.baidu.com", "baidu.com", "example.com", "localhost"]
    invalid_name_patterns = ["官网", "剩余流量", "套餐时间", "到期", "续费", "余额", "剩余", "流量", "时间", "地址", "信息"]
    
    filtered_count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 提取节点名称和服务器地址
        name = ""
        server = ""
        
        # vmess:// 链接
        if line.startswith("vmess://"):
            try:
                data = decode_base64_urlsafe(line[8:])
                info = yaml.safe_load(data)
                name = info.get("ps", "unknown")
                server = info.get("add", "")
                
                # 检查是否是无效节点
                is_invalid = False
                for pattern in invalid_server_patterns:
                    if pattern in server.lower():
                        is_invalid = True
                        break
                if not is_invalid:
                    for pattern in invalid_name_patterns:
                        if pattern in name:
                            is_invalid = True
                            break
                
                if is_invalid:
                    filtered_count += 1
                    print(f"[Subscription] 跳过无效节点: {name} (服务器: {server})", flush=True)
                    continue
                
                node = {
                    "name": name,
                    "type": "VMESS",
                    "server": server,
                    "port": int(info.get("port", 0)),
                    "raw": {
                        "name": name,
                        "type": "vmess",
                        "server": server,
                        "port": int(info.get("port", 0)),
                        "uuid": info.get("id", ""),
                        "alterId": int(info.get("aid", 0)),
                        "cipher": info.get("scy", "auto"),
                        "network": info.get("net", "tcp"),
                        "tls": info.get("tls", "") == "tls",
                        "ws-opts": {},
                    },
                }
                if info.get("net") == "ws":
                    node["raw"]["ws-opts"] = {
                        "path": info.get("path", ""),
                        "headers": {"Host": info.get("host", "")},
                    }
                nodes.append(node)
            except Exception:
                continue

        # ss:// 链接
        elif line.startswith("ss://"):
            try:
                decoded = decode_base64_urlsafe(line[5:])
                # 格式: method:password@server:port#name
                match = re.match(
                    r"^(.+?):(.+?)@(.+?):(\d+)(?:#.*)?$", decoded
                )
                if match:
                    method, password, server, port = match.groups()
                    name = decoded.split("#")[-1] if "#" in decoded else "unknown"
                    
                    # 检查是否是无效节点
                    is_invalid = False
                    for pattern in invalid_server_patterns:
                        if pattern in server.lower():
                            is_invalid = True
                            break
                    if not is_invalid:
                        for pattern in invalid_name_patterns:
                            if pattern in name:
                                is_invalid = True
                                break
                    
                    if is_invalid:
                        filtered_count += 1
                        print(f"[Subscription] 跳过无效节点: {name} (服务器: {server})", flush=True)
                        continue
                    
                    node = {
                        "name": name,
                        "type": "SS",
                        "server": server,
                        "port": int(port),
                        "raw": {
                            "name": name,
                            "type": "ss",
                            "server": server,
                            "port": int(port),
                            "cipher": method,
                            "password": password,
                        },
                    }
                    nodes.append(node)
            except Exception:
                continue

        # ssr:// 链接 (ShadowsocksR)
        elif line.startswith("ssr://"):
            try:
                decoded = decode_base64_urlsafe(line[6:])
                # SSR 格式: server:port:protocol:method:obfs:base64pass/?params
                parts = decoded.split(":")
                if len(parts) >= 6:
                    server = parts[0]
                    port = int(parts[1])
                    protocol = parts[2]
                    cipher = parts[3]
                    obfs = parts[4]
                    password_base64 = parts[5]
                    password = decode_base64_urlsafe(password_base64)
                    
                    # 解析参数
                    params = {}
                    if "/?" in decoded:
                        param_str = decoded.split("/?")[1]
                        for param in param_str.split("&"):
                            if "=" in param:
                                k, v = param.split("=", 1)
                                params[k] = v
                    
                    name = params.get("remarks", f"SSR-{server}:{port}")
                    # 解码名称
                    try:
                        name = decode_base64_urlsafe(name)
                    except Exception:
                        pass
                    
                    # 检查是否是无效节点
                    is_invalid = False
                    for pattern in invalid_server_patterns:
                        if pattern in server.lower():
                            is_invalid = True
                            break
                    if not is_invalid:
                        for pattern in invalid_name_patterns:
                            if pattern in name:
                                is_invalid = True
                                break
                    
                    if is_invalid:
                        filtered_count += 1
                        print(f"[Subscription] 跳过无效节点: {name} (服务器: {server})", flush=True)
                        continue
                    
                    node = {
                        "name": name,
                        "type": "SSR",
                        "server": server,
                        "port": port,
                        "raw": {
                            "name": name,
                            "type": "ssr",
                            "server": server,
                            "port": port,
                            "cipher": cipher,
                            "password": password,
                            "protocol": protocol,
                            "obfs": obfs,
                            "obfs-param": params.get("obfsparam", ""),
                            "protocol-param": params.get("protoparam", ""),
                        },
                    }
                    nodes.append(node)
            except Exception:
                continue
    
    print(f"[Subscription] 过滤了 {filtered_count} 个无效节点, 剩余 {len(nodes)} 个有效节点", flush=True)
    return nodes


def parse_subscription(content: str) -> List[Dict[str, Any]]:
    """
    自动识别并解析订阅内容
    支持:
      - Clash YAML 格式 (proxies 字段)
      - Base64 编码的链接列表
      - 明文链接列表 (ss://, vmess://, trojan://)
    """
    print(f"[Subscription] 开始解析订阅内容, 长度: {len(content)}", flush=True)
    
    # 尝试 Clash YAML 格式
    if "proxies:" in content or "Proxy:" in content:
        print(f"[Subscription] 检测到 Clash YAML 格式", flush=True)
        nodes = parse_clash_yaml(content)
        if nodes:
            print(f"[Subscription] Clash YAML 解析成功, 节点数: {len(nodes)}", flush=True)
            return nodes

    # 尝试 base64 解码
    try:
        decoded = decode_base64_urlsafe(content.strip())
        if "://" in decoded:
            content = decoded
    except Exception:
        pass

    # 解析各种链接格式
    nodes = parse_v2ray_links(content)
    if nodes:
        print(f"[Subscription] 链接格式解析成功, 节点数: {len(nodes)}", flush=True)
        return nodes

    # 尝试作为 Clash YAML 解码后的内容
    try:
        decoded = decode_base64_urlsafe(content.strip())
        nodes = parse_clash_yaml(decoded)
        if nodes:
            print(f"[Subscription] 解码后 Clash YAML 解析成功, 节点数: {len(nodes)}", flush=True)
            return nodes
    except Exception:
        pass

    print(f"[Subscription] 解析失败, 返回空列表", flush=True)
    return []


async def get_nodes_from_subscription(url: str) -> List[Dict[str, Any]]:
    """从订阅链接获取节点列表"""
    content = await fetch_subscription(url)
    return parse_subscription(content)
