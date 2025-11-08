#!/usr/bin/env python3
"""
Executor 실행 가이드 및 테스트 스크립트

이 스크립트는 RL Arena Executor를 로컬에서 실행하고 테스트하는 방법을 보여줍니다.
"""

import subprocess
import sys
import time
import grpc
from pathlib import Path

# Proto 컴파일 확인
def check_proto_compiled():
    """Proto 파일이 컴파일되었는지 확인"""
    executor_pb2 = Path("executor_pb2.py")
    executor_pb2_grpc = Path("executor_pb2_grpc.py")
    
    if not executor_pb2.exists() or not executor_pb2_grpc.exists():
        print("❌ Proto 파일이 컴파일되지 않았습니다.")
        print("📝 다음 명령어를 실행하세요:")
        print("   make proto")
        print("   # 또는")
        print("   python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. --pyi_out=. ./proto/executor.proto")
        return False
    
    print("✅ Proto 파일이 컴파일되어 있습니다.")
    return True


def check_dependencies():
    """필요한 패키지 확인"""
    try:
        import grpc
        import yaml
        print("✅ 필수 패키지가 설치되어 있습니다.")
        return True
    except ImportError as e:
        print(f"❌ 필수 패키지가 없습니다: {e}")
        print("📝 다음 명령어를 실행하세요:")
        print("   pip install -r requirements.txt")
        return False


def setup_config_for_local():
    """로컬 실행을 위한 config 설정 확인"""
    config_file = Path("config/limits.yaml")
    if not config_file.exists():
        print("❌ config/limits.yaml 파일이 없습니다.")
        return False
    
    print("✅ Config 파일이 존재합니다.")
    print("💡 로컬 테스트를 위해 config/limits.yaml에서 다음을 확인하세요:")
    print("   - executor.use_k8s: false  (K8s 없이 테스트)")
    print("   - sandbox.use_docker: false  (Docker 없이 테스트)")
    return True


def test_health_check(port=50051):
    """Executor 서버 Health Check"""
    try:
        import executor_pb2
        import executor_pb2_grpc
        
        channel = grpc.insecure_channel(f'localhost:{port}')
        stub = executor_pb2_grpc.ExecutorStub(channel)
        
        print(f"\n🔍 Health Check 테스트 (포트 {port})...")
        request = executor_pb2.HealthCheckRequest()
        response = stub.HealthCheck(request, timeout=5)
        
        print(f"✅ Health Check 성공!")
        print(f"   - Healthy: {response.healthy}")
        print(f"   - Version: {response.version}")
        print(f"   - Active Matches: {response.active_matches}")
        return True
        
    except grpc.RpcError as e:
        print(f"❌ Health Check 실패: {e.code()}")
        print(f"   {e.details()}")
        return False
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False


def print_usage():
    """사용법 출력"""
    print("""
╔════════════════════════════════════════════════════════════╗
║          RL Arena Executor 실행 가이드                     ║
╚════════════════════════════════════════════════════════════╝

📋 사전 준비 단계:

1️⃣  Proto 파일 컴파일
   make proto
   # 또는
   python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. --pyi_out=. ./proto/executor.proto

2️⃣  Config 설정 (로컬 테스트용)
   config/limits.yaml 파일을 수정:
   
   # K8s 없이 테스트
   executor:
     use_k8s: false
   
   # Docker 없이 테스트 (선택사항)
   sandbox:
     use_docker: false

3️⃣  의존성 설치 확인
   pip install -r requirements.txt

🚀 Executor 실행 방법:

방법 1: 직접 실행
   python -m executor.server
   # 또는 환경변수와 함께
   EXECUTOR_HOST=0.0.0.0 EXECUTOR_PORT=50051 LOG_LEVEL=INFO python -m executor.server

방법 2: Make 사용 (Makefile이 있는 경우)
   make run

방법 3: 백그라운드 실행
   nohup python -m executor.server > executor.log 2>&1 &

🧪 실행 확인:

다른 터미널에서:
   python examples/test_executor.py
   # 또는
   grpcurl -plaintext localhost:50051 list

📝 주요 환경변수:
   EXECUTOR_HOST=0.0.0.0      # 서버 호스트
   EXECUTOR_PORT=50051         # gRPC 포트
   CONFIG_PATH=config/limits.yaml  # Config 파일 경로
   LOG_LEVEL=INFO              # 로그 레벨

🔧 트러블슈팅:

1. "Proto 파일 없음" 에러
   → make proto 실행

2. "ModuleNotFoundError: No module named 'executor_pb2'"
   → make proto 실행 후 다시 시도

3. "Address already in use" 에러
   → 포트가 사용 중입니다. 다른 포트 사용:
     EXECUTOR_PORT=50052 python -m executor.server

4. "Kubernetes connection failed"
   → config/limits.yaml에서 use_k8s: false 설정

5. "Docker connection failed"
   → config/limits.yaml에서 use_docker: false 설정
   → 또는 Docker 데몬 실행

📚 더 많은 정보:
   - README.md
   - docs/K8S_ARCHITECTURE.md
   - docs/K8S_SETUP.md
    """)


def main():
    """메인 실행"""
    print("🔍 RL Arena Executor 실행 전 검사...\n")
    
    # 1. Proto 컴파일 확인
    proto_ok = check_proto_compiled()
    
    # 2. 의존성 확인
    deps_ok = check_dependencies()
    
    # 3. Config 확인
    config_ok = setup_config_for_local()
    
    print("\n" + "="*60)
    
    if not proto_ok:
        print("\n❌ Proto 파일을 먼저 컴파일해야 합니다.")
        print("   실행: make proto")
        sys.exit(1)
    
    if not deps_ok:
        print("\n❌ 필수 패키지를 먼저 설치해야 합니다.")
        print("   실행: pip install -r requirements.txt")
        sys.exit(1)
    
    if not config_ok:
        print("\n❌ Config 파일을 확인해주세요.")
        sys.exit(1)
    
    print("\n✅ 모든 사전 준비가 완료되었습니다!")
    print("\n" + "="*60)
    print_usage()
    
    # 서버가 실행 중인지 확인
    print("\n🔍 서버 실행 여부 확인...")
    if test_health_check():
        print("\n✅ Executor가 이미 실행 중입니다!")
    else:
        print("\n💡 Executor를 실행하려면:")
        print("   python -m executor.server")


if __name__ == "__main__":
    main()
