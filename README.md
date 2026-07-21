# ClashSpeedTest Pro

代理节点速度测试工具，支持多种代理协议，提供 WebUI 界面。

## 功能特性

- 🚀 支持多种代理协议：SS、VMess、VLESS、Trojan、SSR、AnyTLS、Hysteria
- 📊 实时测速结果展示
- 🔍 流媒体解锁检测（Netflix、YouTube、ChatGPT 等）
- 📸 测速结果图片生成
- ⏰ 定时测速任务
- 🌓 深色/浅色主题切换
- 🔐 用户认证系统

## 快速开始

### Docker 部署

```bash
docker run -d \
  -p 8080:8080 \
  -v /path/to/data:/app/data \
  -v /path/to/results:/app/results \
  -e SECRET_KEY=your-secret-key \
  --name speedtest \
  1263478456/clash-speedtest-pro:latest
```

### Docker Compose

```yaml
version: '3.8'
services:
  speedtest:
    image: 1263478456/clash-speedtest-pro:latest
    container_name: speedtest
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
      - ./results:/app/results
    environment:
      - SECRET_KEY=your-secret-key
      - TZ=Asia/Shanghai
    restart: unless-stopped
```

### 从 ghcr.io 拉取

```bash
docker pull ghcr.io/1263478456/clash-speedtest-pro:latest
```

## 默认账户

- 用户名：`admin`
- 密码：`admin123`

**请在首次登录后立即修改密码！**

## 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| SECRET_KEY | JWT 密钥 | your-secret-key-change-this |
| WEB_PORT | Web 端口 | 8080 |
| WEB_HOST | 监听地址 | 0.0.0.0 |

## 技术栈

- **后端**：Python FastAPI
- **代理核心**：mihomo (Clash Meta)
- **前端**：原生 HTML/CSS/JS
- **数据库**：SQLite

## 项目结构

```
clash-speedtest-pro/
├── app.py              # 主应用
├── config.py           # 配置文件
├── requirements.txt    # Python 依赖
├── Dockerfile          # Docker 构建文件
├── backend/
│   ├── models.py       # 数据模型
│   ├── database.py     # 数据库操作
│   ├── auth.py         # 认证模块
│   ├── scheduler.py    # 定时任务
│   └── utils/
│       ├── subscription.py    # 订阅解析
│       ├── mihomo_manager.py  # mihomo 管理
│       ├── speedtest.py       # 测速逻辑
│       ├── streaming.py       # 流媒体检测
│       └── image_gen.py       # 图片生成
└── frontend/
    ├── index.html      # 主页面
    ├── js/app.js       # 前端逻辑
    └── css/style.css   # 样式
```

## License

MIT License
