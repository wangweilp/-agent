# Enterprise Knowledge OS — 部署指南

> AI Second Brain 知识管理系统部署文档

---

## 目录

1. [环境变量说明](#1-环境变量说明)
2. [Docker 部署](#2-docker-部署)
3. [Docker Compose 部署](#3-docker-compose-部署)
4. [离线部署步骤](#4-离线部署步骤)
5. [内网部署注意事项](#5-内网部署注意事项)
6. [Kubernetes Helm 部署](#6-kubernetes-helm-部署)
7. [数据备份建议](#7-数据备份建议)

---

## 1. 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | 是 | - | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | API 基础地址 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-chat` | 模型名称 |
| `CHROMA_PERSIST_DIR` | 否 | `./data/chroma_db` | ChromaDB 向量库路径 |
| `SQLITE_DB_PATH` | 否 | `./data/agent_memory.db` | SQLite 数据库路径 |
| `UPLOAD_DIR` | 否 | `./data/uploads` | 文件上传目录 |
| `AUDIO_UPLOAD_DIR` | 否 | `./data/audio_uploads` | 音频上传目录 |
| `VIDEO_UPLOAD_DIR` | 否 | `./data/video_uploads` | 视频上传目录 |
| `EMBEDDING_MODEL` | 否 | `BAAI/bge-small-zh-v1.5` | 向量化模型 |
| `AGENT_SHORT_TERM_MEMORY_SIZE` | 否 | `20` | 短时记忆条数 |
| `AGENT_MAX_TOOL_ROUNDS` | 否 | `5` | 最大工具调用轮次 |
| `AGENT_CONTEXT_WINDOW` | 否 | `6` | 上下文窗口轮次 |
| `UPLOAD_MAX_SIZE_MB` | 否 | `20` | 文件上传上限 (MB) |
| `AUDIO_MAX_SIZE_MB` | 否 | `50` | 音频上传上限 (MB) |
| `VIDEO_MAX_SIZE_MB` | 否 | `200` | 视频上传上限 (MB) |
| `VIDEO_KEYFRAME_INTERVAL` | 否 | `5` | 视频关键帧间隔 (秒) |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `JWT_SECRET` | 是 | - | JWT 签名密钥，生产环境务必修改 |

---

## 2. Docker 部署

### 构建镜像

```bash
# 后端
docker build -t enterprise-kos-backend:latest \
  -f deployment/docker/Dockerfile .

# 前端
docker build -t enterprise-kos-frontend:latest \
  -f deployment/docker/Dockerfile.frontend .
```

### 运行容器

```bash
# 创建数据目录
mkdir -p ./data

# 运行后端
docker run -d \
  --name ekos-backend \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --env-file deployment/docker/.env.docker \
  enterprise-kos-backend:latest

# 运行前端
docker run -d \
  --name ekos-frontend \
  -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:8000 \
  enterprise-kos-frontend:latest
```

### 查看日志

```bash
docker logs -f ekos-backend
docker logs -f ekos-frontend
```

### 停止和清理

```bash
docker stop ekos-backend ekos-frontend
docker rm ekos-backend ekos-frontend
```

---

## 3. Docker Compose 部署

### 启动

```bash
# 1. 编辑环境变量
cp deployment/docker/.env.docker .env
vim .env   # 填入 DEEPSEEK_API_KEY，修改 JWT_SECRET

# 2. 启动所有服务
cd deployment/docker
docker compose up -d

# 3. 查看状态
docker compose ps
docker compose logs -f
```

### 端口自定义

```bash
BACKEND_PORT=8080 FRONTEND_PORT=3001 docker compose up -d
```

### 常用命令

```bash
docker compose restart    # 重启服务
docker compose down       # 停止并移除
docker compose down -v    # 停止并移除数据卷（谨慎）
docker compose pull       # 拉取最新镜像
```

---

## 4. 离线部署步骤

适用场景：目标机器无法访问互联网。

### 4.1 在有网机器上准备

```bash
# 1. 构建镜像
docker compose build

# 2. 导出镜像为 tar 包
docker save enterprise-kos-backend:latest -o ekos-backend.tar
docker save enterprise-kos-frontend:latest -o ekos-frontend.tar
docker save python:3.12-slim -o python-3.12-slim.tar
docker save node:20-alpine -o node-20-alpine.tar

# 3. 预先下载 embedding 模型
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; \
  SentenceTransformer('BAAI/bge-small-zh-v1.5')"
# 模型缓存在 ~/.cache/torch/sentence_transformers/
tar czf models.tar.gz -C ~/.cache/torch sentence_transformers/
```

### 4.2 传输文件到离线机器

将以下文件复制到目标机器：
- `ekos-backend.tar`, `ekos-frontend.tar`
- `python-3.12-slim.tar`, `node-20-alpine.tar`
- `models.tar.gz`（若有）
- 项目完整源码及 `.env.docker`

### 4.3 在离线机器上部署

```bash
# 1. 导入基础镜像
docker load -i python-3.12-slim.tar
docker load -i node-20-alpine.tar

# 2. 导入应用镜像
docker load -i ekos-backend.tar
docker load -i ekos-frontend.tar

# 3. 解压模型
tar xzf models.tar.gz -C /opt/models/

# 4. 配置环境变量
cp deployment/docker/.env.docker .env.docker
vim .env.docker

# 5. 使用离线 compose 启动
docker compose -f deployment/docker/docker-compose.offline.yml up -d
```

---

## 5. 内网部署注意事项

### 5.1 网络依赖

| 组件 | 出站需求 | 替代方案 |
|---|---|---|
| DeepSeek API | `api.deepseek.com` | HTTP 代理或私有 LLM 网关 |
| Embedding 模型 | `huggingface.co` | 预先下载，挂载本地目录 |
| Docker Hub | 拉取基础镜像 | 私有镜像仓库 (Harbor/Nexus) |
| NPM Registry | 前端构建 | 私有 npm registry 或离线缓存 |

### 5.2 HTTP 代理

```bash
# Docker 构建时
docker build --build-arg HTTP_PROXY=http://proxy.internal:8080 \
  --build-arg HTTPS_PROXY=http://proxy.internal:8080 \
  -f deployment/docker/Dockerfile .

# 容器运行时（在 .env.docker 中添加）
# HTTP_PROXY=http://proxy.internal:8080
# HTTPS_PROXY=http://proxy.internal:8080
```

### 5.3 私有镜像仓库

```bash
docker tag enterprise-kos-backend:latest \
  registry.internal:5000/enterprise-kos-backend:v0.1.0
docker push registry.internal:5000/enterprise-kos-backend:v0.1.0

# Helm values 中配置：
# backend.image.repository: registry.internal:5000/enterprise-kos-backend
# backend.image.tag: v0.1.0
```

### 5.4 DeepSeek API 代理

```nginx
# Nginx 反向代理示例
location /v1/ {
    proxy_pass https://api.deepseek.com/v1/;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Host api.deepseek.com;
}
```

然后设置环境变量 `DEEPSEEK_BASE_URL=http://your-proxy:8080`。

### 5.5 模型离线部署

Embedding 模型首次运行时会从 HuggingFace 下载。内网环境需：
1. 在有网机器上下载模型到 `~/.cache/torch/sentence_transformers/`
2. 打包传输到离线机器
3. Docker 挂载：`-v /opt/models/sentence_transformers:/root/.cache/torch/sentence_transformers:ro`
4. 或 K8s 中使用 hostPath 挂载

---

## 6. Kubernetes Helm 部署

### 6.1 前置条件

- Kubernetes 集群 v1.24+
- Helm v3.12+
- 集群已配置默认 StorageClass（用于 PVC 动态供给）
- 可选：安装 ingress-nginx controller（用于域名访问）

### 6.2 安装

```bash
# 1. 创建命名空间
kubectl create namespace knowledge-os

# 2. 创建 Secret（敏感信息通过 K8s Secret 注入）
kubectl -n knowledge-os create secret generic ekos-secrets \
  --from-literal=DEEPSEEK_API_KEY=sk-your-key-here

kubectl -n knowledge-os create secret generic ekos-jwt \
  --from-literal=JWT_SECRET=$(openssl rand -hex 32)

# 3. 安装 Chart
cd deployment/helm
helm install enterprise-knowledge-os . \
  --namespace knowledge-os \
  --create-namespace

# 4. 查看部署状态
kubectl -n knowledge-os get all
kubectl -n knowledge-os get pvc
```

### 6.3 自定义配置

```bash
# 创建自定义 values 文件
cat > my-values.yaml << 'EOF'
backend:
  replicaCount: 2
  persistence:
    size: 20Gi
    storageClass: "longhorn"
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 4000m
      memory: 8Gi

ingress:
  enabled: true
  hosts:
    - host: knowledge.mycompany.com
      paths:
        - path: /
          pathType: Prefix
          backendService: frontend
          backendPort: 3000
        - path: /api
          pathType: Prefix
          backendService: backend
          backendPort: 8000
EOF

helm upgrade enterprise-knowledge-os . \
  --namespace knowledge-os \
  -f my-values.yaml
```

### 6.4 内网 NodePort 模式

无 Ingress Controller 时使用 NodePort 暴露服务：

```bash
cat > nodeport-values.yaml << 'EOF'
backend:
  service:
    type: NodePort
    nodePort: 30800
  image:
    pullPolicy: Never

frontend:
  service:
    type: NodePort
    nodePort: 30300
  image:
    pullPolicy: Never
EOF

helm install enterprise-knowledge-os . \
  --namespace knowledge-os \
  -f nodeport-values.yaml
```

访问方式：
- 后端 API: `http://<任意节点IP>:30800`
- 前端页面: `http://<任意节点IP>:30300`

### 6.5 升级和回滚

```bash
# 升级
helm upgrade enterprise-knowledge-os . --namespace knowledge-os

# 查看历史
helm history enterprise-knowledge-os --namespace knowledge-os

# 回滚到上一版本
helm rollback enterprise-knowledge-os --namespace knowledge-os

# 回滚到指定版本
helm rollback enterprise-knowledge-os 1 --namespace knowledge-os
```

### 6.6 卸载

```bash
helm uninstall enterprise-knowledge-os --namespace knowledge-os
# PVC 默认不随 release 删除，如需清理数据：
kubectl -n knowledge-os delete pvc enterprise-knowledge-os-data
```

### 6.7 水平扩展

```bash
# 临时扩展
kubectl -n knowledge-os scale deployment enterprise-knowledge-os-backend --replicas=3

# 持久化（通过 Helm）
helm upgrade enterprise-knowledge-os . \
  --namespace knowledge-os \
  --set backend.replicaCount=3
```

---

## 7. 数据备份建议

### 7.1 需要备份的数据

| 数据 | 位置 | 说明 |
|---|---|---|
| SQLite 数据库 | `data/agent_memory.db` | 结构化数据：用户、记忆、工作区 |
| ChromaDB 向量库 | `data/chroma_db/` | 向量索引，不可通过 SQLite 恢复 |
| 上传文件 | `data/uploads/` | 用户上传的原始文件 |
| 音视频 | `data/audio_uploads/`, `data/video_uploads/` | 媒体文件 |

### 7.2 Docker 环境备份

```bash
# 压缩备份整个 data 目录
tar czf backup-$(date +%Y%m%d-%H%M%S).tar.gz ./data/

# 定时备份 (crontab)
# 每天凌晨 2 点备份，保留最近 7 天：
# 0 2 * * * cd /opt/knowledge-os && tar czf backups/backup-$(date +\%Y\%m\%d).tar.gz data/ && find backups/ -mtime +7 -delete
```

### 7.3 Kubernetes 环境备份

```bash
# 从 Pod 导出数据
kubectl -n knowledge-os exec deployment/enterprise-knowledge-os-backend -- \
  tar czf - /app/data > backup-$(date +%Y%m%d).tar.gz
```

也可以部署 Kubernetes CronJob 进行自动化备份。

### 7.4 恢复步骤

```bash
# 1. 停止应用
docker compose down

# 2. 备份当前数据（防误操作）
mv data data.broken.$(date +%Y%m%d)

# 3. 解压备份
tar xzf backup-20240601.tar.gz

# 4. 启动
docker compose up -d
```

### 7.5 SQLite 热备份

SQLite 支持在线热备份（`.backup` 命令），不会阻塞读写：

```bash
sqlite3 data/agent_memory.db ".backup backup.db"
```

不建议直接用 `cp` 复制正在写入的 SQLite 文件。

---

## 附录：快速启动检查清单

- [ ] `.env.docker` 中 `DEEPSEEK_API_KEY` 已填写
- [ ] `.env.docker` 中 `JWT_SECRET` 已修改为强随机值
- [ ] 已创建数据目录，磁盘空间 >= 10GB
- [ ] 内网部署：已准备好模型文件和所有镜像
- [ ] 防火墙已开放 8000（后端）和 3000（前端）端口
- [ ] K8s 部署：已创建 `ekos-secrets` 和 `ekos-jwt` Secret
- [ ] 已配置日志收集方案（ELK / Loki / 文件轮转）
- [ ] 已设置定时备份任务并完成首次备份验证
