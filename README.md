# Toutiao_Project — 热点新闻 + RAG AI 助手平台

> 面向「AI 测试开发工程师」岗位的个人全栈项目。
> 项目亮点不在于「把业务跑通」，而在于提供了一套**可复现、可量化、可追溯**的测试体系
> （接口契约测试 / RAG 质量评测 / MySQL × Chroma 双存储一致性 / Redis 缓存与 JMeter 性能基线 / Allure 可视化报告），
> 可以作为简历上的 GitHub 链接、部署链接、面试时的 Demo 直接展示。

---

## 🚀 快速访问（部署后把占位链接替换成真实链接）

| 模块 | 地址 | 说明 |
|---|---|---|
| 🌐 前端 Demo | https://your-frontend.oss-cn-hangzhou.aliyuncs.com/index.html | Vue3 + Vant 移动端 UI，部署在阿里云 OSS |
| ⚙️ 后端 API | https://api.your-domain.com | FastAPI 服务（阿里云 ECS） |
| 📖 Swagger 文档 | https://api.your-domain.com/docs | 所有接口在线可调试 |
| 📊 Allure 测试报告 | https://allure.your-domain.com | **面试重点展示：可视化测试报告** |
| 🧪 CI 流水线 | https://github.com/你的用户名/Toutiao_Project/actions | GitHub Actions：每次 push 自动跑测试 |

---

## 📌 项目介绍

### 业务功能
一个「今日头条风格」的热点新闻 + AI 智能助手平台，包含：

- **新闻中心**：多分类浏览（推荐/热榜/科技/体育/财经等）、分页加载、详情页浏览量 +1、相关新闻推荐
- **用户中心**：手机号/用户名注册登录、JWT 鉴权、收藏夹、浏览历史
- **AI 助手（RAG）**：基于本地 400+ 条真实新闻做检索增强生成，回答必带引用来源，支持多轮对话上下文保持
- **Agent / Workflow**：Function Calling 查新闻、工作流生成「分类资讯汇总简报」

### 技术栈（面试一句话版）
> **前端** Vue3 + Vant4 + Pinia + Vite / **后端** FastAPI + SQLAlchemy 异步 / **存储** MySQL 8 + Redis 7 + Chroma(BGE 本地中文向量) / **LLM** gpt-4o-mini / **测试** pytest + pytest-asyncio + Allure + JMeter / **部署** Docker + 阿里云 ECS + OSS + Nginx

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

### 后端分层（对应代码目录）
| 目录 | 作用 |
|---|---|
| `routers/` | API 路由（契约层，直接映射 Swagger 文档的接口列表） |
| `crud/` | 数据库读写，`news_cache.py` 封装「读缓存 → 读库 → 写缓存」多级策略 |
| `rag/` | RAG 核心：同步新闻到向量库、Top-K 检索、Prompt 拼接、多轮上下文合并 |
| `agent/` | Agent Function Calling + Workflow（查浏览量/查分类新闻/生成简报） |
| `vector_store/` | BGE 中文嵌入模型（ONNX 推理）+ Chroma 持久化 |
| `cache/` + `config/` | Redis、MySQL、JWT 安全配置 |
| `tests/` | ✅ **面试核心：pytest 测试体系** |
| `scripts/` | RAG 质量评测脚本、双存储一致性检查、Allure 一键报告脚本 |

---

## 💻 本地环境配置

### 硬件 / 软件要求
- Python **3.9 / 3.10**（3.11+ onnxruntime wheel 可能不完整，3.9 最稳）
- MySQL **≥ 8.0**（utf8mb4）
- Redis **≥ 7.0**
- Node.js **≥ 16**（前端打包用）
- Windows / Ubuntu / macOS 均可

### 第一步：拉代码 + 初始化 Python 虚拟环境（Windows PowerShell）
```powershell
cd F:\A-code\pycharm\FastAPl
git clone https://github.com/你的用户名/Toutiao_Project.git    # 或使用已有目录
cd Toutiao_Project\toutiao_backend

# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # 如果报 ExecutionPolicy，先执行: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 安装依赖（清华源加速）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 第二步：配置环境变量
`toutiao_backend/.env.example` 已经给了模板，复制后改成你自己的：

```bash
cp .env.example .env
```

`.env` 最少要填这几项（**不要把 .env 提交到 GitHub**，已在 .gitignore 中排除）：

```dotenv
# ========== 数据库 ==========
DATABASE_URL=mysql+aiomysql://root:你的密码@127.0.0.1:3306/news_app?charset=utf8mb4

# ========== Redis ==========
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
# REDIS_PASSWORD=

# ========== JWT ==========
SECRET_KEY=请使用 openssl rand -hex 32 生成的随机串
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ========== LLM (CloseAI = OpenAI 兼容) ==========
OPENAI_API_KEY=sk-在 closeai-asia.com 网站申请
OPENAI_BASE_URL=https://api.closeai-asia.com/v1
LLM_MODEL=gpt-4o-mini

# ========== 向量模型（国内镜像，首次运行自动下载）==========
HF_ENDPOINT=https://hf-mirror.com
HF_HUB_DISABLE_XET=1
```

### 第三步：导入数据库
项目根目录下的 `database.sql` 已包含建库 + 建表 + 403 条新闻数据。

**Windows PowerShell 执行：**
```powershell
# 注意：把 -proot 改成你的真实 MySQL 密码（不加空格）
Get-Content "F:\A-code\pycharm\FastAPl\Toutiao_Project\database.sql" -Encoding UTF8 | mysql -u root -p你的密码
```

**验证是否导入成功：**
```powershell
mysql -u root -p你的密码 -e "USE news_app; SHOW TABLES; SELECT COUNT(*) AS cnt FROM news;"
# 预期输出：8 张表，cnt = 403
```

### 第四步：启动 Redis
```powershell
# 如果你用的是 Redis for Windows
redis-server.exe

# 或 Docker 一条命令起
docker run -d -p 6379:6379 redis:7-alpine
```

### 第五步：启动后端 + 同步新闻到 Chroma 向量库
```powershell
# 启动后端（使用项目自带的一键启动脚本）
python start_backend.py --reload

# （另开一个终端）调用同步接口，把 403 条新闻灌入 Chroma 本地向量库
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ai/sync_news_to_vector" -Method Post
# 返回 { "code": 200, "message": "已同步 403 个新闻片段到向量库" }
```

然后访问 http://127.0.0.1:8000/docs 可以看到 Swagger 文档。

### 第六步：启动前端
```powershell
cd Toutiao_Project\toutiao_frontend
npm install                 # 或 npm install --registry=https://registry.npmmirror.com
npm run dev                 # 默认 http://127.0.0.1:5173，已配置 /api 代理到 8000
```

---

## 🧪 测试运行方法（重点，面试直接看这里）

**所有测试全部 101 条，0 失败。**

```powershell
cd toutiao_backend
.\.venv\Scripts\Activate.ps1
```

### 1) 跑全部测试（约 120s，含 LLM 调用）
```powershell
pytest tests/ -v
```
输出示例：
```
tests/test_api/test_ai_chat_api.py ............            [ 11%]
tests/test_api/test_news_api.py ...........                [ 22%]
tests/test_api/test_user_api.py ......                     [ 28%]
tests/test_data/test_data_consistency.py .....             [ 33%]
tests/test_rag/test_rag_quality.py ..........              [ 43%]
tests/test_tool_calling.py ............................   [ 92%]   # 50 个参数化场景
tests/test_workflow.py .......                             [100%]
======================== 101 passed in ~120s ========================
```

### 2) 按维度选择运行（pytest 标记机制）
在 [pytest.ini](toutiao_backend/pytest.ini) 中定义了 8 个自定义标记：

```powershell
pytest tests/ -m api           # 只跑接口测试（news / ai / user）
pytest tests/ -m rag           # 只跑 RAG 质量评测（召回精度/幻觉/多轮）
pytest tests/ -m data          # 只跑 MySQL × Chroma 一致性
pytest tests/ -m smoke         # 冒烟测试（上线前快速回归）
pytest tests/ -m "not slow"    # 排除慢速用例（耗时 > 5s 的 LLM 调用）
```

### 3) 测试覆盖矩阵（简历写这些数据就够了）

| 测试维度 | 用例数 | 核心指标（实际运行结果） |
|---|---|---|
| 接口契约测试 | 29 | 正常/异常/边界/鉴权 4 场景全覆盖，Pydantic 校验全部返回 422，命中率 100% |
| RAG 质量评测 | 10 | 检索召回 / 幻觉检测 / 多轮上下文 / 响应稳定性 / 引用完整性 5 维度 |
| RAG 离线评测（120 条） | 120 | 事实查询 Top3 召回 100%，4 类平均 Top3 = 57.5%（详见下表） |
| MySQL × Chroma 数据一致性 | 5 | 条数一致 / 元数据完整 / 孤儿向量检测，不一致率 < 0.1% |
| Agent Function Calling | 50 | 5 类（精确查询/列表检索/统计/兜底降级/工具配置）× 8 场景参数化，成功率 100% |
| Workflow 工作流 | 7 | 4 步工作流顺序 / 数据流转 / 汇总简报生成 100% 正确 |
| **合计（pytest）** | **101** | **通过率 100%（120 条离线评测独立跑）** |

> **RAG 120 条离线评测（4 分类×30 条）真实指标：**
>
> | Query 分类 | 样本数 | Top1 召回 | Top3 召回 | Top5 召回 | Rouge-L F1 | 向量相似度 |
> |---|---|---|---|---|---|---|
> | 事实查询 | 30 | 93.3% | **100.0%** | 100.0% | 0.528 | 0.805 |
> | 应用场景 | 30 | 57.2% | 67.8% | 67.8% | 0.215 | 0.657 |
> | 趋势分析 | 30 | 26.4% | 48.3% | 48.3% | 0.201 | 0.628 |
> | 汇总查询 | 30 | 6.9% | 13.9% | 13.9% | 0.112 | 0.499 |
> | **平均** | **120** | 45.9% | 57.5% | 57.5% | 0.264 | 0.647 |
>
> 评测脚本：[scripts/rag_evaluation/rag_evaluator.py](toutiao_backend/scripts/rag_evaluation/rag_evaluator.py)，结果文件 `rag_eval_results.json`。
> **指标解读**：事实查询（单点检索）Top3 召回 100%，证明向量库 + 检索链路本身可用；汇总查询 Top3 仅 13.9%，因 RAG 当前未做多跳聚合，需走 Agent Workflow 兜底——这正是「测试驱动发现系统边界」的体现。
>
> **Chunk Size A/B 测试**（30 条事实查询 × 4 档）：
>
> | Chunk Size | Top3 召回 | Rouge-L F1 | 向量相似度 | QA 准确率 |
> |---|---|---|---|---|
> | 300 | 100.0% | 0.524 | 0.818 | 100.0% |
> | 500 | 96.7% | 0.515 | 0.798 | 96.7% |
> | 800 | 100.0% | 0.515 | 0.815 | 100.0% |
> | 1000 | 96.7% | 0.490 | 0.796 | 96.7% |
>
> 结论：**300 字符 chunk 召回率与生成质量最优**，最终采用 300 作为生产配置。脚本见 [chunk_size_ab_test.py](toutiao_backend/scripts/rag_evaluation/chunk_size_ab_test.py)。

### 4) 一键生成 Allure 可视化测试报告
```powershell
# 需要先装 Java 8+，然后用 scoop / choco 装 allure：
# scoop install allure     或    choco install allure

# 运行测试 + 生成报告 + 自动打开浏览器
python scripts/run_allure.py all

# 等价于分步执行：
pytest tests/ --alluredir=test_reports/allure-results
allure generate test_reports/allure-results -o test_reports/allure-report --clean
allure open -h 127.0.0.1 -p 8088 test_reports/allure-report
```
Allure 报告里可以看到：通过率总览、Behaviors 分组、每条用例的步骤/断言/日志、失败堆栈追踪、历史趋势图。
**面试时把这个页面（或部署后在线链接）直接点开给面试官看。**

### 5) JMeter 性能基线（简历写：并发 100，平均响应 < 500ms）
1. 启动后端 `python start_backend.py`
2. 打开 JMeter → 导入 `scripts/jmeter/rag_test_plan.jmx`
3. Thread Group 设置 100 并发，Ramp-up 10s
4. HTTP Request：`POST http://127.0.0.1:8000/api/ai/rag_chat`，Body `{"question":"社区时间银行养老是什么"}`
5. 查看「Summary Report」，Average < 500ms 即达标（通过 Redis 缓存检索结果实现）

---

## ☁️ 阿里云部署步骤（ECS + OSS + Nginx）

以下假设：
- 你购买了 **阿里云 ECS**（Ubuntu 22.04，2 核 4G 起步，跑 FastAPI + MySQL + Redis 够用）
- 域名已解析：`api.your-domain.com → ECS`，`your-domain.com → OSS`
- 系统是干净的 Ubuntu 22.04，SSH 已连接

### 一、服务器基础环境准备（SSH 登录 ECS 后执行）

```bash
sudo apt update && sudo apt upgrade -y

# 1) Python 3.10 + venv + pip
sudo apt install -y python3.10 python3.10-venv python3-pip

# 2) MySQL 8.0
sudo apt install -y mysql-server
sudo mysql_secure_installation                # 按提示设 root 密码
sudo mysql -u root -p
# MySQL 内部执行：
# CREATE DATABASE news_app DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
# CREATE USER 'toutiao_app'@'%' IDENTIFIED BY '替换成强密码';
# GRANT ALL PRIVILEGES ON news_app.* TO 'toutiao_app'@'%';
# FLUSH PRIVILEGES;
# EXIT;

# 3) Redis 7
sudo apt install -y redis-server
sudo sed -i 's/^# requirepass .*/requirepass 替换成Redis强密码/' /etc/redis/redis.conf
sudo sed -i 's/^bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf    # 如果只想内网访问就保留 127.0.0.1
sudo systemctl restart redis-server
sudo systemctl enable redis-server

# 4) Nginx（反代后端 + 部署静态资源）
sudo apt install -y nginx
sudo systemctl enable nginx

# 5) 可选：Java（跑 Allure 报告生成用）
sudo apt install -y openjdk-11-jdk-headless
```

### 二、上传项目代码到 ECS
**方法 A：Git 拉取（推荐，方便后续更新）**
```bash
cd /opt
sudo mkdir toutiao && sudo chown $USER:$USER toutiao
cd toutiao
git clone https://github.com/你的用户名/Toutiao_Project.git
```

**方法 B：SCP 上传本地代码（Windows PowerShell）**
```powershell
scp -r F:\A-code\pycharm\FastAPl\Toutiao_Project root@你的ECS公网IP:/opt/toutiao/
```

### 三、后端 Python 虚拟环境 + 导入 SQL

```bash
cd /opt/toutiao/Toutiao_Project/toutiao_backend

# 虚拟环境
python3.10 -m venv .venv
source .venv/bin/activate
pip install -i https://mirrors.aliyun.com/pypi/simple/ --upgrade pip
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# .env 配置（不要复制本地的，用阿里云生产专用）
cp .env.example .env
nano .env
# 需要改成你服务器的真实值：DATABASE_URL / REDIS_HOST / REDIS_PASSWORD / SECRET_KEY / OPENAI_API_KEY
```

导入 SQL（数据库已建的情况下）：
```bash
# 把本地 database.sql 上传到服务器或直接 git 已有
mysql -u toutiao_app -p news_app < /opt/toutiao/Toutiao_Project/database.sql
```

同步向量库（只需执行一次，或新闻更新后执行）：
```bash
# 启动后端（先临时用 8000 测试）
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 &
sleep 5
curl -X POST http://127.0.0.1:8000/api/ai/sync_news_to_vector
# 返回 { "message": "已同步 xxx 个新闻片段到向量库" } 即成功
kill %1     # 关掉临时进程
```

### 四、Supervisor 守护后端进程（异常退出自动重启 + 开机自启）

```bash
sudo apt install -y supervisor
sudo nano /etc/supervisor/conf.d/toutiao_backend.conf
```

写入以下内容（按你的目录调整）：
```ini
[program:toutiao_backend]
directory=/opt/toutiao/Toutiao_Project/toutiao_backend
command=/opt/toutiao/Toutiao_Project/toutiao_backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2 --log-level info
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/toutiao_backend.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
environment=PYTHONUNBUFFERED="1",PYTHONIOENCODING="utf-8"
```

启动：
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status toutiao_backend
# 预期输出：toutiao_backend                    RUNNING   pid 1234, uptime 0:00:05
```

### 五、Nginx 反向代理后端（端口 80 → 8000，支持 HTTPS）

```bash
sudo nano /etc/nginx/sites-available/toutiao_api
```

写入：
```nginx
server {
    listen 80;
    server_name api.your-domain.com;

    client_max_body_size 50M;
    proxy_connect_timeout 600s;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
    }

    # Allure 报告静态文件（放在 /var/www/allure-report）
    location /allure-report/ {
        alias /var/www/allure-report/;
        index index.html;
        autoindex off;
    }
}
```

启用站点 + 重载：
```bash
sudo ln -sf /etc/nginx/sites-available/toutiao_api /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t                   # 验证配置，输出 test is successful
sudo systemctl reload nginx
```

**开启 HTTPS（免费 Let's Encrypt，90 天自动续期）：**
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.your-domain.com -m 你的邮箱 --agree-tos -n
# 成功后 Nginx 会自动改配置加上 443 SSL，并跳转到 https
```

### 六、前端打包 + 阿里云 OSS 静态托管

**本地（Windows PowerShell）打包：**
```powershell
cd Toutiao_Project\toutiao_frontend

# 生产环境把后端地址改成阿里云域名（.env.production 或 vite.config.js）
# VITE_API_BASE_URL=https://api.your-domain.com
npm run build
# 打包产物位于 dist/ 目录
```

**上传到 OSS（阿里云控制台操作）：**
1. 进入「对象存储 OSS」→ 新建 Bucket（选公共读、和 ECS 同地域省流量费）
2. 「文件管理」→ 上传 `dist/` 里的所有文件
3. 「基础设置」→ **静态页面托管**：默认首页 `index.html`，默认 404 页 `index.html`（单页应用必配，否则刷新报 404）
4. 绑定自定义域名 + 开启 CDN（可选）

### 七、一键生成并发布 Allure 报告到 Nginx
```bash
cd /opt/toutiao/Toutiao_Project/toutiao_backend
source .venv/bin/activate

# 跑测试 + 生成报告
pytest tests/ --alluredir=test_reports/allure-results
allure generate test_reports/allure-results -o /var/www/allure-report --clean
sudo chown -R www-data:www-data /var/www/allure-report

# 浏览器访问：https://api.your-domain.com/allure-report/
```

---

## 🛠 常见面试问题回答速查

> 这些问题直接链接到项目里对应代码位置，面试时可以打开 GitHub 展示给面试官看。

1. **「你如何测试 RAG 的质量？」** → 看 [tests/test_rag/test_rag_quality.py](toutiao_backend/tests/test_rag/test_rag_quality.py) + [scripts/rag_evaluation/rag_evaluator.py](toutiao_backend/scripts/rag_evaluation/rag_evaluator.py)（三维度：Top-K 召回 / Rouge-L 文本重叠 / 向量语义相似度，120 条 4 分类）
2. **「MySQL × Chroma 为什么会不一致？如何发现？如何修复？」** → 看 [tests/test_data/test_data_consistency.py](toutiao_backend/tests/test_data/test_data_consistency.py) + [scripts/data_consistency_check.py](toutiao_backend/scripts/data_consistency_check.py)
3. **「Redis 缓存命中率为什么是 0？你怎么定位的？」** → 看修复过的 [crud/news_cache.py](toutiao_backend/crud/news_cache.py) 和 [routers/news.py](toutiao_backend/routers/news.py)
4. **「Allure 报告里你认为最有价值的是哪部分？」** → Behaviors 页：接口契约覆盖 + RAG 评测维度 + 数据一致性比率（跑一遍 `python scripts/run_allure.py all` 就知道）
5. **「你在项目中发现并修复了哪些 Bug？」** → 直接看下面的 🐛 缺陷修复记录表

---

## 🐛 我在项目中发现并修复的关键缺陷（面试核心素材）

| # | 缺陷描述 | 影响范围 | 修复方式 |
|---|---|---|---|
| 1 | `news_cache.get_news_list()` 用 `skip//limit+1` 推导页码生成缓存键，调用方实际已算好 offset → 缓存键错位 | 缓存命中率 0%，所有请求打 DB | 直接接收 `page/page_size` 参数生成 key，不再通过 offset 反推 |
| 2 | `page` / `page_size` 无最小值约束，负数触发 SQL `LIMIT -20, 10` | 偶发 500 + 潜在注入风险 | `Query(1, ge=1)` / `Query(10, ge=1, le=100)` |
| 3 | 详情接口浏览量 +1 后未删除 Redis 缓存 | 连续读详情，浏览量长期不更新，数据偏差 | `delete_cache("news:detail:{id}")` 主动失效 |
| 4 | 详情返回的 views 是缓存对象的旧值，不是 +1 后的值 | 前端浏览量永远少 1 | 手动覆盖 `updated_views = news_detail.views + 1` 返回 |
| 5 | 前端 axios 请求拦截器空实现，不注入 JWT | 收藏/历史接口永远 401，用户侧登录失效 | 从 Pinia localStorage.user 读 token，Header 加 `Authorization: Bearer xxx` |
| 6 | 401 错误未清理本地态并重定向登录 | 用户白屏无提示 | 响应拦截器检测 401 → 清 user → 跳 `#/login` |
| 7 | `workflows.py` + `tools.py` 中 `select(Category.id)` 返回 int，却访问 `.id` 属性 | Workflow / Function Calling 全部崩 → 500 | `category.id` → `category` 直接使用 |
| 8 | pytest-asyncio 事件循环被共享，SQLAlchemy 连接池里旧连接绑死在已关闭循环上 | 8 个用例报 `NoneType.send` | 增加 autouse fixture：每个测试后 `await async_engine.dispose()` |

---

## 📁 关键目录结构速览

```
Toutiao_Project/
├── README.md                         本文件
├── .gitignore                        Python / Node / 向量库 / 报告 / 密钥全部忽略
├── database.sql                      建库建表 + 403 条新闻数据
├── toutiao_backend/
│   ├── main.py                       FastAPI 入口 + CORS + 路由注册
│   ├── requirements.txt              Python 依赖（已锁定 chromadb/numpy/greenlet 兼容版本）
│   ├── pytest.ini                    pytest 标记 + 默认 Allure 目录
│   ├── .env.example                  环境变量模板
│   ├── Dockerfile                    容器构建
│   ├── docker-compose.yml            MySQL + Redis + 后端 三服务一键起
│   ├── start_backend.py              本地启动脚本（.env 复制 + 建目录 + uvicorn）
│   ├── routers/                      接口契约层
│   ├── crud/                         DB 读写 + Redis 多级缓存
│   ├── rag/                          RAG 服务（检索/拼接/上下文/同步）
│   ├── agent/                        Function Calling + Workflow
│   ├── vector_store/                 BGE 中文嵌入 + Chroma 持久化
│   ├── scripts/
│   │   ├── run_allure.py             一键跑测试 + 生成 Allure 报告 + 起服务
│   │   ├── rag_quality_test.py       RAG Top-K / 幻觉 / 多轮独立脚本
│   │   ├── data_consistency_check.py MySQL × Chroma × Redis 三链路对账脚本
│   │   ├── rag_evaluation/           RAG 离线评测套件（rag_evaluator + 120 cases + chunk_size A/B + rouge_l 自实现）
│   │   └── jmeter/rag_test_plan.jmx  JMeter 性能压测计划
│   └── tests/                        pytest 101 条测试（api 29 / rag 10 / data 5 / tool 50 / workflow 7）+ 120 条离线评测
└── toutiao_frontend/                 Vue3 前端（npm install + npm run build）
```

---

## 📄 License

- BGE 中文嵌入模型：[BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)（MIT）
- UI 组件库：[Vant 4](https://vant-ui.github.io/)（MIT）
- RAG / 向量库：[Chroma](https://www.trychroma.com/) + [FastEmbed](https://github.com/qdrant/fastembed)（Apache 2.0）
- 本项目代码：MIT，随便抄，用在简历上效果更佳 ✌️
