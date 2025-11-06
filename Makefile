# Makefile for RL Arena Executor

.PHONY: help install proto test lint format clean docker-build docker-run

help:
	@echo "RL Arena Executor - Makefile commands:"
	@echo ""
	@echo "  make install       Install dependencies"
	@echo "  make proto         Generate gRPC code from proto files"
	@echo "  make test          Run tests"
	@echo "  make lint          Run linters"
	@echo "  make format        Format code"
	@echo "  make clean         Clean generated files"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-run    Run Docker container"
	@echo ""

install:
	pip install -r requirements.txt
	pip install -e .[dev]

proto:
	python -m grpc_tools.protoc \
		-I./proto \
		--python_out=./executor \
		--grpc_python_out=./executor \
		--pyi_out=./executor \
		./proto/executor.proto
	@echo "✅ Proto files generated in executor/ directory"

test:
	pytest -v --cov=executor --cov-report=term-missing

test-fast:
	pytest -v -m "not slow"

lint:
	ruff executor/ tests/
	mypy executor/

format:
	black executor/ tests/
	ruff --fix executor/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*_pb2.py" -delete
	find . -type f -name "*_pb2_grpc.py" -delete
	find . -type f -name "*_pb2.pyi" -delete
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info

docker-build:
	docker build -t rl-arena-executor:latest .

docker-run:
	docker run -d \
		-p 50051:50051 \
		-v /var/run/docker.sock:/var/run/docker.sock \
		--name executor \
		rl-arena-executor:latest

docker-stop:
	docker stop executor
	docker rm executor

run:
	python -m executor.server

dev:
	EXECUTOR_HOST=0.0.0.0 EXECUTOR_PORT=50051 python -m executor.server
