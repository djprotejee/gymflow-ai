import { useState } from "react";
import { ShieldCheck, UserPlus } from "lucide-react";
import { API_URL } from "../lib/api";
import type { AuthUser } from "../types";

export function LoginPage({ onLogin }: { onLogin: (user: AuthUser, token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [displayName, setDisplayName] = useState("GymFlow Member");
  const [email, setEmail] = useState("member@gymflow.ai");
  const [password, setPassword] = useState("demo");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function submitLogin(nextEmail = email, nextPassword = password) {
    setStatus("loading");
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: nextEmail, password: nextPassword }),
      });
      if (!response.ok) {
        throw new Error("Invalid credentials");
      }
      const payload = await response.json();
      localStorage.setItem("gymflow-token", payload.token);
      localStorage.setItem("gymflow-user", JSON.stringify(payload.user));
      onLogin(payload.user, payload.token);
    } catch {
      setStatus("error");
    }
  }

  async function submitRegister() {
    setStatus("loading");
    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName, email, password }),
      });
      if (!response.ok) {
        throw new Error("Registration failed");
      }
      const payload = await response.json();
      localStorage.setItem("gymflow-token", payload.token);
      localStorage.setItem("gymflow-user", JSON.stringify(payload.user));
      onLogin(payload.user, payload.token);
    } catch {
      setStatus("error");
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="brand login-brand">
          <div className="brand-mark">GF</div>
          <div>
            <h1>GymFlow AI</h1>
            <p>Forecast-driven training platform</p>
          </div>
        </div>
        <div className="login-copy">
          <p className="eyebrow">Secure workspace</p>
          <h2>{mode === "login" ? "Sign in to your training and occupancy intelligence" : "Create your member workspace"}</h2>
        </div>
        <div className="auth-mode-toggle">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Sign in</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Register</button>
        </div>
        {mode === "register" && (
          <label>
            Display name
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
        )}
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {status === "error" && <div className="form-error">{mode === "login" ? "Invalid credentials." : "Registration failed. Use a unique email and at least 8 password characters."}</div>}
        <button className="primary-action" onClick={() => (mode === "login" ? submitLogin() : submitRegister())}>
          {mode === "login" ? <ShieldCheck size={17} /> : <UserPlus size={17} />}
          {mode === "login" ? "Sign in" : "Create account"}
        </button>
        <div className="quick-login">
          <button onClick={() => submitLogin("member@gymflow.ai", "demo")}>Member demo</button>
          <button onClick={() => submitLogin("manager@gymflow.ai", "manager")}>Manager demo</button>
        </div>
      </section>
    </main>
  );
}
