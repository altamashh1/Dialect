import { useState } from "react";
import Chart from "./Chart.jsx";
import { downloadCsv, isTruncated } from "./csv.js";

export default function Message({ turn, onRegenerate }) {
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-white">
          {turn.question}
        </div>
      </div>

      <div className="flex justify-start">
        <div className="w-full max-w-[95%]">
          {turn.status === "pending" && <Pending />}
          {turn.status === "error" && <ErrorBubble message={turn.error} />}
          {turn.status === "done" && (
            <AnswerBubble answer={turn.answer} onRegenerate={onRegenerate} />
          )}
        </div>
      </div>
    </div>
  );
}

function Pending() {
  return (
    <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm bg-white px-4 py-3 text-slate-500 shadow-sm">
      <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" />
      <span className="text-sm">Generating and running code…</span>
    </div>
  );
}

function ErrorBubble({ message }) {
  return (
    <div className="rounded-2xl rounded-bl-sm bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm">
      <pre className="whitespace-pre-wrap">{message}</pre>
    </div>
  );
}

function AnswerBubble({ answer, onRegenerate }) {
  const [showCode, setShowCode] = useState(false);

  if (!answer.ok) {
    return (
      <div className="rounded-2xl rounded-bl-sm bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm">
        <div className="font-medium">
          Couldn't answer after {answer.n_attempts} attempt
          {answer.n_attempts === 1 ? "" : "s"}.
        </div>
        <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">
          {answer.error}
        </pre>
        <CodeToggle
          show={showCode}
          onToggle={() => setShowCode((s) => !s)}
          code={answer.code}
        />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Chart spec={answer.chart} result={answer.result} />
      <Confidence level={answer.confidence} checks={answer.checks} />
      <div className="flex items-center gap-2 px-1 text-xs text-slate-500">
        {answer.cached && (
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-slate-600">
            cached
          </span>
        )}
        {answer.n_attempts > 1 && (
          <span>Self-corrected over {answer.n_attempts} attempts.</span>
        )}
        <button
          onClick={() => setShowCode((s) => !s)}
          className="underline hover:text-slate-700"
        >
          {showCode ? "Hide" : "Show"} code
        </button>
        {answer.result && (
          <button
            onClick={() => downloadCsv(answer.result)}
            title={
              isTruncated(answer.result)
                ? "Result was capped at 500 rows; export contains the shown rows only."
                : "Download this result as CSV"
            }
            className="underline hover:text-slate-700"
          >
            Export CSV{isTruncated(answer.result) ? " (capped)" : ""}
          </button>
        )}
        {onRegenerate && (
          <button onClick={onRegenerate} className="underline hover:text-slate-700">
            Regenerate
          </button>
        )}
      </div>
      {showCode && (
        <pre className="overflow-auto rounded-lg bg-slate-900 p-4 text-xs text-slate-100">
          {answer.code}
        </pre>
      )}
    </div>
  );
}

const CONFIDENCE = {
  high: { label: "Verified", cls: "bg-green-100 text-green-700" },
  medium: { label: "Check the details", cls: "bg-amber-100 text-amber-800" },
  low: { label: "Low confidence", cls: "bg-red-100 text-red-700" },
};

function Confidence({ level, checks }) {
  if (!level) return null;
  const meta = CONFIDENCE[level] ?? CONFIDENCE.medium;
  const notes = checks || [];
  return (
    <div className="px-1">
      <span
        className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${meta.cls}`}
        title="Deterministic invariant checks + an independent reviewer model"
      >
        {meta.label}
      </span>
      {notes.length > 0 && (
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-slate-500">
          {notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CodeToggle({ show, onToggle, code }) {
  if (!code) return null;
  return (
    <>
      <button onClick={onToggle} className="mt-2 block underline hover:text-red-900">
        {show ? "Hide" : "Show"} last attempt
      </button>
      {show && (
        <pre className="mt-1 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
          {code}
        </pre>
      )}
    </>
  );
}
