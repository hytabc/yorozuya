# 开发镜像：源码通过 docker-compose.dev.yml 挂载到 /app，Vite 热更新即时生效
FROM node:22-alpine AS dev
WORKDIR /app
ENV NODE_ENV=development
COPY package.json package-lock.json ./
RUN npm ci
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
