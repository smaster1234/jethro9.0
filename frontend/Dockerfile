# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first for better caching
COPY package.json package-lock.json* ./

# Install dependencies (with fallback)
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install

# Copy source files
COPY . .

# Build argument for API URL (with default fallback)
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}

# Build the app
RUN npm run build

# Production stage
FROM node:20-alpine AS runner

WORKDIR /app

# Install serve
RUN npm install -g serve@14

# Copy built files from builder
COPY --from=builder /app/dist ./dist

# Default port
ENV PORT=3000

# Start the server
CMD ["sh", "-c", "serve dist -s -l $PORT"]
