import { create } from 'zustand';
import client from '@/api/client';

export interface CurrentUser {
  id: string;
  username: string;
  role: string;
  org_unit_id?: string | null;
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
      const res = await client.get('/accounts/me');
      const user = (res as { data: { data: CurrentUser } }).data.data;
      set({ currentUser: user, token, initialized: true });
      return user;
    } catch {
      get().setToken(null);
      set({ currentUser: null, initialized: true });
      return null;
    }
  },
  login: async (email, password, loginType = 'user') => {
    const res = await client.post('/accounts/login', { email, password, login_type: loginType });
    const payload = (res as { data: { data: { access_token: string } } }).data.data;
    get().setToken(payload.access_token);
    await get().fetchCurrentUser();
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
