import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, Scale, ArrowLeft, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Button, Input, Card } from '../components/ui';
import { handleApiError } from '../api';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const isPasswordTooLong = (value: string) => new TextEncoder().encode(value).length > 72;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (isPasswordTooLong(password)) {
        setError('הסיסמה ארוכה מדי (מקסימום 72 בתים)');
        return;
      }
      await login({ email, password });
      navigate('/dashboard');
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Branding */}
      <motion.div
        initial={{ opacity: 0, x: -50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6 }}
        className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-slate-900 via-primary-900 to-slate-900 relative overflow-hidden"
      >
        {/* Background elements */}
        <div className="absolute inset-0">
          <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-primary-500/20 rounded-full blur-3xl animate-float" />
          <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-accent-500/20 rounded-full blur-3xl animate-float animation-delay-200" />
        </div>

        {/* Content */}
        <div className="relative z-10 flex flex-col justify-center items-center w-full p-12 text-white">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
            className="w-24 h-24 rounded-3xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center mb-8 shadow-2xl shadow-primary-500/30"
          >
            <Scale className="w-12 h-12 text-white" />
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="text-5xl font-bold mb-4 text-center"
          >
            Jethro
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="text-xl text-slate-300 text-center max-w-md mb-8"
          >
            מערכת AI לזיהוי סתירות וייצור שאלות חקירה נגדית
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="grid grid-cols-3 gap-8 mt-8"
          >
            {[
              { value: '99%', label: 'דיוק בזיהוי' },
              { value: '50+', label: 'סוגי סתירות' },
              { value: '10x', label: 'מהיר יותר' },
            ].map((stat, i) => (
              <div key={i} className="text-center">
                <div className="text-3xl font-bold gradient-text">{stat.value}</div>
                <div className="text-sm text-slate-400">{stat.label}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </motion.div>

      {/* Right side - Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-gradient-to-br from-slate-50 via-white to-blue-50">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-md"
        >
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center justify-center mb-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-xl shadow-primary-500/30">
              <Scale className="w-8 h-8 text-white" />
            </div>
          </div>

          <Card padding="lg" className="shadow-2xl">
            <div className="text-center mb-8">
              <h2 className="text-3xl font-bold text-slate-900 mb-2">ברוכים הבאים</h2>
              <p className="text-slate-500">התחברו לחשבון שלכם</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm"
                >
                  {error}
                </motion.div>
              )}

              <Input
                label="אימייל"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                leftIcon={<Mail className="w-5 h-5" />}
                required
              />

              <div className="relative">
                <Input
                  label="סיסמה"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="הזינו את הסיסמה"
                  leftIcon={<Lock className="w-5 h-5" />}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute left-12 top-[42px] text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>

              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                  <input
                    type="checkbox"
                    className="w-4 h-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                  />
                  זכור אותי
                </label>
                <a href="#" className="text-sm text-primary-600 hover:text-primary-700 font-medium">
                  שכחת סיסמה?
                </a>
              </div>

              <Button
                type="submit"
                className="w-full"
                size="lg"
                isLoading={isLoading}
                rightIcon={<ArrowLeft className="w-5 h-5" />}
              >
                התחבר
              </Button>
            </form>

            <div className="mt-8 text-center">
              <p className="text-slate-500">
                אין לכם חשבון?{' '}
                <Link
                  to="/register"
                  className="text-primary-600 hover:text-primary-700 font-semibold"
                >
                  הירשמו עכשיו
                </Link>
              </p>
            </div>
          </Card>

          <p className="text-center text-sm text-slate-400 mt-6">
            בהתחברות אתם מסכימים ל
            <a href="#" className="text-primary-600 hover:underline mx-1">תנאי השימוש</a>
            ול
            <a href="#" className="text-primary-600 hover:underline mx-1">מדיניות הפרטיות</a>
          </p>
        </motion.div>
      </div>
    </div>
  );
};

export default LoginPage;
