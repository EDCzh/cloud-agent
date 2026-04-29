# Cloud Agent - 智能云服务助手

基于 LangGraph 的多 Agent 协作系统，提供智能化的云产品咨询、故障排查、账单查询等服务。

## 🌟 项目简介

Cloud Agent 是一个智能客服系统，采用多 Agent 架构设计，能够理解用户意图并协调不同的专业 Agent 完成任务。系统结合了知识图谱、向量检索和传统数据库查询，提供准确、高效的云服务支持。

## 🎯 核心功能

### 1. 多 Agent 协同工作流
- **Orchestrator Agent**: 统一调度中心，负责意图识别和任务分发
- **Product Agent**: 云产品咨询，通过 Neo4j 知识图谱查询规格参数
- **Billing Agent**: 账单查询，通过 MySQL 查询订单和消费记录
- **Recommendation Agent**: 智能推荐，基于用户需求和历史行为推荐产品
- **FinOps Agent**: 成本优化建议，分析资源使用情况并提供优化方案
- **Promotion Agent**: 促销活动查询，提供最新的优惠信息

### 2. 知识增强检索
- **文档 RAG**: 基于 Milvus 的产品文档语义检索
- **图谱 RAG**: 基于 Neo4j 的产品规格精确查询
- **混合检索**: 并行查询向量库和图谱，去重排序后返回最优结果

### 3. 智能记忆系统
- **短期记忆**: Redis 存储当前会话上下文，支持多轮对话
- **长期记忆**: Milvus 向量化存储历史对话，支持跨会话记忆
- **记忆提取**: 自动提取用户偏好和行为模式，实现个性化服务

### 4. MCP 工具集成
- **订单查询**: 通过 MCP 协议查询用户订单信息
- **实例管理**: 查询和管理云资源实例
- **工单系统**: 创建和查询技术支持工单

### 5. 流式交互体验
- **SSE 实时推送**: 服务端推送 Agent 思考过程
- **可视化调试**: 前端实时展示 Agent 调用链路和状态流转
- **智能缓存**: L1/L2 双层缓存机制，提升响应速度

## 🏗️ 系统架构

### 整体架构

```
┌─────────────────────────────────────────────┐
│           Frontend (Vue3 + Vite)            │
│         http://localhost:5173               │
──────────────────┬──────────────────────────┘
                   │ HTTP/SSE
┌──────────────────▼──────────────────────────┐
│         Backend API (FastAPI)               │
│         http://localhost:5000               │
├─────────────────────────────────────────────┤
│  Orchestrator Agent (LangGraph)             │
│  ├─ Product Agent      (产品咨询)           │
│  ├─ Billing Agent      (账单查询)           │
│  ├─ FinOps Agent       (成本优化)           │
│  ├─ Recommendation     (产品推荐)           │
│  └─ Promotion Agent    (促销活动)           │
├─────────────────────────────────────────────┤
│  Memory System                              │
│  ├─ Short-term: Redis                       │
│  └─ Long-term: Milvus                       │
└──────────┬──────────────┬───────────────────┘
           │              │
    ┌──────▼──────┐ ┌────▼──────────┐
    │   MySQL     │ │   Neo4j       │
    │  (业务数据)  │ │ (知识图谱)     │
    └─────────────┘ └───────────────┘
           │
    ┌──────▼──────┐
    │   Milvus    │
    │ (向量数据库) │
    └─────────────┘
```

### 架构设计要点

#### 🎯 核心引擎
- **LangGraph StateGraph**: 构建复杂状态图，通过6个Agent协同工作（Orchestrator、Product、Billing、Recommend、FinOps、Promotion）
- **AgentState 状态管理**: 实现状态图路由与Agent协作，解决 Prompt 注入问题并增强系统稳定性
- **Checkpoint 机制**: 利用 LangGraph 的 Checkpoint 实现多轮对话的状态保存，用户主动退出后自动释放

#### 🔄 通信与协议
- **FastMCP 协议**: 将内部后端服务调用（订单、实例、工单API）封装为 MCP Server，统一给 MCP Tool 进行调用
- **SSE 流式返回**: FastAPI 网关层设置 Milvus 向量查询，支持流式SSE返回，实时展示 Agent 思考过程
- **L1/L2 双层向量设计**: 在 FastAPI 网关层构建双层向量化设计，提升检索效率

#### 💾 数据与检索
- **混合检索 (Hybrid RAG)**: Milvus（全文本）+ Neo4j（图谱）并行查询，去重排序合并返回，减少对 MySQL 的参数查询
- **MCP 工具集成**: 采用 Milvus 实现文档 RAG、Neo4j 实现图谱 RAG、MySQL 实现 MCP 工具查询
- **三层检索架构**:
  - 第一层：Milvus 向量检索（语义匹配）
  - 第二层：Neo4j 图谱检索（精确查询）
  - 第三层：MySQL 业务查询（参数化查询）

#### 🧠 记忆系统
- **双层记忆架构**: 
  - **短期记忆**: Redis 短期窗口（会话级），存储当前对话上下文
  - **长期记忆**: Milvus 向量化提取（跨会话），支持长期的复杂对话场景
- **动态记忆注入**: 会话窗口动态记忆注入 Orchestrator 路由，实现个性化推荐和上下文感知
- **会话状态控制**: 支持会话的长期记忆与个性化推荐

#### ⚡ 性能优化
- **Token 优化**: 拦截原始用户问题，给予响应缓存 Score，节省 token 消耗
- **L1/L2 缓存**: 基于向量相似度实现智能缓存，减少重复计算
- **并行查询**: Milvus 和 Neo4j 并行查询，提升响应速度

#### 🎨 前端展示
- **Vue3 + TypeScript**: 现代化前端技术栈
- **实时状态展示**: Web 客户端实时展示 Agent 之间的内部调用与流转过程
- **可视化调试**: 全面展示复杂的 LLM 内部流转，便于调试和优化

### 数据流向

```
用户输入 → Orchestrator (意图识别)
         ↓
    ┌────┴────┬───────────┬──────────┬─────────┐
    ↓         ↓           ↓          ↓         ↓
Product   Billing   Recommend   FinOps   Promotion
    ↓         ↓           ↓          ↓         ↓
Neo4j/    MySQL      Milvus/    MySQL     Milvus
Milvus    (订单)    Neo4j     (成本)    (活动)
    ↓         ↓           ↓          ↓         ↓
    └────┬────┴───────────┴──────────┴─────────┘
         ↓
    结果聚合 → SSE 流式返回 → 前端展示
```

## 🛠️ 技术栈

### 后端
- **Python 3.10+**
- **FastAPI** - Web 框架
- **LangGraph 1.x** - Agent 编排
- **LangChain 1.x** - LLM 应用框架
- **MCP (Model Context Protocol)** - 工具协议

### 前端
- **Vue 3** - 渐进式框架
- **Vite** - 构建工具
- **TypeScript** - 类型安全

### 数据存储
- **MySQL 8.0** - 业务数据存储（订单、实例等）
- **Redis** - 短期记忆/会话缓存
- **Neo4j 5.18** - 知识图谱（产品规格、关系）
- **Milvus 2.5** - 向量数据库（语义搜索、缓存）

### AI 模型
- **通义千问 Plus** (qwen-plus) - Orchestrator 主模型
- **text-embedding-v2** - 文本嵌入模型

## 📋 环境要求

- Python 3.10 或更高版本
- Docker & Docker Compose
- Node.js 16+ 和 npm
- Git

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/cloud-agent.git
cd cloud-agent
```

### 2. 部署依赖服务

#### 部署 Redis

```bash
docker run -d --name redis \
  -p 6379:6379 \
  -e REDIS_USERNAME=root \
  -e REDIS_PASSWORD=YourPassword123 \
  bitnami/redis:latest
```

#### 部署 MySQL

```bash
docker run -d --name mysql8 \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=RootPass123! \
  -e MYSQL_DATABASE=mydb \
  -e MYSQL_USER=root \
  -e MYSQL_PASSWORD=UserPass123! \
  -v mysql_data:/var/lib/mysql \
  --restart unless-stopped \
  mysql:8.0
```

#### 部署 Neo4j

```bash
docker run -d --name neo4j \
  --restart always \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/YourPassword123 \
  -e NEO4J_PLUGINS='["apoc"]' \
  -v $HOME/neo4j/data:/data \
  -v $HOME/neo4j/logs:/logs \
  neo4j:5.18.0
```

#### 部署 Milvus

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  etcd:
    container_name: milvus-etcd
    image: quay.io/coreos/etcd:v3.5.18
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
    volumes:
      - ./etcd/data:/etcd
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    networks:
      - milvus-network

  minio:
    container_name: milvus-minio
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - ./minio/data:/minio_data
    command: minio server /minio_data --console-address ":9001"
    networks:
      - milvus-network

  milvus-standalone:
    container_name: milvus-standalone
    image: milvusdb/milvus:v2.5.7
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
      MINIO_ACCESS_KEY_ID: minioadmin
      MINIO_SECRET_ACCESS_KEY: minioadmin
    volumes:
      - ./milvus/data:/var/lib/milvus/data
      - ./milvus/logs:/var/lib/milvus/logs
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - etcd
      - minio
    networks:
      - milvus-network

networks:
  milvus-network:
    driver: bridge
```

启动 Milvus：

```bash
mkdir -p etcd/data minio/data milvus/data milvus/logs
docker compose up -d
```

### 3. 配置环境变量

```bash
# 复制配置模板
cp agent/.env.example agent/.env

# 编辑 .env 文件，填入真实的 API 密钥和密码
# Windows: notepad agent\.env
# Linux/Mac: vim agent/.env
```

编辑 `agent/.env`：

```env
# LLM 密钥配置
DASHSCOPE_API_KEY=sk-your-actual-api-key-here
BOCHA_API_KEY=sk-your-bocha-api-key-here

# Redis 配置
REDIS_URL=redis://:YourPassword123@localhost:6379

# MySQL 配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=RootPass123!
MYSQL_DATABASE=mydb

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=mult_agent_memory2

# Neo4j 配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=YourPassword123
```

### 4. 安装 Python 依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
cd agent
pip install -r requirements.txt
```

### 5. 初始化数据库

#### 初始化 MySQL 业务数据

```bash
# 连接到 MySQL 并执行初始化脚本
mysql -h localhost -P 3306 -u root -p < agent/database/init_mock_data.sql
```

#### 导入向量知识库

```bash
cd agent/test
python milvus_rag.py
```

#### 构建知识图谱

```bash
cd agent/test
python build_kg.py
```

### 6. 启动后端服务

```bash
# 返回 app 目录
cd ../../app

# 启动 FastAPI 服务
uvicorn app_main:app --host 0.0.0.0 --port 5000 --reload
```

访问 API 文档：http://localhost:5000/docs

### 7. 启动前端服务

打开新的终端窗口：

```bash
cd front/cloud_agent

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问前端界面：http://localhost:5173

## 📁 项目结构

```
cloud_agent/
├── agent/                      # Agent 核心逻辑
│   ├── agents/                 # 各类 Agent 实现
│   │   ├── orchestrator.py     # 编排器 Agent
│   │   ├── product_agent.py    # 产品咨询 Agent
│   │   ├── billing_agent.py    # 账单查询 Agent
│   │   ├── finops_agent.py     # 成本优化 Agent
│   │   ├── recommendation_agent.py  # 推荐 Agent
│   │   └── promotion_agent.py  # 促销 Agent
│   ├── core/                   # 核心组件
│   │   ├── graph/              # 知识图谱处理
│   │   ├── mcp/                # MCP 管理器
│   │   ├── memory/             # 记忆系统
│   │   └── workflow/           # 工作流管理
│   ├── tools/                  # 工具集
│   │   ├── graph_tool.py       # 图谱查询工具
│   │   └── vector_tool.py      # 向量检索工具
│   ├── config/                 # 配置文件
│   ├── test/                   # 测试和数据导入脚本
│   ├── main.py                 # Agent 入口
│   └── requirements.txt        # Python 依赖
├── app/                        # FastAPI 应用
│   ├── router/                 # API 路由
│   ├── service/                # 业务逻辑
│   ├── schemas/                # 数据模型
│   └── app_main.py             # 应用入口
├── front/cloud_agent/          # Vue3 前端
│   ├── src/                    # 源代码
│   ├── public/                 # 静态资源
│   └── package.json            # 前端依赖
├── mock_data/                  # 测试数据
│   ├── ecs_product_info.md     # ECS 产品信息
│   ├── rds_product_info.md     # RDS 产品信息
│   └── ...                     # 其他文档
└── README.md                   # 项目说明
```

## 🎯 使用示例

### 产品咨询

```
用户: "我想了解 ECS 云服务器有哪些规格？"
→ Product Agent 通过 Neo4j 知识图谱查询规格信息
```

### 账单查询

```
用户: "帮我查一下上个月的账单"
→ Billing Agent 查询 MySQL 业务数据库
```

### 故障排查

```
用户: "我的 ECS 实例无法连接网络怎么办？"
→ Product Agent 通过 Milvus RAG 检索故障排查文档
```

### 产品推荐

```
用户: "我需要运行一个高并发的 Web 应用，推荐什么配置？"
→ Recommendation Agent 分析需求并推荐合适的产品组合
```

## 🔧 开发指南

### 添加新的 Agent

1. 在 `agent/agents/` 目录下创建新的 Agent 文件
2. 继承基础 Agent 类，实现业务逻辑
3. 在 `orchestrator.py` 中注册新 Agent
4. 更新意图识别提示词

### 扩展知识图谱

1. 在 `mock_data/` 中添加新的产品文档（Markdown/JSON）
2. 运行 `agent/test/build_kg.py` 重新构建图谱
3. 验证 Neo4j 中的数据：http://localhost:7474

### 自定义 MCP 工具

1. 在 `agent/mcp_servers/` 中创建新的 MCP 服务器
2. 更新 `agent/config/mcp_servers.json` 配置
3. 重启服务加载新工具

## 📊 监控和管理

### 数据库管理界面

- **Neo4j Browser**: http://localhost:7474
- **Milvus Attu**: http://localhost:8000 (如果部署了 Attu)
- **MinIO Console**: http://localhost:9001

### 查看日志

```bash
# 查看所有容器状态
docker ps

# 查看特定服务日志
docker logs -f neo4j
docker logs -f milvus-standalone
```

## ⚠️ 注意事项

1. **保护敏感信息**: 永远不要将 `.env` 文件提交到 Git
2. **APOC 插件**: Neo4j 需要安装 APOC 插件才能使用图谱功能
3. **内存要求**: Milvus 建议至少 4GB 可用内存
4. **端口冲突**: 确保 3306, 6379, 7687, 19530, 5000, 5173 端口未被占用

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 📞 联系方式

如有问题或建议，请提交 Issue 或通过以下方式联系：

- 项目地址: https://github.com/your-username/cloud-agent
- 邮箱: your-email@example.com

---

**Happy Coding! 🚀**