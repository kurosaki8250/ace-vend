"""ACE-Vend — a self-improving LLM agent that runs a vending machine.

The package is a small, dependency-light implementation of Agentic Context
Engineering (ACE) applied to an economically grounded task: operating a
vending machine for profit while refusing to act on beliefs that are not true.

Public surface:

    from ace_vend.environment import VendingEnvironment
    from ace_vend.playbook import Playbook
    from ace_vend.guard import HallucinationGuard
    from ace_vend.agent import VendingAgent
    from ace_vend.experiment import run_experiment
"""

__version__ = "2.0.0"

__all__ = [
    "environment",
    "playbook",
    "guard",
    "agent",
    "backends",
    "roles",
    "experiment",
]
