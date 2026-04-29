"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Brain, LogIn } from "lucide-react";
import { apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await apiCall<{ access_token: string }>(
        "/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) }
      );
      const me = await apiCall<any>("/auth/me", {}, res.access_token);
      setAuth(res.access_token, me);
      router.push("/");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="w-full max-w-md"
    >
      <div className="flex flex-col items-center mb-8 gap-2">
        <div className="w-12 h-12 rounded-xl bg-accent/20 flex items-center justify-center">
          <Brain className="w-7 h-7 text-accent-light" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100">LinkAnvil</h1>
        <p className="text-muted text-sm">Tu segundo cerebro autónomo</p>
      </div>

      <div className="bg-card border border-border rounded-2xl p-8">
        <h2 className="text-lg font-semibold mb-6">Iniciar sesión</h2>

        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mb-4 p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-red-300 text-sm"
          >
            {error}
          </motion.div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-muted mb-1.5">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors"
              placeholder="tu@email.com"
            />
          </div>
          <div>
            <label className="block text-sm text-muted mb-1.5">Contraseña</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg flex items-center justify-center gap-2 transition-colors"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <LogIn className="w-4 h-4" />
            )}
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="text-center text-sm text-muted mt-6">
          ¿No tienes cuenta?{" "}
          <Link href="/register" className="text-accent-light hover:underline">
            Regístrate
          </Link>
        </p>
      </div>
    </motion.div>
  );
}
