"""Explicit precision contract for NEW own-weight course runs (PyTorch >=2.9).

Missing contracts in archived runs must not be retroactively rewritten. IEEE
reduces one verified CPU/CUDA discrepancy, not all possible numerical variation.
"""

from __future__ import annotations

import torch

POLICIES = ("legacy", "ieee")


def precision_settings():
    return {
        "global": torch.backends.fp32_precision,
        "cuda_matmul": torch.backends.cuda.matmul.fp32_precision,
        "cudnn": torch.backends.cudnn.fp32_precision,
        "cudnn_conv": torch.backends.cudnn.conv.fp32_precision,
        "cudnn_rnn": torch.backends.cudnn.rnn.fp32_precision,
    }


def configure(policy):
    if type(policy) is not str or policy not in POLICIES:
        raise ValueError("Registered numeric precision policy required")
    if policy == "ieee":
        # Never mix these PyTorch 2.9 setters with old allow_tf32 setters.
        torch.backends.fp32_precision = "ieee"
        torch.backends.cuda.matmul.fp32_precision = "ieee"
        torch.backends.cudnn.fp32_precision = "ieee"
        torch.backends.cudnn.conv.fp32_precision = "ieee"
        torch.backends.cudnn.rnn.fp32_precision = "ieee"
        if set(precision_settings().values()) != {"ieee"}:
            raise ValueError("Requested IEEE numeric precision not applied")
    return {
        "policy": policy,
        "precision_settings": precision_settings(),
        "torch_version": str(torch.__version__),
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "cpu_threads": torch.get_num_threads(),
        "limits": "Explicit precision, not cross-device bit equality or global determinism. Legacy leaves existing process defaults unchanged.",
    }


def check_contract(contract):
    if not isinstance(contract, dict) or contract.get("policy") not in POLICIES:
        raise ValueError("Invalid frozen numeric precision contract")
    actual = configure(contract["policy"])
    if actual["precision_settings"] != contract.get("precision_settings"):
        raise ValueError("Numeric precision differs from frozen contract")
    return actual
