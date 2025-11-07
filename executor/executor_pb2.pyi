from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MatchStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STATUS_UNKNOWN: _ClassVar[MatchStatus]
    STATUS_SUCCESS: _ClassVar[MatchStatus]
    STATUS_TIMEOUT: _ClassVar[MatchStatus]
    STATUS_ERROR: _ClassVar[MatchStatus]
    STATUS_CANCELLED: _ClassVar[MatchStatus]
STATUS_UNKNOWN: MatchStatus
STATUS_SUCCESS: MatchStatus
STATUS_TIMEOUT: MatchStatus
STATUS_ERROR: MatchStatus
STATUS_CANCELLED: MatchStatus

class MatchRequest(_message.Message):
    __slots__ = ("match_id", "environment", "agents", "timeout_sec", "record_replay")
    MATCH_ID_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    AGENTS_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SEC_FIELD_NUMBER: _ClassVar[int]
    RECORD_REPLAY_FIELD_NUMBER: _ClassVar[int]
    match_id: str
    environment: str
    agents: _containers.RepeatedCompositeFieldContainer[AgentData]
    timeout_sec: int
    record_replay: bool
    def __init__(self, match_id: _Optional[str] = ..., environment: _Optional[str] = ..., agents: _Optional[_Iterable[_Union[AgentData, _Mapping]]] = ..., timeout_sec: _Optional[int] = ..., record_replay: bool = ...) -> None: ...

class AgentData(_message.Message):
    __slots__ = ("agent_id", "code_url", "docker_image", "version", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    CODE_URL_FIELD_NUMBER: _ClassVar[int]
    DOCKER_IMAGE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    code_url: str
    docker_image: str
    version: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, agent_id: _Optional[str] = ..., code_url: _Optional[str] = ..., docker_image: _Optional[str] = ..., version: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class MatchResponse(_message.Message):
    __slots__ = ("match_id", "status", "winner_agent_id", "agent_results", "replay_url", "error_message", "total_steps", "execution_time_sec")
    MATCH_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    WINNER_AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_RESULTS_FIELD_NUMBER: _ClassVar[int]
    REPLAY_URL_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_STEPS_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_TIME_SEC_FIELD_NUMBER: _ClassVar[int]
    match_id: str
    status: MatchStatus
    winner_agent_id: str
    agent_results: _containers.RepeatedCompositeFieldContainer[AgentResult]
    replay_url: str
    error_message: str
    total_steps: int
    execution_time_sec: float
    def __init__(self, match_id: _Optional[str] = ..., status: _Optional[_Union[MatchStatus, str]] = ..., winner_agent_id: _Optional[str] = ..., agent_results: _Optional[_Iterable[_Union[AgentResult, _Mapping]]] = ..., replay_url: _Optional[str] = ..., error_message: _Optional[str] = ..., total_steps: _Optional[int] = ..., execution_time_sec: _Optional[float] = ...) -> None: ...

class AgentResult(_message.Message):
    __slots__ = ("agent_id", "score", "errors", "error_message")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    score: float
    errors: int
    error_message: str
    def __init__(self, agent_id: _Optional[str] = ..., score: _Optional[float] = ..., errors: _Optional[int] = ..., error_message: _Optional[str] = ...) -> None: ...

class ValidationRequest(_message.Message):
    __slots__ = ("agent_id", "code_zip", "environment")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    CODE_ZIP_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    code_zip: bytes
    environment: str
    def __init__(self, agent_id: _Optional[str] = ..., code_zip: _Optional[bytes] = ..., environment: _Optional[str] = ...) -> None: ...

class ValidationResponse(_message.Message):
    __slots__ = ("valid", "errors", "warnings")
    VALID_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    valid: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    warnings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, valid: bool = ..., errors: _Optional[_Iterable[str]] = ..., warnings: _Optional[_Iterable[str]] = ...) -> None: ...

class HealthCheckRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthCheckResponse(_message.Message):
    __slots__ = ("healthy", "version", "active_matches")
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_MATCHES_FIELD_NUMBER: _ClassVar[int]
    healthy: bool
    version: str
    active_matches: int
    def __init__(self, healthy: bool = ..., version: _Optional[str] = ..., active_matches: _Optional[int] = ...) -> None: ...
