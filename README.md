# LLM Monitor

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

vLLM 实例监控系统，支持多实例、多模型的实时监控与数据可视化。

## 功能特性

- **多实例监控**: 支持同时监控多个 vLLM 实例
- **实时数据采集**: 每 10 秒自动采集一次监控数据（可配置）
- **模型维度聚合**: 按模型名称聚合展示集群指标
- **数据持久化**: Elasticsearch 存储，支持自定义数据保留时间
- **可视化面板**: 前端 Dashboard 实时展示监控指标
- **健康检查**: 提供应用和 Elasticsearch 连接状态检查
- **Docker 支持**: 提供完整的 Docker 部署方案

## 监控指标

### 性能指标
- Prompt 吞吐量 (tokens/s)
- 生成吞吐量 (tokens/s)
- TTFT (Time to First Token) - 首个 Token 延迟
- TPOT (Time Per Output Token) - 每个 Token 生成时间

### 资源指标
- 模型状态 (on/off)
- 运行中请求数
- 等待中请求数
- GPU KV Cache 使用率

### 缓存指标
- 前缀缓存命中率
- 外部前缀缓存命中率
- 多模态缓存命中率

## 快速开始

### 方式一: 本地开发环境

#### 1. 安装依赖

```bash
pip install -e .
```

或使用提供的启动脚本:

```bash
# Windows
start.bat

# Linux/Mac
chmod +x start.sh
./start.sh
```

#### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置:

```bash
cp .env.example .env
```

主要配置项:
| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ELASTICSEARCH_URL` | Elasticsearch 地址 | `http://10.1.246.236:9200` |
| `COLLECTION_INTERVAL` | 数据采集间隔(秒) | `10` |
| `RETENTION_DAYS` | 数据保留天数 | `30` |
| `DEBUG` | 调试模式 | `False` |

#### 3. 启动服务

```bash
uvicorn llm_monitor.main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后:
- **监控面板**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

### 方式二: Docker 部署

#### 1. 构建镜像

```bash
chmod +x image_build.sh
./image_build.sh
```

或手动构建:

```bash
docker build -t llm-monitor:latest .
```

#### 2. 使用 Docker Compose

```bash
docker-compose up -d
```

服务将在后台运行，访问地址同上。

## 使用说明

### 1. 配置 vLLM 实例

访问监控面板，点击"实例配置"页签:

1. 填写实例名称、IP 地址和端口
2. 点击"添加实例"
3. 启用监控

实例配置存储在 `config/instances.json` 文件中。

### 2. 查看监控数据

返回"监控面板"页签:

1. 选择要查看的模型
2. 查看实时监控指标和趋势图
3. 数据每 10 秒自动刷新

### 3. 无 Elasticsearch 模式

如果 Elasticsearch 不可用，系统将以有限功能模式启动:
- 实例管理功能正常
- 监控数据采集和持久化功能不可用
- 前端会显示 Elasticsearch 连接状态

## API 接口

### 实例管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/instances/` | 获取所有实例列表 |
| `POST` | `/api/v1/instances/` | 添加新实例 |
| `DELETE` | `/api/v1/instances/{id}` | 删除实例 |
| `POST` | `/api/v1/instances/{id}/toggle` | 启用/禁用监控 |

### 监控数据

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/vllm/models` | 获取所有模型列表 |
| `GET` | `/api/v1/vllm/models/{model}/aggregated` | 获取模型聚合数据 |
| `GET` | `/api/v1/vllm/models/{model}/metrics` | 获取模型原始数据 |
| `GET` | `/api/v1/vllm/aggregated` | 获取所有模型聚合数据 |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查（包含 ES 连接状态） |

### 追踪数据 (Trace)

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/traces/` | 创建追踪记录 |
| `GET` | `/api/v1/traces/{trace_id}` | 获取追踪详情 |

### 指标汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/metrics/summary` | 获取指标汇总 |
| `GET` | `/api/v1/metrics/by-model` | 按模型分组获取指标 |

## 项目结构

```
llm-monitor/
├── config/
│   └── instances.json            # 实例配置文件
├── llm_monitor/
│   ├── api/
│   │   └── endpoints/
│   │       ├── instances.py      # 实例管理接口
│   │       ├── vllm_metrics.py   # vLLM 监控数据接口
│   │       ├── metrics.py        # 指标汇总接口
│   │       └── traces.py         # 追踪数据接口
│   ├── core/
│   │   └── config.py             # 配置管理
│   ├── models/
│   │   └── vllm.py               # vLLM 数据模型
│   ├── services/
│   │   ├── vllm_collector.py     # 数据采集服务
│   │   └── metrics_query.py      # 数据查询服务
│   ├── static/
│   │   └── index.html            # 前端监控面板
│   └── main.py                   # 应用入口
├── tests/                        # 测试目录
├── docker-compose.yml            # Docker Compose 配置
├── Dockerfile                    # Docker 镜像构建
├── pyproject.toml                # 项目配置
├── requirements.txt              # 依赖列表
├── start.bat / start.sh          # 启动脚本
└── README.md
```

## 技术栈

- **Web 框架**: FastAPI 0.109+
- **异步服务**: Uvicorn
- **数据验证**: Pydantic 2.5+
- **HTTP 客户端**: httpx
- **数据存储**: Elasticsearch 8.x
- **任务调度**: APScheduler
- **Python 版本**: 3.10+

## 数据存储

使用 Elasticsearch 存储，自动创建 ILM (索引生命周期管理) 策略:

### 索引配置

- **索引模式**: `vllm-metrics-*`
- **Rollover 策略**: 7天或 50GB
- **数据保留**: 30天自动删除（可通过环境变量配置）

### 数据结构

每条监控记录包含:
- 时间戳
- 实例信息 (名称、地址、模型)
- 性能指标 (吞吐量、延迟等)
- 资源指标 (请求数、缓存使用率等)

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码检查

```bash
# Ruff 格式化和检查
ruff check llm_monitor/
ruff format llm_monitor/

# 类型检查
mypy llm_monitor/
```

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

## 常见问题

### 1. Elasticsearch 连接失败

**现象**: 启动时提示 "Elasticsearch not available"

**解决方案**:
- 检查 Elasticsearch 是否运行: `curl http://your-es-host:9200`
- 确认环境变量 `ELASTICSEARCH_URL` 配置正确
- 检查网络连接和防火墙设置

### 2. 监控数据未采集

**现象**: 前端显示无数据

**解决方案**:
- 确认已添加 vLLM 实例并启用监控
- 检查实例是否可访问: `curl http://vllm-host:port/health`
- 查看应用日志确认采集任务是否运行

### 3. 前端无法访问

**现象**: 浏览器无法打开监控面板

**解决方案**:
- 确认服务启动参数包含 `--host 0.0.0.0`
- 检查端口是否被占用
- 查看浏览器控制台是否有错误信息

## 更新日志

### v0.1.0 (当前版本)
- 多实例 vLLM 监控
- 实时数据采集和可视化
- Elasticsearch 数据持久化
- Docker 部署支持
- 健康检查接口
- 无 ES 模式支持

## 贡献

欢迎提交 Issue 和 Pull Request！

## License

MIT License - 详见 [LICENSE](LICENSE) 文件
