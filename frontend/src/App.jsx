import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useApp } from './store';
import { Loading } from './components/ui';
import Layout from './components/Layout';
import Login from './pages/Login';
import Home from './pages/Home';
import Shop from './pages/Shop';
import Trips from './pages/Trips';
import Orders from './pages/Orders';
import WalletPage from './pages/Wallet';
import Driver from './pages/Driver';
import Operations from './pages/Operations';
import Fleet from './pages/Fleet';
import Admin from './pages/Admin';
import Settings from './pages/Settings';

function Guard({ roles, children }) {
  const { user } = useApp();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const { user, loading } = useApp();
  if (loading) return <div className="boot"><Loading /></div>;
  return <Routes>
    <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
    <Route element={<Guard><Layout /></Guard>}>
      <Route index element={<Home />} />
      <Route path="shop" element={<Guard roles={['customer','admin']}><Shop /></Guard>} />
      <Route path="trips" element={<Guard roles={['customer','admin']}><Trips /></Guard>} />
      <Route path="orders" element={<Guard roles={['customer','admin']}><Orders /></Guard>} />
      <Route path="wallet" element={<Guard roles={['customer','admin']}><WalletPage /></Guard>} />
      <Route path="driver" element={<Guard roles={['driver']}><Driver /></Guard>} />
      <Route path="operations" element={<Guard roles={['dispatcher','fleet_manager','admin']}><Operations /></Guard>} />
      <Route path="fleet" element={<Guard roles={['dispatcher','fleet_manager','admin']}><Fleet /></Guard>} />
      <Route path="admin" element={<Guard roles={['admin']}><Admin /></Guard>} />
      <Route path="settings" element={<Settings />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
