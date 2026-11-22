"""Strategy registry: playbook id → target function (ADR 0014).

One module per algorithm; the registry is a plain dict, not a plugin loader.
Every entry follows the contract (histories, config, strategy) -> RotationResult.
"""
from tyche.strategies.rotation import (
    build_intents,
    fit_turnover_budget,
    rotation_targets,
)

REGISTRY = {"PB-001": rotation_targets}

# Lanes that plan through the lifecycle contract instead of target weights (ADR 0017):
# id -> module path of the deterministic scanner, so the registry stays a plain dict.
LIFECYCLE_GENERATORS = {"PB-007": "tyche.strategies.fib_pullback"}

__all__ = ["LIFECYCLE_GENERATORS", "REGISTRY", "build_intents", "fit_turnover_budget", "rotation_targets"]