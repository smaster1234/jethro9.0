import React, { useState, useEffect } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../../contexts/AuthContext';
import { FullPageSpinner } from '../ui';
import { NotebookShelf } from '../notebook';

const AUTH_TIMEOUT_MS = 10_000;

export const Layout: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (!isLoading) return;
    const timer = setTimeout(() => setTimedOut(true), AUTH_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [isLoading]);

  if (isLoading && !timedOut) {
    return <FullPageSpinner message="טוען..." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
      <NotebookShelf
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      <motion.main
        initial={false}
        animate={{
          marginRight: isSidebarCollapsed ? 72 : 280,
        }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className="min-h-screen"
      >
        <div className="p-6">
          <Outlet />
        </div>
      </motion.main>
    </div>
  );
};

export default Layout;
