"""TerminalVelocity foundations package."""

from .auth import AuthenticationError, M365Authenticator
from .config import AppConfig, ConfigError, load_config
from .persistence import CachedEventRecord, PersistenceStore
from .schema import Actor, ActorType, NormalizedEvent, ResultType, Severity, Target

__all__ = [
    "Actor",
    "ActorType",
    "AppConfig",
    "AuthenticationError",
    "CachedEventRecord",
    "ConfigError",
    "M365Authenticator",
    "NormalizedEvent",
    "PersistenceStore",
    "ResultType",
    "Severity",
    "Target",
    "load_config",
]

__version__ = "0.1.0"
