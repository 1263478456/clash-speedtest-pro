"""
ClashSpeedTest Pro - 主应用
支持 Docker 部署、用户认证、历史记录、定时任务
"""
import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from config import (
    WEB_HOST, WEB_PORT, MIHOMO_DIR, RESULTS_DIR,
    LOG_LEVELS, DEFAULT_LOG_LEVEL, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
)
from backend.models import Base
from backend.database import (
    init_db, get_user_by_username, create_user, update_user_password, update_username,
    create_subscription, get_subscriptions, get_subscription_by_id, delete_subscription, update_subscription_usage, update_subscription,
    create_test_result, update_test_result, add_node_result,
    get_test_results, get_test_result_by_id, get_node_results, delete_test_result,
    create_schedule_task, get_schedule_tasks, get_schedule_task_by_id,
    update_schedule_task, delete_schedule_task, update_task_last_run
)
from backend.auth import create_access_token, get_current_user, authenticate_user
from backend.scheduler import (
    scheduler, start_scheduler, stop_scheduler, load_scheduled_tasks,
    run_scheduled_test, get_cron_trigger
)
from backend.utils.subscription import get_nodes_from_subscription, parse_subscription
from backend.utils.mihomo_manager import start_mihomo, stop_mihomo, switch_node, is_mihomo_running, get_current_ports
from backend.utils.speedtest import test_node_speed
from backend.utils.streaming import check_all_streaming
from backend.utils.image_gen import generate_result_image

# FastAPI 应用
app = FastAPI(title="ClashSpeedTest Pro", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 禁用 uvicorn access 日志
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# 全局状态
class TestState:
    def __init__(self):
        self.is_running = False
        self.should_stop = False
        self.current_user_id = None
        self.current_result_id = None
        self.theme = "light"
        self.log_level = DEFAULT_LOG_LEVEL
        self.progress = {
            "total": 0,
            "completed": 0,
            "current_node": "",
            "status": "idle",
            "message": "",
        }
        self.results: List[Dict[str, Any]] = []
        self.nodes: List[Dict[str, Any]] = []

state = TestState()

# ========== 启动事件 ==========

@app.on_event("startup")
async def startup_event():
    """应用启动"""
    await init_db()
    
    # 将之前运行中的任务标记为已停止（重启后测速会中断）
    try:
        from backend.database import mark_running_as_stopped
        await mark_running_as_stopped()
    except Exception as e:
        print(f"[App] 清理运行中任务失败: {e}")
    
    await load_scheduled_tasks()
    start_scheduler()
    print(f"[App] ClashSpeedTest Pro 启动成功")
    print(f"[App] 访问地址: http://localhost:{WEB_PORT}")
    print(f"[App] 默认账户: admin / admin123")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭"""
    stop_scheduler()
    await stop_mihomo()

# ========== 静态文件 ==========

app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.mount("/results", StaticFiles(directory="results"), name="results")

# ========== 认证 API ==========

@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """用户登录"""
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
    }


@app.get("/api/auth/me")
async def get_me(current_user=Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "created_at": current_user.created_at.isoformat(),
    }


@app.post("/api/auth/change-password")
async def change_password(request: Request, current_user=Depends(get_current_user)):
    """修改密码"""
    data = await request.json()
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    
    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="请输入旧密码和新密码")
    
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    
    from backend.database import verify_password
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    
    success = await update_user_password(current_user.id, new_password)
    if success:
        return {"success": True, "message": "密码修改成功"}
    raise HTTPException(status_code=500, detail="密码修改失败")


@app.post("/api/auth/change-username")
async def change_username(request: Request, current_user=Depends(get_current_user)):
    """修改用户名"""
    data = await request.json()
    new_username = data.get("new_username", "")
    
    if not new_username or len(new_username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少 3 位")
    
    existing = await get_user_by_username(new_username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    success = await update_username(current_user.id, new_username)
    if success:
        return {"success": True, "message": "用户名修改成功"}
    raise HTTPException(status_code=500, detail="用户名修改失败")

# ========== 订阅管理 API ==========

@app.get("/api/subscriptions")
async def list_subscriptions(current_user=Depends(get_current_user)):
    """获取订阅列表"""
    subs = await get_subscriptions(current_user.id)
    return {
        "subscriptions": [
            {
                "id": s.id,
                "name": s.name,
                "url": s.url[:50] + "..." if len(s.url) > 50 else s.url,
                "node_count": s.node_count,
                "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in subs
        ]
    }


@app.post("/api/subscriptions")
async def add_subscription(request: Request, current_user=Depends(get_current_user)):
    """添加订阅"""
    data = await request.json()
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    
    if not name or not url:
        raise HTTPException(status_code=400, detail="名称和链接不能为空")
    
    # 尝试解析订阅获取节点数
    try:
        nodes = await get_nodes_from_subscription(url)
        node_count = len(nodes)
    except Exception:
        node_count = 0
    
    sub = await create_subscription(current_user.id, name, url, node_count)
    return {
        "success": True,
        "subscription": {
            "id": sub.id,
            "name": sub.name,
            "node_count": node_count,
        }
    }


@app.delete("/api/subscriptions/{sub_id}")
async def remove_subscription(sub_id: int, current_user=Depends(get_current_user)):
    """删除订阅"""
    success = await delete_subscription(sub_id, current_user.id)
    if success:
        return {"success": True, "message": "订阅已删除"}
    raise HTTPException(status_code=404, detail="订阅不存在")


@app.put("/api/subscriptions/{sub_id}")
async def modify_subscription(sub_id: int, request: Request, current_user=Depends(get_current_user)):
    """更新订阅（名称、URL、节点数）"""
    data = await request.json()
    name = data.get("name")
    url = data.get("url")
    
    # 检查订阅是否存在
    sub = await get_subscription_by_id(sub_id, current_user.id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    
    # 如果更新了URL，重新获取节点数
    node_count = None
    if url:
        try:
            nodes = await get_nodes_from_subscription(url)
            node_count = len(nodes)
        except Exception:
            node_count = 0
    
    success = await update_subscription(sub_id, current_user.id, name=name, url=url, node_count=node_count)
    if success:
        return {"success": True, "message": "订阅已更新", "node_count": node_count}
    raise HTTPException(status_code=500, detail="更新失败")


@app.post("/api/subscriptions/{sub_id}/refresh")
async def refresh_subscription(sub_id: int, current_user=Depends(get_current_user)):
    """刷新订阅（重新拉取订阅内容并更新节点数）"""
    # 检查订阅是否存在
    sub = await get_subscription_by_id(sub_id, current_user.id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    
    # 重新拉取订阅获取节点数
    try:
        nodes = await get_nodes_from_subscription(sub.url)
        node_count = len(nodes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"订阅刷新失败: {str(e)}")
    
    # 更新节点数和使用时间
    await update_subscription(sub_id, current_user.id, node_count=node_count)
    await update_subscription_usage(sub_id)
    
    return {
        "success": True,
        "message": "订阅已刷新",
        "subscription": {
            "id": sub.id,
            "name": sub.name,
            "node_count": node_count,
        }
    }

# ========== 测速 API ==========

@app.get("/api/status")
async def get_status():
    """获取当前状态"""
    mihomo_running = await is_mihomo_running()
    return {
        "mihomo_running": mihomo_running,
        "test_running": state.is_running,
        "progress": state.progress,
        "results_count": len(state.results),
        "theme": state.theme,
    }


@app.get("/api/live-results")
async def get_live_results():
    """获取实时测速结果（从内存中）"""
    return {
        "results": state.results,
        "progress": state.progress,
        "is_running": state.is_running,
    }


@app.post("/api/start-test")
async def start_test(request: Request, current_user=Depends(get_current_user)):
    """开始测速"""
    if state.is_running:
        raise HTTPException(status_code=400, detail="测速正在进行中")
    
    data = await request.json()
    subscription_id = data.get("subscription_id")
    test_streaming = data.get("test_streaming", True)
    theme = data.get("theme", "dark")
    
    # 获取订阅
    if subscription_id:
        sub = await get_subscription_by_id(subscription_id, current_user.id)
        if not sub:
            raise HTTPException(status_code=404, detail="订阅不存在")
        url = sub.url
        sub_name = sub.name
    else:
        url = data.get("url", "").strip()
        sub_name = "临时订阅"
        if not url:
            raise HTTPException(status_code=400, detail="请提供订阅链接或选择已保存的订阅")
    
    # 解析订阅
    try:
        nodes = await get_nodes_from_subscription(url)
        if not nodes:
            raise HTTPException(status_code=400, detail="未解析到任何节点")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"订阅解析失败: {str(e)}")
    
    # 更新订阅使用时间
    if subscription_id:
        await update_subscription_usage(subscription_id)
    
    # 创建测速结果记录
    test_result = await create_test_result(
        user_id=current_user.id,
        subscription_name=sub_name,
        total_nodes=len(nodes),
        theme=theme
    )
    
    # 启动后台测速
    state.is_running = True
    state.should_stop = False
    state.current_user_id = current_user.id
    state.current_result_id = test_result.id
    state.theme = theme
    state.nodes = nodes
    state.results = []
    state.progress = {
        "total": len(nodes),
        "completed": 0,
        "current_node": "",
        "status": "starting",
        "message": "正在启动...",
    }
    
    asyncio.create_task(run_speed_test(test_result.id, test_streaming))
    
    return {"success": True, "result_id": test_result.id, "message": "测速已开始"}


@app.post("/api/stop-test")
async def stop_test(current_user=Depends(get_current_user)):
    """停止测速"""
    state.should_stop = True
    state.progress["status"] = "stopping"
    state.progress["message"] = "正在停止..."
    
    await asyncio.sleep(0.5)
    
    state.is_running = False
    state.progress["status"] = "stopped"
    state.progress["message"] = "测速已停止"
    
    if state.current_result_id:
        await update_test_result(state.current_result_id, status="stopped", completed_at=datetime.utcnow())
    
    await stop_mihomo()
    return {"success": True, "message": "测速已停止"}


@app.get("/api/results")
async def get_results_list(current_user=Depends(get_current_user)):
    """获取测速结果列表"""
    results = await get_test_results(current_user.id)
    return {
        "results": [
            {
                "id": r.id,
                "subscription_name": r.subscription_name,
                "total_nodes": r.total_nodes,
                "tested_nodes": r.tested_nodes,
                "total_traffic_mb": r.total_traffic_mb,
                "image_path": r.image_path,
                "status": r.status,
                "theme": r.theme,
                "created_at": r.created_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in results
        ]
    }


@app.get("/api/results/{result_id}")
async def get_result_detail(result_id: int, current_user=Depends(get_current_user)):
    """获取测速结果详情"""
    result = await get_test_result_by_id(result_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="结果不存在")
    
    nodes = await get_node_results(result_id)
    return {
        "result": {
            "id": result.id,
            "subscription_name": result.subscription_name,
            "total_nodes": result.total_nodes,
            "tested_nodes": result.tested_nodes,
            "total_traffic_mb": result.total_traffic_mb,
            "image_path": result.image_path,
            "status": result.status,
            "theme": result.theme,
            "created_at": result.created_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        },
        "nodes": [
            {
                "name": n.node_name,
                "type": n.node_type,
                "server": n.server,
                "port": n.port,
                "speed_mb_per_sec": n.speed_mb_per_sec,
                "max_speed_mb_per_sec": n.max_speed_mb_per_sec,
                "traffic_mb": n.traffic_mb,
                "tcp_ping": n.tcp_ping,
                "tls_rtt": n.tls_rtt,
                "https_ping": n.https_ping,
                "streaming": {
                    "Netflix": n.netflix or "-",
                    "YouTube": n.youtube or "-",
                    "Bilibili": n.bilibili or "-",
                    "Disney+": n.disney_plus or "-",
                    "TikTok": n.tiktok or "-",
                    "ChatGPT": n.chatgpt or "-",
                    "Spotify": n.spotify or "-",
                    "Steam": n.steam or "-",
                },
                "error": n.error,
            }
            for n in nodes
        ]
    }


@app.delete("/api/results/{result_id}")
async def remove_result(result_id: int, current_user=Depends(get_current_user)):
    """删除测速结果"""
    success = await delete_test_result(result_id, current_user.id)
    if success:
        return {"success": True, "message": "结果已删除"}
    raise HTTPException(status_code=404, detail="结果不存在")

# ========== 定时任务 API ==========

@app.get("/api/schedules")
async def list_schedules(current_user=Depends(get_current_user)):
    """获取定时任务列表"""
    tasks = await get_schedule_tasks(current_user.id)
    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "subscription_id": t.subscription_id,
                "schedule_type": t.schedule_type,
                "schedule_config": json.loads(t.schedule_config),
                "test_streaming": t.test_streaming,
                "theme": t.theme,
                "enabled": t.enabled,
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    }


@app.post("/api/schedules")
async def add_schedule(request: Request, current_user=Depends(get_current_user)):
    """添加定时任务"""
    data = await request.json()
    name = data.get("name", "").strip()
    subscription_id = data.get("subscription_id")
    schedule_type = data.get("schedule_type", "daily")
    schedule_config = data.get("schedule_config", {})
    test_streaming = data.get("test_streaming", True)
    theme = data.get("theme", "dark")
    
    if not name:
        raise HTTPException(status_code=400, detail="任务名称不能为空")
    
    if not subscription_id:
        raise HTTPException(status_code=400, detail="请选择订阅")
    
    # 验证订阅存在
    sub = await get_subscription_by_id(subscription_id, current_user.id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    
    task = await create_schedule_task(
        user_id=current_user.id,
        name=name,
        subscription_id=subscription_id,
        schedule_type=schedule_type,
        schedule_config=schedule_config,
        test_streaming=test_streaming,
        theme=theme
    )
    
    # 添加到调度器
    trigger = get_cron_trigger(schedule_type, schedule_config)
    scheduler.add_job(
        run_scheduled_test,
        trigger=trigger,
        id=f"task_{task.id}",
        kwargs={
            "task_id": task.id,
            "user_id": current_user.id,
            "subscription_id": subscription_id,
            "test_streaming": test_streaming,
            "theme": theme,
        },
        replace_existing=True
    )
    
    return {
        "success": True,
        "task": {
            "id": task.id,
            "name": task.name,
            "schedule_type": task.schedule_type,
        }
    }


@app.put("/api/schedules/{task_id}")
async def update_schedule(task_id: int, request: Request, current_user=Depends(get_current_user)):
    """更新定时任务"""
    data = await request.json()
    
    task = await get_schedule_task_by_id(task_id, current_user.id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    success = await update_schedule_task(task_id, current_user.id, **data)
    
    # 更新调度器
    if success and data.get("enabled") is not None:
        if data["enabled"]:
            config = json.loads(task.schedule_config)
            trigger = get_cron_trigger(task.schedule_type, config)
            scheduler.add_job(
                run_scheduled_test,
                trigger=trigger,
                id=f"task_{task.id}",
                kwargs={
                    "task_id": task.id,
                    "user_id": current_user.id,
                    "subscription_id": task.subscription_id,
                    "test_streaming": task.test_streaming,
                    "theme": task.theme,
                },
                replace_existing=True
            )
        else:
            try:
                scheduler.remove_job(f"task_{task.id}")
            except Exception:
                pass
    
    return {"success": True, "message": "任务已更新"}


@app.delete("/api/schedules/{task_id}")
async def remove_schedule(task_id: int, current_user=Depends(get_current_user)):
    """删除定时任务"""
    success = await delete_schedule_task(task_id, current_user.id)
    if success:
        try:
            scheduler.remove_job(f"task_{task_id}")
        except Exception:
            pass
        return {"success": True, "message": "任务已删除"}
    raise HTTPException(status_code=404, detail="任务不存在")

# ========== 配置 API ==========

@app.get("/api/theme")
async def get_theme():
    return {"theme": state.theme}


@app.post("/api/theme")
async def set_theme(request: Request):
    data = await request.json()
    theme = data.get("theme", "dark")
    if theme in ["dark", "light"]:
        state.theme = theme
        return {"success": True, "theme": theme}
    return {"success": False, "error": "无效的主题"}


@app.get("/api/log-level")
async def get_log_level():
    return {"level": state.log_level, "levels": list(LOG_LEVELS.keys())}


@app.post("/api/log-level")
async def set_log_level(request: Request):
    data = await request.json()
    level = data.get("level", DEFAULT_LOG_LEVEL)
    if level in LOG_LEVELS:
        state.log_level = level
        return {"success": True, "level": level}
    return {"success": False, "error": "无效的日志等级"}

# ========== 主页 ==========

@app.get("/")
async def index():
    return FileResponse("frontend/index.html")

# ========== 测速核心逻辑 ==========

async def run_speed_test(result_id: int, test_streaming: bool = True):
    """执行测速"""
    try:
        state.progress["status"] = "running"
        state.progress["message"] = f"共 {len(state.nodes)} 个节点，开始测速..."
        
        # 启动 mihomo
        print(f"[SpeedTest] 开始启动 mihomo, 节点数: {len(state.nodes)}")
        started = await start_mihomo(state.nodes)
        if not started:
            state.progress["status"] = "error"
            state.progress["message"] = "mihomo 启动失败"
            print("[SpeedTest] mihomo 启动失败!")
            await update_test_result(result_id, status="failed")
            return
        
        # 获取当前端口
        from backend.utils.mihomo_manager import get_current_ports
        ports = get_current_ports()
        print(f"[SpeedTest] mihomo 启动成功! 端口: {ports}")
        
        # 逐个测试
        for idx, node in enumerate(state.nodes):
            if state.should_stop:
                break
            
            node_name = node["name"]
            state.progress["current_node"] = node_name
            state.progress["completed"] = idx
            state.progress["message"] = f"[{idx+1}/{len(state.nodes)}] 测试: {node_name}"
            print(f"[SpeedTest] 开始测试节点 {idx+1}/{len(state.nodes)}: {node_name}", flush=True)
            
            try:
                result = await test_node_speed(node_name, node)
                print(f"[SpeedTest] 节点 {node_name} 测试完成: speed_mb_per_sec={result.get('speed_mb_per_sec', 0)}", flush=True)
                
                if state.should_stop:
                    result["streaming"] = {}
                elif test_streaming:
                    state.progress["message"] = f"[{idx+1}/{len(state.nodes)}] 检测流媒体: {node_name}"
                    streaming = await check_all_streaming()
                    result["streaming"] = streaming
                else:
                    result["streaming"] = {}
                
                state.results.append(result)
                await add_node_result(result_id, result)
                await update_test_result(result_id, tested_nodes=idx + 1)
                
            except Exception as e:
                print(f"[SpeedTest] 节点 {node_name} 测试异常: {type(e).__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                error_result = {
                    "name": node_name,
                    "type": node.get("type", ""),
                    "server": node.get("server", ""),
                    "speed_mb_per_sec": 0,
                    "max_speed_mb_per_sec": 0,
                    "traffic_mb": 0,
                    "streaming": {},
                    "error": str(e),
                }
                state.results.append(error_result)
                await add_node_result(result_id, error_result)
        
        # 生成结果图片
        if state.results:
            state.progress["message"] = "正在生成结果图片..."
            image_filename = f"result_{result_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            image_path = str(RESULTS_DIR / image_filename)
            generate_result_image(state.results, output_path=image_path, theme=state.theme)
            
            total_traffic = sum(r.get("traffic_mb", 0) for r in state.results)
            
            if state.should_stop:
                status_val = "stopped"
            else:
                status_val = "completed"
            
            await update_test_result(
                result_id,
                status=status_val,
                image_path=f"results/{image_filename}",
                tested_nodes=len(state.results),
                total_traffic_mb=total_traffic,
                completed_at=datetime.utcnow()
            )
        
        state.progress["completed"] = len(state.results)
        if state.should_stop:
            state.progress["status"] = "stopped"
            state.progress["message"] = f"测速已停止! 已测试 {len(state.results)} 个节点"
        else:
            state.progress["status"] = "completed"
            state.progress["message"] = f"测速完成! 共测试 {len(state.results)} 个节点"
        
    except Exception as e:
        state.progress["status"] = "error"
        state.progress["message"] = f"测速出错: {str(e)}"
        await update_test_result(result_id, status="failed")
    finally:
        state.is_running = False
        await stop_mihomo()


# ========== 启动 ==========

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="warning",
        access_log=False
    )
