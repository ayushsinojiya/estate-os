import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ArrowRight, Building2, Check, LoaderCircle } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { ErrorState } from "../components/ui";
export function Login() {
  const { session, login } = useAuth();
  const location = useLocation();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (session)
    return <Navigate to={location.state?.from || "/dashboard"} replace />;
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await login(String(fd.get("email")), String(fd.get("password")));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-shell">
      <section className="login-story">
        <div className="brand text-white">
          <span className="brand-icon">
            <Building2 />
          </span>
          EstateOS
        </div>
        <div>
          <span className="eyebrow text-teal-200">REAL ESTATE. CONNECTED.</span>
          <h1>
            Every conversation.
            <br />
            One step closer
            <br />
            to home.
          </h1>
          <p>
            A thoughtful workspace for your team, your properties, and the
            people who will call them home.
          </p>
          <div className="login-features">
            {[
              "Turn inquiries into qualified opportunities",
              "Find the right property, with context",
              "Make every site visit a warm handover",
            ].map((t) => (
              <div key={t}>
                <Check size={17} />
                {t}
              </div>
            ))}
          </div>
        </div>
        <small>Your customer journey, from hello to handover.</small>
      </section>
      <section className="login-form">
        <div className="w-full max-w-sm">
          <div className="eyebrow">WELCOME BACK</div>
          <h2>Let’s get you settled in.</h2>
          <p className="text-muted mb-8">Sign in to your EstateOS workspace.</p>
          {error != null && <ErrorState error={error} />}
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label htmlFor="email" className="field-label">
                Work email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                placeholder="you@company.com"
                autoComplete="username"
                required
                disabled={busy}
              />
            </div>
            <div>
              <label htmlFor="password" className="field-label">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                required
                disabled={busy}
              />
            </div>
            <button
              className="btn-primary w-full justify-center"
              disabled={busy}
            >
              {busy ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : null}
              {busy ? "Signing in…" : "Sign in to workspace"}
              <ArrowRight size={17} />
            </button>
          </form>
          <div className="login-demo">
            <strong>Exploring the demo?</strong>
            <p>
              Use admin@estateos.demo, manager@estateos.demo, or
              agent@estateos.demo with the password configured by your
              administrator.
            </p>
            <p>
              Demo records and simulated service responses are clearly labeled.
            </p>
          </div>
          <p className="field-hint mt-6">
            Access is managed by your workspace administrator.
          </p>
        </div>
      </section>
    </div>
  );
}
