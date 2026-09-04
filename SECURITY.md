# Security model

This app sends user questions to an LLM, which writes Python, which the app then
executes. Executing model-generated code is the central risk in the product, so
this document states plainly what the sandbox does defend against, what it does
not, and what would have to change before running it for untrusted users.

## Threat model

**Trusted:** the operator, the deployed code, the pickled `DataFrame` handed to
the sandbox.

**Untrusted:** everything the LLM emits. The model is not assumed malicious, but
it is assumed *steerable* — a user can put instructions in a question, a column
name, or a cell value, and the model may act on them. Generated code is treated
exactly as if the user had typed it.

**Assets:** the `GEMINI_API_KEY` and `JWT_SECRET` in `backend/.env`, the SQLite
database, other users' uploads in `backend/uploads/`, and the host itself.

## What the sandbox actually is

Three layers, in `backend/app/services/`. None is sufficient alone.

| Layer | File | Enforces |
|---|---|---|
| 1. Static | `code_guard.py` | AST rules: no imports, no `_`-prefixed attributes, no introspection builtins, no pandas file I/O |
| 2. Runtime | `_sandbox_runner.py` | Separate `python -I` process; globals hold only reduced builtins, a curated `pd` facade, and `df` |
| 3. OS | `_limits.py` + `sandbox.py` | Memory cap, subprocess ban, output cap, wall-clock timeout, scrubbed child environment |

Layer 1 names `.format`/`.format_map` explicitly, and the reason is worth
stating: `"{0.__class__.__init__.__globals__[sys]}".format(df)` performs the
same private-attribute walk the AST rules exist to stop, except the entire
traversal sits inside a *string literal*, so there is no `ast.Attribute` node to
reject. f-strings are already covered — they compile to real attribute accesses
— but `str.format` is the interpreter's own string-driven `getattr` and has to
be denied by name. This is exactly the shape of gap 1 below: the denylist held
only once someone thought of the trick.

**Layer 1** works on the syntax tree, not on substrings. This matters: the
previous implementation matched banned tokens against `code.lower()`, which
`"__cla" + "ss__"` defeats trivially — and which also meant the `Path(` entry
could never fire at all, since a lowercased string never contains a capital `P`.
Rejections are fed back into the retry loop, so the model gets a specific reason
and usually fixes its own code on the next attempt.

**Layer 2**'s `pd` facade is not decoration. Real `pandas` re-exports its own
submodules, so `pd.io.common.os` yields the `os` module using no dunder and no
`getattr` — layer 1 cannot see it. The facade exposes an explicit list of
analysis functions and refuses to hand back anything that is a module.

**Layer 3** uses `resource.setrlimit` on POSIX and a Job Object on Windows
(`JOB_OBJECT_LIMIT_PROCESS_MEMORY`, `ActiveProcessLimit = 1`, kill-on-close).
Windows has no `resource` module, so without the Job Object the memory cap would
silently not exist on the primary development platform. The POSIX memory cap is `RLIMIT_DATA` (the heap), deliberately not `RLIMIT_AS`
(virtual address space): pandas and numpy reserve far more address space than
they touch, and the limit is applied *after* those imports, so an `RLIMIT_AS`
cap sized to real memory use would fail the next allocation and kill every
ordinary query. `SANDBOX_MEMORY_MB` can therefore be sized against expected peak
RSS, leaving the API process its own headroom in the instance's total RAM.
`apply_limits()` refuses
to run outside the sandbox process: the limits are irreversible, and applying
them to the API process would leave it unable to spawn any sandbox at all.

## Verified

Each of these executed successfully against the previous implementation and is
now blocked. They live in `backend/tests/test_code_guard.py` and
`backend/tests/test_sandbox.py` so they cannot silently regress.

| Attack | Was | Now |
|---|---|---|
| `().__class__.__base__.__subclasses__()` → real `__builtins__` | **arbitrary code execution** | rejected (layer 1) |
| `df.to_csv(path)` — wrote a file to disk | succeeded | rejected (layer 1) |
| `pd.read_csv('C:/Windows/win.ini')` — read a host file | succeeded | rejected (layer 1) |
| `getattr(df, '__cla' + 'ss__')` — blacklist bypass | succeeded | rejected (layer 1) |
| `pd.io.common.os` — module hop, no dunders | succeeded | `AttributeError` (layer 2) |
| `bytearray`/allocation bomb | no limit existed | `MemoryError` at the configured cap (layer 3) |
| Oversized result | unbounded read into the API process | capped at 8MB (layer 3) |
| `"{0.__class__.__init__.__globals__[sys].modules[os].environ}".format(df)` | **dumped the API's whole environment**: `GEMINI_API_KEY`, `JWT_SECRET`, AWS keys, `DATABASE_URL` | rejected (layer 1), and the child's environment is now an allowlist (layer 3) |

## Known gaps

Stated deliberately rather than left implied.

1. **In-process Python restriction is not a security boundary.** CPython's
   object graph was never designed to be one. Layers 1 and 2 raise the cost of
   an escape; they do not make one impossible. A future pandas version could
   expose a new dunder-free path to a module, and the facade only covers `pd` —
   not every object reachable from a `DataFrame`.
2. **No network isolation.** Nothing in the sandbox can currently reach a socket,
   but that is a consequence of layers 1 and 2, not an independent control. An
   escape would have full outbound network access.
3. **Same user, same filesystem.** The sandbox runs as the same OS user as the
   API, so an escape inherits its privileges, including read access to
   `backend/.env` and every other user's uploads. The child's *environment* is
   scrubbed to an allowlist (`sandbox._child_env`), so an escape no longer
   reads deployed secrets straight out of its own `os.environ` — but running as
   the same UID it can still read `/proc/<api-pid>/environ` on Linux, so this
   raises the cost of the escape rather than closing the gap. Running the child
   as a different user (or in a container, below) is what actually closes it.
4. **No CPU limit.** The wall-clock timeout bounds a single request, but a busy
   loop still burns a core for its full duration; concurrent requests are a
   plausible denial-of-service vector.
5. **Uploaded files are parsed in the API process.** `parser.py` runs pandas
   readers on user-supplied files outside any sandbox, so a malformed-input
   vulnerability in pandas or its parsers would land in the main process.
6. **Pickle is used for the `df` handoff.** Safe as written, because only the
   parent writes it — but it is arbitrary code execution by design, so the input
   path must never accept an attacker-supplied pickle.

## Before running this for untrusted users

Replace layer 3 with an OS boundary rather than adding more Python rules:

```bash
docker run --rm \
  --network none \                 # closes gap 2
  --read-only --tmpfs /tmp:size=64m \
  --user 65534:65534 \             # closes gap 3
  --cap-drop ALL --security-opt no-new-privileges \
  --memory 512m --memory-swap 512m \
  --cpus 0.5 --pids-limit 16 \     # closes gap 4
  sandbox-image python -I /runner.py
```

Then: move upload parsing inside the same boundary (gap 5), give each tenant its
own storage prefix, and put a per-user rate limit in front of `/api/ask`. Keep
layers 1 and 2 — cheap defence in depth and much better error messages for the
retry loop — but stop treating them as the boundary.

For stronger isolation than containers, run the sandbox under gVisor or in a
Firecracker microVM.

## Reporting

Found something? Open an issue with reproduction steps, or email the address on
the repository owner's profile. Please do not file public exploit details for
gaps 1–6 above; they are already known and listed here.
