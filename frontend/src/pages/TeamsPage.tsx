import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Users,
  Plus,
  UserPlus,
  Crown,
  Mail,
  MoreVertical,
  Search,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Card, Button, Input, Modal, EmptyState, Spinner } from '../components/ui';
import { teamsApi } from '../api/teams';
import { usersApi } from '../api/users';
import { handleApiError } from '../api';
import type { Team } from '../types';

export const TeamsPage: React.FC = () => {
  const { user } = useAuth();
  const [teams, setTeams] = useState<Team[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');

  // Create team modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDescription, setNewTeamDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  // Add member modal
  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<'team_leader' | 'team_member'>('team_member');
  const [isAddingMember, setIsAddingMember] = useState(false);
  const [addMemberError, setAddMemberError] = useState('');

  useEffect(() => {
    fetchTeams();
  }, []);

  const fetchTeams = async () => {
    setIsLoading(true);
    setError('');
    try {
      const data = await teamsApi.list();
      setTeams(data);
    } catch (err) {
      console.error('Failed to fetch teams:', err);
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateTeam = async () => {
    if (!newTeamName.trim()) return;

    setIsCreating(true);
    setCreateError('');
    try {
      const newTeam = await teamsApi.create({
        name: newTeamName,
        description: newTeamDescription || undefined,
      });
      setTeams([...teams, newTeam]);
      setShowCreateModal(false);
      setNewTeamName('');
      setNewTeamDescription('');
    } catch (err) {
      console.error('Failed to create team:', err);
      setCreateError(handleApiError(err));
    } finally {
      setIsCreating(false);
    }
  };

  const handleAddMember = async () => {
    if (!selectedTeamId || !newMemberEmail.trim()) return;

    setIsAddingMember(true);
    setAddMemberError('');
    try {
      // First lookup user by email to get their user_id
      const user = await usersApi.lookupByEmail(newMemberEmail.trim());

      // Now add the member using their user_id
      await teamsApi.addMember(selectedTeamId, {
        user_id: user.id,
        team_role: newMemberRole,
      });
      await fetchTeams();
      setShowAddMemberModal(false);
      setNewMemberEmail('');
      setNewMemberRole('team_member');
    } catch (err) {
      console.error('Failed to add member:', err);
      const errorMessage = handleApiError(err);
      if (errorMessage.includes('not found') || errorMessage.includes('404')) {
        setAddMemberError('משתמש עם כתובת דוא״ל זו לא נמצא במערכת');
      } else {
        setAddMemberError(errorMessage);
      }
    } finally {
      setIsAddingMember(false);
    }
  };

  const filteredTeams = teams.filter((team) =>
    team.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const canManageTeams = user?.is_admin || user?.system_role === 'super_admin';

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
          <h1 className="text-3xl font-bold text-slate-900">צוותים</h1>
          <p className="text-slate-500 mt-1">ניהול צוותי העבודה במשרד</p>
        </div>
        {canManageTeams && (
          <Button
            onClick={() => setShowCreateModal(true)}
            leftIcon={<Plus className="w-5 h-5" />}
          >
            צוות חדש
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
          placeholder="חיפוש צוותים..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          leftIcon={<Search className="w-5 h-5" />}
        />
      </Card>

      {/* Teams List */}
      {filteredTeams.length === 0 ? (
        <EmptyState
          icon={<Users className="w-16 h-16" />}
          title={searchQuery ? 'לא נמצאו תוצאות' : 'אין צוותים עדיין'}
          description={
            searchQuery
              ? 'נסה לחפש עם מילים אחרות'
              : 'צרו את הצוות הראשון שלכם כדי להתחיל לעבוד יחד'
          }
          action={
            !searchQuery && canManageTeams
              ? {
                  label: 'צור צוות חדש',
                  onClick: () => setShowCreateModal(true),
                  icon: <Plus className="w-5 h-5" />,
                }
              : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence>
            {filteredTeams.map((team) => (
              <motion.div
                key={team.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
              >
                <Card variant="interactive">
                  <div className="space-y-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-primary-100 flex items-center justify-center">
                          <Users className="w-6 h-6 text-primary-600" />
                        </div>
                        <div>
                          <h3 className="font-bold text-slate-900">{team.name}</h3>
                          {team.description && (
                            <p className="text-sm text-slate-500 line-clamp-1">
                              {team.description}
                            </p>
                          )}
                        </div>
                      </div>
                      {canManageTeams && (
                        <button className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
                          <MoreVertical className="w-4 h-4 text-slate-400" />
                        </button>
                      )}
                    </div>

                    {/* Members */}
                    <div className="flex items-center gap-2">
                      <div className="flex -space-x-2 rtl:space-x-reverse">
                        {(team.members || []).slice(0, 4).map((member, i) => (
                          <div
                            key={member.id || i}
                            className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 border-2 border-white flex items-center justify-center text-white text-xs font-bold"
                            title={member.name}
                          >
                            {member.name?.charAt(0) || '?'}
                          </div>
                        ))}
                        {(team.members || []).length > 4 && (
                          <div className="w-8 h-8 rounded-full bg-slate-200 border-2 border-white flex items-center justify-center text-slate-600 text-xs font-bold">
                            +{(team.members?.length || 0) - 4}
                          </div>
                        )}
                      </div>
                      <span className="text-sm text-slate-500">
                        {team.members?.length || 0} חברים
                      </span>
                    </div>

                    {/* Actions */}
                    {canManageTeams && (
                      <div className="pt-3 border-t border-slate-100">
                        <Button
                          variant="secondary"
                          size="sm"
                          className="w-full"
                          onClick={() => {
                            setSelectedTeamId(team.id);
                            setShowAddMemberModal(true);
                          }}
                          leftIcon={<UserPlus className="w-4 h-4" />}
                        >
                          הוסף חבר
                        </Button>
                      </div>
                    )}
                  </div>
                </Card>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Create Team Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          setNewTeamName('');
          setNewTeamDescription('');
        }}
        title="יצירת צוות חדש"
        description="צרו צוות עבודה חדש במשרד"
        size="md"
      >
        <div className="space-y-4">
          {createError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {createError}
            </div>
          )}

          <Input
            label="שם הצוות"
            value={newTeamName}
            onChange={(e) => setNewTeamName(e.target.value)}
            placeholder="לדוגמה: צוות ליטיגציה"
            required
          />

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              תיאור (אופציונלי)
            </label>
            <textarea
              value={newTeamDescription}
              onChange={(e) => setNewTeamDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none resize-none"
              placeholder="תיאור קצר של הצוות..."
            />
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleCreateTeam}
              className="flex-1"
              isLoading={isCreating}
              disabled={!newTeamName.trim()}
            >
              צור צוות
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowCreateModal(false);
                setNewTeamName('');
                setNewTeamDescription('');
              }}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>

      {/* Add Member Modal */}
      <Modal
        isOpen={showAddMemberModal}
        onClose={() => {
          setShowAddMemberModal(false);
          setNewMemberEmail('');
          setNewMemberRole('team_member');
        }}
        title="הוספת חבר לצוות"
        description="הזמינו משתמש קיים להצטרף לצוות"
        size="md"
      >
        <div className="space-y-4">
          {addMemberError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {addMemberError}
            </div>
          )}

          <Input
            label="כתובת דוא״ל"
            type="email"
            value={newMemberEmail}
            onChange={(e) => setNewMemberEmail(e.target.value)}
            placeholder="user@example.com"
            leftIcon={<Mail className="w-5 h-5" />}
            required
          />

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              תפקיד בצוות
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setNewMemberRole('team_member')}
                className={`p-4 rounded-xl border-2 transition-colors text-center ${
                  newMemberRole === 'team_member'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <Users className="w-6 h-6 mx-auto mb-2 text-slate-600" />
                <p className="font-medium text-slate-900">חבר צוות</p>
                <p className="text-xs text-slate-500">גישה לתיקי הצוות</p>
              </button>
              <button
                onClick={() => setNewMemberRole('team_leader')}
                className={`p-4 rounded-xl border-2 transition-colors text-center ${
                  newMemberRole === 'team_leader'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <Crown className="w-6 h-6 mx-auto mb-2 text-amber-500" />
                <p className="font-medium text-slate-900">ראש צוות</p>
                <p className="text-xs text-slate-500">ניהול הצוות והרשאות</p>
              </button>
            </div>
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleAddMember}
              className="flex-1"
              isLoading={isAddingMember}
              disabled={!newMemberEmail.trim()}
            >
              הוסף לצוות
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowAddMemberModal(false);
                setNewMemberEmail('');
                setNewMemberRole('team_member');
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

export default TeamsPage;
