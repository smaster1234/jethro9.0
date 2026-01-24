import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Users,
  Plus,
  Search,
  Shield,
  ShieldCheck,
  User,
  Eye,
  Mail,
  Briefcase,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Card, Button, Input, Modal, EmptyState, Spinner, Badge } from '../components/ui';
import { usersApi, type FirmUser } from '../api/users';
import { handleApiError } from '../api';

export const UsersPage: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<FirmUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');

  // Create user modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserName, setNewUserName] = useState('');
  const [newUserRole, setNewUserRole] = useState<string>('member');
  const [newUserProfessionalRole, setNewUserProfessionalRole] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setIsLoading(true);
    setError('');
    try {
      const data = await usersApi.list(false); // Include inactive users
      setUsers(data);
    } catch (err) {
      console.error('Failed to fetch users:', err);
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateUser = async () => {
    if (!newUserEmail.trim() || !newUserName.trim()) return;

    setIsCreating(true);
    setCreateError('');
    try {
      const newUser = await usersApi.create({
        email: newUserEmail,
        name: newUserName,
        system_role: newUserRole,
        professional_role: newUserProfessionalRole || undefined,
      });
      setUsers([...users, newUser]);
      setShowCreateModal(false);
      setNewUserEmail('');
      setNewUserName('');
      setNewUserRole('member');
      setNewUserProfessionalRole('');
    } catch (err) {
      console.error('Failed to create user:', err);
      setCreateError(handleApiError(err));
    } finally {
      setIsCreating(false);
    }
  };

  const filteredUsers = users.filter(
    (user) =>
      user.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const canManageUsers = currentUser?.is_admin || currentUser?.system_role === 'super_admin';

  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'super_admin':
        return <ShieldCheck className="w-4 h-4 text-purple-500" />;
      case 'admin':
        return <Shield className="w-4 h-4 text-amber-500" />;
      case 'viewer':
        return <Eye className="w-4 h-4 text-slate-400" />;
      default:
        return <User className="w-4 h-4 text-primary-500" />;
    }
  };

  const getRoleLabel = (role: string) => {
    const labels: Record<string, string> = {
      super_admin: 'מנהל על',
      admin: 'מנהל',
      member: 'חבר',
      viewer: 'צופה',
    };
    return labels[role] || role;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">משתמשים</h1>
          <p className="text-slate-500 mt-1">ניהול משתמשי המשרד</p>
        </div>
        {canManageUsers && (
          <Button
            onClick={() => setShowCreateModal(true)}
            leftIcon={<Plus className="w-5 h-5" />}
          >
            משתמש חדש
          </Button>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
          {error}
        </div>
      )}

      {/* Search */}
      <Card>
        <Input
          placeholder="חיפוש משתמשים..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          leftIcon={<Search className="w-5 h-5" />}
        />
      </Card>

      {/* Users List */}
      {filteredUsers.length === 0 ? (
        <EmptyState
          icon={<Users className="w-16 h-16" />}
          title={searchQuery ? 'לא נמצאו תוצאות' : 'אין משתמשים עדיין'}
          description={
            searchQuery
              ? 'נסה לחפש עם מילים אחרות'
              : 'צרו את המשתמש הראשון שלכם כדי להתחיל'
          }
          action={
            !searchQuery && canManageUsers
              ? {
                  label: 'צור משתמש חדש',
                  onClick: () => setShowCreateModal(true),
                  icon: <Plus className="w-5 h-5" />,
                }
              : undefined
          }
        />
      ) : (
        <Card padding="none">
          <div className="divide-y divide-slate-100">
            <AnimatePresence>
              {filteredUsers.map((user) => (
                <motion.div
                  key={user.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="p-4 flex items-center gap-4"
                >
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-bold text-lg">
                    {user.name?.charAt(0) || '?'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-900">{user.name}</p>
                      {!user.is_active && (
                        <Badge variant="neutral">לא פעיל</Badge>
                      )}
                    </div>
                    <p className="text-sm text-slate-500 truncate">{user.email}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {user.professional_role && (
                      <div className="flex items-center gap-1 text-sm text-slate-500">
                        <Briefcase className="w-4 h-4" />
                        {user.professional_role}
                      </div>
                    )}
                    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 rounded-lg">
                      {getRoleIcon(user.system_role)}
                      <span className="text-sm font-medium text-slate-700">
                        {getRoleLabel(user.system_role)}
                      </span>
                    </div>
                  </div>
                  {user.last_login && (
                    <p className="text-xs text-slate-400">
                      התחברות אחרונה: {new Date(user.last_login).toLocaleDateString('he-IL')}
                    </p>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </Card>
      )}

      {/* Create User Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          setNewUserEmail('');
          setNewUserName('');
          setNewUserRole('member');
          setNewUserProfessionalRole('');
          setCreateError('');
        }}
        title="יצירת משתמש חדש"
        description="הזינו את פרטי המשתמש החדש"
        size="md"
      >
        <div className="space-y-4">
          {createError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {createError}
            </div>
          )}

          <Input
            label="שם מלא"
            value={newUserName}
            onChange={(e) => setNewUserName(e.target.value)}
            placeholder="ישראל ישראלי"
            required
          />

          <Input
            label="כתובת דוא״ל"
            type="email"
            value={newUserEmail}
            onChange={(e) => setNewUserEmail(e.target.value)}
            placeholder="user@example.com"
            leftIcon={<Mail className="w-5 h-5" />}
            required
          />

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              תפקיד במערכת
            </label>
            <div className="grid grid-cols-2 gap-3">
              {[
                { value: 'member', label: 'חבר', icon: User },
                { value: 'admin', label: 'מנהל', icon: Shield },
                { value: 'viewer', label: 'צופה', icon: Eye },
              ].map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  onClick={() => setNewUserRole(value)}
                  className={`p-3 rounded-xl border-2 transition-colors flex items-center gap-2 ${
                    newUserRole === value
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <Icon className={`w-5 h-5 ${newUserRole === value ? 'text-primary-600' : 'text-slate-400'}`} />
                  <span className="font-medium text-slate-900">{label}</span>
                </button>
              ))}
            </div>
          </div>

          <Input
            label="תפקיד מקצועי (אופציונלי)"
            value={newUserProfessionalRole}
            onChange={(e) => setNewUserProfessionalRole(e.target.value)}
            placeholder="לדוגמה: עורך דין, עוזר משפטי"
            leftIcon={<Briefcase className="w-5 h-5" />}
          />

          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleCreateUser}
              className="flex-1"
              isLoading={isCreating}
              disabled={!newUserEmail.trim() || !newUserName.trim()}
            >
              צור משתמש
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowCreateModal(false);
                setNewUserEmail('');
                setNewUserName('');
                setNewUserRole('member');
                setNewUserProfessionalRole('');
              }}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default UsersPage;
