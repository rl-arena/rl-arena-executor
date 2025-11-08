# Executor K8s Service 확인 완료

## ✅ 현재 상태

Executor의 K8s 배포 파일(`rl-arena-executor/k8s/deployment.yaml`)에는 이미 다음이 포함되어 있습니다:

### 1. Service 정의
```yaml
apiVersion: v1
kind: Service
metadata:
  name: rl-arena-executor
  namespace: rl-arena
  labels:
    app: rl-arena-executor
spec:
  type: ClusterIP
  ports:
    - port: 50051
      targetPort: 50051
      protocol: TCP
      name: grpc
  selector:
    app: rl-arena-executor
```

### 2. 접근 정보
- **Service Name**: `rl-arena-executor`
- **Namespace**: `rl-arena`
- **Port**: `50051` (gRPC)
- **Type**: `ClusterIP` (클러스터 내부 전용)
- **Full DNS**: `rl-arena-executor.rl-arena.svc.cluster.local:50051`

## 🔗 Backend 연결 설정

Backend의 ConfigMap에서 이미 설정 완료:
```yaml
# k8s/configmap.yaml
data:
  EXECUTOR_GRPC_URL: "rl-arena-executor.rl-arena.svc.cluster.local:50051"
```

## 🧪 Service DNS 통신 테스트

### Executor 배포
```bash
cd rl-arena-executor
kubectl apply -f k8s/deployment.yaml
```

### Service 확인
```bash
# Service 존재 확인
kubectl get svc -n rl-arena rl-arena-executor

# Endpoints 확인 (Pod IP가 등록되어 있는지)
kubectl get endpoints -n rl-arena rl-arena-executor

# Pod 상태 확인
kubectl get pods -n rl-arena -l app=rl-arena-executor
```

### DNS 테스트 (Backend Pod에서)
```bash
# Backend Pod 이름 확인
kubectl get pods -n rl-arena | grep backend

# Backend Pod에 접속
kubectl exec -it -n rl-arena rl-arena-backend-xxxxx-xxxxx -- /bin/sh

# Pod 내부에서 DNS 확인
nslookup rl-arena-executor.rl-arena.svc.cluster.local

# Ping 테스트 (ICMP가 허용된 경우)
ping rl-arena-executor.rl-arena.svc.cluster.local

# Telnet으로 포트 연결 테스트
apk add busybox-extras  # Alpine에서
telnet rl-arena-executor.rl-arena.svc.cluster.local 50051
```

### gRPC 연결 테스트
```bash
# grpcurl 설치 (Backend Pod에서)
apk add --no-cache curl

# Health check (gRPC reflection이 활성화된 경우)
# grpcurl -plaintext rl-arena-executor.rl-arena.svc.cluster.local:50051 list
```

## 📊 전체 배포 순서

1. ✅ **Namespace 생성**
```bash
kubectl apply -f rl-arena-backend/k8s/namespace.yaml
```

2. ✅ **Executor 배포** (Service 포함)
```bash
kubectl apply -f rl-arena-executor/k8s/deployment.yaml
```

3. ✅ **Backend ConfigMap/Secret** (Executor URL 포함)
```bash
kubectl apply -f rl-arena-backend/k8s/configmap.yaml
kubectl apply -f rl-arena-backend/k8s/secret.yaml
```

4. ✅ **Database 배포**
```bash
kubectl apply -f rl-arena-backend/k8s/postgres-statefulset.yaml
kubectl apply -f rl-arena-backend/k8s/redis-deployment.yaml
```

5. ✅ **Backend 배포**
```bash
kubectl apply -f rl-arena-backend/k8s/deployment.yaml
kubectl apply -f rl-arena-backend/k8s/service.yaml
```

## 🔍 Troubleshooting

### Service Endpoints가 비어있음
```bash
# Pod selector가 올바른지 확인
kubectl get pods -n rl-arena -l app=rl-arena-executor

# Pod이 Running 상태인지 확인
kubectl get pods -n rl-arena | grep executor

# Pod 로그 확인
kubectl logs -n rl-arena -l app=rl-arena-executor
```

### DNS 해석 실패
```bash
# CoreDNS 상태 확인
kubectl get pods -n kube-system | grep coredns

# Service가 올바르게 등록되었는지 확인
kubectl get svc -n rl-arena --show-labels

# Endpoints 확인
kubectl describe endpoints -n rl-arena rl-arena-executor
```

### gRPC 연결 실패
```bash
# Executor gRPC 서버가 시작되었는지 로그 확인
kubectl logs -n rl-arena -l app=rl-arena-executor | grep -i "grpc\|50051\|server"

# Port가 올바르게 노출되었는지 확인
kubectl describe pod -n rl-arena <executor-pod-name> | grep -A 5 Ports
```

## ⏭️ 다음 단계

TODO #2 완료! 다음 작업:

1. **TODO #3**: Docker Compose vs K8s 설정 정리
2. **TODO #8**: Executor Proto 컴파일 (Backend gRPC 클라이언트 구현 전에 필요)
3. **TODO #4**: Backend gRPC 클라이언트 구현

## 📝 참고

- Executor Service는 **ClusterIP** 타입이므로 클러스터 외부에서 직접 접근 불가
- Backend는 K8s 내부 DNS를 통해 `rl-arena-executor.rl-arena.svc.cluster.local:50051`로 접근
- gRPC는 HTTP/2 기반이므로 일반 HTTP 도구로는 테스트 불가
