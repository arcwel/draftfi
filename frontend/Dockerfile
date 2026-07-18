# Containerized frontend runs the Vite dev server so its /api proxy can reach
# the backend service by name (VITE_PROXY_TARGET). For a static production
# deploy, run `npm run build` and serve `dist/` behind a reverse proxy instead.
FROM node:20-slim
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
