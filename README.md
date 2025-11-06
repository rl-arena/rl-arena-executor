# RL Arena Executor

A secure, scalable microservice for executing reinforcement learning agent matches in isolated Kubernetes pods.

## Overview

The RL Arena Executor is a gRPC-based service that:
- Receives agent Docker images from the backend
- Creates Kubernetes Jobs to run matches in isolated pods
- Executes RL agent code with resource limits
- Records match replays with frame-by-frame data
- Returns match results to the backend

## Key Features

- **Kubernetes-Native**: Leverages K8s for scheduling, isolation, and resource management
- **Docker Image Support**: Agents packaged as Docker images for consistency
- **Secure Execution**: Pod-level isolation with RBAC and resource limits
- **Scalable**: Handles multiple concurrent matches across cluster nodes
- **gRPC API**: High-performance bidirectional streaming support
- **Replay Recording**: Full match recordings with observations, actions, and rewards
- **Auto-Cleanup**: Failed jobs and completed matches are automatically cleaned up

## Architecture

```
Backend → Executor Service (gRPC) → K8s Job Creation → Match Execution
            (Deployment)                  ↓
                                   Init Containers (Agent Images)
                                          ↓
                                   Orchestrator Container
                                          ↓
                                   Match Result
```

See [K8S_ARCHITECTURE.md](docs/K8S_ARCHITECTURE.md) for detailed architecture documentation.

## Project Structure

```
rl-arena-executor/
├── README.md
├── Dockerfile                      # Executor service Docker image
├── Dockerfile.orchestrator         # Orchestrator Docker image
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── Makefile
│
├── proto/
│   └── executor.proto              # gRPC service definitions (with docker_image field)
│
├── executor/
│   ├── __init__.py
│   ├── server.py                   # gRPC server entry point
│   ├── k8s_runner.py              # Kubernetes-based match runner (NEW)
│   ├── match_runner.py             # Legacy match runner
│   ├── sandbox.py                  # Docker sandbox (legacy)
│   ├── utils.py                    # Utility functions
│   ├── validation.py               # Agent code validation
│   ├── replay_recorder.py          # Match replay recording
│   └── config.py                   # Configuration management
│
├── orchestrator/                   # NEW: Runs inside K8s pods
│   └── run_match.py               # Match execution logic
│
├── tests/
│   ├── __init__.py
│   ├── test_match_runner.py
│   ├── test_sandbox.py
│   └── test_validation.py
│
├── k8s/                           # NEW: Kubernetes manifests
│   └── deployment.yaml            # Executor deployment, RBAC, etc.
│
├── docs/                          # NEW: Documentation
│   ├── K8S_ARCHITECTURE.md        # Architecture details
│   └── K8S_SETUP.md              # Setup guide
│
└── config/
    └── limits.yaml                 # Resource limits and settings
```

## Installation

### Prerequisites

- Python 3.10 or higher
- Kubernetes cluster (minikube, GKE, EKS, AKS, etc.)
- kubectl configured
- Docker for building images
- gRPC tools

### Quick Start with Kubernetes

```bash
# 1. Clone repository
git clone https://github.com/rl-arena/rl-arena-executor.git
cd rl-arena-executor

# 2. Build Docker images
docker build -t rl-arena-executor:latest .
docker build -f Dockerfile.orchestrator -t rl-arena-orchestrator:latest .

# 3. Deploy to Kubernetes
kubectl apply -f k8s/deployment.yaml

# 4. Verify deployment
kubectl get pods -n rl-arena
kubectl get svc -n rl-arena

# 5. Test connection
kubectl port-forward -n rl-arena svc/rl-arena-executor 50051:50051
```

See [K8S_SETUP.md](docs/K8S_SETUP.md) for detailed setup instructions.

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Generate gRPC code
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=. \
    --grpc_python_out=. \
    ./proto/executor.proto

# Or use make
make proto

# Run tests
pytest -v
```

## Configuration

### Kubernetes Configuration

Edit `config/limits.yaml` to configure the executor:

```yaml
executor:
  use_k8s: true                   # Enable Kubernetes mode (recommended)

k8s:
  namespace: rl-arena             # K8s namespace
  orchestrator_image: rl-arena-orchestrator:latest

resource_limits:
  cpu_count: 1                    # CPU cores per match
  memory_limit: "512m"            # Memory per match
  step_timeout_sec: 5             # Timeout per agent step
  match_timeout_sec: 300          # Total match timeout (5 minutes)

sandbox:
  tmp_dir: "/tmp/agent_code"
  replay_dir: "/tmp/replays"
  max_code_size_mb: 50

validation:
  max_file_size_mb: 10
  forbidden_imports:
    - "os.system"
    - "subprocess"
    - "eval"
```

### Environment Variables

```bash
# Executor service
EXECUTOR_HOST=0.0.0.0           # gRPC server host
EXECUTOR_PORT=50051             # gRPC server port
CONFIG_PATH=/config/config.yaml # Config file path
LOG_LEVEL=INFO                  # Logging level

# Kubernetes
KUBECONFIG=/path/to/kubeconfig  # K8s config (optional)
```

## Usage

### Starting the Executor Service

#### In Kubernetes (Production)

```bash
# Deploy to K8s
kubectl apply -f k8s/deployment.yaml

# Check status
kubectl get pods -n rl-arena
kubectl logs -n rl-arena -l app=rl-arena-executor -f

# Access from within cluster
# Service endpoint: rl-arena-executor.rl-arena.svc.cluster.local:50051
```

#### Local Development

```bash
# Start gRPC server locally
python -m executor.server

# Or with make
make dev-run

# With custom config
EXECUTOR_HOST=0.0.0.0 EXECUTOR_PORT=50051 python -m executor.server
```

### gRPC API Reference

#### 1. RunMatch - Execute Agent Match

**Request:**
```protobuf
message MatchRequest {
  string match_id = 1;              // Unique match ID
  string environment = 2;            // Environment name (e.g., "pong")
  repeated AgentData agents = 3;     // Agent list (exactly 2)
  uint32 timeout_sec = 4;            // Match timeout
  bool record_replay = 5;            // Record replay data
}

message AgentData {
  string agent_id = 1;               // Agent identifier
  string docker_image = 5;           // Docker image URL (NEW!)
  string version = 3;                // Agent version
  map<string, string> metadata = 4;  // Additional metadata
}
```

**Response:**
```protobuf
message MatchResponse {
  string match_id = 1;               // Match ID
  MatchStatus status = 2;            // SUCCESS/ERROR/TIMEOUT
  string winner_agent_id = 3;        // Winner (or empty for draw)
  repeated AgentResult agent_results = 4;
  string replay_url = 5;             // Replay file path/URL
  string error_message = 6;          // Error details (if failed)
  uint32 total_steps = 7;            // Steps executed
  double execution_time_sec = 8;     // Execution time
}
```

**Example Usage (Backend):**

```python
import grpc
from proto import executor_pb2, executor_pb2_grpc

# Connect to executor service (in K8s)
channel = grpc.insecure_channel('rl-arena-executor.rl-arena.svc.cluster.local:50051')
stub = executor_pb2_grpc.ExecutorStub(channel)

# Submit match with Docker images
request = executor_pb2.MatchRequest(
    match_id="match_123",
    environment="pong",
    agents=[
        executor_pb2.AgentData(
            agent_id="agent1",
            docker_image="myregistry/agent1:v1.0",  # Docker image URL
            version="1.0",
            metadata={"user_id": "user_123"}
        ),
        executor_pb2.AgentData(
            agent_id="agent2",
            docker_image="myregistry/agent2:v2.1",  # Docker image URL
            version="2.1",
            metadata={"user_id": "user_456"}
        ),
    ],
    timeout_sec=300,
    record_replay=True
)

response = stub.RunMatch(request)
print(f"Match result: {response.status}")
print(f"Winner: {response.winner_agent_id}")
print(f"Replay: {response.replay_url}")
print(f"Steps: {response.total_steps}")
```

#### 2. ValidateAgent - Validate Agent Code

```protobuf
message ValidationRequest {
  string agent_id = 1;
  bytes code_zip = 2;                // Zipped agent code
  string environment = 3;
}

message ValidationResponse {
  bool valid = 1;
  repeated string errors = 2;
  repeated string warnings = 3;
}
```

#### 3. HealthCheck - Service Health

```protobuf
message HealthCheckRequest {}

message HealthCheckResponse {
  bool healthy = 1;
  string version = 2;
  uint32 active_matches = 3;        // Currently running matches
}
```

### Kubernetes Operations

#### Monitoring Matches

```bash
# Watch executor pods
kubectl get pods -n rl-arena -w

# Get running matches (Jobs)
kubectl get jobs -n rl-arena

# Check specific match logs
kubectl logs -n rl-arena job/match-<match-id>

# Get match details
kubectl describe job -n rl-arena match-<match-id>
```

#### Troubleshooting

```bash
# Check executor service logs
kubectl logs -n rl-arena -l app=rl-arena-executor -f

# Check events
kubectl get events -n rl-arena --sort-by='.lastTimestamp'

# Debug failed match
kubectl logs -n rl-arena job/match-<match-id> --all-containers=true

# Access executor pod shell
kubectl exec -it -n rl-arena <pod-name> -- /bin/bash
```

#### Scaling

```bash
# Scale executor replicas
kubectl scale deployment rl-arena-executor -n rl-arena --replicas=5

# Enable autoscaling
kubectl autoscale deployment rl-arena-executor -n rl-arena \
  --min=2 --max=10 --cpu-percent=80
```

For detailed Kubernetes setup and operations, see [K8S_SETUP.md](docs/K8S_SETUP.md).
```

## Development

### Building Docker Images

```bash
# Build orchestrator image
docker build -t rl-arena-orchestrator:latest -f Dockerfile.orchestrator .

# Build executor service image
docker build -t rl-arena-executor:latest .

# Or use make
make build-all
```

### Running Tests

```bash
# Run all tests
pytest

# Or use make
make test

# Run with coverage
pytest --cov=executor --cov-report=html

# Run specific test file
pytest tests/test_k8s_runner.py -v
```

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Or manually
black executor/ tests/ orchestrator/
ruff executor/ tests/ orchestrator/
mypy executor/
```

### Local Development with Minikube

```bash
# Start minikube
minikube start

# Build and load images
eval $(minikube docker-env)
docker build -t rl-arena-executor:latest .
docker build -t rl-arena-orchestrator:latest -f Dockerfile.orchestrator .

# Deploy
kubectl apply -f k8s/deployment.yaml

# Test
kubectl port-forward -n rl-arena svc/rl-arena-executor 50051:50051

# Run sample match
python examples/run_sample_match.py
```
```

## Security

The executor implements multiple security layers:

### Kubernetes-Level Security
1. **Pod Isolation**: Each match runs in an isolated K8s Job
2. **Resource Limits**: CPU and memory constraints enforced by K8s
3. **RBAC**: ServiceAccount with minimal permissions (Job/ConfigMap only)
4. **Network Policies**: Optional network isolation between pods
5. **SecurityContext**: Pods run as non-root with dropped capabilities

### Application-Level Security
6. **Code Validation**: Syntax and security checks before execution
7. **Timeout Enforcement**: Step and match-level timeouts
8. **Sandbox Environment**: Agent code isolated from host system
9. **Input Validation**: All gRPC inputs validated and sanitized
10. **Replay Isolation**: Replay files stored in isolated volume

For security configuration details, see [K8S_ARCHITECTURE.md](docs/K8S_ARCHITECTURE.md#security-features).

## Implementation Status

### Completed ✅
- **Kubernetes Architecture**: Full K8s-based execution with Jobs
- **gRPC Proto**: Agent match execution and Docker image support
- **K8s Match Runner**: Job creation, monitoring, and cleanup
- **Match Orchestrator**: Runs matches inside K8s pods
- **Configuration Management**: K8s ConfigMaps and YAML config
- **Agent Validation**: Syntax and security checks
- **Replay Recording**: JSON-based replay system
- **Resource Limits**: K8s resource quotas and limits
- **RBAC & Security**: ServiceAccount, Role, RoleBinding
- **Documentation**: Complete K8s setup and architecture docs
- **Docker Images**: Executor and Orchestrator Dockerfiles

### Legacy Components �
- **Docker Sandbox**: Original Docker-based runner (deprecated)
- **Local Execution**: Direct code execution mode (deprecated)

### Planned Enhancements 📋
- **Metrics & Monitoring**: Prometheus integration
- **Distributed Tracing**: OpenTelemetry support
- **Agent Caching**: Cache Docker images for faster startup
- **GPU Support**: NVIDIA GPU scheduling for ML agents
- **Multi-Cluster**: Federation across multiple K8s clusters
- **Priority Queues**: Match priority and scheduling
- **Cost Optimization**: Spot instances and autoscaling

## Troubleshooting

### Kubernetes Issues

#### Executor pods not starting
```bash
# Check pod status
kubectl describe pod -n rl-arena -l app=rl-arena-executor

# Check logs
kubectl logs -n rl-arena -l app=rl-arena-executor --tail=50

# Common fixes:
# - Verify images are built and pushed
# - Check RBAC permissions
# - Verify ConfigMap exists
```

#### Match Jobs stuck in Pending
```bash
# Check Job status
kubectl describe job -n rl-arena match-<match-id>

# Common issues:
# - Insufficient cluster resources
# - Image pull errors (check image exists and is accessible)
# - PVC not bound (check storage class)
```

#### Cannot pull agent Docker images
```bash
# Verify image exists
docker pull <agent-image>

# Check image pull secrets (if using private registry)
kubectl get secrets -n rl-arena

# Add image pull secret to ServiceAccount
kubectl patch serviceaccount rl-arena-executor -n rl-arena \
  -p '{"imagePullSecrets": [{"name": "regcred"}]}'
```

### gRPC Connection Issues

```bash
# Check service is running (inside cluster)
kubectl get svc -n rl-arena

# Test connection from pod
kubectl run test-pod -n rl-arena --rm -it --image=alpine/curl -- sh
# Inside pod: curl -v rl-arena-executor:50051

# Check executor logs
kubectl logs -n rl-arena -l app=rl-arena-executor -f | grep -i error
```

### Match Execution Failures

```bash
# Get failed match logs
kubectl logs -n rl-arena job/match-<match-id> --all-containers

# Check orchestrator container specifically
kubectl logs -n rl-arena job/match-<match-id> -c orchestrator

# Check agent init containers
kubectl logs -n rl-arena job/match-<match-id> -c agent1
kubectl logs -n rl-arena job/match-<match-id> -c agent2

# Common issues:
# - Agent code errors (check agent logs)
# - Timeout exceeded (increase timeout_sec)
# - Resource limits too low (increase CPU/memory)
```

For more troubleshooting tips, see [K8S_SETUP.md](docs/K8S_SETUP.md#troubleshooting).

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Related Projects

- [rl-arena-env](https://github.com/rl-arena/rl-arena-env): Environment library
- [rl-arena-backend](https://github.com/rl-arena/rl-arena-backend): Backend API
- [rl-arena-web](https://github.com/rl-arena/rl-arena-web): Web interface
