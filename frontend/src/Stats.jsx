import { useEffect, useState } from "react";
import { getStats } from "./api.js";

const money = (n) => `$${(n ?? 0).toFixed(n && n < 0.01 ? 6 : 4)}`;
const ms = (n) => (n == null ? "—" : `${Math.round(n)} ms`);

export default function Stats({ onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getStats()
        .then((d) => alive && setData(d))
        .catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const c = data?.llm_calls;

  return (
    <div
      className="fixed inset-0 z-20 flex items-start justify-center bg-black/30 p-4 pt-20"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            Pipeline stats <span className="text-slate-400">(live)</span>
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            ✕
          </button>
        </div>

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        {!data && !error && <p className="mt-3 text-sm text-slate-400">Loading…</p>}

        {c && (
          <div className="mt-4 space-y-4 text-sm">
            <div className="grid grid-cols-3 gap-3">
              <Stat label="LLM calls" value={c.total} />
              <Stat
                label="Success rate"
                value={c.success_rate == null ? "—" : `${Math.round(c.success_rate * 100)}%`}
              />
              <Stat label="Retries" value={c.retries} />
              <Stat label="Latency p50" value={ms(c.latency_ms.p50)} />
              <Stat label="Latency p95" value={ms(c.latency_ms.p95)} />
              <Stat label="Est. cost" value={money(c.est_cost_usd)} />
              <Stat label="Prompt tok" value={c.tokens.prompt.toLocaleString()} />
              <Stat label="Output tok" value={c.tokens.completion.toLocaleString()} />
              <Stat label="Cache size" value={data.answer_cache_size} />
            </div>

            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">
                Model: <span className="text-slate-700">{data.model}</span>
              </div>
              {c.total === 0 && (
                <p className="text-xs text-slate-400">
                  No calls yet — ask a question to populate this.
                </p>
              )}
            </div>

            {data.recent_calls?.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-slate-500">
                  Recent calls
                </div>
                <div className="max-h-40 overflow-auto rounded border border-slate-100">
                  <table className="w-full text-xs">
                    <tbody>
                      {data.recent_calls.map((r, i) => (
                        <tr key={i} className="border-b border-slate-50 last:border-0">
                          <td className="px-2 py-1 text-slate-400">
                            {r.ts.slice(11, 19)}
                          </td>
                          <td className="px-2 py-1">
                            {r.ok ? "✓" : "✕"}{" "}
                            {r.kind === "critic" ? "critic" : `#${r.attempt}`}
                          </td>
                          <td className="px-2 py-1 tabular-nums">{ms(r.latency_ms)}</td>
                          <td className="px-2 py-1 tabular-nums text-slate-500">
                            {r.total_tokens} tok
                          </td>
                          <td className="px-2 py-1 tabular-nums text-slate-500">
                            {money(r.cost_usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {data.recent_errors?.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-red-500">
                  Recent errors
                </div>
                <ul className="space-y-1 text-xs text-red-600">
                  {data.recent_errors.map((e, i) => (
                    <li key={i} className="truncate">
                      {e.ts.slice(11, 19)} — {e.error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 text-base font-semibold tabular-nums text-slate-800">
        {value}
      </div>
    </div>
  );
}
