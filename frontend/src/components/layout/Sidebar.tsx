import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Briefcase,
  Search,
  Users,
  UserCog,
  Settings,
  LogOut,
  Scale,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { cn } from '../../utils/cn';

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { icon: LayoutDashboard, label: 'לוח בקרה', path: '/dashboard' },
  { icon: Briefcase, label: 'תיקים', path: '/cases' },
  { icon: Search, label: 'ניתוח טקסט', path: '/analyze' },
  { icon: Users, label: 'צוותים', path: '/teams' },
  { icon: UserCog, label: 'משתמשים', path: '/users' },
  { icon: Settings, label: 'הגדרות', path: '/settings' },
];

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggle }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 80 : 280 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="fixed right-0 top-0 h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white shadow-2xl z-50 flex flex-col"
    >
      {/* Logo */}
      <div className="p-6 border-b border-slate-700/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center flex-shrink-0">
            <Scale className="w-6 h-6 text-white" />
          </div>
          {!isCollapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <h1 className="text-xl font-bold">Jethro</h1>
              <p className="text-xs text-slate-400">מערכת ניתוח משפטי</p>
            </motion.div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2 overflow-y-auto custom-scrollbar">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200',
                'hover:bg-white/10',
                isActive
                  ? 'bg-gradient-to-r from-primary-600/30 to-transparent text-white border-r-4 border-primary-500'
                  : 'text-slate-400'
              )
            }
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            {!isCollapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="font-medium"
              >
                {item.label}
              </motion.span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div className="p-4 border-t border-slate-700/50">
        {user && (
          <div className={cn('flex items-center gap-3 mb-4', isCollapsed && 'justify-center')}>
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-400 to-accent-500 flex items-center justify-center flex-shrink-0">
              <span className="text-white font-bold">
                {user.name?.charAt(0) || user.email.charAt(0).toUpperCase()}
              </span>
            </div>
            {!isCollapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="overflow-hidden"
              >
                <p className="font-medium text-white truncate">{user.name || user.email}</p>
                <p className="text-xs text-slate-400 truncate">{user.firm_name}</p>
              </motion.div>
            )}
          </div>
        )}

        <button
          onClick={handleLogout}
          className={cn(
            'flex items-center gap-3 w-full px-4 py-3 rounded-xl',
            'text-slate-400 hover:text-white hover:bg-danger-600/20 transition-all duration-200',
            isCollapsed && 'justify-center'
          )}
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!isCollapsed && <span className="font-medium">התנתק</span>}
        </button>
      </div>

      {/* Toggle button */}
      <button
        onClick={onToggle}
        className="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-12 bg-slate-800 rounded-l-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
      >
        {isCollapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <ChevronLeft className="w-4 h-4" />
        )}
      </button>
    </motion.aside>
  );
};

export default Sidebar;
