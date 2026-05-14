# Cloud Agent

Cloud Agent 是一个面向云服务咨询、账单查询、资源优化和营销推广的多 Agent 智能客服项目。后端使用 FastAPI 提供聊天接口，核心 Agent 编排基于 LangGraph，工具侧通过 MCP 接入订单、实例、监控、促销物料等能力；前端使用 Vue 3 + Vite + Element Plus 提供实时流式聊天体验。

## 核心能力

- 多 Agent 路由：`OrchestratorAgent` 根据用户意图分发到产品咨询、账单查询、促销推广、选型推荐或 FinOps 工作流。
- 产品知识问答：结合 Milvus 文档 RAG 和 Neo4j 知识图谱，回答云产品概念、规格、限制和操作类问题。
- 账单与实例查询：通过 MCP 工具查询用户订单、云服务器实例和资源监控数据。
- FinOps 降本建议：先查询用户实例，再分析近 7 天 CPU、内存、带宽等指标，输出资源优化建议。
- 营销推广助手：查询可推广商品、生成专属推广链接，并可调用 DashScope 图像接口生成推广海报。
- 记忆系统：Redis 保存短期会话上下文，Milvus 保存长期偏好和事实，并支持会话摘要压缩。
- 语义缓存：FastAPI 网关层使用 Milvus 维护问答缓存，减少重复问题的 LLM 调用。
- 流式前端：`/api/chat` 使用 SSE 返回分片响应，前端按会话保存聊天记录并渲染 Markdown。

## 系统架构

```text
front/cloud_agent
  Vue 3 + Vite + Element Plus
          |
          | HTTP POST /api/chat
          v
app
  FastAPI 网关、SSE 流式响应、语义缓存、记忆上下文注入
          |
          v
agent
  LangGraph StateGraph
  OrchestratorAgent
      |-- ProductAgent          -> Milvus RAG / Neo4j Graph RAG
      |-- BillingAgent          -> MCP 工具 / MySQL
      |-- RecommendationAgent   -> 产品选型推荐
      |-- PromotionAgent        -> 促销物料 / 海报生成
      |-- FinOpsAgent           -> 实例监控分析 / 降本建议

外部依赖：DashScope、Redis、Milvus、Neo4j、MySQL
```

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Agent 编排 | LangGraph、LangChain、LangChain MCP Adapters |
| 大模型与嵌入 | DashScope 兼容 OpenAI 接口、`text-embedding-v2` |
| API 服务 | FastAPI、StreamingResponse |
| 工具协议 | MCP / FastMCP |
| 数据与缓存 | MySQL、Redis、Milvus、Neo4j |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、marked |
| 测试 | Python `unittest` |

## 目录结构

```text
cloud_agent/
├── agent/                         # Agent 核心代码
│   ├── agents/                    # 各业务 Agent 与 MCP 工具缓存
│   ├── config/                    # Agent 配置与 MCP server 配置
│   ├── core/
│   │   ├── graph/                 # 知识图谱解析与写入
│   │   ├── mcp/                   # MCP 管理器
│   │   ├── memory/                # Redis/Milvus 记忆系统
│   │   ├── resilience/            # 工具结果结构、错误分类、重试与观测
│   │   └── workflow/              # LangGraph 状态与图构建
│   ├── database/                  # MySQL 初始化脚本
│   ├── mcp_servers/               # FastMCP 工具服务
│   ├── test/                      # 检查脚本与单元测试
│   ├── tools/                     # Milvus 与 Neo4j 工具
│   └── main.py                    # CLI 调试入口
├── app/                           # FastAPI 网关
│   ├── app_config/                # API 层配置
│   ├── infra/                     # 语义缓存
│   ├── router/                    # HTTP 路由
│   ├── schemas/                   # 请求/响应模型
│   ├── service/                   # 聊天流式服务
│   └── app_main.py                # FastAPI 应用入口
├── front/cloud_agent/             # Vue 前端
├── mock_data/                     # 产品、网络、安全、账单等模拟知识数据
├── pyproject.toml                 # 项目元信息
└── README.md
```

## 环境要求

- Python 3.13+
- Node.js `^20.19.0` 或 `>=22.12.0`
- npm
- 可访问的 DashScope API Key
- Redis、Milvus、Neo4j、MySQL

## 环境变量

后端和 Agent 默认从 `agent/.env` 读取配置。最小示例：

```env
DASHSCOPE_API_KEY=sk-your-key
MODEL=qwen-plus
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MEMORY_SUMMARY_MODEL=qwen-turbo
PREFERENCE_EXTRACT_MODEL=qwen-turbo

REDIS_URL=redis://localhost:6379
REDIS_TTL=1800

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_API_KEY=

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DATABASE=cloud_platform
MYSQL_CHARSET=utf8mb4
MYSQL_POOL_MINCACHED=1
MYSQL_POOL_MAXCACHED=5
MYSQL_POOL_MAXCONNECTIONS=10
MYSQL_POOL_BLOCKING=true

LOG_LEVEL=INFO
```

可选变量：

- `MCP_SERVERS_CONFIG`：覆盖 MCP server 配置文件路径，默认是 `agent/config/mcp_servers.json`。
- `OPENWEATHER_API_KEY`：预留天气 API Key。
- `MYSQL_CONNECT_TIMEOUT`、`MYSQL_READ_TIMEOUT`、`MYSQL_WRITE_TIMEOUT`：MySQL 超时控制。

## 本地启动

### 1. 安装 Python 依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r agent/requirements.txt
```

Linux/macOS 激活虚拟环境：

```bash
source .venv/bin/activate
```

### 2. 准备基础服务

项目需要 Redis、Milvus、Neo4j 和 MySQL。可以使用本地服务或 Docker 部署，只要端口与 `.env` 保持一致即可。默认使用：

| 服务 | 默认地址 |
| --- | --- |
| Redis | `localhost:6379` |
| Milvus | `localhost:19530` |
| Neo4j Bolt | `bolt://localhost:7687` |
| MySQL | `localhost:3306` |

初始化 MySQL 模拟数据：

```bash
mysql -h localhost -P 3306 -u root -p cloud_platform < agent/database/init_mock_data.sql
```

构建向量知识库和知识图谱：

```bash
cd agent/test
python milvus_rag.py
python build_kg.py
```

### 3. 启动 FastAPI 后端

```bash
cd app
uvicorn app_main:app --host 0.0.0.0 --port 5000 --reload
```

聊天接口：

```text
POST http://localhost:5000/api/chat
```

请求体：

```json
{
  "query": "帮我查一下最近的订单记录",
  "user_id": "user_1001",
  "session_id": "session_default_1"
}
```

该接口返回 `text/event-stream`，每个事件包含 `content`、`error` 或 `done` 字段。

### 4. 启动前端

```bash
cd front/cloud_agent
npm install
npm run dev
```

默认访问：

```text
http://localhost:5173
```

前端当前直接请求 `http://localhost:5000/api/chat`，因此后端端口需要保持为 `5000`，或同步修改前端请求地址。

## CLI 调试

可以直接从 `agent/main.py` 运行 Agent：

```bash
cd agent
python main.py
```

单次查询：

```bash
python main.py --query "什么是 ECS？" --user user_1001 --session session_demo
```

## MCP 工具

默认 MCP 配置位于 `agent/config/mcp_servers.json`，会以 stdio 方式启动：

```text
python -m mcp_servers.cloud_platform_server
```

当前 MCP server 提供的主要工具包括：

- `query_user_orders`：查询用户订单和账单记录。
- `query_user_instances`：查询用户名下实例。
- `analyze_instance_usage`：分析实例近 7 天资源使用。
- `get_promotable_products`：查询可推广商品。
- `search_product_catalog`：根据关键词匹配商品。
- `get_promotion_materials`：生成推广物料和专属链接。
- `generate_ai_poster`：调用 DashScope 生成推广海报。

## 测试与检查

当前测试脚本位于 `agent/test/`，可以按需执行：

```bash
python -m unittest agent.test.schema_check
python -m unittest agent.test.resilience_check
python agent/test/mcp_client_cache_check.py
python agent/test/mysql_pool_check.py
```

部分检查依赖本地 Redis、Milvus、Neo4j、MySQL 或 DashScope Key。若外部服务不可用，相关能力会通过 resilience 模块降级并记录结构化事件。

## 开发提示

- 新增 Agent 时，优先放在 `agent/agents/`，并在 `agent/core/workflow/graph_manager.py` 注册节点和路由。
- 新增 MCP 工具时，优先扩展 `agent/mcp_servers/cloud_platform_server.py`，并保持返回值符合 `agent/core/resilience/schema.py` 的工具结果结构。
- 新增产品知识时，将 Markdown/JSON 放入 `mock_data/`，再运行向量库和知识图谱构建脚本。
- 根目录 `pyproject.toml` 只声明项目元信息和 Python 版本，运行依赖以 `agent/requirements.txt` 为准。
- 不要提交 `agent/.env`、数据库本地数据目录、虚拟环境或其他敏感配置。

