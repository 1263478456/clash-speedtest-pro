"""
数据库操作
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update, delete
from passlib.context import CryptContext

from config import DATABASE_URL
from backend.models import Base, User, Subscription, TestResult, NodeResult, ScheduleTask

# 创建异步引擎
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 检查是否有默认用户，如果没有则创建
    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if not result.scalar():
            default_user = User(
                username="admin",
                password_hash=pwd_context.hash("admin123")
            )
            session.add(default_user)
            await session.commit()
            print("[DB] 创建默认用户: admin / admin123")


async def get_user_by_username(username: str) -> Optional[User]:
    """根据用户名获取用户"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


async def create_user(username: str, password: str) -> User:
    """创建用户"""
    async with async_session() as session:
        user = User(
            username=username,
            password_hash=pwd_context.hash(password)
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def update_user_password(user_id: int, new_password: str) -> bool:
    """更新用户密码"""
    async with async_session() as session:
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=pwd_context.hash(new_password), updated_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount > 0


async def update_username(user_id: int, new_username: str) -> bool:
    """更新用户名"""
    async with async_session() as session:
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(username=new_username, updated_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount > 0


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


# ========== 订阅管理 ==========

async def create_subscription(user_id: int, name: str, url: str, node_count: int = 0) -> Subscription:
    """创建订阅"""
    async with async_session() as session:
        sub = Subscription(
            user_id=user_id,
            name=name,
            url=url,
            node_count=node_count
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


async def get_subscriptions(user_id: int) -> List[Subscription]:
    """获取用户的所有订阅"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())


async def get_subscription_by_id(sub_id: int, user_id: int) -> Optional[Subscription]:
    """根据 ID 获取订阅"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.id == sub_id, Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def delete_subscription(sub_id: int, user_id: int) -> bool:
    """删除订阅"""
    async with async_session() as session:
        result = await session.execute(
            delete(Subscription)
            .where(Subscription.id == sub_id, Subscription.user_id == user_id)
        )
        await session.commit()
        return result.rowcount > 0


async def update_subscription_usage(sub_id: int):
    """更新订阅最后使用时间"""
    async with async_session() as session:
        result = await session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(last_used_at=datetime.utcnow())
        )
        await session.commit()


async def update_subscription(sub_id: int, user_id: int, name: str = None, url: str = None, node_count: int = None) -> bool:
    """更新订阅信息"""
    async with async_session() as session:
        # 先查询订阅是否存在
        result = await session.execute(
            select(Subscription)
            .where(Subscription.id == sub_id, Subscription.user_id == user_id)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return False
        
        # 更新字段
        if name is not None:
            sub.name = name
        if url is not None:
            sub.url = url
        if node_count is not None:
            sub.node_count = node_count
        sub.updated_at = datetime.utcnow()
        
        await session.commit()
        return True


async def mark_running_as_stopped():
    """将所有运行中的任务标记为已停止（用于应用重启后清理）"""
    async with async_session() as session:
        result = await session.execute(
            update(TestResult)
            .where(TestResult.status == "running")
            .values(status="stopped", completed_at=datetime.utcnow())
        )
        await session.commit()
        if result.rowcount > 0:
            print(f"[DB] 已将 {result.rowcount} 个运行中的任务标记为已停止")


async def update_subscription(sub_id: int, user_id: int, name: str = None, url: str = None, node_count: int = None) -> bool:
    """更新订阅信息"""
    async with async_session() as session:
        values = {}
        if name is not None:
            values["name"] = name
        if url is not None:
            values["url"] = url
        if node_count is not None:
            values["node_count"] = node_count
        
        if not values:
            return False
        
        result = await session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id, Subscription.user_id == user_id)
            .values(**values)
        )
        await session.commit()
        return result.rowcount > 0


# ========== 测速结果管理 ==========

async def create_test_result(user_id: int, subscription_name: str, total_nodes: int, theme: str = "dark", task_id: int = None) -> TestResult:
    """创建测速结果"""
    async with async_session() as session:
        result = TestResult(
            user_id=user_id,
            task_id=task_id,
            subscription_name=subscription_name,
            total_nodes=total_nodes,
            theme=theme,
            status="running"
        )
        session.add(result)
        await session.commit()
        await session.refresh(result)
        return result


async def update_test_result(result_id: int, **kwargs) -> bool:
    """更新测速结果"""
    async with async_session() as session:
        result = await session.execute(
            update(TestResult)
            .where(TestResult.id == result_id)
            .values(**kwargs)
        )
        await session.commit()
        return result.rowcount > 0


async def add_node_result(test_result_id: int, node_data: dict) -> NodeResult:
    """添加节点测速结果"""
    async with async_session() as session:
        node = NodeResult(
            test_result_id=test_result_id,
            node_name=node_data.get("name", ""),
            node_type=node_data.get("type", ""),
            server=node_data.get("server", ""),
            port=node_data.get("port", 0),
            speed_mb_per_sec=node_data.get("speed_mb_per_sec", 0),
            max_speed_mb_per_sec=node_data.get("max_speed_mb_per_sec", 0),
            traffic_mb=node_data.get("traffic_mb", 0),
            tcp_ping=node_data.get("tcp_ping"),
            tls_rtt=node_data.get("tls_rtt"),
            https_ping=node_data.get("https_ping"),
            netflix=node_data.get("streaming", {}).get("Netflix"),
            youtube=node_data.get("streaming", {}).get("YouTube"),
            bilibili=node_data.get("streaming", {}).get("Bilibili"),
            disney_plus=node_data.get("streaming", {}).get("Disney+"),
            tiktok=node_data.get("streaming", {}).get("TikTok"),
            chatgpt=node_data.get("streaming", {}).get("ChatGPT"),
            spotify=node_data.get("streaming", {}).get("Spotify"),
            steam=node_data.get("streaming", {}).get("Steam"),
            error=node_data.get("error"),
        )
        session.add(node)
        await session.commit()
        await session.refresh(node)
        return node


async def get_test_results(user_id: int, limit: int = 50) -> List[TestResult]:
    """获取用户的测速结果列表"""
    async with async_session() as session:
        result = await session.execute(
            select(TestResult)
            .where(TestResult.user_id == user_id)
            .order_by(TestResult.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_test_result_by_id(result_id: int, user_id: int) -> Optional[TestResult]:
    """根据 ID 获取测速结果详情"""
    async with async_session() as session:
        result = await session.execute(
            select(TestResult)
            .where(TestResult.id == result_id, TestResult.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def get_node_results(test_result_id: int) -> List[NodeResult]:
    """获取测速结果的所有节点"""
    async with async_session() as session:
        result = await session.execute(
            select(NodeResult)
            .where(NodeResult.test_result_id == test_result_id)
        )
        return list(result.scalars().all())


async def delete_test_result(result_id: int, user_id: int) -> bool:
    """删除测速结果"""
    async with async_session() as session:
        result = await session.execute(
            delete(TestResult)
            .where(TestResult.id == result_id, TestResult.user_id == user_id)
        )
        await session.commit()
        return result.rowcount > 0


# ========== 定时任务管理 ==========

async def create_schedule_task(user_id: int, name: str, subscription_id: int, 
                               schedule_type: str, schedule_config: dict,
                               test_streaming: bool = True, theme: str = "dark") -> ScheduleTask:
    """创建定时任务"""
    import json
    async with async_session() as session:
        task = ScheduleTask(
            user_id=user_id,
            name=name,
            subscription_id=subscription_id,
            schedule_type=schedule_type,
            schedule_config=json.dumps(schedule_config),
            test_streaming=test_streaming,
            theme=theme,
            enabled=True
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


async def get_schedule_tasks(user_id: int) -> List[ScheduleTask]:
    """获取用户的所有定时任务"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleTask)
            .where(ScheduleTask.user_id == user_id)
            .order_by(ScheduleTask.created_at.desc())
        )
        return list(result.scalars().all())


async def get_enabled_schedule_tasks() -> List[ScheduleTask]:
    """获取所有启用的定时任务"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleTask)
            .where(ScheduleTask.enabled == True)
        )
        return list(result.scalars().all())


async def get_schedule_task_by_id(task_id: int, user_id: int) -> Optional[ScheduleTask]:
    """根据 ID 获取定时任务"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleTask)
            .where(ScheduleTask.id == task_id, ScheduleTask.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def update_schedule_task(task_id: int, user_id: int, **kwargs) -> bool:
    """更新定时任务"""
    async with async_session() as session:
        result = await session.execute(
            update(ScheduleTask)
            .where(ScheduleTask.id == task_id, ScheduleTask.user_id == user_id)
            .values(**kwargs)
        )
        await session.commit()
        return result.rowcount > 0


async def delete_schedule_task(task_id: int, user_id: int) -> bool:
    """删除定时任务"""
    async with async_session() as session:
        result = await session.execute(
            delete(ScheduleTask)
            .where(ScheduleTask.id == task_id, ScheduleTask.user_id == user_id)
        )
        await session.commit()
        return result.rowcount > 0


async def update_task_last_run(task_id: int):
    """更新任务最后运行时间"""
    async with async_session() as session:
        result = await session.execute(
            update(ScheduleTask)
            .where(ScheduleTask.id == task_id)
            .values(last_run_at=datetime.utcnow())
        )
        await session.commit()
