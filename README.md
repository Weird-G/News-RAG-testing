# 热点新闻 + RAG AI 助手平台 — 个人练手项目

> 技术选型： FastAPI + 本地向量库 + Redis 缓存
> 我搭了一整套测试（pytest + 自动化评测脚本） 有量化指标、有脚本、有真实踩过的坑，代码都在本仓库里，欢迎看。

---

## 项目介绍

一个「今日头条风格」的热点新闻 + AI 智能助手平台，主要功能：

- **新闻中心**：多分类浏览（推荐/热榜/科技/体育/财经）、分页、详情页浏览量 +1、相关新闻推荐
- **用户中心**：手机号/用户名注册登录、JWT 鉴权、收藏夹、浏览历史
- **AI 助手（RAG）**：基于本地 400+ 条真实新闻做检索增强生成，回答必带引用来源，支持多轮对话上下文保持
- **Agent / Workflow**：Function Calling 查新闻、工作流生成「分类资讯汇总简报」

### 技术栈

**前端**：Vue3 + Vant4 + Pinia + Vite
**后端**：FastAPI + SQLAlchemy（异步）
**存储**：MySQL 8 + Redis 7 + Chroma（BGE 本地中文向量）
**LLM**：OpenAI 兼容接口（gpt-4o-mini）
**测试**：pytest + pytest-asyncio + Allure

### 架构图

```
                      ┌──────────────────────────────────────────┐
                      │   前端 (Vue3 + Vant + Pinia + Vite)       │
                      │   Home/Category/Detail/AIChat/Favorite    │
                      └────────────────┬─────────────────────────┘
                                       │  HTTPS + JWT Bearer
                      ┌────────────────▼─────────────────────────┐
                      │      FastAPI (Python Async)               │
                      │ routers / crud_cache / rag / agent        │
                      └─────┬───────────┬──────────────┬──────────┘
                            │           │              │
                   ┌────────▼──┐  ┌─────▼─────┐  ┌─────▼──────────┐
                   │ MySQL 8   │  │ Redis 7   │  │ Chroma         │
                   │ 4张表关联 │  │ 多级缓存  │  │ BGE zh-v1.5   │
                   └───────────┘  └───────────┘  │ ONNX 本地推理 │
                                                  └──────┬─────────┘
                                                         │ Embed
                                                  ┌──────▼─────────┐
                                                  │ LLM:gpt-4o-mini│
                                                  └────────────────┘
```

### 后端代码分层

| 目录 | 我做的事 |
|---|---|
| `routers/` | API 路由层，参数校验 + 返回格式统一（Pydantic） |
| `crud/` | 数据库读写，`news_cache.py` 做了「读缓存→读库→写缓存」多级策略 |
| `rag/` | RAG 核心逻辑：同步新闻到向量库、Top-K 检索、Prompt 拼接、多轮上下文合并 |
| `agent/` | Function Calling + Workflow（查浏览量、查分类新闻、生成简报） |
| `vector_store/` | BGE 中文嵌入（ONNX 本地推理）+ Chroma 持久化 |
| `cache/` + `config/` | Redis、MySQL、JWT 相关配置 |
| `tests/` | pytest 测试（我做的核心） |
| `scripts/` | RAG 质量评测脚本、三链路一致性检查、Allure 一键报告 |

---

## 本地怎么跑起来

### 环境要求
- Python 3.9 / 3.10（3.11+ onnxruntime 的 wheel 在 Windows 上有时装不上，3.9 最稳）
- MySQL ≥ 8.0（utf8mb4）
- Redis ≥ 7.0
- Node.js ≥ 16（前端打包用）
- Windows / macOS / Linux 都行，我自己在 Windows 上开发的

### 第一步：拉代码 + 装 Python 依赖
```powershell
# Windows PowerShell
cd 你放代码的目录
git clone https://github.com/Weird-G/News-RAG-testing.git
cd News-RAG-testing\toutiao_backend

# 创建虚拟环境并激活
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# 上面报 ExecutionPolicy 的话，先执行一次：
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 安装依赖（我用清华源装的，快一些）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 第二步：配置 .env 文件
`toutiao_backend/.env.example` 里是模板，复制一份改名 `.env`：
```powershell
copy .env.example .env
```
至少填下面这几项（`.env` 已经被 `.gitignore` 排除，不会被 commit）：
```dotenv
# ========== MySQL ==========
DATABASE_URL=mysql+aiomysql://root:你的MySQL密码@127.0.0.1:3306/news_app?charset=utf8mb4

# ========== Redis ==========
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# ========== JWT ==========
SECRET_KEY=随便一串随机字符，越长越安全
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ========== LLM（我用的是 OpenAI 兼容的 CloseAI）==========
OPENAI_API_KEY=sk-你自己的 key
OPENAI_BASE_URL=https://api.closeai-asia.com/v1
LLM_MODEL=gpt-4o-mini

# ========== HuggingFace 镜像（下向量模型用，不然很慢）==========
HF_ENDPOINT=https://hf-mirror.com
```

### 第三步：导入数据库
项目根目录有个 `database.sql`，里面含建库 + 建表 + 403 条真实新闻数据。
```powershell
# Windows PowerShell（把 -proot 改成你自己的 MySQL 密码，中间不要加空格）
Get-Content "你的完整路径\News-RAG-testing\database.sql" -Encoding UTF8 | mysql -u root -p你的密码
```
验证：
```powershell
mysql -u root -p你的密码 -e "USE news_app; SHOW TABLES; SELECT COUNT(*) FROM news;"
# 8 张表 + news.count = 403 就对了
```

### 第四步：启动 Redis
```powershell
# Windows 版 Redis 直接双击 redis-server.exe
# 或者用 Docker：
docker run -d -p 6379:6379 redis:7-alpine
```

### 第五步：启动后端 + 同步向量库
```powershell
cd toutiao_backend
.\.venv\Scripts\Activate.ps1
python start_backend.py --reload
```
等 uvicorn 启动后，**另开一个终端**把新闻灌到 Chroma 向量库（只需要做一次）：
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ai/sync_news_to_vector" -Method Post
# 返回 code:200 + "已同步 xxx 个新闻片段" 就成功了
```
然后 Swagger 文档在 http://127.0.0.1:8000/docs

### 第六步：启动前端
```powershell
cd News-RAG-testing\toutiao_frontend
npm install           # 慢的话加 --registry=https://registry.npmmirror.com
npm run dev           # 默认 http://127.0.0.1:5173
```

---

## 我做的测试体系

我一共跑通了 **101 条 pytest 用例，0 失败**，加上一套 **120 条的 RAG 离线评测**（不放在 pytest 里，因为跑一次要好几分钟）。

### 怎么跑测试

先进入后端虚拟环境：
```powershell
cd toutiao_backend
.\.venv\Scripts\Activate.ps1
```

跑全部测试（大概 1~2 分钟，有几条会调 LLM）：
```powershell
pytest tests/ -v
```
预期输出类似：
```
tests/test_api/test_ai_chat_api.py ............            [ 11%]
tests/test_api/test_news_api.py ...........                [ 22%]
tests/test_api/test_user_api.py ......                     [ 28%]
tests/test_data/test_data_consistency.py .....             [ 33%]
tests/test_rag/test_rag_quality.py ..........              [ 43%]
tests/test_tool_calling.py ............................   [ 92%]   # 50 个参数化场景
tests/test_workflow.py .......                             [100%]
======================== 101 passed in 87.97s ========================
```

按分类跑：
```powershell
pytest tests/ -m api          # 接口测试（news / ai / user）
pytest tests/ -m rag          # RAG 质量（召回精度/幻觉/多轮上下文）
pytest tests/ -m data         # MySQL × Chroma × Redis 三链路一致性
pytest tests/ -m "not slow"   # 跳过调 LLM 的慢用例
```
标记定义在 [pytest.ini](toutiao_backend/pytest.ini) 里。

### 测试覆盖矩阵

| 测试维度 | 用例数 | 核心指标（真实运行结果） |
|---|---|---|
| 接口契约测试 | 29 | 正常/异常/边界/鉴权 4 类覆盖，Pydantic 参数校验命中 100% |
| RAG 质量评测（pytest） | 10 | 检索召回 / 幻觉检测 / 多轮上下文 / 响应稳定性 / 引用完整性 |
| RAG 离线评测（脚本） | 120 | 事实查询 Top3 召回 100%，4 类平均 Top3 = 57.5% |
| 三链路数据一致性 | 5 | 条数对账 / 元数据完整 / 孤儿向量 / 缓存时效 |
| Agent Function Calling | 50 | 5 类 × 多场景参数化，全部通过 |
| Workflow 工作流 | 7 | 工作流顺序 / 数据流转 / 汇总简报生成 |
| **合计（pytest）** | **101** | **101/101 全绿** |

### 120 条 RAG 离线评测真实指标

120 条 query 我自己按 **事实查询 / 应用场景 / 趋势分析 / 汇总查询** 4 类各标了 30 条，从三个维度评估：
- **Top-K 召回率**：检索返回的新闻 id 和我标注的 expected_news_ids 重合度
- **Rouge-L F1**：LLM 生成的回答 vs 数据库里新闻 description 的最长公共子序列
- **向量语义相似度**：query embedding 和 answer embedding 的 cosine 距离

| Query 分类 | 样本数 | Top1 召回 | Top3 召回 | Top5 召回 | Rouge-L F1 | 向量相似度 |
|---|---|---|---|---|---|---|
| 事实查询 | 30 | 93.3% | **100.0%** | 100.0% | 0.528 | 0.805 |
| 应用场景 | 30 | 57.2% | 67.8% | 67.8% | 0.215 | 0.657 |
| 趋势分析 | 30 | 26.4% | 48.3% | 48.3% | 0.201 | 0.628 |
| 汇总查询 | 30 | 6.9% | 13.9% | 13.9% | 0.112 | 0.499 |
| **平均** | **120** | 45.9% | 57.5% | 57.5% | 0.264 | 0.647 |

脚本在 [scripts/rag_evaluation/rag_evaluator.py](toutiao_backend/scripts/rag_evaluation/rag_evaluator.py)，跑一次输出到 `rag_eval_results.json`。

> 我自己的解读：事实查询（单跳检索）Top3 召回 100%，说明向量库 + 检索链路本身是好的；汇总查询 Top3 只有 13.9%，因为当前 RAG 没做多跳聚合，这种场景得走 Agent Workflow——这也是我做评测发现的系统边界。

### chunk_size A/B 对比（30 / 500 / 800 / 1000 四档）

我一开始照着网上推荐用了 1000 字符的 chunk，总感觉召回有点不稳定，于是写了脚本把 4 档全跑了一遍（30 条事实查询）：

| Chunk Size | Top3 召回 | Rouge-L F1 | 向量相似度 | QA 准确率 |
|---|---|---|---|---|
| 300 | 100.0% | 0.524 | 0.818 | 100.0% |
| 500 | 96.7% | 0.515 | 0.798 | 96.7% |
| 800 | 100.0% | 0.515 | 0.815 | 100.0% |
| 1000 | 96.7% | 0.490 | 0.796 | 96.7% |

结论是 **300 字符 chunk 整体最优**，我最终就用的 300。脚本在 [scripts/rag_evaluation/chunk_size_ab_test.py](toutiao_backend/scripts/rag_evaluation/chunk_size_ab_test.py)。

### 一键生成 Allure 报告

```powershell
# 先装 Java 8+，再装 allure（scoop install allure 或 choco install allure）
python scripts/run_allure.py all
# 跑完会自动开浏览器看报告（默认 http://127.0.0.1:8088）
```
报告里能看到通过率总览、Behaviors 分组、每条用例的步骤/断言/日志、失败堆栈。

---

## 我踩过的坑和修复

做这个项目的过程中陆陆续续发现了一些 bug，大部分是我自己写的时候没考虑周全，列在下面方便自己回头看，也方便你 review：

| # | 我遇到的问题 | 影响 | 我的修复方式 |
|---|---|---|---|
| 1 | `news_cache.get_news_list()` 通过 `skip//limit+1` 反推页码生成缓存键，但调用方其实已经传了正确 offset → 键位全错位 | 缓存键命中率 0%，所有请求都打 DB | 直接接收调用方的 `page/page_size` 生成 key，不再通过 offset 反推 |
| 2 | `page` / `page_size` 没做最小值限制，传负数会触发 SQL `LIMIT -20, 10` 这种怪写法 | 偶发 500 + 潜在注入风险 | FastAPI `Query(1, ge=1)` / `Query(10, ge=1, le=100)` 硬约束 |
| 3 | 新闻详情浏览量 +1 后没删 Redis 缓存 | 连续刷详情，浏览量一直显示旧值 | 写入后主动 `delete_cache("news:detail:{id}")` 失效缓存 |
| 4 | 详情接口返回的 views 是从缓存对象取的旧值，不是 +1 后新值 | 前端浏览量永远比真实值少 1 | 更新 DB 后手动覆盖 `updated_views = news_detail.views + 1` 再返回 |
| 5 | 前端 axios 请求拦截器是空实现，没有加 JWT | 收藏/历史接口永远 401，登了也没用 | 从 Pinia localStorage.user 读 token，Header 加 `Authorization: Bearer xxx` |
| 6 | 401 错误没有清本地状态并跳登录 | 用户白屏懵逼 | 响应拦截器检测 401 → 清 user → 跳 `#/login` |
| 7 | `workflows.py` 里 `select(Category.id)` 返回的是 int，我却当 Row 对象访问 `.id` 属性 | Workflow 和 Function Calling 全崩 500 | `category.id` → 直接用 `category` |
| 8 | pytest-asyncio 的事件循环被多个测试共享，SQLAlchemy 连接池里旧连接绑在已经关闭的循环上 | 8 条用例报 `NoneType.send` | 加了一个 autouse fixture，每个测试结束后 `await async_engine.dispose()` 释放连接 |

---

## 项目目录速览

```
News-RAG-testing/
├── README.md                          ← 你现在看的这个文件
├── .gitignore                         排除 Python/Node/向量库/报告/.env 等
├── database.sql                       建库建表 + 403 条新闻数据
├── toutiao_backend/                   ← 后端（重点是这里）
│   ├── main.py                        FastAPI 入口 + CORS + 路由注册
│   ├── requirements.txt               Python 依赖（锁了 chromadb/numpy/greenlet 兼容版本）
│   ├── pytest.ini                     pytest 标记 + 默认 Allure 目录
│   ├── .env.example                   环境变量模板
│   ├── Dockerfile                     容器化
│   ├── docker-compose.yml             MySQL + Redis + 后端 一条命令起
│   ├── start_backend.py               本地启动脚本
│   ├── routers/                       接口契约层
│   ├── crud/                          DB 读写 + Redis 多级缓存
│   ├── rag/                           RAG 服务：检索/拼接/上下文/同步向量库
│   ├── agent/                         Function Calling + Workflow
│   ├── vector_store/                  BGE 中文嵌入 + Chroma 持久化
│   ├── scripts/
│   │   ├── run_allure.py              一键跑测试 + 生成 Allure 报告
│   │   ├── rag_quality_test.py        RAG Top-K / 幻觉 / 多轮独立脚本
│   │   ├── data_consistency_check.py  MySQL × Chroma × Redis 三链路对账
│   │   ├── rag_evaluation/            RAG 离线评测套件（120 条用例 + chunk_size A/B + Rouge-L）
│   │   └── jmeter/rag_test_plan.jmx   JMeter 压测计划
│   └── tests/                         pytest 101 条（api 29 / rag 10 / data 5 / tool 50 / workflow 7）
└── toutiao_frontend/                  Vue3 前端（npm install + npm run dev）
```

---

## 开源协议说明

- BGE 中文嵌入模型：[BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)（MIT License）
- UI 组件库：[Vant 4](https://vant-ui.github.io/)（MIT License）
- 向量库：[Chroma](https://www.trychroma.com/)（Apache 2.0）
- 我写的代码：MIT License，随便看
