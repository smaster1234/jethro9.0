# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install ALL dependencies (including devDependencies for build)
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install --legacy-peer-deps

# Copy source files
COPY . .

# Build argument for API URL
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}

# Build the app
RUN npm run build

# Production stage - simple static server
FROM node:20-alpine

WORKDIR /app

# Install serve globally
RUN npm install -g serve@14

# Copy only the built files
COPY --from=builder /app/dist ./dist

# Railway sets PORT automatically
ENV PORT=3000
EXPOSE 3000

# Run serve directly (no npm needed)
CMD serve dist -s -l $PORT
