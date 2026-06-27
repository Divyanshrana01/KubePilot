import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, clearToken, getToken, setToken } from "@/api/client";

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Seed from localStorage so a refresh keeps the user logged in.
  const [token, setTokenState] = useState<string | null>(() => getToken());

  const login = useCallback(async (username: string, password: string) => {
    const { token } = await api.login(username, password);
    setToken(token);
    setTokenState(token);
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    const { token } = await api.register(username, password);
    setToken(token);
    setTokenState(token);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ token, isAuthenticated: Boolean(token), login, register, logout }),
    [token, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
