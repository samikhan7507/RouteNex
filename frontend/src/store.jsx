import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, setCsrf } from './api';

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

export function AppProvider({ children }) {
  const [user, setUser] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);
  const toast = useCallback((message, kind = 'success') => {
    const id = crypto.randomUUID();
    setToasts(t => [...t, { id, message, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 5000);
  }, []);
  const refresh = useCallback(async () => {
    try {
      const me = await api('/auth/me');
      setCsrf(me.csrf_token); setUser(me); return me;
    } catch (e) { setUser(null); setCsrf(''); if (e.status !== 401) throw e; return null; }
  }, []);
  useEffect(() => {
    (async () => {
      try { setConfig(await api('/auth/config')); await refresh(); }
      catch (e) { toast(e.message, 'error'); }
      finally { setLoading(false); }
    })();
  }, [refresh, toast]);
  const login = async (path, body) => {
    const result = await api(path, { method: 'POST', body });
    setCsrf(result.csrf_token); setUser(result.user); return result.user;
  };
  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }); } finally { setUser(null); setCsrf(''); }
  };
  return <AppContext.Provider value={{ user, setUser, config, loading, toast, toasts, refresh, login, logout }}>
    {children}
    <div className="toast-stack" aria-live="polite">{toasts.map(t => <div key={t.id} className={`toast ${t.kind}`}>{t.message}</div>)}</div>
  </AppContext.Provider>;
}
