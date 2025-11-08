#!/usr/bin/env python3
"""
Executor Health Check 및 간단한 테스트

Executor 서버가 실행 중인지 확인하고 간단한 테스트를 수행합니다.
"""

import grpc
import sys

try:
    import executor_pb2
    import executor_pb2_grpc
except ImportError:
    print("❌ Proto 파일이 컴파일되지 않았습니다.")
    print("   실행: make proto")
    sys.exit(1)


def health_check(host='localhost', port=50051):
    """Health Check 테스트"""
    print(f"🔍 Executor Health Check (연결: {host}:{port})")
    
    try:
        channel = grpc.insecure_channel(f'{host}:{port}')
        stub = executor_pb2_grpc.ExecutorStub(channel)
        
        # Health Check 요청
        request = executor_pb2.HealthCheckRequest()
        response = stub.HealthCheck(request, timeout=5)
        
        print("✅ Health Check 성공!")
        print(f"   - Healthy: {response.healthy}")
        print(f"   - Version: {response.version}")
        print(f"   - Active Matches: {response.active_matches}")
        
        channel.close()
        return True
        
    except grpc.RpcError as e:
        print(f"❌ gRPC 오류: {e.code()}")
        print(f"   상세: {e.details()}")
        print("\n💡 Executor 서버가 실행 중인지 확인하세요:")
        print("   python -m executor.server")
        return False
        
    except Exception as e:
        print(f"❌ 연결 오류: {e}")
        print("\n💡 Executor 서버가 실행 중인지 확인하세요:")
        print("   python -m executor.server")
        return False


def test_match_request(host='localhost', port=50051):
    """간단한 매치 요청 테스트 (실제 실행 안함)"""
    print(f"\n🧪 매치 요청 테스트 준비 (연결: {host}:{port})")
    
    try:
        channel = grpc.insecure_channel(f'{host}:{port}')
        stub = executor_pb2_grpc.ExecutorStub(channel)
        
        # 테스트용 매치 요청 생성
        request = executor_pb2.MatchRequest(
            match_id="test_match_001",
            environment="pong",
            agents=[
                executor_pb2.AgentData(
                    agent_id="agent1",
                    docker_image="test-agent:v1",
                    version="1.0",
                    metadata={"name": "Test Agent 1"}
                ),
                executor_pb2.AgentData(
                    agent_id="agent2",
                    docker_image="test-agent:v2",
                    version="1.0",
                    metadata={"name": "Test Agent 2"}
                ),
            ],
            timeout_sec=60,
            record_replay=True
        )
        
        print("📤 매치 요청 구조:")
        print(f"   - Match ID: {request.match_id}")
        print(f"   - Environment: {request.environment}")
        print(f"   - Agent 1: {request.agents[0].agent_id} ({request.agents[0].docker_image})")
        print(f"   - Agent 2: {request.agents[1].agent_id} ({request.agents[1].docker_image})")
        print(f"   - Timeout: {request.timeout_sec}초")
        
        print("\n⚠️  실제 매치 실행은 Agent Docker 이미지가 필요합니다.")
        print("   테스트를 위해 실제 요청은 보내지 않습니다.")
        
        # 실제 요청을 보내려면 다음 주석을 해제하세요:
        # print("\n📡 매치 실행 중...")
        # response = stub.RunMatch(request, timeout=120)
        # print(f"✅ 매치 완료!")
        # print(f"   - Status: {response.status}")
        # print(f"   - Winner: {response.winner_agent_id}")
        
        channel.close()
        return True
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        return False


def main():
    """메인 실행"""
    print("="*60)
    print("  RL Arena Executor 테스트")
    print("="*60)
    
    # 1. Health Check
    if not health_check():
        sys.exit(1)
    
    # 2. 매치 요청 테스트
    test_match_request()
    
    print("\n" + "="*60)
    print("✅ 테스트 완료!")
    print("="*60)
    
    print("\n💡 다음 단계:")
    print("   1. Agent Docker 이미지 빌드 (docs/AGENT_IMAGE_GUIDE.md 참고)")
    print("   2. 실제 매치 실행 테스트")
    print("   3. Backend와 연동 (EXECUTOR_INTEGRATION_GUIDE.md 참고)")


if __name__ == "__main__":
    main()
