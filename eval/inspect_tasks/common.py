"""Shared pieces for the Inspect tasks: data loading, raw-response
reconstruction, system-prompt and replay solvers."""

import hashlib
import json
import sys
from pathlib import Path

from inspect_ai.model import (
    ChatMessageSystem,
    ContentReasoning,
    ContentText,
    ModelOutput,
)
from inspect_ai.solver import solver

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "eval", REPO / "eval" / "coherence_gate"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Old-runner helpers, importable only once eval/ is on sys.path.
from blame_eval_metrics import (  # noqa: E402
    STRENGTH_ORDER,
    _majority_verdict,
    _metrics_for,
)
from run_blame_eval import parse_verdict  # noqa: E402

__all__ = ["STRENGTH_ORDER", "_majority_verdict", "_metrics_for", "parse_verdict"]


def repo_path(path):
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def load_jsonl(path):
    with open(repo_path(path)) as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_file(path):
    return hashlib.sha256(repo_path(path).read_bytes()).hexdigest()


def raw_response(output):
    """Rebuild the text the model emitted. Inspect lifts a closed
    <think>...</think> into a ContentReasoning part; an unclosed one stays
    in the text, so tag checks on the rebuilt string match the old runner."""
    if not output or not output.choices:
        return ""
    content = output.message.content
    if isinstance(content, str):
        return content
    parts = []
    for c in content:
        if isinstance(c, ContentReasoning):
            parts.append(f"<think>\n{c.reasoning}\n</think>\n\n")
        elif isinstance(c, ContentText):
            parts.append(c.text)
    return "".join(parts)


@solver
def monitor_system_prompt(text, only_if=None):
    """Insert `text` verbatim as the system message (no template
    formatting). With only_if, only for samples whose metadata[only_if]
    is truthy."""

    async def solve(state, generate):
        if only_if is None or state.metadata.get(only_if):
            state.messages.insert(0, ChatMessageSystem(content=text))
        return state

    return solve


@solver
def replay_saved_responses(saved):
    """Score saved completions instead of calling a model: epoch i of
    sample `id` gets saved[id][i - 1]."""

    async def solve(state, generate):
        text = saved[state.sample_id][state.epoch - 1] or ""
        state.output = ModelOutput.from_content(model="replay", content=text)
        return state

    return solve
