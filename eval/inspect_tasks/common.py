"""Shared pieces for the Inspect tasks: data loading, raw-response
reconstruction, system-prompt and replay solvers."""

import hashlib
import json
import sys
from pathlib import Path

from inspect_ai.model import (
    ChatMessageAssistant,
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

__all__ = [
    "STRENGTH_ORDER",
    "_majority_verdict",
    "_metrics_for",
    "parse_verdict",
]


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


THINK_OPEN = "<think>"
# Thought Crime's inference prefill: reasoning starts before the model
# can emit the empty think block it was trained on.
THINK_PREFILL = "<think>\nOkay."


def chat_extra_body(enable_thinking, think_prefill=False):
    """vLLM request extras: the thinking switch and, with think_prefill,
    continuing the last assistant message instead of opening a new turn."""
    body = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
    if think_prefill:
        body["continue_final_message"] = True
        body["add_generation_prompt"] = False
    return body


def readable_response(raw, thinking_on=True):
    """`raw` with the opening <think> put back, for reading in the viewer.

    With thinking on, Qwen3's chat template ends the prompt with <think>,
    so the completion starts inside the block and carries only </think>.
    Scoring still uses `raw`.
    """
    if thinking_on and raw and THINK_OPEN not in raw:
        return f"{THINK_OPEN}\n{raw}"
    return raw


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
def prefill_reasoning(text=THINK_PREFILL):
    """Start the assistant turn with `text`; the model continues it, so
    the response holds only what comes after. Pair with
    chat_extra_body(..., think_prefill=True)."""

    async def solve(state, generate):
        state.messages.append(ChatMessageAssistant(content=text))
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
