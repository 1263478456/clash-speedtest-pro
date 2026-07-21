"""
数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("ScheduleTask", back_populates="user", cascade="all, delete-orphan")
    results = relationship("TestResult", back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    """订阅链接表"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    url = Column(Text, nullable=False)
    node_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="subscriptions")


class TestResult(Base):
    """测速结果表"""
    __tablename__ = "test_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("schedule_tasks.id"), nullable=True)
    subscription_name = Column(String(100), nullable=True)
    total_nodes = Column(Integer, default=0)
    tested_nodes = Column(Integer, default=0)
    total_traffic_mb = Column(Float, default=0)
    image_path = Column(String(255), nullable=True)
    theme = Column(String(10), default="dark")
    status = Column(String(20), default="running")  # running, completed, failed, stopped
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="results")
    task = relationship("ScheduleTask", back_populates="results")
    nodes = relationship("NodeResult", back_populates="test_result", cascade="all, delete-orphan")


class NodeResult(Base):
    """节点测速结果表"""
    __tablename__ = "node_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_result_id = Column(Integer, ForeignKey("test_results.id"), nullable=False)
    node_name = Column(String(200), nullable=False)
    node_type = Column(String(20), nullable=True)
    server = Column(String(200), nullable=True)
    port = Column(Integer, nullable=True)
    speed_mb_per_sec = Column(Float, default=0)
    upload_speed_mb_per_sec = Column(Float, default=0)
    max_speed_mb_per_sec = Column(Float, default=0)
    traffic_mb = Column(Float, default=0)
    tcp_ping = Column(Float, nullable=True)
    tls_rtt = Column(Float, nullable=True)
    https_ping = Column(Float, nullable=True)
    netflix = Column(String(50), nullable=True)
    youtube = Column(String(50), nullable=True)
    bilibili = Column(String(50), nullable=True)
    disney_plus = Column(String(50), nullable=True)
    tiktok = Column(String(50), nullable=True)
    chatgpt = Column(String(50), nullable=True)
    spotify = Column(String(50), nullable=True)
    steam = Column(String(50), nullable=True)
    error = Column(Text, nullable=True)
    
    test_result = relationship("TestResult", back_populates="nodes")


class ScheduleTask(Base):
    """定时任务表"""
    __tablename__ = "schedule_tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    schedule_type = Column(String(20), nullable=False)  # daily, weekly, monthly, cron
    schedule_config = Column(Text, nullable=False)  # JSON: {"hour": 3, "minute": 0, "weekday": 1, ...}
    test_streaming = Column(Boolean, default=True)
    theme = Column(String(10), default="dark")
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="tasks")
    subscription = relationship("Subscription")
    results = relationship("TestResult", back_populates="task")
