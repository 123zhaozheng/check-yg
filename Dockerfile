# syntax=docker/dockerfile:1

# ===========================================================================
# Stage 1: fe-build — 构建前端 dist
# 用 Node 22：pnpm-workspace.yaml 的 allowBuilds（esbuild 构建许可）是 pnpm 11
# 特性，pnpm 11 需 Node 22.13+。锁文件由 pnpm 11 生成，故此处用 pnpm 11。
# ===========================================================================
FROM node:22-alpine AS fe-build
WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@11.1.3 --activate
# 国内 npm 镜像：裸连 registry.npmjs.org 仅 1-15 KiB/s 且频繁断连重试
RUN pnpm config set registry https://registry.npmmirror.com
# 利用层缓存：先拷锁文件与 package 元数据，再装依赖
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
# 再拷源码
COPY frontend/ ./
RUN pnpm build
# 产物位于 /app/frontend/dist

# ===========================================================================
# Stage 2: be-deps — 安装后端依赖（uv sync 到独立 venv）
# ===========================================================================
FROM python:3.13-slim AS be-deps
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
WORKDIR /app/backend
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv
# pyproject 的依赖全在 dependencies 里、无 dev group，全装即可
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen

# ===========================================================================
# Stage 3: runtime — 最终镜像
# ===========================================================================
FROM python:3.13-slim AS runtime
WORKDIR /app/backend

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    # 绝对路径覆盖默认的 ../frontend/dist（相对 backend/ 解析）
    FRONTEND_DIST=/app/frontend/dist \
    # compose 内用 service 名 postgres，不是 localhost
    DATABASE_URL=postgresql+asyncpg://check_yg:check_yg@postgres:5432/check_yg \
    JWT_SECRET=change-me-in-production \
    UPLOAD_DIR=/app/backend/data/uploads \
    OUTPUT_DIR=/app/backend/data/outputs

# 依赖 venv
COPY --from=be-deps /opt/venv /opt/venv
# 后端业务代码（app/、migrations/、alembic.ini 等）
COPY backend/ ./
# 前端构建产物（静态同源）
COPY --from=fe-build /app/frontend/dist /app/frontend/dist

# 运行时产物目录（亦由 compose volume 持久化）
RUN mkdir -p data/uploads data/outputs

EXPOSE 8000
# alembic 迁移 + seed 在 lifespan 内完成（uvicorn 启动即就绪，无需单独迁移步骤）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
