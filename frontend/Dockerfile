# ==============================================================================
# Multi-Stage Production Dockerfile for LLM-DPECI React Frontend
# ==============================================================================
# Stage 1: Build static production bundle using Node.js
# Stage 2: Serve static assets using high-performance Nginx Alpine web server
# ==============================================================================

# ------------------------------------------------------------------------------
# STAGE 1: BUILDER
# ------------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package definitions first for optimal layer caching
COPY package.json package-lock.json* ./

# Install exact dependencies
RUN npm ci --prefer-offline --no-audit || npm install

# Copy source code and build production assets
COPY . .
RUN npm run build

# ------------------------------------------------------------------------------
# STAGE 2: RUNNER (NGINX)
# ------------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runner

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled SPA bundle from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom reverse proxy and SPA routing configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP port
EXPOSE 80

# Healthcheck to ensure Nginx is actively responding to requests
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1

# Start Nginx in the foreground (daemon off is mandatory for Docker containers)
CMD ["nginx", "-g", "daemon off;"]
