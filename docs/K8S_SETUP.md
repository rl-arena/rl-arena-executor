# Kubernetes-based Executor Setup Guide

## Quick Start

### 1. Prerequisites
- Kubernetes cluster (minikube, GKE, EKS, AKS, etc.)
- kubectl configured
- Docker for building images

### 2. Build Images

```bash
# Navigate to executor directory
cd rl-arena-executor

# Build executor service image
docker build -t rl-arena-executor:latest .

# Build orchestrator image
docker build -f Dockerfile.orchestrator -t rl-arena-orchestrator:latest .

# If using registry, push images
docker tag rl-arena-executor:latest your-registry.com/rl-arena-executor:latest
docker push your-registry.com/rl-arena-executor:latest

docker tag rl-arena-orchestrator:latest your-registry.com/rl-arena-orchestrator:latest
docker push your-registry.com/rl-arena-orchestrator:latest
```

### 3. Deploy to Kubernetes

```bash
# Apply all K8s resources
kubectl apply -f k8s/deployment.yaml

# Check deployment status
kubectl get all -n rl-arena

# Expected output:
# NAME                                      READY   STATUS    RESTARTS   AGE
# pod/rl-arena-executor-xxxxxxxxxx-xxxxx    1/1     Running   0          30s
# pod/rl-arena-executor-xxxxxxxxxx-xxxxx    1/1     Running   0          30s
#
# NAME                        TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)     AGE
# service/rl-arena-executor   ClusterIP   10.96.xxx.xxx   <none>        50051/TCP   30s
#
# NAME                                READY   UP-TO-DATE   AVAILABLE   AGE
# deployment.apps/rl-arena-executor   2/2     2            2           30s
```

### 4. Test the Service

```bash
# Port forward for local testing
kubectl port-forward -n rl-arena svc/rl-arena-executor 50051:50051

# In another terminal, test with grpcurl
grpcurl -plaintext localhost:50051 executor.Executor/HealthCheck
```

## Local Development with Minikube

### 1. Start Minikube

```bash
# Start with sufficient resources
minikube start --cpus=4 --memory=8192 --disk-size=50g

# Enable metrics
minikube addons enable metrics-server
```

### 2. Build Images in Minikube

```bash
# Use minikube's Docker daemon
eval $(minikube docker-env)

# Build images
docker build -t rl-arena-executor:latest .
docker build -f Dockerfile.orchestrator -t rl-arena-orchestrator:latest .

# Verify images
docker images | grep rl-arena
```

### 3. Deploy

```bash
kubectl apply -f k8s/deployment.yaml
```

### 4. Access Service

```bash
# Option 1: Port forward
kubectl port-forward -n rl-arena svc/rl-arena-executor 50051:50051

# Option 2: Use minikube service
minikube service -n rl-arena rl-arena-executor --url
```

## Production Deployment (GKE Example)

### 1. Create GKE Cluster

```bash
gcloud container clusters create rl-arena-cluster \
  --region us-central1 \
  --num-nodes 3 \
  --machine-type n1-standard-4 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10
```

### 2. Configure kubectl

```bash
gcloud container clusters get-credentials rl-arena-cluster --region us-central1
```

### 3. Create Container Registry

```bash
# Enable Artifact Registry
gcloud services enable artifactregistry.googleapis.com

# Create repository
gcloud artifacts repositories create rl-arena-images \
  --repository-format=docker \
  --location=us-central1

# Configure Docker auth
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### 4. Build and Push Images

```bash
# Tag images
docker tag rl-arena-executor:latest \
  us-central1-docker.pkg.dev/YOUR-PROJECT/rl-arena-images/executor:latest

docker tag rl-arena-orchestrator:latest \
  us-central1-docker.pkg.dev/YOUR-PROJECT/rl-arena-images/orchestrator:latest

# Push images
docker push us-central1-docker.pkg.dev/YOUR-PROJECT/rl-arena-images/executor:latest
docker push us-central1-docker.pkg.dev/YOUR-PROJECT/rl-arena-images/orchestrator:latest
```

### 5. Update Deployment YAML

```yaml
# Edit k8s/deployment.yaml
# Update image references:
containers:
  - name: executor
    image: us-central1-docker.pkg.dev/YOUR-PROJECT/rl-arena-images/executor:latest
```

### 6. Deploy

```bash
kubectl apply -f k8s/deployment.yaml

# Create ingress (optional)
kubectl apply -f k8s/ingress.yaml
```

## Configuration

### Update Executor Config

```bash
# Edit ConfigMap
kubectl edit configmap -n rl-arena executor-config

# Or apply from file
kubectl apply -f k8s/configmap.yaml
```

### Resource Limits

```yaml
# Edit deployment to change resource limits
spec:
  template:
    spec:
      containers:
        - name: executor
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 2000m
              memory: 2Gi
```

## Monitoring

### View Logs

```bash
# All executor logs
kubectl logs -n rl-arena -l app=rl-arena-executor -f

# Specific pod
kubectl logs -n rl-arena rl-arena-executor-xxxxxxxxxx-xxxxx -f

# Match job logs
kubectl logs -n rl-arena -l match-id=match_123 -f
```

### Check Resource Usage

```bash
# Pod resources
kubectl top pods -n rl-arena

# Node resources
kubectl top nodes
```

### View Active Matches

```bash
# List running match jobs
kubectl get jobs -n rl-arena -l component=match-executor

# Watch jobs
watch kubectl get jobs -n rl-arena
```

## Troubleshooting

### Executor Not Starting

```bash
# Check pod status
kubectl describe pod -n rl-arena -l app=rl-arena-executor

# Common issues:
# - ImagePullBackOff: Check image name and registry access
# - CrashLoopBackOff: Check logs for errors
# - Pending: Check resource availability
```

### Match Job Failing

```bash
# Get job details
kubectl describe job -n rl-arena match-match_123

# Check pod events
kubectl get events -n rl-arena --field-selector involvedObject.name=match-match_123

# View init container logs
kubectl logs -n rl-arena match-match_123-xxxxx -c agent-1-init
kubectl logs -n rl-arena match-match_123-xxxxx -c agent-2-init

# View orchestrator logs
kubectl logs -n rl-arena match-match_123-xxxxx -c match-orchestrator
```

### Permission Issues

```bash
# Check ServiceAccount
kubectl get sa -n rl-arena rl-arena-executor

# Check RoleBinding
kubectl get rolebinding -n rl-arena rl-arena-executor-binding

# Test permissions
kubectl auth can-i create jobs --as=system:serviceaccount:rl-arena:rl-arena-executor -n rl-arena
```

## Scaling

### Horizontal Pod Autoscaler

```bash
# Create HPA
kubectl autoscale deployment rl-arena-executor \
  -n rl-arena \
  --cpu-percent=70 \
  --min=2 \
  --max=10

# View HPA status
kubectl get hpa -n rl-arena
```

### Cluster Autoscaler

```bash
# Enable GKE autoscaling (if not already enabled)
gcloud container clusters update rl-arena-cluster \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 20 \
  --region us-central1
```

## Cleanup

### Delete All Resources

```bash
# Delete namespace (removes everything)
kubectl delete namespace rl-arena

# Or delete individual resources
kubectl delete -f k8s/deployment.yaml
```

### Delete GKE Cluster

```bash
gcloud container clusters delete rl-arena-cluster --region us-central1
```

## Integration with Backend

### Update Backend Configuration

The backend should connect to the executor service:

```go
// In backend config
executorClient := executor.NewClient("rl-arena-executor.rl-arena.svc.cluster.local:50051")
```

### Service Discovery

Within the same K8s cluster, use DNS:
```
rl-arena-executor.rl-arena.svc.cluster.local:50051
```

### External Access (if needed)

```yaml
# Create LoadBalancer service
apiVersion: v1
kind: Service
metadata:
  name: rl-arena-executor-external
  namespace: rl-arena
spec:
  type: LoadBalancer
  ports:
    - port: 50051
      targetPort: 50051
  selector:
    app: rl-arena-executor
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy Executor

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build and push images
        run: |
          docker build -t ${{ secrets.REGISTRY }}/executor:${{ github.sha }} .
          docker push ${{ secrets.REGISTRY }}/executor:${{ github.sha }}
      
      - name: Deploy to K8s
        run: |
          kubectl set image deployment/rl-arena-executor \
            executor=${{ secrets.REGISTRY }}/executor:${{ github.sha }} \
            -n rl-arena
```

## Next Steps

1. Set up monitoring (Prometheus/Grafana)
2. Configure log aggregation (ELK/Loki)
3. Implement replay storage (S3/GCS)
4. Add network policies for security
5. Set up backup and disaster recovery
