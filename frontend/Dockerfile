# Frontend Dockerfile for Engineer Cafe Navigator
# Next.js 15.3.2 frontend

# Base image - Node.js 18
FROM node:18-alpine AS base

# Install pnpm globally
RUN npm install -g pnpm@10.12.1

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml* ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Development stage
FROM base AS development

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Start development server (0.0.0.0 so iPad/other devices can connect)
CMD ["pnpm", "run", "dev:network"]

# Production build stage
FROM base AS builder

# Copy application code
COPY . .

# Build Next.js app
RUN pnpm build

# Production stage
FROM node:18-alpine AS production

# Install pnpm
RUN npm install -g pnpm@10.12.1

WORKDIR /app

# Copy built files from builder
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

# Expose port
EXPOSE 3000

# Start production server
CMD ["pnpm", "start"]
