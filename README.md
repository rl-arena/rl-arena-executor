# RL-Arena Executor

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python)](https://www.python.org)
[![gRPC](https://img.shields.io/badge/gRPC-1.60+-00ADD8?style=flat&logo=google)](https://grpc.io)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.28+-326CE5?style=flat&logo=kubernetes)](https://kubernetes.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

**RL-Arena Executor** is a secure, scalable microservice for executing reinforcement learning agent matches in isolated Kubernetes pods with Docker-based agents.

##  Features

- **Kubernetes-Native**: Leverages K8s Jobs for scheduling and isolation
- **Docker Agent Support**: Agents packaged as Docker images
- **gRPC API**: High-performance bidirectional streaming
- **Secure Execution**: Pod-level isolation with RBAC and resource limits
- **Replay Recording**: Frame-by-frame match recordings in JSON format
- **Auto-Cleanup**: Automatic cleanup of completed and failed jobs
- **Scalable**: Handles multiple concurrent matches across cluster nodes
- **Resource Management**: CPU and memory limits enforced by Kubernetes

##  Architecture

```
Backend  Executor Service (gRPC)  K8s Job Creation  Match Execution
            (Deployment)                  
                                   Init Containers (Agent Images)
                                          
                                   Orchestrator Container
                                          
                                   Match Result + Replay
```

**Components:**
- **Executor Service**: gRPC server that receives match requests
- **Kubernetes Jobs**: Isolated match execution environment
- **Init Containers**: Load agent Docker images
- **Orchestrator**: Runs matches and records replays
- **ConfigMap**: Environment configurations and limits

##  Project Structure

```
executor/
 server.py              # gRPC server entry point
 k8s_runner.py         # Kubernetes Job runner
 match_runner.py       # Match execution logic
 replay_recorder.py    # Replay recording system
 validation.py         # Agent code validation
 sandbox.py            # Security sandbox
 config.py             # Configuration management

orchestrator/
 run_match.py          # Runs inside K8s pods

k8s/
 deployment.yaml       # Kubernetes manifests (Deployment, RBAC, Service)

proto/
 executor.proto        # gRPC service definitions

config/
 limits.yaml           # Resource limits and settings
```

##  Quick Start

### Prerequisites

- Python 3.10+
- Kubernetes cluster (minikube, GKE, EKS, AKS)
- kubectl configured
- Docker

### Installation

1. Clone the repository:
```bash
git clone https://github.com/rl-arena/rl-arena-executor.git
cd rl-arena-executor
```

2. Build Docker images:
```bash
# Build executor service
docker build -t rl-arena-executor:latest .

# Build orchestrator
docker build -f Dockerfile.orchestrator -t rl-arena-orchestrator:latest .
```

3. Deploy to Kubernetes:
```bash
kubectl apply -f k8s/deployment.yaml
```

4. Verify deployment:
```bash
kubectl get pods -n rl-arena
kubectl get svc -n rl-arena
```

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

# Run tests
pytest -v

# Start server locally
python -m executor.server
```

##  Configuration

Edit `config/limits.yaml`:

```yaml
executor:
  use_k8s: true                   # Enable Kubernetes mode

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

##  gRPC API

### RunMatch - Execute Agent Match

**Request:**
```protobuf
message MatchRequest {
  string match_id = 1;              // Unique match ID
  string environment = 2;            // Environment (e.g., "pong")
  repeated AgentData agents = 3;     // Agent list (exactly 2)
  uint32 timeout_sec = 4;            // Match timeout
  bool record_replay = 5;            // Record replay data
}

message AgentData {
  string agent_id = 1;               // Agent identifier
  string docker_image = 5;           // Docker image URL
  string version = 3;                // Agent version
  map<string, string> metadata = 4;  // Additional metadata
}
```

**Response:**
```protobuf
message MatchResponse {
  string match_id = 1;               // Match ID
  MatchStatus status = 2;            // SUCCESS/ERROR/TIMEOUT
  string winner_agent_id = 3;        // Winner (empty for draw)
  repeated AgentResult agent_results = 4;
  string replay_url = 5;             // Replay file path
  string error_message = 6;          // Error details
  uint32 total_steps = 7;            // Steps executed
  double execution_time_sec = 8;     // Execution time
}
```

### Example Usage

```python
import grpc
from proto import executor_pb2, executor_pb2_grpc

# Connect to executor
channel = grpc.insecure_channel('localhost:50051')
stub = executor_pb2_grpc.ExecutorStub(channel)

# Submit match
request = executor_pb2.MatchRequest(
    match_id="match_123",
    environment="pong",
    agents=[
        executor_pb2.AgentData(
            agent_id="agent1",
            docker_image="myregistry/agent1:v1.0",
            version="1.0"
        ),
        executor_pb2.AgentData(
            agent_id="agent2",
            docker_image="myregistry/agent2:v2.1",
            version="2.1"
        ),
    ],
    timeout_sec=300,
    record_replay=True
)

response = stub.RunMatch(request)
print(f"Winner: {response.winner_agent_id}")
print(f"Replay: {response.replay_url}")
```

##  Security

**Kubernetes-Level:**
- Pod isolation for each match
- Resource limits (CPU, memory)
- RBAC with minimal permissions
- Non-root pod execution
- Dropped Linux capabilities

**Application-Level:**
- Code syntax and security validation
- Timeout enforcement (step and match level)
- Input validation and sanitization
- Isolated replay storage

##  Kubernetes Operations

### Monitoring

```bash
# Watch executor pods
kubectl get pods -n rl-arena -w

# Get running matches
kubectl get jobs -n rl-arena

# Check match logs
kubectl logs -n rl-arena job/match-<match-id>

# Service logs
kubectl logs -n rl-arena -l app=rl-arena-executor -f
```

### Scaling

```bash
# Scale replicas
kubectl scale deployment rl-arena-executor -n rl-arena --replicas=5

# Enable autoscaling
kubectl autoscale deployment rl-arena-executor -n rl-arena \
  --min=2 --max=10 --cpu-percent=80
```

### Troubleshooting

```bash
# Check pod status
kubectl describe pod -n rl-arena -l app=rl-arena-executor

# Get events
kubectl get events -n rl-arena --sort-by='.lastTimestamp'

# Debug failed match
kubectl logs -n rl-arena job/match-<match-id> --all-containers=true

# Access pod shell
kubectl exec -it -n rl-arena <pod-name> -- /bin/bash
```

##  Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=executor --cov-report=html

# Run specific test
pytest tests/test_k8s_runner.py -v
```

##  Documentation

- [Kubernetes Architecture](docs/K8S_ARCHITECTURE.md) - Detailed architecture
- [Kubernetes Setup](docs/K8S_SETUP.md) - Setup guide
- [Agent Image Guide](docs/AGENT_IMAGE_GUIDE.md) - Building agent images

##  Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

##  Related Projects

- [rl-arena-backend](https://github.com/rl-arena/rl-arena-backend) - Go REST API server
- [rl-arena-web](https://github.com/rl-arena/rl-arena-web) - React web frontend
- [rl-arena-env](https://github.com/rl-arena/rl-arena-env) - RL environment library
