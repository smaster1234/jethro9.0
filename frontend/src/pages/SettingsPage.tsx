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
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Card, Button, Badge, Input } from '../components/ui';
import { authApi, handleApiError } from '../api';

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
