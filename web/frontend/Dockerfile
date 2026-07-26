# Stage 1: build React static bundle
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: serve bằng nginx, proxy /api sang service web-api (không cần CORS
# vì trình duyệt chỉ thấy 1 origin duy nhất — xem nginx.conf)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
