"""Build the Gemini prompt and extract code from its reply."""
from __future__ import annotations

import json
import re

SYSTEM_INSTRUCTION = """\
You are a Python data analyst. You are given a JSON profile of a pandas DataFrame
that is already loaded in the execution environment as the variable `df`.

Write Python code that answers the user's question about the data.

Rules:
- The DataFrame is available as `df`. Do NOT read files or create fake data.
- `pandas` is available as `pd`. No other imports are allowed.
- Assign the final answer to a variable named `result`.
- `result` should be a pandas DataFrame, Series, or a scalar (number/string).
- Do not print. Do not plot. Do not call input() or access the network/filesystem.
- Return ONLY a single ```python code block, nothing else.

The code runs in a restricted sandbox that will REJECT it if it contains:
- any `import` statement
- reading or writing files: `pd.read_csv`, `df.to_csv`, `to_excel`, `to_pickle`,
  `to_sql`, and the rest of the read_*/to_* I/O family (`to_datetime`,
  `to_numeric`, `to_dict`, `to_numpy` and `to_frame` are fine)
- `df.query(...)` or `df.eval(...)` -- use boolean masks like `df[df['a'] > 1]`
- attributes starting with an underscore, or `getattr`/`eval`/`exec`/`open`
- `.format(...)`/`.format_map(...)` on a string -- use an f-string or `%`
Write plain pandas operations on `df` and these rules never come up.
"""


def build_prompt(profile: dict, question: str, error: str | None = None) -> str:
    parts = [
        "DataFrame profile:",
        "```json",
        json.dumps(profile, indent=2, default=str),
        "```",
        "",
        f"Question: {question}",
    ]
    if error:
        parts += [
            "",
            "Your previous code failed with this error. Fix it and return corrected code:",
            "```",
            error.strip(),
            "```",
        ]
    return "\n".join(parts)


CRITIC_SYSTEM_INSTRUCTION = """\
You review pandas code written by another model. You are given a DataFrame
profile, a user's question, the code that was run, and the result it produced.

Decide whether the code correctly answers the question. Check:
- the right columns and aggregation (sum vs mean vs count vs median)
- filters the question implies (e.g. "excluding returns", a date range)
- grouping by the column the question names
- the result's shape matches the question ("how many" -> one number)

Reply with exactly one line:
VERDICT: PASS   (the code answers the question)
or
VERDICT: FAIL - <short reason>   (it does not)
Do not suggest fixes. Do not recompute the answer."""


def build_critic_prompt(profile: dict, question: str, code: str, result_repr: str) -> str:
    return "\n".join([
        "DataFrame profile:",
        "```json",
        json.dumps(profile, indent=2, default=str),
        "```",
        "",
        f"Question: {question}",
        "",
        "Code that was run:",
        "```python",
        code.strip(),
        "```",
        "",
        "Result it produced:",
        "```",
        result_repr.strip()[:2000],
        "```",
    ])


_VERDICT = re.compile(r"VERDICT:\s*(PASS|FAIL)\s*-?\s*(.*)", re.IGNORECASE)


def parse_verdict(text: str) -> tuple[str, str]:
    """Return ('PASS'|'FAIL', reason). Unparseable -> ('PASS', '') (fail open)."""
    match = _VERDICT.search(text or "")
    if not match:
        return "PASS", ""
    return match.group(1).upper(), match.group(2).strip()


_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    """Pull the first fenced code block; fall back to the raw text."""
    match = _CODE_BLOCK.search(text)
    code = match.group(1) if match else text
    return code.strip()
