# 这个文件告诉 Docker：如何先用 Node 编译前端，再用 Nginx 托管静态网页

# ========== 第一阶段：用 Node 20 编译 Vue 项目 ==========
FROM node:20-alpine AS builder

WORKDIR /app

# 先复制 package 文件，利用缓存加速 npm install
COPY client/package.json client/package-lock.json* ./
RUN npm ci

# 复制前端全部源码（本项目前端在 client/ 目录）
COPY client/ .

# 生产环境通过 Nginx 同域反代 /api；接口路径已含 /api 前缀，baseURL 留空即可
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# 编译，产物输出到 dist/ 目录
RUN npm run build

# ========== 第二阶段：用 Nginx 托管编译好的静态文件 ==========
FROM nginx:1.27-alpine

# 复制 Nginx 配置（含 /api 反向代理）
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# ⚠️ 请确认构建产物目录为 dist/（Vite 默认输出路径）
# 若你的构建目录不同，请修改下面 COPY 的源路径
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
