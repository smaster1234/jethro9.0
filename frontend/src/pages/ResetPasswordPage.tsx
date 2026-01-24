import React, { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Lock, ArrowRight, CheckCircle, AlertTriangle } from 'lucide-react';
import { Card, Button, Input } from '../components/ui';
import { authApi, handleApiError } from '../api';

export const ResetPasswordPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [error, setError] = useState('');

  const validatePassword = (): string | null => {
    if (password.length < 8) {
      return 'הסיסמה חייבת להכיל לפחות 8 תווים';
    }
    if (password !== confirmPassword) {
      return 'הסיסמאות אינן תואמות';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const validationError = validatePassword();
    if (validationError) {
      setError(validationError);
      return;
    }

    if (!token) {
      setError('טוקן איפוס חסר');
      return;
    }

    setIsLoading(true);

    try {
      await authApi.resetPassword({
        token,
        new_password: password,
      });
      setIsSuccess(true);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          <Card className="text-center">
            <div className="w-16 h-16 rounded-full bg-danger-100 flex items-center justify-center mx-auto mb-6">
              <AlertTriangle className="w-8 h-8 text-danger-600" />
            </div>
            <h1 className="text-2xl font-bold text-slate-900 mb-2">קישור לא תקין</h1>
            <p className="text-slate-600 mb-6">
              הקישור לאיפוס הסיסמה אינו תקין או שפג תוקפו.
            </p>
            <Link to="/forgot-password">
              <Button variant="primary" className="w-full">
                בקש קישור חדש
              </Button>
            </Link>
          </Card>
        </motion.div>
      </div>
    );
  }

  if (isSuccess) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          <Card className="text-center">
            <div className="w-16 h-16 rounded-full bg-success-100 flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-success-600" />
            </div>
            <h1 className="text-2xl font-bold text-slate-900 mb-2">הסיסמה אופסה בהצלחה</h1>
            <p className="text-slate-600 mb-6">
              עכשיו תוכל להתחבר עם הסיסמה החדשה.
            </p>
            <Button onClick={() => navigate('/login')} className="w-full">
              התחבר
            </Button>
          </Card>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <Link to="/" className="inline-block mb-6">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center mx-auto shadow-lg shadow-primary-500/25">
              <span className="text-3xl font-bold text-white">J</span>
            </div>
          </Link>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">איפוס סיסמה</h1>
          <p className="text-slate-500">הזן סיסמה חדשה לחשבון שלך</p>
        </div>

        <Card>
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
                {error}
              </div>
            )}

            <Input
              label="סיסמה חדשה"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="לפחות 8 תווים"
              leftIcon={<Lock className="w-5 h-5" />}
              required
            />

            <Input
              label="אימות סיסמה"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="הזן שוב את הסיסמה"
              leftIcon={<Lock className="w-5 h-5" />}
              required
            />

            <div className="text-xs text-slate-500">
              הסיסמה חייבת להכיל לפחות 8 תווים
            </div>

            <Button
              type="submit"
              className="w-full"
              isLoading={isLoading}
              rightIcon={<ArrowRight className="w-5 h-5" />}
            >
              אפס סיסמה
            </Button>
          </form>
        </Card>
      </motion.div>
    </div>
  );
};

export default ResetPasswordPage;
