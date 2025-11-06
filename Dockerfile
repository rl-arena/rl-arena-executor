FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files and generate gRPC code
COPY proto/ ./proto/
RUN python -m grpc_tools.protoc \
    -I./proto \
    --python_out=. \
    --grpc_python_out=. \
    ./proto/executor.proto

# Copy application code
COPY executor/ ./executor/
COPY config/ ./config/

# Create directories for temporary files
RUN mkdir -p /tmp/agent_code /tmp/replays

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV EXECUTOR_HOST=0.0.0.0
ENV EXECUTOR_PORT=50051

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50051'); channel.close()" || exit 1

# Run the executor server
CMD ["python", "-m", "executor.server"]
