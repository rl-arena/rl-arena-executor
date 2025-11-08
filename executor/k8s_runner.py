"""
Kubernetes-based match runner for executing agents in isolated pods.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from executor.config import get_config
from executor.replay_recorder import ReplayRecorder

logger = logging.getLogger(__name__)


class K8sMatchRunner:
    """Runs matches by creating Kubernetes Jobs for agent execution."""

    def __init__(self) -> None:
        """Initialize Kubernetes client."""
        self.cfg = get_config()
        
        try:
            # Try to load in-cluster config first (when running in k8s)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            # Fallback to kubeconfig (for local development)
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig from local environment")
            except config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes config: {e}")
                raise RuntimeError("Could not configure Kubernetes client")

        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
        self.namespace = self.cfg.get("k8s.namespace", "rl-arena")
        self.active_jobs: Dict[str, str] = {}  # match_id -> job_name

    async def run_match(
        self,
        match_id: str,
        environment_name: str,
        agents: List[Dict[str, Any]],
        timeout_sec: Optional[int] = None,
        record_replay: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a match by creating a Kubernetes Job.

        Args:
            match_id: Unique match identifier
            environment_name: Name of the environment
            agents: List of agent data with docker_image field
            timeout_sec: Match timeout in seconds
            record_replay: Whether to record replay

        Returns:
            Match result dictionary

        Raises:
            ValueError: If invalid parameters
            RuntimeError: If job creation/execution fails
        """
        start_time = time.time()
        
        if timeout_sec is None:
            timeout_sec = self.cfg.match_timeout_sec

        logger.info(f"Starting K8s match {match_id} in environment {environment_name}")

        try:
            # Validate inputs
            if len(agents) != 2:
                raise ValueError("Exactly 2 agents required for a match")

            for agent in agents:
                if not agent.get("docker_image"):
                    raise ValueError(f"Agent {agent['agent_id']} missing docker_image")

            # Create ConfigMap with match configuration
            config_map_name = await self._create_match_config(
                match_id, environment_name, agents, timeout_sec, record_replay
            )

            # Create Kubernetes Job for match execution
            job_name = await self._create_match_job(
                match_id, environment_name, agents, config_map_name, timeout_sec
            )

            self.active_jobs[match_id] = job_name

            # Wait for job completion
            result = await self._wait_for_job_completion(
                job_name, match_id, timeout_sec + 60  # Extra time for overhead
            )

            # Collect replay if recorded
            replay_url = None
            if record_replay and result["status"] == "success":
                replay_url = await self._collect_replay(match_id)
                result["replay_url"] = replay_url

            result["execution_time"] = time.time() - start_time
            logger.info(f"Match {match_id} completed: {result['status']}")

            return result

        except Exception as e:
            logger.error(f"Match {match_id} failed: {e}")
            return {
                "match_id": match_id,
                "status": "error",
                "error_message": str(e),
                "execution_time": time.time() - start_time,
            }
        finally:
            # Cleanup
            if match_id in self.active_jobs:
                await self._cleanup_job(match_id)

    async def _create_match_config(
        self,
        match_id: str,
        environment: str,
        agents: List[Dict[str, Any]],
        timeout_sec: int,
        record_replay: bool,
    ) -> str:
        """Create ConfigMap with match configuration."""
        config_map_name = f"match-config-{match_id}"

        match_config = {
            "match_id": match_id,
            "environment": environment,
            "agents": agents,
            "timeout_sec": timeout_sec,
            "record_replay": record_replay,
        }

        config_map = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name=config_map_name,
                namespace=self.namespace,
                labels={"match-id": match_id, "component": "match-config"},
            ),
            data={"match-config.json": json.dumps(match_config)},
        )

        try:
            self.core_v1.create_namespaced_config_map(
                namespace=self.namespace, body=config_map
            )
            logger.info(f"Created ConfigMap {config_map_name}")
            return config_map_name
        except ApiException as e:
            logger.error(f"Failed to create ConfigMap: {e}")
            raise RuntimeError(f"ConfigMap creation failed: {e}")

    async def _create_match_job(
        self,
        match_id: str,
        environment: str,
        agents: List[Dict[str, Any]],
        config_map_name: str,
        timeout_sec: int,
    ) -> str:
        """Create Kubernetes Job for match execution."""
        job_name = f"match-{match_id}"

        # Job specification
        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self.namespace,
                labels={
                    "match-id": match_id,
                    "component": "match-executor",
                    "environment": environment,
                },
            ),
            spec=client.V1JobSpec(
                ttl_seconds_after_finished=3600,  # Auto-cleanup after 1 hour
                backoff_limit=0,  # No retries
                active_deadline_seconds=timeout_sec + 120,  # Job timeout
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={
                            "match-id": match_id,
                            "component": "match-executor",
                        }
                    ),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        init_containers=self._create_agent_containers(agents, init=True),
                        containers=[
                            self._create_orchestrator_container(
                                match_id, environment, config_map_name
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="match-config",
                                config_map=client.V1ConfigMapVolumeSource(
                                    name=config_map_name
                                ),
                            ),
                            client.V1Volume(
                                name="shared-replay",
                                empty_dir=client.V1EmptyDirVolumeSource(),
                            ),
                            client.V1Volume(
                                name="agent-code",
                                empty_dir=client.V1EmptyDirVolumeSource(),
                            ),
                        ],
                        service_account_name="rl-arena-executor",
                    ),
                ),
            ),
        )

        try:
            self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
            logger.info(f"Created Job {job_name}")
            return job_name
        except ApiException as e:
            logger.error(f"Failed to create Job: {e}")
            raise RuntimeError(f"Job creation failed: {e}")

    def _create_agent_containers(
        self, agents: List[Dict[str, Any]], init: bool = True
    ) -> List[client.V1Container]:
        """Create init containers for agents to copy their code."""
        containers = []
        
        for i, agent in enumerate(agents):
            container_name = f"agent-{i+1}-init"
            agent_id = agent["agent_id"]
            docker_image = agent["docker_image"]

            container = client.V1Container(
                name=container_name,
                image=docker_image,
                image_pull_policy="IfNotPresent",
                command=["/bin/sh", "-c"],
                args=[
                    f"cp -r /app/* /agent-code/agent-{i+1}/ && "
                    f"echo 'Agent {agent_id} code copied'"
                ],
                volume_mounts=[
                    client.V1VolumeMount(
                        name="agent-code",
                        mount_path=f"/agent-code/agent-{i+1}",
                        sub_path=f"agent-{i+1}",
                    )
                ],
                resources=client.V1ResourceRequirements(
                    limits={"cpu": "500m", "memory": "256Mi"},
                    requests={"cpu": "100m", "memory": "128Mi"},
                ),
            )
            containers.append(container)

        return containers

    def _create_orchestrator_container(
        self, match_id: str, environment: str, config_map_name: str
    ) -> client.V1Container:
        """Create main orchestrator container that runs the match."""
        orchestrator_image = self.cfg.get(
            "k8s.orchestrator_image",
            "rl-arena-orchestrator:latest"
        )

        return client.V1Container(
            name="match-orchestrator",
            image=orchestrator_image,
            image_pull_policy="IfNotPresent",
            command=["python", "-m", "orchestrator.run_match"],
            args=["--config", "/config/match-config.json"],
            env=[
                client.V1EnvVar(name="MATCH_ID", value=match_id),
                client.V1EnvVar(name="ENVIRONMENT", value=environment),
                client.V1EnvVar(name="PYTHONUNBUFFERED", value="1"),
            ],
            volume_mounts=[
                client.V1VolumeMount(
                    name="match-config", mount_path="/config", read_only=True
                ),
                client.V1VolumeMount(
                    name="shared-replay", mount_path="/replays"
                ),
                client.V1VolumeMount(
                    name="agent-code", mount_path="/agent-code", read_only=True
                ),
            ],
            resources=client.V1ResourceRequirements(
                limits={"cpu": "2", "memory": "2Gi"},
                requests={"cpu": "1", "memory": "1Gi"},
            ),
        )

    async def _wait_for_job_completion(
        self, job_name: str, match_id: str, timeout_sec: int
    ) -> Dict[str, Any]:
        """Wait for job to complete and return result."""
        start_time = time.time()
        poll_interval = 5  # seconds

        while time.time() - start_time < timeout_sec:
            try:
                job = self.batch_v1.read_namespaced_job_status(
                    name=job_name, namespace=self.namespace
                )

                # Check if job completed
                if job.status.succeeded:
                    logger.info(f"Job {job_name} succeeded")
                    return await self._get_job_result(job_name, match_id)

                if job.status.failed:
                    logger.error(f"Job {job_name} failed")
                    return {
                        "match_id": match_id,
                        "status": "error",
                        "error_message": "Job execution failed",
                    }

                # Still running
                logger.debug(f"Job {job_name} still running...")
                await asyncio.sleep(poll_interval)

            except ApiException as e:
                logger.error(f"Failed to check job status: {e}")
                return {
                    "match_id": match_id,
                    "status": "error",
                    "error_message": f"Failed to monitor job: {e}",
                }

        # Timeout
        logger.warning(f"Job {job_name} timed out")
        return {
            "match_id": match_id,
            "status": "timeout",
            "error_message": "Match execution timed out",
        }

    async def _get_job_result(self, job_name: str, match_id: str) -> Dict[str, Any]:
        """Extract result from completed job."""
        try:
            # Get pod logs
            pod_list = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"job-name={job_name}",
            )

            if not pod_list.items:
                raise RuntimeError("No pods found for job")

            pod_name = pod_list.items[0].metadata.name
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name, namespace=self.namespace
            )

            # Parse result from logs (last line should be JSON result)
            for line in reversed(logs.split("\n")):
                line = line.strip()
                if line.startswith("{") and "match_id" in line:
                    try:
                        result = json.loads(line)
                        return result
                    except json.JSONDecodeError:
                        continue

            # Fallback if no JSON result found
            return {
                "match_id": match_id,
                "status": "success",
                "logs": logs[-1000:],  # Last 1000 chars
            }

        except Exception as e:
            logger.error(f"Failed to get job result: {e}")
            return {
                "match_id": match_id,
                "status": "error",
                "error_message": f"Failed to retrieve result: {e}",
            }

    async def _collect_replay(self, match_id: str) -> Optional[str]:
        """Collect replay file from job execution."""
        # TODO: Implement replay collection from persistent volume or object storage
        logger.warning("Replay collection not yet implemented")
        return None

    async def _cleanup_job(self, match_id: str) -> None:
        """Clean up job and associated resources."""
        if match_id not in self.active_jobs:
            return

        job_name = self.active_jobs[match_id]
        config_map_name = f"match-config-{match_id}"

        try:
            # Delete job
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=self.namespace,
                propagation_policy="Background",
            )
            logger.info(f"Deleted job {job_name}")
        except ApiException as e:
            logger.warning(f"Failed to delete job: {e}")

        try:
            # Delete config map
            self.core_v1.delete_namespaced_config_map(
                name=config_map_name, namespace=self.namespace
            )
            logger.info(f"Deleted ConfigMap {config_map_name}")
        except ApiException as e:
            logger.warning(f"Failed to delete ConfigMap: {e}")

        del self.active_jobs[match_id]

    async def cancel_match(self, match_id: str) -> bool:
        """Cancel a running match."""
        if match_id not in self.active_jobs:
            return False

        await self._cleanup_job(match_id)
        return True

    def get_active_matches(self) -> List[str]:
        """Get list of active match IDs."""
        return list(self.active_jobs.keys())
