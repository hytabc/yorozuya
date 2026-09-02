# 开发镜像：node_modules 固定在镜像内（Linux 版依赖，含 vite 可执行文件）。
# 源码由 docker-compose.yml 按子路径挂载（src / index.html / vite.config.js）实现热更新，
# 避免把宿主机（其他平台）的 node_modules 带入容器。
FROM node:22-alpine AS dev
WORKDIR /app
ENV NODE_ENV=development
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
EXPOSE 8889
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "8889"]

# 生产构建
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
