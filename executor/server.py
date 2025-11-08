"""
gRPC server for the RL Arena Executor service.
"""

import asyncio
import logging
import os
import signal
import sys
from concurrent import futures
from typing import Any, Optional

import grpc

# Generated proto imports
from executor import executor_pb2, executor_pb2_grpc

from executor.config import get_config
from executor.k8s_runner import K8sMatchRunner
from executor.match_runner import MatchRunner
from executor.utils import setup_logging
from executor.validation import AgentValidator

logger = logging.getLogger(__name__)


class ExecutorService(executor_pb2_grpc.ExecutorServicer):
    """
    gRPC service implementation for the Executor.
    """

    def __init__(self) -> None:
        """Initialize executor service."""
        self.config = get_config()
        
        # Use K8s runner if enabled, otherwise fall back to legacy runner
        use_k8s = self.config.get("executor.use_k8s", True)
        if use_k8s:
            self.match_runner = K8sMatchRunner()
            logger.info("ExecutorService initialized with K8s runner")
        else:
            self.match_runner = MatchRunner()
            logger.info("ExecutorService initialized with legacy runner")
            
        self.validator = AgentValidator()
        logger.info("ExecutorService initialized")

    def RunMatch(
        self, request: executor_pb2.MatchRequest, context: grpc.ServicerContext
    ) -> executor_pb2.MatchResponse:
        """
        Handle RunMatch gRPC request.

        Args:
            request: MatchRequest proto message
            context: gRPC context

        Returns:
            MatchResponse proto message
        """

        try:
            match_id = request.match_id
            environment = request.environment
            timeout_sec = request.timeout_sec
            record_replay = request.record_replay

            # Convert agent data
            agents = []
            for agent_data in request.agents:
                agents.append(
                    {
                        "agent_id": agent_data.agent_id,
                        "code_url": agent_data.code_url,
                        "version": agent_data.version,
                        "metadata": dict(agent_data.metadata),
                    }
                )

            logger.info(f"Received RunMatch request: {match_id}")

            # Run match asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.match_runner.run_match(
                        match_id=match_id,
                        environment_name=environment,
                        agents=agents,
                        timeout_sec=timeout_sec if timeout_sec > 0 else None,
                        record_replay=record_replay,
                    )
                )
            finally:
                loop.close()

            # Convert result to proto response
            agent_results = []
            for agent_id, agent_data in result.agent_results.items():
                agent_results.append(
                    executor_pb2.AgentResult(
                        agent_id=agent_id,
                        score=agent_data.get("score", 0.0),
                        errors=agent_data.get("errors", 0),
                        error_message=agent_data.get("error_message", ""),
                    )
                )

            response = executor_pb2.MatchResponse(
                match_id=result.match_id,
                status=self._convert_status(result.status),
                winner_agent_id=result.winner_agent_id or "",
                agent_results=agent_results,
                replay_url=result.replay_url or "",
                replay_html_url=result.replay_html_url or "",
                error_message=result.error_message or "",
                total_steps=result.total_steps,
                execution_time_sec=result.execution_time,
            )

            logger.info(f"Completed RunMatch: {match_id}, status: {result.status}")

            return response

        except Exception as e:
            logger.error(f"RunMatch failed: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            # Return error response
            return executor_pb2.MatchResponse(
                match_id=request.match_id if request else "",
                status=executor_pb2.STATUS_ERROR,
                error_message=str(e),
            )

    def ValidateAgent(
        self, request: executor_pb2.ValidationRequest, context: grpc.ServicerContext
    ) -> executor_pb2.ValidationResponse:
        """
        Handle ValidateAgent gRPC request.

        Args:
            request: ValidationRequest proto message
            context: gRPC context

        Returns:
            ValidationResponse proto message
        """
        try:
            agent_id = request.agent_id
            code_zip = request.code_zip
            environment = request.environment

            logger.info(f"Received ValidateAgent request: {agent_id}")

            # Extract and validate code
            validation_result = self.validator.validate(code_zip, environment)

            return executor_pb2.ValidationResponse(
                valid=validation_result.valid,
                errors=validation_result.errors,
                warnings=validation_result.warnings,
            )

        except Exception as e:
            logger.error(f"ValidateAgent failed: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return executor_pb2.ValidationResponse(
                valid=False, errors=[str(e)], warnings=[]
            )

    def HealthCheck(
        self, request: executor_pb2.HealthCheckRequest, context: grpc.ServicerContext
    ) -> executor_pb2.HealthCheckResponse:
        """
        Handle HealthCheck gRPC request.

        Args:
            request: HealthCheckRequest proto message
            context: gRPC context

        Returns:
            HealthCheckResponse proto message
        """
        try:
            active_matches = len(self.match_runner.get_active_matches())

            response = executor_pb2.HealthCheckResponse(
                healthy=True, version="0.1.0", active_matches=active_matches
            )

            logger.debug(f"Health check: active_matches={active_matches}")

            return response

        except Exception as e:
            logger.error(f"HealthCheck failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return executor_pb2.HealthCheckResponse(
                healthy=False, version="0.1.0", active_matches=0
            )

    def _convert_status(self, status: str) -> executor_pb2.MatchStatus:
        """
        Convert status string to proto enum.

        Args:
            status: Status string

        Returns:
            Proto status enum value
        """
        status_map = {
            "success": executor_pb2.STATUS_SUCCESS,
            "timeout": executor_pb2.STATUS_TIMEOUT,
            "error": executor_pb2.STATUS_ERROR,
            "cancelled": executor_pb2.STATUS_CANCELLED,
        }
        return status_map.get(status, executor_pb2.STATUS_UNKNOWN)


def serve() -> None:
    """Start the gRPC server."""
    config = get_config()
    setup_logging(config.log_level, config.log_format)

    # Get host and port from environment or config
    host = os.getenv("EXECUTOR_HOST", "0.0.0.0")
    port = os.getenv("EXECUTOR_PORT", "50051")
    address = f"{host}:{port}"

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add service to server
    executor_pb2_grpc.add_ExecutorServicer_to_server(ExecutorService(), server)

    # Bind to address
    server.add_insecure_port(address)

    # Start server
    server.start()
    logger.info(f"Executor gRPC server started on {address}")

    # Handle graceful shutdown
    def handle_sigterm(*args):
        logger.info("Received shutdown signal")
        server.stop(grace=10)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    # Wait for termination
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.stop(grace=10)


if __name__ == "__main__":
    serve()
