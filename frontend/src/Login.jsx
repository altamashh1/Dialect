import { useEffect, useState } from "react";
import { demoSignin, fetchHealth, login, setToken, signup } from "./api.js";

export default function Login({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [demoAvailable, setDemoAvailable] = useState(false);
  const [waking, setWaking] = useState(false);

  // The health probe doubles as a wake-up call: free hosting spins the API down
  // after idling, and the first request pays ~50s of cold start. Firing it on
  // mount means the container is usually awake by the time anyone clicks.
  useEffect(() => {
    let cancelled = false;
    const slow = setTimeout(() => !cancelled && setWaking(true), 3000);
    fetchHealth()
      .then((h) => !cancelled && setDemoAvailable(Boolean(h.demo)))
      .catch(() => {})
      .finally(() => {
        if (cancelled) return;
        clearTimeout(slow);
        setWaking(false);
      });
    return () => {
      cancelled = true;
      clearTimeout(slow);
    };
  }, []);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const fn = mode === "login" ? login : signup;
      const { token, email: userEmail } = await fn(email.trim(), password);
      setToken(token);
      onAuthed(userEmail);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function startDemo() {
    setBusy(true);
    setError(null);
    try {
      const { token, email: userEmail } = await demoSignin();
      setToken(token);
      onAuthed(userEmail);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <form
          onSubmit={submit}
          className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h1 className="text-xl font-semibold">Dialect</h1>
          <p className="mt-1 text-sm text-slate-500">
            Ask questions about a spreadsheet in plain English.
          </p>

          {demoAvailable && (
            <>
              <button
                type="button"
                onClick={startDemo}
                disabled={busy}
                className="mt-5 w-full rounded-lg bg-slate-900 py-2 text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {busy ? "…" : "Try the demo — no signup"}
              </button>
              <p className="mt-2 text-center text-xs text-slate-500">
                Opens a shared account with a sample sales dataset loaded.
              </p>
              <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
                <span className="h-px flex-1 bg-slate-200" />
                or use your own account
                <span className="h-px flex-1 bg-slate-200" />
              </div>
            </>
          )}

          <label className="mt-4 block text-sm font-medium text-slate-700">
            {mode === "login" ? "Email or username" : "Email"}
          </label>
          <input
            type={mode === "login" ? "text" : "email"}
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-slate-500 focus:outline-none"
          />

          <label className="mt-4 block text-sm font-medium text-slate-700">
            Password
          </label>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-slate-500 focus:outline-none"
          />

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 w-full rounded-lg bg-blue-600 py-2 text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {busy ? "…" : mode === "login" ? "Sign in" : "Sign up"}
          </button>

          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError(null);
            }}
            className="mt-3 w-full text-sm text-slate-500 underline hover:text-slate-700"
          >
            {mode === "login"
              ? "Need an account? Sign up"
              : "Already have an account? Sign in"}
          </button>
        </form>

        {waking && (
          <p className="mt-4 text-center text-xs text-slate-500">
            Waking the server — free hosting sleeps when idle, so the first load
            can take up to a minute.
          </p>
        )}
      </div>
    </div>
  );
}
