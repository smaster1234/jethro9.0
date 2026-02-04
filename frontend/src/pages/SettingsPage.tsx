import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  User,
  Building2,
  Bell,
  Shield,
  Palette,
  Save,
  CheckCircle,
  AlertTriangle,
  Search,
  UserPlus,
  Mail,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Card, Button, Badge, Input } from '../components/ui';
import { authApi, handleApiError, orgsApi } from '../api';
import type { Organization, OrganizationMember, UserSearchResult } from '../types';

type SettingsTab = 'profile' | 'firm' | 'notifications' | 'appearance';

export const SettingsPage: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Profile form state
  const [profileForm, setProfileForm] = useState({
    name: '',
    email: '',
    professional_role: '',
    phone: '',
  });

  // Organization state
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState('');
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [isLoadingOrg, setIsLoadingOrg] = useState(false);
  const [orgError, setOrgError] = useState('');
  const [newOrgName, setNewOrgName] = useState('');
  const [isCreatingOrg, setIsCreatingOrg] = useState(false);

  // Member search/invite
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserSearchResult[]>([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [memberRole, setMemberRole] = useState<'viewer' | 'intern' | 'lawyer' | 'owner'>('viewer');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'viewer' | 'intern' | 'lawyer' | 'owner'>('viewer');
  const [isAddingMember, setIsAddingMember] = useState(false);
  const [isInviting, setIsInviting] = useState(false);
  const [memberActionError, setMemberActionError] = useState('');

  // Load user data
  useEffect(() => {
    if (user) {
      setProfileForm({
        name: user.name || '',
        email: user.email || '',
        professional_role: user.professional_role || '',
        phone: '',
      });
    }
  }, [user]);

  useEffect(() => {
    if (activeTab !== 'firm') return;
    const loadOrgs = async () => {
      setIsLoadingOrg(true);
      setOrgError('');
      try {
        const orgList = await orgsApi.list();
        setOrgs(orgList);
        if (!selectedOrgId && orgList.length > 0) {
          setSelectedOrgId(orgList[0].id);
        }
      } catch (err) {
        setOrgError(handleApiError(err));
      } finally {
        setIsLoadingOrg(false);
      }
    };
    loadOrgs();
  }, [activeTab, selectedOrgId]);

  useEffect(() => {
    if (!selectedOrgId || activeTab !== 'firm') return;
    const loadMembers = async () => {
      setIsLoadingOrg(true);
      setOrgError('');
      try {
        const list = await orgsApi.listMembers(selectedOrgId);
        setMembers(list);
      } catch (err) {
        setOrgError(handleApiError(err));
      } finally {
        setIsLoadingOrg(false);
      }
    };
    loadMembers();
  }, [selectedOrgId, activeTab]);

  useEffect(() => {
    if (!selectedOrgId || activeTab !== 'firm') return;
    if (!searchQuery || searchQuery.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    const handler = setTimeout(async () => {
      try {
        const results = await orgsApi.searchUsers(searchQuery.trim());
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery, selectedOrgId, activeTab]);

  const [saveError, setSaveError] = useState('');

  const handleSaveProfile = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    setSaveError('');

    try {
      await authApi.updateProfile({
        name: profileForm.name,
        professional_role: profileForm.professional_role || undefined,
      });

      // Refresh user data in context
      if (refreshUser) {
        await refreshUser();
      }

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error('Failed to save profile:', err);
      setSaveError(handleApiError(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateOrg = async () => {
    if (!newOrgName.trim()) return;
    setIsCreatingOrg(true);
    setOrgError('');
    try {
      const org = await orgsApi.create({ name: newOrgName.trim() });
      setOrgs((prev) => [...prev, org]);
      setSelectedOrgId(org.id);
      setNewOrgName('');
    } catch (err) {
      setOrgError(handleApiError(err));
    } finally {
      setIsCreatingOrg(false);
    }
  };

  const handleAddMember = async () => {
    if (!selectedOrgId || !selectedUserId) return;
    setIsAddingMember(true);
    setMemberActionError('');
    try {
      await orgsApi.addMember(selectedOrgId, { user_id: selectedUserId, role: memberRole });
      const list = await orgsApi.listMembers(selectedOrgId);
      setMembers(list);
      setSelectedUserId('');
      setSearchQuery('');
      setSearchResults([]);
    } catch (err) {
      setMemberActionError(handleApiError(err));
    } finally {
      setIsAddingMember(false);
    }
  };

  const handleInvite = async () => {
    if (!selectedOrgId || !inviteEmail.trim()) return;
    setIsInviting(true);
    setMemberActionError('');
    try {
      await orgsApi.invite(selectedOrgId, { email: inviteEmail.trim(), role: inviteRole });
      setInviteEmail('');
    } catch (err) {
      setMemberActionError(handleApiError(err));
    } finally {
      setIsInviting(false);
    }
  };

  const tabs = [
    { id: 'profile' as const, label: 'פרופיל', icon: User },
    { id: 'firm' as const, label: 'משרד', icon: Building2 },
    { id: 'notifications' as const, label: 'התראות', icon: Bell },
    { id: 'appearance' as const, label: 'תצוגה', icon: Palette },
  ];

  const getRoleBadge = (role: string) => {
    switch (role) {
      case 'super_admin':
        return <Badge variant="danger">מנהל מערכת</Badge>;
      case 'admin':
        return <Badge variant="warning">מנהל משרד</Badge>;
      case 'member':
        return <Badge variant="primary">חבר</Badge>;
      default:
        return <Badge variant="neutral">צופה</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">הגדרות</h1>
        <p className="text-slate-500 mt-1">ניהול הפרופיל והעדפות המערכת</p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar */}
        <div className="w-64 flex-shrink-0">
          <Card padding="none">
            <nav className="p-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors ${
                    activeTab === tab.id
                      ? 'bg-primary-50 text-primary-700 font-medium'
                      : 'text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <tab.icon className="w-5 h-5" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </Card>
        </div>

        {/* Content */}
        <div className="flex-1">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {activeTab === 'profile' && (
              <Card>
                <div className="space-y-6">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                      <h2 className="text-xl font-bold text-slate-900">פרופיל אישי</h2>
                      <p className="text-sm text-slate-500 mt-1">עדכון פרטים אישיים</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {getRoleBadge(user?.system_role || 'viewer')}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-6">
                    <Input
                      label="שם מלא"
                      value={profileForm.name}
                      onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })}
                      placeholder="ישראל ישראלי"
                    />
                    <Input
                      label="דוא״ל"
                      type="email"
                      value={profileForm.email}
                      onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                      placeholder="email@example.com"
                      disabled
                    />
                    <Input
                      label="תפקיד מקצועי"
                      value={profileForm.professional_role}
                      onChange={(e) => setProfileForm({ ...profileForm, professional_role: e.target.value })}
                      placeholder="לדוגמה: עו״ד בכיר, שותף"
                    />
                    <Input
                      label="טלפון"
                      type="tel"
                      value={profileForm.phone}
                      onChange={(e) => setProfileForm({ ...profileForm, phone: e.target.value })}
                      placeholder="050-1234567"
                    />
                  </div>

                  <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                    <div>
                      {saveSuccess && (
                        <div className="flex items-center gap-2 text-success-600">
                          <CheckCircle className="w-5 h-5" />
                          <span className="text-sm font-medium">השינויים נשמרו</span>
                        </div>
                      )}
                      {saveError && (
                        <div className="flex items-center gap-2 text-danger-600">
                          <AlertTriangle className="w-5 h-5" />
                          <span className="text-sm font-medium">{saveError}</span>
                        </div>
                      )}
                    </div>
                    <Button
                      onClick={handleSaveProfile}
                      isLoading={isSaving}
                      leftIcon={<Save className="w-4 h-4" />}
                    >
                      שמור שינויים
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'firm' && (
              <Card>
                <div className="space-y-6">
                  <div className="border-b border-slate-100 pb-4">
                    <h2 className="text-xl font-bold text-slate-900">פרטי המשרד</h2>
                    <p className="text-sm text-slate-500 mt-1">מידע על המשרד שלך</p>
                  </div>

                  <div className="p-6 bg-slate-50 rounded-2xl">
                    <div className="flex items-center gap-4 mb-4">
                      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center">
                        <Building2 className="w-8 h-8 text-white" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">
                          {user?.firm_name || 'משרד עורכי דין'}
                        </h3>
                        <p className="text-sm text-slate-500">
                          מזהה משרד: {user?.firm_id?.slice(0, 8) || 'N/A'}
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-slate-500">תפקיד במשרד:</span>
                        <div className="mt-1">
                          {getRoleBadge(user?.system_role || 'viewer')}
                        </div>
                      </div>
                      <div>
                        <span className="text-slate-500">צוותים:</span>
                        <p className="mt-1 font-medium text-slate-900">
                          {user?.teams?.length || 0} צוותים
                        </p>
                      </div>
                    </div>
                  </div>

                  {user?.is_admin && (
                    <div className="p-4 bg-warning-50 rounded-xl border border-warning-200">
                      <div className="flex items-center gap-2 text-warning-700">
                        <Shield className="w-5 h-5" />
                        <span className="font-medium">הרשאות מנהל</span>
                      </div>
                      <p className="text-sm text-warning-600 mt-1">
                        יש לך הרשאות מנהל במשרד. ניתן לנהל משתמשים וצוותים.
                      </p>
                    </div>
                  )}

                  <div className="border-t border-slate-100 pt-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-slate-900">חברי משרד</h3>
                      {isLoadingOrg && <span className="text-xs text-slate-500">טוען...</span>}
                    </div>

                    {orgError && (
                      <div className="p-3 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
                        {orgError}
                      </div>
                    )}
                    {memberActionError && (
                      <div className="p-3 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
                        {memberActionError}
                      </div>
                    )}

                    {orgs.length === 0 ? (
                      <div className="space-y-3">
                        <Input
                          label="שם משרד"
                          value={newOrgName}
                          onChange={(e) => setNewOrgName(e.target.value)}
                          placeholder="משרד ראשי"
                        />
                        <Button onClick={handleCreateOrg} isLoading={isCreatingOrg}>
                          צור משרד
                        </Button>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-sm text-slate-600">בחירת משרד</label>
                            <select
                              value={selectedOrgId}
                              onChange={(e) => setSelectedOrgId(e.target.value)}
                              className="mt-2 w-full px-3 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                            >
                              {orgs.map((org) => (
                                <option key={org.id} value={org.id}>
                                  {org.name}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        <div className="space-y-2">
                          {members.length === 0 ? (
                            <div className="text-sm text-slate-500">אין חברי משרד להצגה.</div>
                          ) : (
                            <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl">
                              {members.map((member) => (
                                <div key={member.user_id} className="p-3 flex items-center justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-slate-900">{member.name}</p>
                                    <p className="text-xs text-slate-500">{member.email}</p>
                                  </div>
                                  <Badge variant="neutral">{member.role}</Badge>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <Input
                            label="חפש משתמש"
                            value={searchQuery}
                            onChange={(e) => {
                              setSearchQuery(e.target.value);
                              setSelectedUserId('');
                            }}
                            placeholder="שם או דוא״ל"
                            leftIcon={<Search className="w-4 h-4" />}
                          />
                          <div>
                            <label className="text-sm text-slate-600">תפקיד</label>
                            <select
                              value={memberRole}
                              onChange={(e) => setMemberRole(e.target.value as typeof memberRole)}
                              className="mt-2 w-full px-3 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                            >
                              <option value="viewer">viewer</option>
                              <option value="intern">intern</option>
                              <option value="lawyer">lawyer</option>
                              <option value="owner">owner</option>
                            </select>
                          </div>
                        </div>

                        {searchResults.length > 0 && (
                          <div className="border border-slate-200 rounded-xl divide-y divide-slate-100">
                            {searchResults.map((result) => (
                              <button
                                key={result.id}
                                onClick={() => setSelectedUserId(result.id)}
                                className={`w-full text-right p-3 hover:bg-slate-50 ${
                                  selectedUserId === result.id ? 'bg-primary-50' : ''
                                }`}
                              >
                                <div className="text-sm font-medium text-slate-900">{result.name}</div>
                                <div className="text-xs text-slate-500">{result.email}</div>
                              </button>
                            ))}
                          </div>
                        )}

                        <Button
                          onClick={handleAddMember}
                          isLoading={isAddingMember}
                          disabled={!selectedUserId}
                          leftIcon={<UserPlus className="w-4 h-4" />}
                        >
                          הוסף חבר משרד
                        </Button>

                        {searchQuery.trim().length >= 2 && searchResults.length === 0 && (
                          <div className="space-y-3 border-t border-slate-100 pt-4">
                            <Input
                              label="הזמנה בדוא״ל"
                              value={inviteEmail}
                              onChange={(e) => setInviteEmail(e.target.value)}
                              placeholder="user@example.com"
                              leftIcon={<Mail className="w-4 h-4" />}
                            />
                            <div>
                              <label className="text-sm text-slate-600">תפקיד בהזמנה</label>
                              <select
                                value={inviteRole}
                                onChange={(e) => setInviteRole(e.target.value as typeof inviteRole)}
                                className="mt-2 w-full px-3 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                              >
                                <option value="viewer">viewer</option>
                                <option value="intern">intern</option>
                                <option value="lawyer">lawyer</option>
                                <option value="owner">owner</option>
                              </select>
                            </div>
                            <Button onClick={handleInvite} isLoading={isInviting}>
                              שלח הזמנה
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'notifications' && (
              <Card>
                <div className="space-y-6">
                  <div className="border-b border-slate-100 pb-4">
                    <h2 className="text-xl font-bold text-slate-900">העדפות התראות</h2>
                    <p className="text-sm text-slate-500 mt-1">בחר אילו התראות לקבל</p>
                  </div>

                  <div className="space-y-4">
                    {[
                      { id: 'analysis_complete', label: 'ניתוח הושלם', desc: 'התראה כשניתוח מסמכים מסתיים' },
                      { id: 'new_contradiction', label: 'סתירה חדשה', desc: 'התראה כשמתגלה סתירה חדשה' },
                      { id: 'team_activity', label: 'פעילות צוות', desc: 'התראות על פעילות חברי הצוות' },
                      { id: 'weekly_summary', label: 'סיכום שבועי', desc: 'דוח שבועי על פעילות במערכת' },
                    ].map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between p-4 bg-slate-50 rounded-xl"
                      >
                        <div>
                          <p className="font-medium text-slate-900">{item.label}</p>
                          <p className="text-sm text-slate-500">{item.desc}</p>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input type="checkbox" className="sr-only peer" defaultChecked />
                          <div className="w-11 h-6 bg-slate-300 peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
                        </label>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'appearance' && (
              <Card>
                <div className="space-y-6">
                  <div className="border-b border-slate-100 pb-4">
                    <h2 className="text-xl font-bold text-slate-900">העדפות תצוגה</h2>
                    <p className="text-sm text-slate-500 mt-1">התאמה אישית של ממשק המערכת</p>
                  </div>

                  <div className="space-y-4">
                    <div className="p-4 bg-slate-50 rounded-xl">
                      <p className="font-medium text-slate-900 mb-3">ערכת צבעים</p>
                      <div className="flex gap-3">
                        <button className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 ring-2 ring-primary-500 ring-offset-2" />
                        <button className="w-12 h-12 rounded-xl bg-gradient-to-br from-slate-700 to-slate-900 hover:ring-2 hover:ring-slate-500 hover:ring-offset-2" />
                        <button className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 hover:ring-2 hover:ring-emerald-500 hover:ring-offset-2" />
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                      <div>
                        <p className="font-medium text-slate-900">מצב כהה</p>
                        <p className="text-sm text-slate-500">החלף למצב תצוגה כהה</p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" className="sr-only peer" />
                        <div className="w-11 h-6 bg-slate-300 peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
                      </label>
                    </div>

                    <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                      <div>
                        <p className="font-medium text-slate-900">אנימציות מופחתות</p>
                        <p className="text-sm text-slate-500">הפחת אנימציות בממשק</p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" className="sr-only peer" />
                        <div className="w-11 h-6 bg-slate-300 peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
                      </label>
                    </div>
                  </div>
                </div>
              </Card>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
