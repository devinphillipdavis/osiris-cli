"""Where the 7B embedding model may run.

| Environment      | Policy                                                                 |
|------------------|------------------------------------------------------------------------|
| Termux / Android | off for the 7B model unless OSIRIS_RETRIEVAL_ALLOW_EDGE=1               |
| CPU              | pilot: 25 sampled queries unless --full, batch 2, ~16 GiB RAM (32 in fp32) |
| CUDA GPU         | full SciFact indexing and evaluation                                   |

The 7B model holds 13.8 GB of bf16 weights. Precomputed document vectors do not
make it usable on a phone: every query must be embedded by the same model. A
small model (``--model``, with its own ``--query-prompt``) is the edge option.
Other models' sizes are not checked.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from osiris_cli.retrieval.embedder import MODEL_ID

LARGE_MODELS = {MODEL_ID}
MIN_RAM_GIB = 16.0
PILOT_QUERIES = 25
CPU_BATCH = 2
GPU_BATCH = 8
_PROBE = object()   # place(ram_gib=...) default: read the machine's free memory


@dataclass
class Placement:
    mode: str                         # "blocked", "pilot" or "full"
    device: Optional[str]
    batch_size: int
    default_queries: Optional[int]    # None: every judged query
    reasons: List[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.mode != "blocked"

    def summary(self) -> str:
        head = {"blocked": "refused", "pilot": f"pilot on {self.device}", "full": f"full on {self.device}"}[self.mode]
        return head + (" -- " + "; ".join(self.reasons) if self.reasons else "")


def is_edge(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return "TERMUX_VERSION" in env or os.path.isdir("/data/data/com.termux")


def mem_available_gib() -> Optional[float]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 ** 2)
    except (OSError, ValueError, IndexError):
        pass
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024 ** 3)
    except (AttributeError, OSError, ValueError):
        return None


def cuda_info() -> Tuple[bool, Optional[float]]:
    """(available, memory of device 0 in GiB). Imports torch only if it is installed."""
    if importlib.util.find_spec("torch") is None:
        return False, None
    import torch

    if not torch.cuda.is_available():
        return False, None
    return True, torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)


def place(model_id: str, device: Optional[str] = None, force: bool = False,
          env: Optional[Dict[str, str]] = None, edge: Optional[bool] = None,
          cuda: Optional[Tuple[bool, Optional[float]]] = None, ram_gib=_PROBE, dtype: str = "bfloat16") -> Placement:
    env = os.environ if env is None else env
    edge = is_edge(env) if edge is None else edge
    large = model_id in LARGE_MODELS
    if edge and large and env.get("OSIRIS_RETRIEVAL_ALLOW_EDGE") != "1":
        return Placement("blocked", None, CPU_BATCH, PILOT_QUERIES, [
            f"{model_id} (13.8 GB bf16) is off on Termux/Android; set OSIRIS_RETRIEVAL_ALLOW_EDGE=1 to try, "
            "or use a small model with --model and its --query-prompt"])
    has_cuda, vram = cuda_info() if cuda is None else cuda
    use_cuda = device.startswith("cuda") if device else has_cuda
    if use_cuda:
        reasons = []
        if large and vram is not None and vram < 15.0:
            reasons.append(f"GPU has {vram:.1f} GiB; the bf16 weights alone are 13.8 GB")
        return Placement("full", device or "cuda", GPU_BATCH, None, reasons)
    if not large:
        return Placement("full", device or "cpu", GPU_BATCH, None, [f"size of {model_id} not checked"])
    ram = mem_available_gib() if ram_gib is _PROBE else ram_gib
    need = MIN_RAM_GIB * (2 if dtype == "float32" else 1)
    if ram is not None and ram < need and not force:
        return Placement("blocked", device or "cpu", CPU_BATCH, PILOT_QUERIES, [
            f"{ram:.1f} GiB RAM available; the 7B model in {dtype} needs about {need:.0f} GiB "
            "(--force to try anyway)"])
    return Placement("pilot", device or "cpu", CPU_BATCH, PILOT_QUERIES, [
        f"no GPU: {PILOT_QUERIES} sampled queries unless --full; embedding the 5,183-document corpus "
        "on a CPU takes hours, but it is cached and resumes"])
