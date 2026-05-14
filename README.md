# Cloud Agent - 智能云客服系统

<div align="center">

**基于 LangGraph 的多 Agent 编排 · RAG 知识检索 · MCP 工具集成 · 实时流式对话**

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.x-brightgreen.svg)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Latest-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📖 项目简介

Cloud Agent 是一个面向云服务咨询、账单查询、资源优化和营销推广的**多 Agent 智能客服系统**。系统采用分层架构设计，结合大语言模型（LLM）、检索增强生成（RAG）、知识图谱（Knowledge Graph）和 Model Context Protocol（MCP），为用户提供智能化的云服务支持。

### ✨ 核心特性

- **🤖 多 Agent 协同**：基于 LangGraph 的状态图编排，5 个专业 Agent 分工协作
- **🧠 双层记忆系统**：Redis 短期会话 + Milvus 长期偏好，支持会话摘要压缩
- **📚 混合知识检索**：Milvus 向量 RAG + Neo4j 知识图谱，精准回答产品问题
- **🔧 MCP 工具集成**：标准化接入订单查询、实例监控、促销物料等外部能力
- **💰 FinOps 降本建议**：分析用户资源使用情况，提供智能化优化方案
- **🎨 AI 海报生成**：调用 DashScope 文生图接口，自动生成营销推广物料
- **⚡ 语义缓存加速**：网关层 Milvus 问答缓存，减少重复 LLM 调用
- **🌊 实时流式响应**：SSE 协议分片返回，前端即时渲染 Markdown

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    front/cloud_agent                         │
│              Vue 3 + Vite + Element Plus                     │
│                  (实时流式聊天界面)                           │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP POST /api/chat (SSE)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                        app/                                  │
│                 FastAPI API Gateway                          │
│  • SSE 流式响应  • 语义缓存  • 记忆上下文注入                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      agent/                                  │
│              LangGraph StateGraph Orchestration              │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ OrchestratorAgent │ ← 意图识别与路由决策                  │
│  └────┬─────┬───────┼──────────┬──────────┐                │
│       │     │       │          │          │                 │
│       ▼     ▼       ▼          ▼          ▼                 │
│  ┌────────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌────────┐       │
│  │Product │ │Billing│ │Recomm│ │Promotn │ │ FinOps │       │
│  │ Agent  │ │ Agent │ │ation │ │ Agent  │ │ Agent  │       │
│  └───┬────┘ └──┬───┘ └──┬───┘ └───┬────┘ └───┬────┘       │
│      │         │        │         │          │              │
│      ▼         ▼        ▼         ▼          ▼              │
│  ┌────────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌────────┐       │
│  │Milvus  │ │ MySQL│ │MCP   │ │DashScope│ │ MySQL  │       │
│  │ RAG    │ │ MCP  │ │Tools │ │Image   │ │ Monitor│       │
│  └────────┘ └──────┘ └──────┘ └────────┘ └────────┘       │
│                                                             │
│  ┌──────────────────────────────────────────────┐          │
│  │         Memory System (Redis + Milvus)       │          │
│  │  Short-term: Session History (TTL 30min)     │          │
│  │  Long-term:  User Preferences & Facts        │          │
│  └──────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘

External Dependencies:
  • DashScope LLM (qwen-plus / qwen-turbo)
  • Redis (Short-term Memory)
  • Milvus (Vector DB + Semantic Cache + Long-term Memory)
  • Neo4j (Knowledge Graph)
  • MySQL (User Orders, Instances, Monitoring Data)
```

---

## 🛠️ 技术栈

| 模块 | 技术选型 |
|------|---------|
| **Agent 编排** | LangGraph、LangChain、LangChain MCP Adapters |
| **大语言模型** | DashScope (通义千问 qwen-plus / qwen-turbo) |
| **向量嵌入** | DashScope text-embedding-v2 (1536 维) |
| **API 服务** | FastAPI、StreamingResponse (SSE) |
| **工具协议** | Model Context Protocol (MCP) / FastMCP |
| **向量数据库** | Milvus v2.3+ (IVF_FLAT, COSINE) |
| **知识图谱** | Neo4j v5.18+ (Cypher Query) |
| **缓存与会话** | Redis v7+ (List + String, TTL 1800s) |
| **关系数据库** | MySQL 8.0+ (DBUtils Connection Pool) |
| **前端框架** | Vue 3、TypeScript、Vite、Element Plus |
| **Markdown 渲染** | marked.js |
| **测试框架** | Python unittest |

---

## 📂 目录结构

```
cloud_agent/
├── agent/                         # Agent 核心代码
│   ├── agents/                    # 业务 Agent 实现
│   │   ├── orchestrator.py        # 中心路由 Agent (意图识别)
│   │   ├── product_agent.py       # 产品咨询 Agent (RAG + KG)
│   │   ├── billing_agent.py       # 账单查询 Agent (MCP + MySQL)
│   │   ├── recommendation_agent.py # 产品选型推荐 Agent
│   │   ├── promotion_agent.py     # 营销推广 Agent (海报生成)
│   │   ├── finops_agent.py        # FinOps 降本建议 Agent
│   │   └── mcp_client_cache.py    # MCP 客户端懒加载与缓存
│   ├── config/                    # 配置管理
│   │   ├── settings.py            # Pydantic Settings (环境变量)
│   │   └── mcp_servers.json       # MCP Server 配置文件
│   ├── core/                      # 核心基础设施
│   │   ├── graph/                 # 知识图谱解析与写入
│   │   │   ├── parser.py          # LLM 驱动的实体抽取
│   │   │   ├── ingestor.py        # 批量数据导入 Neo4j
│   │   │   └── client.py          # Neo4j 连接管理
│   │   ├── mcp/                   # MCP 管理器
│   │   │   └── mcp_manager.py     # MCP Server 生命周期管理
│   │   ├── memory/                # 双层记忆系统
│   │   │   ├── short_term.py      # Redis 短期会话 (Lua 原子操作)
│   │   │   ├── long_term.py       # Milvus 长期偏好 (向量检索)
│   │   │   ├── preference_extractor.py # 偏好提取器
│   │   │   └── memory_manager.py  # 记忆系统统一入口
│   │   ├── resilience/            # 韧性层 (容错与观测)
│   │   │   ├── result.py          # 统一工具结果结构
│   │   │   ├── retry.py           # 智能重试 (指数退避)
│   │   │   ├── observer.py        # 结构化事件日志
│   │   │   └── models.py          # 错误码定义
│   │   └── workflow/              # LangGraph 工作流
│   │       ├── state.py           # AgentState 定义
│   │       └── graph_manager.py   # StateGraph 构建与编译
│   ├── database/                  # 数据库初始化脚本
│   │   └── init_mock_data.sql     # MySQL 模拟数据
│   ├── mcp_servers/               # FastMCP 工具服务
│   │   └── cloud_platform_server.py # 云平台 MCP Server
│   ├── tools/                     # 本地工具封装
│   │   ├── vector_tool.py         # Milvus 向量检索工具
│   │   └── graph_tool.py          # Neo4j 图谱查询工具
│   ├── test/                      # 测试与检查脚本
│   │   ├── milvus_rag.py          # 构建向量知识库
│   │   ├── build_kg.py            # 构建知识图谱
│   │   ├── validate_tool_results.py # 工具返回格式验证
│   │   └── *_check.py             # 组件健康检查
│   ├── main.py                    # CLI 调试入口
│   ├── requirements.txt           # Python 依赖清单
│   └── .env.example               # 环境变量模板
├── app/                           # FastAPI 网关层
│   ├── app_config/                # API 层配置
│   │   └── settings.py            # API Settings
│   ├── infra/                     # 基础设施
│   │   └── cache.py               # Milvus 语义缓存
│   ├── router/                    # HTTP 路由
│   │   └── chat.py                # /api/chat 端点
│   ├── schemas/                   # Pydantic 数据模型
│   │   └── chat.py                # ChatRequest / ChatResponse
│   ├── service/                   # 业务逻辑
│   │   └── chat_service.py        # 流式聊天服务
│   ├── app_main.py                # FastAPI 应用入口
│   └── preload_cache.py           # 缓存预热脚本
├── front/cloud_agent/             # Vue 3 前端
│   ├── src/
│   │   ├── App.vue                # 主应用组件
│   │   ├── components/            # UI 组件
│   │   └── assets/                # 静态资源
│   ├── package.json               # Node.js 依赖
│   └── vite.config.ts             # Vite 配置
├── mock_data/                     # 模拟知识数据
│   ├── ecs_product_info.md        # ECS 产品信息
│   ├── rds_product_info.md        # RDS 产品信息
│   ├── billing_and_refund_policy.md # 账单与退款政策
│   └── ...                        # 其他领域文档
├── docs/                          # 项目文档
│   ├── tool_result_format_refactoring.md # 工具格式改造记录
│   └── project_optimization.md    # 项目优化指南
├── pyproject.toml                 # 项目元信息
├── .gitignore                     # Git 忽略规则
└── README.md                      # 本文件
```

---

## 🚀 快速开始

### 环境要求

- **Python**: 3.13+
- **Node.js**: ^20.19.0 或 >=22.12.0
- **npm**: 最新稳定版
- **Docker**: (可选) 用于快速部署基础服务

### 1️⃣ 克隆项目

```bash
git clone https://github.com/your-username/cloud_agent.git
cd cloud_agent
```

### 2️⃣ 配置环境变量

复制环境变量模板并填写配置：

```bash
cp agent/.env.example agent/.env
```

编辑 `agent/.env`：

```env
# === LLM 配置 ===
DASHSCOPE_API_KEY=sk-your-api-key-here
MODEL=qwen-plus
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MEMORY_SUMMARY_MODEL=qwen-turbo
PREFERENCE_EXTRACT_MODEL=qwen-turbo

# === Redis (短期记忆) ===
REDIS_URL=redis://localhost:6379
REDIS_TTL=1800

# === Milvus (向量数据库 + 长期记忆 + 语义缓存) ===
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_API_KEY=

# === Neo4j (知识图谱) ===
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
NEO4J_DATABASE=neo4j

# === MySQL (用户数据) ===
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=cloud_platform
MYSQL_CHARSET=utf8mb4
MYSQL_POOL_MINCACHED=1
MYSQL_POOL_MAXCACHED=5
MYSQL_POOL_MAXCONNECTIONS=10
MYSQL_POOL_BLOCKING=true

# === 日志级别 ===
LOG_LEVEL=INFO
```

> ⚠️ **重要**：不要将 `.env` 文件提交到 Git！已在 `.gitignore` 中排除。

### 3️⃣ 安装 Python 依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 安装依赖
pip install -r agent/requirements.txt
```

### 4️⃣ 启动基础服务

#### 方式 A：使用 Docker（推荐）

```bash
# 启动 Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 启动 Milvus Standalone
docker run -d \
  --name milvus-standalone \
  -p 19530:19530 \
  -p 9091:9091 \
  -p 8080:8080 \
  milvusdb/milvus:v2.3.0 \
  milvus run standalone

# 启动 Neo4j
docker run -d \
  --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:5.18.0

# 启动 MySQL
docker run -d \
  --name mysql \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=your-mysql-password \
  -e MYSQL_DATABASE=cloud_platform \
  mysql:8.0
```

#### 方式 B：使用本地服务

确保以下服务已启动并在默认端口监听：
- Redis: `localhost:6379`
- Milvus: `localhost:19530`
- Neo4j Bolt: `bolt://localhost:7687`
- MySQL: `localhost:3306`

### 5️⃣ 初始化数据库

#### MySQL 模拟数据

```bash
mysql -h localhost -P 3306 -u root -p cloud_platform < agent/database/init_mock_data.sql
```

#### Milvus 向量知识库

```bash
cd agent/test
python milvus_rag.py
```

这会读取 `mock_data/` 下的 Markdown 文档，生成向量嵌入并存入 Milvus。

#### Neo4j 知识图谱

```bash
python build_kg.py
```

这会使用 LLM 从文档中抽取实体和关系，构建云产品知识图谱。

### 6️⃣ 启动后端服务

```bash
cd app
uvicorn app_main:app --host 0.0.0.0 --port 5000 --reload
```

后端将在 `http://localhost:5000` 启动。

**API 端点**：
- `POST /api/chat` - 流式聊天接口（SSE）

**请求示例**：
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "帮我查一下最近的订单记录",
    "user_id": "user_1001",
    "session_id": "session_default_1"
  }'
```

### 7️⃣ 启动前端服务

```bash
cd front/cloud_agent
npm install
npm run dev
```

前端将在 `http://localhost:5173` 启动。

打开浏览器访问该地址，即可开始与 Cloud Agent 对话！

---

## 💻 CLI 调试模式

如果不使用前端，可以直接通过命令行与 Agent 交互：

```bash
cd agent

# 交互模式
python main.py

# 单次查询模式
python main.py --query "什么是 ECS？" --user user_1001 --session session_demo

# 启用 DEBUG 日志
python main.py --debug --query "华北2有哪些可用区？"
```

**CLI 功能**：
- ✅ 自动加载短期/长期记忆
- ✅ 显示路由决策过程
- ✅ 输出完整的 Agent 思考链
- ✅ 每 5 轮对话自动提取长期偏好

---

## 🔧 MCP 工具列表

当前 MCP Server (`cloud_platform_server.py`) 提供的工具：

| 工具名 | 功能描述 | 参数 |
|--------|---------|------|
| `query_user_orders` | 查询用户订单和账单记录 | `user_id`, `limit` |
| `query_user_instances` | 查询用户名下云服务器实例 | `user_id`, `limit` |
| `analyze_instance_usage` | 分析实例近 7 天资源使用率 | `instance_id`, `user_id` |
| `get_promotable_products` | 获取可推广商品列表 | 无 |
| `search_product_catalog` | 根据关键词搜索产品 | `keyword` |
| `get_promotion_materials` | 生成专属推广链接和返佣信息 | `product_id`, `user_id` |
| `generate_ai_poster` | 调用 DashScope 生成推广海报 | `prompt` |

**新增 MCP 工具**：
1. 在 `agent/mcp_servers/cloud_platform_server.py` 中添加 `@mcp.tool()` 装饰的函数
2. 确保返回值符合统一格式（使用 `_success_json()` / `_error_json()`）
3. 重启 FastAPI 服务即可生效

---

## 🧪 测试与验证

### 单元测试

```bash
# 运行所有测试
cd agent
python -m unittest discover test

# 运行特定测试
python -m unittest test.schema_check
python -m unittest test.resilience_check
```

### 组件健康检查

```bash
# 检查 MCP 客户端缓存
python test/mcp_client_cache_check.py

# 检查 MySQL 连接池
python test/mysql_pool_check.py

# 验证工具返回格式
python test/validate_tool_results.py

# 检查韧性层配置
python test/resilience_check.py
```

### 性能测试

```bash
# 测试 Milvus 向量检索性能
python test/milvus_rag.py --benchmark

# 测试 Neo4j 图谱查询性能
python test/build_kg.py --benchmark
```

---

## 📊 可观测性

### 日志查看

```bash
# 启动时添加 --debug 参数
uvicorn app_main:app --host 0.0.0.0 --port 5000 --reload --log-level debug

# 或在 agent/.env 中设置
LOG_LEVEL=DEBUG
```

**关键日志标识**：
- `✅` - 成功操作
- `❌` - 失败操作
- `[Init]` - 初始化阶段
- `[Orchestrator]` - 路由决策
- `[METRIC]` - 性能指标
- `🔒 [安全拦截]` - 工具调用拦截

### 结构化事件日志

系统在 `agent/core/resilience/observer.py` 中记录结构化事件：

```json
{
  "dependency": "milvus",
  "operation": "query_vector_db",
  "status": "success",
  "duration_ms": 45,
  "attempts": 1,
  "request_id": "abc-123"
}
```

可通过正则提取指标：
```bash
grep "\[METRIC\]" agent.log | awk '{sum+=$4; count++} END {print "Avg:", sum/count, "ms"}'
```

---

## 🎯 开发指南

### 新增 Agent

1. 在 `agent/agents/` 创建新的 Agent 类
2. 实现 `__call__(self, state: AgentState)` 方法
3. 在 `agent/core/workflow/graph_manager.py` 注册节点
4. 在 `OrchestratorAgent` 中添加路由规则

**示例**：
```python
# agent/agents/my_agent.py
from langchain_core.messages import BaseMessage

class MyAgent:
    async def __call__(self, state: AgentState):
        # 你的逻辑
        return {"messages": [...]}
```

### 新增 MCP 工具

1. 在 `agent/mcp_servers/cloud_platform_server.py` 添加函数
2. 使用 `@mcp.tool()` 装饰
3. 返回值使用 `_success_json()` 或 `_error_json()`

**示例**：
```python
@mcp.tool()
def my_new_tool(param: str) -> str:
    """工具描述文档字符串"""
    try:
        result = do_something(param)
        return _success_json("my_new_tool", data=result)
    except Exception as e:
        return _error_json("my_new_tool", ErrorCode.UNKNOWN, str(e))
```

### 新增产品知识

1. 将 Markdown/JSON 文档放入 `mock_data/`
2. 运行向量库构建：`python agent/test/milvus_rag.py`
3. 运行图谱构建：`python agent/test/build_kg.py`

### 修改配置

- **Agent 配置**：编辑 `agent/config/settings.py`
- **API 配置**：编辑 `app/app_config/settings.py`
- **环境变量**：编辑 `agent/.env`（不要提交到 Git）

---

## 🔒 安全注意事项

1. **不要提交敏感信息**：`.env`、数据库密码、API Key 已在 `.gitignore` 中排除
2. **工具调用拦截**：`UserIdInjector` 防止越权访问其他用户数据
3. **输入验证**：所有 MCP 工具都进行参数校验
4. **SQL 注入防护**：使用参数化查询，避免字符串拼接
5. **CORS 配置**：生产环境需限制允许的源

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 提交流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add some amazing feature'`
4. 推送到分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

### 代码规范

- 遵循 PEP 8 Python 代码风格
- 使用 Type Hints 标注函数签名
- 为公共 API 编写文档字符串
- 新增功能需包含单元测试

---

## 📝 更新日志

### v1.0.0 (2024-05-14)
- ✅ 初始版本发布
- ✅ 5 个专业 Agent 实现
- ✅ 双层记忆系统
- ✅ MCP 工具集成
- ✅ 语义缓存加速
- ✅ 流式前端界面
- ✅ 工具返回格式统一化改造

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent 编排引擎
- [FastAPI](https://github.com/tiangolo/fastapi) - 高性能 API 框架
- [Milvus](https://github.com/milvus-io/milvus) - 向量数据库
- [Neo4j](https://neo4j.com/) - 图数据库
- [Vue.js](https://vuejs.org/) - 渐进式 JavaScript 框架

---

<div align="center">

**Made with ❤️ by Cloud Agent Team**

如有问题，请提交 [Issue](https://github.com/your-username/cloud_agent/issues)

</div>
