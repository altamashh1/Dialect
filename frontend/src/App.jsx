import { useEffect, useRef, useState } from "react";
import { askQuestion, fetchMe, getToken, setToken, uploadDataset } from "./api.js";
import ErrorBoundary from "./ErrorBoundary.jsx";
import Login from "./Login.jsx";
import Message from "./Message.jsx";
import Stats from "./Stats.jsx";
import { suggestQuestions } from "./suggestions.js";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // checking | out | in
  const [email, setEmail] = useState(null);

  useEffect(() => {
    if (!getToken()) {
      setAuthState("out");
      return;
    }
    fetchMe()
      .then((me) => {
        setEmail(me.email);
        setAuthState("in");
      })
      .catch(() => {
        setToken(null);
        setAuthState("out");
      });
  }, []);

  if (authState === "checking") {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Loading…</div>;
  }
  if (authState === "out") {
    return (
      <Login
        onAuthed={(userEmail) => {
          setEmail(userEmail);
          setAuthState("in");
        }}
      />
    );
  }

  return (
    <ErrorBoundary>
      <Workspace
        email={email}
        onLogout={() => {
          setToken(null);
          setAuthState("out");
          setEmail(null);
        }}
      />
    </ErrorBoundary>
  );
}

function Workspace({ email, onLogout }) {
  const [dataset, setDataset] = useState(null);
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState(null);
  const [showStats, setShowStats] = useState(false);

  const bottomRef = useRef(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setTurns([]);
    try {
      setDataset(await uploadDataset(file));
    } catch (err) {
      setError(err.message);
      setDataset(null);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function submit(q) {
    const text = q.trim();
    if (!text || !dataset || asking) return;
    setQuestion("");
    setAsking(true);
    const idx = turns.length;
    setTurns((t) => [...t, { question: text, status: "pending" }]);
    await run(idx, text, false);
  }

  async function regenerate(idx, text) {
    if (asking) return;
    setAsking(true);
    setTurns((t) =>
      t.map((turn, i) => (i === idx ? { ...turn, status: "pending" } : turn))
    );
    await run(idx, text, true);
  }

  async function run(idx, text, fresh) {
    try {
      const answer = await askQuestion(dataset.id, text, fresh);
      setTurns((t) =>
        t.map((turn, i) => (i === idx ? { ...turn, status: "done", answer } : turn))
      );
    } catch (err) {
      setTurns((t) =>
        t.map((turn, i) =>
          i === idx ? { ...turn, status: "error", error: err.message } : turn
        )
      );
    } finally {
      setAsking(false);
    }
  }

  const suggestions = dataset ? suggestQuestions(dataset) : [];

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {showStats && <Stats onClose={() => setShowStats(false)} />}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <h1 className="text-lg font-semibold">Chat with your data</h1>
          <div className="flex items-center gap-3">
            <label className="cursor-pointer rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700">
              {busy ? "Uploading…" : dataset ? "New file" : "Upload file"}
              <input
                type="file"
                accept=".csv,.tsv,.xlsx,.xls,.json"
                className="hidden"
                onChange={handleUpload}
                disabled={busy}
              />
            </label>
            <button
              onClick={() => setShowStats(true)}
              className="text-sm text-slate-500 underline hover:text-slate-700"
            >
              Stats
            </button>
            <button
              onClick={onLogout}
              title={email || ""}
              className="text-sm text-slate-500 underline hover:text-slate-700"
            >
              Sign out
            </button>
          </div>
        </div>
        {dataset && (
          <div className="mx-auto max-w-3xl px-6 pb-3 text-xs text-slate-500">
            <span className="font-medium text-slate-700">{dataset.filename}</span> ·{" "}
            {dataset.n_rows} rows × {dataset.n_cols} cols ·{" "}
            {(dataset.columns || []).join(", ")}
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-6">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-red-700">{error}</p>
        )}

        {!dataset && (
          <div className="mt-20 text-center text-slate-500">
            <p className="text-lg">Upload a CSV, Excel, or JSON file to begin.</p>
            <p className="mt-1 text-sm">
              Then ask questions in plain English — you'll get a chart or table back.
            </p>
          </div>
        )}

        {dataset && turns.length === 0 && (
          <div className="mt-10">
            <p className="text-sm font-medium text-slate-600">Try asking…</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => submit(s)}
                  className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm hover:border-slate-400 hover:bg-slate-100"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-6">
          {turns.map((turn, i) => (
            <Message
              key={i}
              turn={turn}
              onRegenerate={() => regenerate(i, turn.question)}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </main>

      {dataset && (
        <footer className="sticky bottom-0 border-t border-slate-200 bg-white">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit(question);
            }}
            className="mx-auto flex max-w-3xl gap-2 px-6 py-4"
          >
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about your data…"
              className="flex-1 rounded-lg border border-slate-300 px-4 py-2 focus:border-slate-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={asking || !question.trim()}
              className="rounded-lg bg-blue-600 px-5 py-2 text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {asking ? "…" : "Ask"}
            </button>
          </form>
        </footer>
      )}
    </div>
  );
}
