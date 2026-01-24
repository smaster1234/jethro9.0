import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  AlertTriangle,
  CheckCircle,
  Lightbulb,
  Copy,
  FileText,
  ArrowDown,
  Sparkles,
  MessageSquare,
} from 'lucide-react';
import { analysisApi, handleApiError } from '../api';
import { Card, Button, Badge, Progress, Spinner, EmptyState } from '../components/ui';
import type { AnalysisResponse, Contradiction, CrossExamQuestion, CrossExamQuestionsOutput } from '../types';

// Helper to flatten cross-exam questions from nested structure
const flattenCrossExamQuestions = (
  questions: CrossExamQuestionsOutput[] | CrossExamQuestion[] | undefined
): CrossExamQuestion[] => {
  if (!questions || questions.length === 0) return [];

  // Check if it's already a flat array of questions
  const first = questions[0];
  if ('question' in first && typeof first.question === 'string') {
    // Already flat
    return questions as CrossExamQuestion[];
  }

  // It's nested - flatten
  return (questions as CrossExamQuestionsOutput[]).flatMap(
    (set) => set.questions || []
  );
};

export const AnalyzePage: React.FC = () => {
  const [text, setText] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'claims' | 'contradictions' | 'questions'>('contradictions');

  const handleAnalyze = async () => {
    if (!text.trim()) {
      setError('יש להזין טקסט לניתוח');
      return;
    }

    setIsAnalyzing(true);
    setError('');
    setProgress(0);
    setResult(null);

    // Simulate progress
    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + 5, 90));
    }, 200);

    try {
      const response = await analysisApi.analyzeText({
        text,
        source_name: sourceName || undefined,
      });

      clearInterval(progressInterval);
      setProgress(100);
      setResult(response);
    } catch (err) {
      clearInterval(progressInterval);
      setError(handleApiError(err));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const copyToClipboard = (textToCopy: string) => {
    navigator.clipboard.writeText(textToCopy);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">ניתוח טקסט</h1>
        <p className="text-slate-500 mt-1">
          הדביקו טקסט מעדות, מסמך או כל מקור אחר וזהו סתירות פוטנציאליות
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input Section */}
        <div className="space-y-4">
          <Card>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  שם המקור (אופציונלי)
                </label>
                <input
                  type="text"
                  value={sourceName}
                  onChange={(e) => setSourceName(e.target.value)}
                  placeholder="לדוגמה: עדות יוסי כהן"
                  className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  טקסט לניתוח
                </label>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="הדביקו כאן את הטקסט לניתוח...

לדוגמה:
בתאריך 15.3.2023 הייתי בבית בשעה 20:00. ראיתי את הנתבע מגיע לביתי בשעה 19:30. יצאתי מהעבודה בשעה 21:00 באותו יום."
                  rows={12}
                  className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none resize-none"
                />
                <div className="flex justify-between mt-2 text-sm text-slate-500">
                  <span>{text.length} תווים</span>
                  <span>{text.split(/\s+/).filter(Boolean).length} מילים</span>
                </div>
              </div>

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm"
                >
                  {error}
                </motion.div>
              )}

              {isAnalyzing && (
                <div className="space-y-3">
                  <Progress value={progress} showLabel label="מנתח טקסט..." />
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Sparkles className="w-4 h-4 animate-pulse text-primary-500" />
                    <span>מחלץ טענות ומזהה סתירות...</span>
                  </div>
                </div>
              )}

              <Button
                onClick={handleAnalyze}
                className="w-full"
                size="lg"
                isLoading={isAnalyzing}
                leftIcon={<Search className="w-5 h-5" />}
              >
                נתח טקסט
              </Button>
            </div>
          </Card>

          {/* Tips */}
          <Card className="bg-primary-50 border-primary-100">
            <div className="flex gap-3">
              <Lightbulb className="w-5 h-5 text-primary-600 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-primary-900 mb-2">טיפים לתוצאות טובות יותר</h3>
                <ul className="text-sm text-primary-700 space-y-1">
                  <li>• הכניסו טקסט מלא עם פרטים ספציפיים</li>
                  <li>• ציינו תאריכים, שעות ומספרים במדויק</li>
                  <li>• כללו מספר פסקאות או עדויות שונות</li>
                  <li>• השתמשו בעברית תקנית</li>
                </ul>
              </div>
            </div>
          </Card>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {!result && !isAnalyzing && (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <EmptyState
                icon={<FileText className="w-16 h-16" />}
                title="מוכן לניתוח"
                description="הזינו טקסט ולחצו על 'נתח טקסט' כדי לזהות סתירות"
              />
            </Card>
          )}

          {isAnalyzing && (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <div className="text-center">
                <Spinner size="lg" className="mx-auto mb-4" />
                <p className="text-lg font-medium text-slate-700">מנתח את הטקסט...</p>
                <p className="text-sm text-slate-500 mt-2">זה עשוי לקחת מספר שניות</p>
              </div>
            </Card>
          )}

          {result && !isAnalyzing && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              {/* Summary */}
              {(() => {
                const flatQuestions = flattenCrossExamQuestions(result.cross_exam_questions);
                return (
                  <>
                    <Card>
                      <div className="grid grid-cols-3 gap-4 text-center">
                        <div>
                          <div className="text-3xl font-bold text-slate-900">
                            {result.claims?.length || 0}
                          </div>
                          <div className="text-sm text-slate-500">טענות זוהו</div>
                        </div>
                        <div>
                          <div className="text-3xl font-bold text-warning-600">
                            {result.contradictions?.length || 0}
                          </div>
                          <div className="text-sm text-slate-500">סתירות נמצאו</div>
                        </div>
                        <div>
                          <div className="text-3xl font-bold text-primary-600">
                            {flatQuestions.length}
                          </div>
                          <div className="text-sm text-slate-500">שאלות הומלצו</div>
                        </div>
                      </div>
                    </Card>

                    {/* Tabs */}
                    <div className="flex gap-2">
                      <Button
                        variant={activeTab === 'claims' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveTab('claims')}
                        leftIcon={<FileText className="w-4 h-4" />}
                      >
                        טענות ({result.claims?.length || 0})
                      </Button>
                      <Button
                        variant={activeTab === 'contradictions' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveTab('contradictions')}
                        leftIcon={<AlertTriangle className="w-4 h-4" />}
                      >
                        סתירות ({result.contradictions?.length || 0})
                      </Button>
                      <Button
                        variant={activeTab === 'questions' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveTab('questions')}
                        leftIcon={<MessageSquare className="w-4 h-4" />}
                      >
                        שאלות ({flatQuestions.length})
                      </Button>
                    </div>
                  </>
                );
              })()}

              {/* Content */}
              <AnimatePresence mode="wait">
                {activeTab === 'claims' && (
                  <motion.div
                    key="claims"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-3"
                  >
                    {result.claims?.length === 0 ? (
                      <Card>
                        <div className="text-center py-8">
                          <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                          <p className="text-lg font-medium text-slate-700">
                            לא זוהו טענות
                          </p>
                          <p className="text-sm text-slate-500 mt-2">
                            נסה להזין טקסט מפורט יותר
                          </p>
                        </div>
                      </Card>
                    ) : (
                      result.claims?.map((claim, index) => (
                        <motion.div
                          key={claim.id || index}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: index * 0.05 }}
                        >
                          <Card className="border-r-4 border-primary-400">
                            <div className="flex items-start gap-3">
                              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-600 font-bold text-sm flex-shrink-0">
                                {index + 1}
                              </div>
                              <div className="flex-1">
                                <p className="text-slate-900">{claim.text}</p>
                                <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                                  {claim.source_name && (
                                    <span>מקור: {claim.source_name}</span>
                                  )}
                                  {claim.speaker && (
                                    <span>דובר: {claim.speaker}</span>
                                  )}
                                  {claim.category && (
                                    <Badge variant="neutral" size="sm">{claim.category}</Badge>
                                  )}
                                </div>
                              </div>
                            </div>
                          </Card>
                        </motion.div>
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === 'contradictions' && (
                  <motion.div
                    key="contradictions"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-4"
                  >
                    {result.contradictions?.length === 0 ? (
                      <Card>
                        <div className="text-center py-8">
                          <CheckCircle className="w-12 h-12 text-success-500 mx-auto mb-4" />
                          <p className="text-lg font-medium text-slate-700">
                            לא נמצאו סתירות
                          </p>
                          <p className="text-sm text-slate-500 mt-2">
                            הטקסט נראה עקבי ואין סתירות ברורות
                          </p>
                        </div>
                      </Card>
                    ) : (
                      result.contradictions?.map((contradiction, index) => (
                        <ContradictionCard
                          key={contradiction.id || index}
                          contradiction={contradiction}
                          index={index}
                        />
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === 'questions' && (
                  <motion.div
                    key="questions"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-4"
                  >
                    {(() => {
                      const flatQuestions = flattenCrossExamQuestions(result.cross_exam_questions);
                      if (flatQuestions.length === 0) {
                        return (
                          <Card>
                            <div className="text-center py-8">
                              <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                              <p className="text-lg font-medium text-slate-700">
                                אין שאלות מומלצות
                              </p>
                              <p className="text-sm text-slate-500 mt-2">
                                שאלות נוצרות כאשר מזוהות סתירות
                              </p>
                            </div>
                          </Card>
                        );
                      }
                      return flatQuestions.map((question, index) => (
                        <QuestionCard
                          key={question.id || index}
                          question={question}
                          index={index}
                          onCopy={copyToClipboard}
                        />
                      ));
                    })()}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

// Contradiction Card Component
const ContradictionCard: React.FC<{ contradiction: Contradiction; index: number }> = ({
  contradiction,
  index,
}) => {
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'high':
        return 'danger';
      case 'medium':
        return 'warning';
      default:
        return 'neutral';
    }
  };

  const getSeverityLabel = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'קריטי';
      case 'high':
        return 'גבוה';
      case 'medium':
        return 'בינוני';
      case 'low':
        return 'נמוך';
      default:
        return severity;
    }
  };

  const getTypeLabel = (type: string) => {
    const types: Record<string, string> = {
      'TEMPORAL_DATE': 'סתירה בתאריכים',
      'QUANTITATIVE_AMOUNT': 'סתירה בכמויות/סכומים',
      'ACTOR_ATTRIBUTION': 'סתירה בזיהוי מבצע הפעולה',
      'PRESENCE_PARTICIPATION': 'סתירה בנוכחות/השתתפות',
      'DOCUMENT_EXISTENCE': 'סתירה בקיום מסמך',
      'IDENTITY_BASIC': 'סתירה בזיהוי/זהות',
    };
    return types[type] || type;
  };

  // Generate explanation if not provided
  const getExplanation = () => {
    if (contradiction.explanation_he) return contradiction.explanation_he;
    if (contradiction.explanation) return contradiction.explanation;

    // Generate a basic explanation based on contradiction type
    const explanations: Record<string, string> = {
      'TEMPORAL_DATE': `התאריכים בשתי הטענות אינם תואמים. יש לברר איזה תאריך הוא הנכון.`,
      'QUANTITATIVE_AMOUNT': `הכמויות או הסכומים המצוינים בשתי הטענות שונים זה מזה.`,
      'ACTOR_ATTRIBUTION': `יש אי-התאמה לגבי מי ביצע את הפעולה המתוארת.`,
      'PRESENCE_PARTICIPATION': `הטענות סותרות זו את זו לגבי נוכחות או השתתפות במאורע.`,
      'DOCUMENT_EXISTENCE': `יש סתירה לגבי קיומו או אי-קיומו של מסמך.`,
      'IDENTITY_BASIC': `פרטי הזיהוי בשתי הטענות אינם תואמים.`,
    };

    return explanations[contradiction.contradiction_type] ||
      `שתי הטענות מכילות מידע סותר שדורש בירור נוסף.`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
    >
      <Card className="border-r-4 border-warning-500">
        <div className="space-y-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-warning-500" />
              <span className="font-bold text-slate-900">סתירה #{index + 1}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={getSeverityColor(contradiction.severity) as any}>
                {getSeverityLabel(contradiction.severity)}
              </Badge>
              <Badge variant="neutral">{getTypeLabel(contradiction.contradiction_type)}</Badge>
            </div>
          </div>

          {/* Claims */}
          <div className="space-y-3">
            <div className="p-4 bg-red-50 rounded-xl border border-red-100">
              <div className="text-xs text-red-500 font-medium mb-1">טענה א'</div>
              <p className="text-slate-800">
                {contradiction.claim_a?.text || 'לא זמין'}
              </p>
            </div>

            <div className="flex justify-center">
              <div className="w-8 h-8 rounded-full bg-warning-100 flex items-center justify-center">
                <ArrowDown className="w-4 h-4 text-warning-600" />
              </div>
            </div>

            <div className="p-4 bg-orange-50 rounded-xl border border-orange-100">
              <div className="text-xs text-orange-500 font-medium mb-1">טענה ב'</div>
              <p className="text-slate-800">
                {contradiction.claim_b?.text || 'לא זמין'}
              </p>
            </div>
          </div>

          {/* Explanation - always shown */}
          <div className="p-4 bg-slate-50 rounded-xl">
            <div className="text-xs text-slate-500 font-medium mb-1">הסבר</div>
            <p className="text-slate-700">{getExplanation()}</p>
          </div>

          {/* Confidence */}
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span>רמת ביטחון:</span>
            <div className="flex-1 h-2 bg-slate-200 rounded-full max-w-32">
              <div
                className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full"
                style={{ width: `${(contradiction.confidence || 0) * 100}%` }}
              />
            </div>
            <span className="font-medium">
              {Math.round((contradiction.confidence || 0) * 100)}%
            </span>
          </div>
        </div>
      </Card>
    </motion.div>
  );
};

// Question Card Component
const QuestionCard: React.FC<{
  question: CrossExamQuestion;
  index: number;
  onCopy: (text: string) => void;
}> = ({ question, index, onCopy }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    onCopy(question.question);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
    >
      <Card>
        <div className="space-y-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-600 font-bold text-sm">
                {index + 1}
              </div>
              <span className="text-xs text-slate-500">{question.strategy || 'שאלה'}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              leftIcon={copied ? <CheckCircle className="w-4 h-4 text-success-500" /> : <Copy className="w-4 h-4" />}
            >
              {copied ? 'הועתק!' : 'העתק'}
            </Button>
          </div>

          <p className="text-lg text-slate-900 font-medium">{question.question}</p>

          {question.purpose && (
            <p className="text-sm text-slate-500">
              <span className="font-medium">מטרה:</span> {question.purpose}
            </p>
          )}

          {/* Show follow-up question if available */}
          {(question.follow_up || (question.follow_ups && question.follow_ups.length > 0)) && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-xs text-slate-500 font-medium mb-2">שאלות המשך:</p>
              <ul className="space-y-1">
                {question.follow_up && (
                  <li className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-slate-400">•</span>
                    {question.follow_up}
                  </li>
                )}
                {question.follow_ups?.map((followUp, i) => (
                  <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-slate-400">•</span>
                    {followUp}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>
    </motion.div>
  );
};

export default AnalyzePage;
