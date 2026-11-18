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

__all__ = ["REGISTRY", "build_intents", "fit_turnover_budget", "rotation_targets"]