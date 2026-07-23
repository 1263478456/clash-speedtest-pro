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

        # vless:// 链接
        elif line.startswith("vless://"):
            try:
                # VLESS 格式: vless://uuid@server:port?params#name
                content_part = line[8:]  # 去掉 "vless://"
                # 分离名称
                if "#" in content_part:
                    name_part, fragment = content_part.rsplit("#", 1)
                    name = fragment
                else:
                    name_part = content_part
                    name = f"VLESS-{line.split('@')[1].split(':')[0] if '@' in line else 'unknown'}"

                # 分离 uuid 和 server:port
                if "@" in name_part:
                    uuid, server_port = name_part.split("@", 1)
                else:
                    continue

                # 分离 server 和 port
                if "?" in server_port:
                    server_port_part, query_string = server_port.split("?", 1)
                else:
                    server_port_part = server_port
                    query_string = ""

                if ":" in server_port_part:
                    server, port_str = server_port_part.rsplit(":", 1)
                    port = int(port_str)
                else:
                    continue

                # 解析查询参数
                params = {}
                if query_string:
                    for param in query_string.split("&"):
                        if "=" in param:
                            k, v = param.split("=", 1)
                            params[k] = v

                # 构建 raw 配置
                raw = {
                    "name": name,
                    "type": "vless",
                    "server": server,
                    "port": port,
                    "uuid": uuid,
                    "network": params.get("type", "tcp"),
                    "udp": True,
                }

                # TLS 配置
                security = params.get("security", "none")
                if security in ["tls", "reality"]:
                    raw["tls"] = True
                    if params.get("sni"):
                        raw["sni"] = params["sni"]
                    if params.get("fp"):
                        raw["client-fingerprint"] = params["fp"]
                    if params.get("allowInsecure") == "1":
                        raw["skip-cert-verify"] = True

                # Reality 配置
                if security == "reality":
                    reality_opts = {}
                    if params.get("pbk"):
                        reality_opts["public-key"] = params["pbk"]
                    if params.get("sid"):
                        reality_opts["short-id"] = params["sid"]
                    if reality_opts:
                        raw["reality-opts"] = reality_opts
                    # Reality 节点必须设置
                    if not raw.get("client-fingerprint"):
                        raw["client-fingerprint"] = "chrome"
                    raw["skip-cert-verify"] = True
                    if not raw.get("sni"):
                        raw["sni"] = params.get("host", server)

                # Flow 控制
                if params.get("flow"):
                    raw["flow"] = params["flow"]

                # 传输层配置
                network = params.get("type", "tcp")
                if network == "ws":
                    ws_opts = {}
                    if params.get("path"):
                        ws_opts["path"] = params["path"]
                    if params.get("host"):
                        ws_opts["headers"] = {"Host": params["host"]}
                    if ws_opts:
                        raw["ws-opts"] = ws_opts
                elif network == "grpc":
                    grpc_opts = {}
                    if params.get("serviceName"):
                        grpc_opts["grpc-service-name"] = params["serviceName"]
                    if grpc_opts:
                        raw["grpc-opts"] = grpc_opts
                elif network == "h2":
                    h2_opts = {}
                    if params.get("path"):
                        h2_opts["path"] = params["path"]
                    if params.get("host"):
                        h2_opts["host"] = [params["host"]]
                    if h2_opts:
                        raw["h2-opts"] = h2_opts

                # Packet encoding
                if params.get("pkt"):
                    raw["packet-encoding"] = params["pkt"]

                node = {
                    "name": name,
                    "type": "VLESS",
                    "server": server,
                    "port": port,
                    "raw": raw,
                }
                nodes.append(node)
            except Exception as e:
                print(f"[Subscription] VLESS 解析失败: {e}", flush=True)
                continue

        # trojan:// 链接
        elif line.startswith("trojan://"):
            try:
                # Trojan 格式: trojan://password@server:port?params#name
                content_part = line[9:]  # 去掉 "trojan://"
                # 分离名称
                if "#" in content_part:
                    name_part, fragment = content_part.rsplit("#", 1)
                    name = fragment
                else:
                    name_part = content_part
                    name = f"Trojan-{line.split('@')[1].split(':')[0] if '@' in line else 'unknown'}"

                # 分离 password 和 server:port
                if "@" in name_part:
                    password, server_port = name_part.split("@", 1)
                else:
                    continue

                # 分离 server 和 port
                if "?" in server_port:
                    server_port_part, query_string = server_port.split("?", 1)
                else:
                    server_port_part = server_port
                    query_string = ""

                if ":" in server_port_part:
                    server, port_str = server_port_part.rsplit(":", 1)
                    port = int(port_str)
                else:
                    continue

                # 解析查询参数
                params = {}
                if query_string:
                    for param in query_string.split("&"):
                        if "=" in param:
                            k, v = param.split("=", 1)
                            params[k] = v

                raw = {
                    "name": name,
                    "type": "trojan",
                    "server": server,
                    "port": port,
                    "password": password,
                }
                if params.get("sni"):
                    raw["sni"] = params["sni"]
                if params.get("allowInsecure") == "1":
                    raw["skip-cert-verify"] = True

                node = {
                    "name": name,
                    "type": "TROJAN",
                    "server": server,
                    "port": port,
                    "raw": raw,
                }
                nodes.append(node)
            except Exception as e:
                print(f"[Subscription] Trojan 解析失败: {e}", flush=True)
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
