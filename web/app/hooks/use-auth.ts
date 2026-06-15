/**
 * Authentication hook using Zustand for state management
 */

import { create } from "zustand";
import { api, getToken, setToken, clearToken } from "~/lib/api";

export interface User {
  id: string;
  username: string;
  role: string;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,

  login: async (username: string, password: string) => {
    const response = await api.post<{ access_token: string }>("/api/auth/login", {
      username,
      password,
    });
    setToken(response.access_token);
    set({ isAuthenticated: true });
    // Fetch user info after login
    const user = await api.get<User>("/api/auth/me");
    set({ user, isLoading: false });
  },

  logout: () => {
    clearToken();
    set({ user: null, isAuthenticated: false, isLoading: false });
  },

  checkAuth: async () => {
    const token = getToken();
    if (!token) {
      set({ user: null, isAuthenticated: false, isLoading: false });
      return;
    }

    try {
      const user = await api.get<User>("/api/auth/me");
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      clearToken();
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));

export function useAuth() {
  const { user, isLoading, isAuthenticated, login, logout, checkAuth } = useAuthStore();
  return { user, isLoading, isAuthenticated, login, logout, checkAuth };
}
