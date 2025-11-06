# Architecture Documentation: Kubernetes-based Execution

## Overview

The RL Arena Executor now uses Kubernetes to run agent matches in isolated pods. This provides:
- **Better isolation**: Each match runs in its own pod with resource limits
- **Scalability**: K8s handles scheduling and resource management
- **Security**: Network policies and RBAC control access
- **Reliability**: Failed jobs are automatically cleaned up

## Architecture Diagram

```
┌─────────────────┐
│  RL Arena       │
│  Backend (Go)   │
│                 │
│  Sends Docker   │
│  images for     │
│  agents         │
└────────┬────────┘
         │ gRPC RunMatch
         ↓
┌─────────────────────────────────────────────────────┐
│  RL Arena Executor Service (Python gRPC Server)     │
│  - Runs in K8s Deployment (2 replicas)              │
│  - Receives match requests with agent Docker images │
│  - Creates K8s Jobs for each match                  │
└────────┬────────────────────────────────────────────┘
         │ Creates K8s Job
         ↓
┌─────────────────────────────────────────────────────┐
│  Kubernetes Job (Per Match)                         │
│  ┌───────────────────────────────────────────────┐  │
│  │  Init Containers (Agent Images)               │  │
│  │  ┌──────────────┐  ┌──────────────┐          │  │
│  │  │ Agent 1 Init │  │ Agent 2 Init │          │  │
│  │  │ Copy code to │  │ Copy code to │          │  │
│  │  │ shared volume│  │ shared volume│          │  │
│  │  └──────────────┘  └──────────────┘          │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │  Main Container (Orchestrator)                │  │
│  │  - Loads both agents                          │  │
│  │  - Creates RL Arena environment               │  │
│  │  - Runs match loop                            │  │
│  │  - Records replay                             │  │
│  │  - Returns result as JSON                     │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  Shared Volumes:                                     │
│  - agent-code: Agent code from init containers      │
│  - shared-replay: Replay recordings                 │
│  - match-config: ConfigMap with match settings      │
└──────────────────────────────────────────────────────┘
```

## Components

### 1. Executor Service (executor/k8s_runner.py)
- **K8sMatchRunner**: Main class that manages K8s jobs
- Creates ConfigMaps with match configuration
- Creates Jobs with init containers for agents
- Monitors job completion
- Collects results from pod logs

### 2. Match Orchestrator (orchestrator/run_match.py)
- Runs inside K8s job pods
- Loads agent code from shared volume
- Executes match loop
- Records replay
- Outputs result as JSON

### 3. Kubernetes Resources

#### ServiceAccount & RBAC
- **ServiceAccount**: `rl-arena-executor`
- **Permissions**:
  - Create/delete Jobs
  - Read Pod logs
  - Create/delete ConfigMaps

#### Deployment
- **Name**: `rl-arena-executor`
- **Replicas**: 2 (for high availability)
- **Image**: `rl-arena-executor:latest`
- **Port**: 50051 (gRPC)

#### Service
- **Type**: ClusterIP
- **Port**: 50051
- Exposes executor to backend within cluster

## Request Flow

### 1. Backend Sends Match Request
```protobuf
MatchRequest {
  match_id: "match_123"
  environment: "pong"
  agents: [
    {
      agent_id: "agent_1"
      docker_image: "registry.example.com/agents/agent1:v1"
    },
    {
      agent_id: "agent_2"
      docker_image: "registry.example.com/agents/agent2:v1"
    }
  ]
  timeout_sec: 300
  record_replay: true
}
```

### 2. Executor Creates ConfigMap
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: match-config-match_123
data:
  match-config.json: |
    {
      "match_id": "match_123",
      "environment": "pong",
      "agents": [...],
      "timeout_sec": 300,
      "record_replay": true
    }
```

### 3. Executor Creates Job
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: match-match_123
spec:
  template:
    spec:
      initContainers:
        - name: agent-1-init
          image: registry.example.com/agents/agent1:v1
          command: ["cp", "-r", "/app/*", "/agent-code/agent-1/"]
        - name: agent-2-init
          image: registry.example.com/agents/agent2:v1
          command: ["cp", "-r", "/app/*", "/agent-code/agent-2/"]
      containers:
        - name: match-orchestrator
          image: rl-arena-orchestrator:latest
          args: ["--config", "/config/match-config.json"]
          volumeMounts:
            - name: agent-code
              mountPath: /agent-code
            - name: match-config
              mountPath: /config
            - name: shared-replay
              mountPath: /replays
```

### 4. Orchestrator Runs Match
```python
1. Load config from /config/match-config.json
2. Import agent modules from /agent-code/agent-1/ and /agent-code/agent-2/
3. Create rl_arena environment
4. Run match loop:
   - Get actions from both agents
   - Step environment
   - Record frames
5. Save replay to /replays/match_123.json
6. Print result as JSON
```

### 5. Executor Collects Result
- Polls job status until completion
- Reads pod logs
- Parses JSON result from last line
- Returns MatchResponse to backend

### 6. Cleanup
- Delete Job (with propagation=Background)
- Delete ConfigMap
- Pods are automatically removed by K8s

## Configuration

### Executor Config (config/limits.yaml)
```yaml
executor:
  use_k8s: true  # Enable K8s mode

k8s:
  namespace: rl-arena
  orchestrator_image: rl-arena-orchestrator:latest

resource_limits:
  cpu_count: 1
  memory_limit: "512m"
  step_timeout_sec: 5
  match_timeout_sec: 300
```

## Deployment

### Prerequisites
```bash
# 1. Kubernetes cluster (local or cloud)
kubectl cluster-info

# 2. Docker images built and pushed
docker build -t rl-arena-executor:latest .
docker build -f Dockerfile.orchestrator -t rl-arena-orchestrator:latest .
docker push rl-arena-executor:latest
docker push rl-arena-orchestrator:latest
```

### Deploy to K8s
```bash
# Apply all resources
kubectl apply -f k8s/deployment.yaml

# Verify deployment
kubectl get pods -n rl-arena
kubectl get svc -n rl-arena

# Check logs
kubectl logs -n rl-arena -l app=rl-arena-executor
```

### Local Development (Minikube)
```bash
# Start minikube
minikube start

# Build images in minikube
eval $(minikube docker-env)
docker build -t rl-arena-executor:latest .
docker build -f Dockerfile.orchestrator -t rl-arena-orchestrator:latest .

# Deploy
kubectl apply -f k8s/deployment.yaml

# Port forward for testing
kubectl port-forward -n rl-arena svc/rl-arena-executor 50051:50051
```

## Security Features

### 1. Pod Security
- Init containers run agent images in isolated environments
- No network access (unless explicitly enabled)
- Read-only root filesystem (optional)
- Resource limits enforced

### 2. RBAC
- Minimal permissions (only Job/ConfigMap management)
- Namespace-scoped (no cluster-wide access)
- ServiceAccount per service

### 3. Network Policies (TODO)
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: executor-network-policy
spec:
  podSelector:
    matchLabels:
      app: rl-arena-executor
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: rl-arena-backend
  egress:
    - to:
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
```

## Agent Docker Image Requirements

### Image Structure
```dockerfile
FROM python:3.10-slim

# Install dependencies
RUN pip install numpy gymnasium

# Copy agent code
COPY agent.py /app/
COPY requirements.txt /app/

WORKDIR /app

# Agent code should be in /app/
# Must have agent.py or main.py with get_action() function
```

### Agent Code Example
```python
# /app/agent.py
import numpy as np

def get_action(observation):
    """
    Get action from observation.
    
    Args:
        observation: Environment observation
        
    Returns:
        Action (int or array)
    """
    # Your agent logic here
    return np.random.randint(0, 4)
```

## Monitoring & Debugging

### View Running Matches
```bash
# List active jobs
kubectl get jobs -n rl-arena -l component=match-executor

# Watch job status
kubectl get jobs -n rl-arena -w

# View pod logs
kubectl logs -n rl-arena -l match-id=match_123 -f
```

### Debug Failed Match
```bash
# Get job details
kubectl describe job -n rl-arena match-match_123

# Get pod details
kubectl describe pod -n rl-arena -l match-id=match_123

# Check events
kubectl get events -n rl-arena --sort-by='.lastTimestamp'
```

### Resource Usage
```bash
# View resource usage
kubectl top pods -n rl-arena

# View resource requests/limits
kubectl describe deployment -n rl-arena rl-arena-executor
```

## Advantages Over Docker Sandbox

| Feature | Docker Sandbox | Kubernetes |
|---------|---------------|------------|
| Isolation | Container-level | Pod-level |
| Resource Management | Manual | Automatic (K8s scheduler) |
| Scaling | Single machine | Multi-node cluster |
| Fault Tolerance | None | Pod restart, node affinity |
| Monitoring | Docker stats | K8s metrics, Prometheus |
| Cleanup | Manual | Automatic (TTL) |
| Multi-tenancy | Limited | Strong (RBAC, Network Policies) |

## Future Enhancements

1. **Persistent Replay Storage**
   - Use PersistentVolumeClaim for replays
   - Upload to object storage (S3, GCS)

2. **GPU Support**
   - Node selectors for GPU nodes
   - Resource limits for GPUs

3. **Advanced Scheduling**
   - Node affinity for dedicated agent nodes
   - Pod priority classes

4. **Observability**
   - OpenTelemetry tracing
   - Prometheus metrics
   - Grafana dashboards

5. **Cost Optimization**
   - Spot instances for match execution
   - Horizontal pod autoscaling
   - Cluster autoscaling
