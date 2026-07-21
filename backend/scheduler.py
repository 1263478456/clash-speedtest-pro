"""
定时任务调度器
"""
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.database import (
    get_enabled_schedule_tasks, get_subscription_by_id,
    create_test_result, update_test_result, add_node_result,
    update_task_last_run
)
from backend.utils.subscription import get_nodes_from_subscription
from backend.utils.mihomo_manager import start_mihomo, stop_mihomo, switch_node
from backend.utils.speedtest import test_node_speed
from backend.utils.streaming import check_all_streaming
from backend.utils.image_gen import generate_result_image

# 全局调度器
scheduler = AsyncIOScheduler()

# 任务状态
running_tasks: Dict[int, bool] = {}


async def run_scheduled_test(task_id: int, user_id: int, subscription_id: int,
                             test_streaming: bool = True, theme: str = "dark"):
    """执行定时测速任务"""
    # 防止重复运行
    if task_id in running_tasks and running_tasks[task_id]:
        print(f"[Scheduler] 任务 {task_id} 正在运行，跳过")
        return
    
    running_tasks[task_id] = True
    
    try:
        # 获取订阅
        sub = await get_subscription_by_id(subscription_id, user_id)
        if not sub:
            print(f"[Scheduler] 订阅 {subscription_id} 不存在")
            return
        
        print(f"[Scheduler] 开始执行任务: {sub.name}")
        
        # 拉取订阅节点
        nodes = await get_nodes_from_subscription(sub.url)
        if not nodes:
            print(f"[Scheduler] 未获取到节点")
            return
        
        # 创建测速结果记录
        test_result = await create_test_result(
            user_id=user_id,
            subscription_name=sub.name,
            total_nodes=len(nodes),
            theme=theme,
            task_id=task_id
        )
        
        # 启动 mihomo
        started = await start_mihomo(nodes)
        if not started:
            await update_test_result(test_result.id, status="failed")
            print(f"[Scheduler] mihomo 启动失败")
            return
        
        # 逐个测试节点
        for idx, node in enumerate(nodes):
            print(f"[Scheduler] [{idx+1}/{len(nodes)}] 测试: {node['name']}")
            
            try:
                result = await test_node_speed(node["name"], node)
                
                if test_streaming:
                    streaming = await check_all_streaming()
                    result["streaming"] = streaming
                else:
                    result["streaming"] = {}
                
                await add_node_result(test_result.id, result)
                await update_test_result(test_result.id, tested_nodes=idx + 1)
                
            except Exception as e:
                print(f"[Scheduler] 节点测试失败: {e}")
                await add_node_result(test_result.id, {
                    "name": node["name"],
                    "type": node.get("type", ""),
                    "server": node.get("server", ""),
                    "error": str(e),
                    "streaming": {}
                })
        
        # 生成结果图片
        from backend.database import get_node_results
        node_results = await get_node_results(test_result.id)
        
        results_for_image = []
        for nr in node_results:
            results_for_image.append({
                "name": nr.node_name,
                "type": nr.node_type,
                "server": nr.server,
                "port": nr.port,
                "speed_mb_per_sec": nr.speed_mb_per_sec,
                "max_speed_mb_per_sec": nr.max_speed_mb_per_sec,
                "traffic_mb": nr.traffic_mb,
                "tcp_ping": nr.tcp_ping,
                "tls_rtt": nr.tls_rtt,
                "https_ping": nr.https_ping,
                "streaming": {
                    "Netflix": nr.netflix or "-",
                    "YouTube": nr.youtube or "-",
                    "Bilibili": nr.bilibili or "-",
                    "Disney+": nr.disney_plus or "-",
                    "TikTok": nr.tiktok or "-",
                    "ChatGPT": nr.chatgpt or "-",
                    "Spotify": nr.spotify or "-",
                    "Steam": nr.steam or "-",
                }
            })
        
        if results_for_image:
            image_filename = f"result_{test_result.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            image_path = f"results/{image_filename}"
            generate_result_image(results_for_image, output_path=image_path, theme=theme)
            
            total_traffic = sum(r.get("traffic_mb", 0) for r in results_for_image)
            await update_test_result(
                test_result.id,
                status="completed",
                image_path=image_path,
                tested_nodes=len(nodes),
                total_traffic_mb=total_traffic,
                completed_at=datetime.utcnow()
            )
        
        await update_task_last_run(task_id)
        print(f"[Scheduler] 任务完成: {sub.name}")
        
    except Exception as e:
        print(f"[Scheduler] 任务执行失败: {e}")
        if 'test_result' in locals():
            await update_test_result(test_result.id, status="failed")
    finally:
        await stop_mihomo()
        running_tasks[task_id] = False


def get_cron_trigger(schedule_type: str, schedule_config: dict) -> CronTrigger:
    """根据配置创建 Cron 触发器"""
    if schedule_type == "daily":
        return CronTrigger(
            hour=schedule_config.get("hour", 0),
            minute=schedule_config.get("minute", 0)
        )
    elif schedule_type == "weekly":
        return CronTrigger(
            day_of_week=schedule_config.get("weekday", 0),
            hour=schedule_config.get("hour", 0),
            minute=schedule_config.get("minute", 0)
        )
    elif schedule_type == "monthly":
        return CronTrigger(
            day=schedule_config.get("day", 1),
            hour=schedule_config.get("hour", 0),
            minute=schedule_config.get("minute", 0)
        )
    elif schedule_type == "cron":
        return CronTrigger(
            hour=schedule_config.get("hour", "*"),
            minute=schedule_config.get("minute", "*"),
            day_of_week=schedule_config.get("weekday", "*"),
            day=schedule_config.get("day", "*"),
            month=schedule_config.get("month", "*")
        )
    else:
        return CronTrigger(hour=0, minute=0)


async def load_scheduled_tasks():
    """加载所有定时任务"""
    tasks = await get_enabled_schedule_tasks()
    for task in tasks:
        try:
            import json
            config = json.loads(task.schedule_config)
            trigger = get_cron_trigger(task.schedule_type, config)
            
            scheduler.add_job(
                run_scheduled_test,
                trigger=trigger,
                id=f"task_{task.id}",
                kwargs={
                    "task_id": task.id,
                    "user_id": task.user_id,
                    "subscription_id": task.subscription_id,
                    "test_streaming": task.test_streaming,
                    "theme": task.theme,
                },
                replace_existing=True
            )
            print(f"[Scheduler] 加载任务: {task.name} ({task.schedule_type})")
        except Exception as e:
            print(f"[Scheduler] 加载任务失败: {task.name} - {e}")


def start_scheduler():
    """启动调度器"""
    if not scheduler.running:
        scheduler.start()
        print("[Scheduler] 调度器已启动")


def stop_scheduler():
    """停止调度器"""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] 调度器已停止")
