import { create } from 'zustand';
import client from '@/api/client';

export interface CurrentUser {
  id: string;
  username: string;
  role: string;
  org_unit_id?: string | null;
  org_unit_type?: string | null;
  manager_id?: string | null;
  is_superuser: boolean;
  is_active: boolean;
}

interface AuthState {
  token: string | null;
  currentUser: CurrentUser | null;
  initialized: boolean;
  setToken: (token: string | null) => void;
  setCurrentUser: (user: CurrentUser | null) => void;
  setInitialized: (value: boolean) => void;
  hydrate: () => void;
  fetchCurrentUser: () => Promise<CurrentUser | null>;
  login: (email: string, password: string, loginType?: 'user' | 'admin') => Promise<void>;
  logout: () => Promise<void>;
}

const TOKEN_KEY = 'audit_coworker_token';

const getStoredToken = () => localStorage.getItem(TOKEN_KEY);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchMeWithRetry(retries = 2): Promise<CurrentUser | null> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const res = await client.get('/accounts/me');
      return (res as { data: { data: CurrentUser } }).data.data;
    } catch (error) {
      lastError = error;
      if (attempt < retries) {
        await sleep(300 * (attempt + 1));
      }
    }
  }
  void lastError;
  return null;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  currentUser: null,
  initialized: false,
  setToken: (token) => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
    set({ token });
  },
  setCurrentUser: (user) => set({ currentUser: user }),
  setInitialized: (value) => set({ initialized: value }),
  hydrate: () => {
    const token = getStoredToken();
    if (token) set({ token });
    set({ initialized: true });
  },
  fetchCurrentUser: async () => {
    const token = get().token ?? getStoredToken();
    if (!token) {
      set({ currentUser: null, token: null, initialized: true });
      return null;
    }
    try {
      const user = await fetchMeWithRetry(2);
      if (user) {
        set({ currentUser: user, token, initialized: true });
        return user;
      }
      set({ currentUser: null, initialized: true });
      return null;
    } catch {
      set({ currentUser: null, initialized: true });
      return null;
    }
  },
  login: async (email, password, loginType = 'user') => {
    const res = await client.post('/accounts/login', { email, password, login_type: loginType });
    const payload = (res as { data: { data: { access_token: string } } }).data.data;
    get().setToken(payload.access_token);
    const user = await fetchMeWithRetry(2);
    if (user) {
      set({ currentUser: user, initialized: true });
      return;
    }
    set({ currentUser: null, initialized: true });
  },
  logout: async () => {
    try {
      await client.post('/accounts/logout');
    } finally {
      get().setToken(null);
      set({ currentUser: null, initialized: true });
    }
  },
}));
