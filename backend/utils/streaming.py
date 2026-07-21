"""
流媒体解锁检测模块
检测 Netflix、YouTube、Bilibili、Disney+、TikTok 等服务的解锁状态
"""
import asyncio
import httpx
import json
import re
from typing import Dict, Any, Optional
from config import STREAMING_TEST_TIMEOUT
from backend.utils.mihomo_manager import get_current_ports


def get_proxy_url() -> str:
    """获取当前代理 URL"""
    ports = get_current_ports()
    return f"http://127.0.0.1:{ports['proxy']}"


async def _get(url: str, timeout: float = STREAMING_TEST_TIMEOUT, **kwargs) -> Optional[httpx.Response]:
    """通过代理发起 GET 请求"""
    try:
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            proxies=get_proxy_url(),
            follow_redirects=True,
        ) as client:
            return await client.get(url, **kwargs)
    except Exception:
        return None


async def _post(url: str, timeout: float = STREAMING_TEST_TIMEOUT, **kwargs) -> Optional[httpx.Response]:
    """通过代理发起 POST 请求"""
    try:
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            proxies=get_proxy_url(),
            follow_redirects=True,
        ) as client:
            return await client.post(url, **kwargs)
    except Exception:
        return None


async def _head(url: str, timeout: float = STREAMING_TEST_TIMEOUT, **kwargs) -> Optional[httpx.Response]:
    """通过代理发起 HEAD 请求"""
    try:
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            proxies=get_proxy_url(),
            follow_redirects=True,
        ) as client:
            return await client.head(url, **kwargs)
    except Exception:
        return None


async def check_netflix() -> str:
    """检测 Netflix 解锁状态"""
    try:
        # Netflix 自製影片检测
        resp = await _get(
            "https://www.netflix.com/title/81280792",
            headers={"Accept-Language": "en"},
        )
        if resp is None:
            return "检测失败"

        if resp.status_code == 403:
            return "未解锁"

        # 检查 redirect URL 中的区域
        url_str = str(resp.url)
        if "netflix.com" not in url_str:
            return "未解锁"

        # 检查页面内容中的区域信息
        text = resp.text
        if "Sorry, this title isn't available" in text:
            return "未解锁"

        # 尝试获取区域
        try:
            resp2 = await _get(
                "https://www.netflix.com/title/70143836",
                headers={"Accept-Language": "en"},
            )
            if resp2 and resp2.status_code == 200:
                # 检查是否重定向到特定区域
                redirect_url = str(resp2.url)
                if "/title/" in redirect_url:
                    # 尝试从页面获取区域
                    region_match = re.search(r'"currentCountry":"(\w+)"', resp2.text)
                    if region_match:
                        region = region_match.group(1).upper()
                        return f"解锁({region})"
                    return "解锁"
        except Exception:
            pass

        return "解锁"
    except Exception:
        return "检测失败"


async def check_youtube() -> str:
    """检测 YouTube Premium 解锁状态"""
    try:
        resp = await _get(
            "https://www.youtube.com/premium",
            headers={"Accept-Language": "en"},
        )
        if resp is None:
            return "检测失败"

        if resp.status_code != 200:
            return "未解锁"

        text = resp.text
        # 检查区域限制
        if "Premium is not available" in text:
            return "未解锁"

        # 尝试识别区域
        region_match = re.search(r'"countryCode":"(\w+)"', text)
        if region_match:
            region = region_match.group(1).upper()
            return f"解锁({region})"

        return "解锁"
    except Exception:
        return "检测失败"


async def check_bilibili() -> str:
    """检测 Bilibili 解锁状态 (港澳台)"""
    try:
        resp = await _get(
            "https://api.bilibili.com/pgc/player/web/playurl?avid=82846771&cid=141541068&qn=0&type=&otype=json&ep_id=307247&fourk=1",
            headers={"Referer": "https://www.bilibili.com"},
        )
        if resp is None:
            return "检测失败"

        data = resp.json()
        code = data.get("code", -1)

        if code == 0:
            # 检查区域
            try:
                area_resp = await _get("https://api.bilibili.com/x/web-interface/zone")
                if area_resp:
                    area_data = area_resp.json()
                    country = area_data.get("data", {}).get("country", "")
                    if country:
                        return f"解锁({country})"
                    return "解锁(中国)"
            except Exception:
                return "解锁"

        elif code == -10403:
            # 尝试获取区域信息
            try:
                area_resp = await _get("https://api.bilibili.com/x/web-interface/zone")
                if area_resp:
                    area_data = area_resp.json()
                    country = area_data.get("data", {}).get("country", "")
                    if country:
                        return f"解锁({country})"
            except Exception:
                pass
            return "解锁(港澳台)"

        return "未解锁"
    except Exception:
        return "检测失败"


async def check_disney() -> str:
    """检测 Disney+ 解锁状态"""
    try:
        # Disney+ Token 获取
        resp = await _post(
            "https://disney.api.edge.bamgrid.com/devices",
            headers={
                "Content-Type": "application/json",
                "Authorization": "ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA88oUHhivTl6OnEh1nRAlBqWBE",
            },
            content=json.dumps({
                "deviceFamily": "browser",
                "applicationRuntime": "chrome",
                "deviceModel": "windows",
                "attributes": {}
            }),
        )
        if resp is None:
            return "检测失败"

        if resp.status_code == 201:
            data = resp.json()
            token = data.get("accessToken", "")
            if token:
                # 检查区域
                region_resp = await _get(
                    "https://disney.api.edge.bamgrid.com/geolocation",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if region_resp and region_resp.status_code == 200:
                    region_data = region_resp.json()
                    region = region_data.get("region", "unknown")
                    return f"解锁({region.upper()})"
                return "解锁"

        return "未解锁"
    except Exception:
        return "检测失败"


async def check_tiktok() -> str:
    """检测 TikTok 解锁状态"""
    try:
        resp = await _get(
            "https://www.tiktok.com/",
            headers={"Accept-Language": "en"},
        )
        if resp is None:
            return "检测失败"

        if resp.status_code == 200:
            text = resp.text
            region_match = re.search(r'"region":"(\w+)"', text)
            if region_match:
                region = region_match.group(1).upper()
                return f"解锁({region})"
            return "解锁"

        return "未解锁"
    except Exception:
        return "检测失败"


async def check_chatgpt() -> str:
    """检测 ChatGPT 解锁状态"""
    try:
        resp = await _get(
            "https://chat.openai.com/cdn-cgi/trace",
            headers={"Accept-Language": "en"},
        )
        if resp is None:
            return "检测失败"

        text = resp.text
        if "cf-ray" in text.lower() or "warp=" in text.lower():
            # 检查是否被拦截
            if "blocked" in text.lower():
                return "未解锁"

            # 获取区域
            region_match = re.search(r"loc=([A-Z]{2})", text)
            if region_match:
                region = region_match.group(1)
                return f"解锁({region})"
            return "解锁"

        return "未解锁"
    except Exception:
        return "检测失败"


async def check_spotify() -> str:
    """检测 Spotify 解锁状态"""
    try:
        resp = await _get(
            "https://spclient.wg.spotify.com/signup/public/v1/account?validate=1&email=test%40test.com",
            headers={"Accept-Language": "en"},
        )
        if resp is None:
            return "检测失败"

        if resp.status_code == 200:
            data = resp.json()
            if data.get("can_accept_mailing", False):
                return "解锁"
            return "未解锁"

        return "未解锁"
    except Exception:
        return "检测失败"


async def check_steam() -> str:
    """检测 Steam 商店区域"""
    try:
        resp = await _get(
            "https://store.steampowered.com/api/?cc=US",
            headers={"Accept-Language": "en"},
        )
        if resp is None:
            return "检测失败"

        data = resp.json()
        # 尝试获取区域
        resp2 = await _get("https://store.steampowered.com/")
        if resp2:
            text = resp2.text
            country_match = re.search(r'"countryCode":"(\w+)"', text)
            if country_match:
                country = country_match.group(1).upper()
                return f"货币: {country}"

        return "检测失败"
    except Exception:
        return "检测失败"


async def check_all_streaming() -> Dict[str, str]:
    """并行检测所有流媒体服务"""
    tasks = {
        "Netflix": check_netflix(),
        "YouTube": check_youtube(),
        "Bilibili": check_bilibili(),
        "Disney+": check_disney(),
        "TikTok": check_tiktok(),
        "ChatGPT": check_chatgpt(),
        "Spotify": check_spotify(),
        "Steam": check_steam(),
    }

    results = {}
    for name, coro in tasks.items():
        try:
            results[name] = await asyncio.wait_for(coro, timeout=STREAMING_TEST_TIMEOUT)
        except asyncio.TimeoutError:
            results[name] = "检测超时"
        except Exception:
            results[name] = "检测失败"

    return results
