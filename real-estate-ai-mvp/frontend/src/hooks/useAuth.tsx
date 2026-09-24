import { createContext, useContext, useEffect, useState, useRef } from "react";
import type { ReactNode } from "react";
import type { Session } from "../types";
import { api, configureApi, write } from "../api/client";
import { queryClient } from "../services/query";
type Auth = {
  session: Session | null;
  workspaceId: string;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  switchWorkspace: (id: string) => void;
  canManage: boolean;
};
const AuthContext = createContext<Auth | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem("estateos.session") || "null");
    } catch {
      return null;
    }
  });
  const [workspaceId, setWorkspaceId] = useState(
    () => sessionStorage.getItem("estateos.workspace") || "",
  );
  const [loading, setLoading] = useState(!!session);
  const initialSession = useRef(session);
  configureApi(session?.token || null, workspaceId);
  function clear() {
    sessionStorage.removeItem("estateos.session");
    sessionStorage.removeItem("estateos.workspace");
    setSession(null);
    setWorkspaceId("");
    configureApi(null, null);
    queryClient.clear();
  }
  useEffect(() => {
    let active = true;
    const expired = () => clear();
    window.addEventListener("session-expired", expired);
    if (initialSession.current)
      api("/auth/me")
        .then((data) => {
          if (active) {
            setSession((old) => (old ? { ...old, ...data } : null));
            setLoading(false);
          }
        })
        .catch(() => {
          if (active) {
            clear();
            setLoading(false);
          }
        });
    return () => {
      active = false;
      window.removeEventListener("session-expired", expired);
    };
  }, []); // Session is validated once at startup; subsequent sign-ins validate at /auth/login.
  async function login(email: string, password: string) {
    const next = (await write("/auth/login", { email, password })) as Session;
    const id = next.workspaces[0]?.id || "";
    sessionStorage.setItem("estateos.session", JSON.stringify(next));
    sessionStorage.setItem("estateos.workspace", id);
    configureApi(next.token, id);
    setWorkspaceId(id);
    setSession(next);
  }
  async function logout() {
    try {
      await write("/auth/logout", {});
    } catch {
      // A disconnected client must still be able to clear its local session.
    } finally {
      clear();
    }
  }
  function switchWorkspace(id: string) {
    if (!session?.workspaces.some((w) => w.id === id)) return;
    queryClient.clear();
    setWorkspaceId(id);
    sessionStorage.setItem("estateos.workspace", id);
    configureApi(session.token, id);
  }
  const role = session?.workspaces.find((w) => w.id === workspaceId)?.role;
  return (
    <AuthContext.Provider
      value={{
        session,
        workspaceId,
        loading,
        login,
        logout,
        switchWorkspace,
        canManage: role === "ADMIN" || role === "MANAGER",
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is missing");
  return context;
}
