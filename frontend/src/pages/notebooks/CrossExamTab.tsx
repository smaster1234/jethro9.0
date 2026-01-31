import React, { useEffect, useState } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import {
  Target,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertTriangle,
  ArrowLeft,
} from 'lucide-react';
import { casesApi } from '../../api';
import { Card, Badge, EmptyState } from '../../components/ui';
import { cn } from '../../utils/cn';
import type { Case } from '../../types';

interface CrossExamQuestion {
  question: string;
  purpose: string;
  expectedResponse?: string;
  followUp?: string;
  contradictionRef?: string;
  stage?: 'early' | 'mid' | 'late';
}

interface CrossExamSet {
  witnessName?: string;
  questions: CrossExamQuestion[];
}

export const CrossExamTab: React.FC = () => {
  const { notebookId } = useParams();
  const { notebook } = useOutletContext<{ notebook: Case }>();
  const [isLoading, setIsLoading] = useState(true);
  const [sets, setSets] = useState<CrossExamSet[]>([]);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  useEffect(() => {
    if (!notebookId) return;
    const fetch = async () => {
      setIsLoading(true);
      try {
        const runs = await casesApi.listRuns(notebookId, 5);
        const latest = runs.find((r: { status: string }) => r.status === 'done');
        if (latest?.metadata) {
          const crossExam = (latest.metadata as Record<string, unknown>).cross_exam_questions;
          if (Array.isArray(crossExam)) {
            setSets(crossExam as CrossExamSet[]);
          }
        }
      } catch {
        // silently fail
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, [notebookId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
      </div>
    );
  }

  if (sets.length === 0) {
    return (
      <div className="p-6">
        <EmptyState
          icon={<Target className="w-12 h-12" />}
          title="אין שאלות חקירה"
          description="הריצו ניתוח וסתירות ייווצרו שאלות חקירה אוטומטית"
        />
      </div>
    );
  }

  const totalQuestions = sets.reduce((sum, s) => sum + s.questions.length, 0);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-lg font-bold text-slate-900">שאלות חקירה נגדית</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          {totalQuestions} שאלות מוכנות · {sets.length} ערכות
        </p>
      </div>

      <div className="space-y-4">
        {sets.map((set, idx) => {
          const isExpanded = expandedIdx === idx;
          return (
            <Card key={idx} className="!p-0">
              <button
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                className="w-full flex items-center justify-between p-4 text-right"
              >
                <div className="flex items-center gap-3">
                  <Target className="w-5 h-5 text-accent-500" />
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">
                      {set.witnessName || `ערכת חקירה ${idx + 1}`}
                    </h3>
                    <p className="text-xs text-slate-500">{set.questions.length} שאלות</p>
                  </div>
                </div>
                {isExpanded ? (
                  <ChevronUp className="w-4 h-4 text-slate-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                )}
              </button>

              {isExpanded && (
                <div className="border-t border-slate-100 p-4 space-y-3">
                  {set.questions.map((q, qi) => (
                    <div key={qi} className="bg-slate-50 rounded-lg p-3 space-y-2">
                      <div className="flex items-start gap-2">
                        <MessageSquare className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-slate-900">{q.question}</p>
                          {q.purpose && (
                            <p className="text-xs text-slate-500 mt-1">
                              <span className="font-medium">מטרה:</span> {q.purpose}
                            </p>
                          )}
                          {q.expectedResponse && (
                            <p className="text-xs text-slate-500 mt-0.5">
                              <span className="font-medium">תשובה צפויה:</span> {q.expectedResponse}
                            </p>
                          )}
                          {q.followUp && (
                            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-accent-600">
                              <ArrowLeft className="w-3 h-3" />
                              <span>המשך: {q.followUp}</span>
                            </div>
                          )}
                        </div>
                        {q.stage && (
                          <Badge variant="neutral" className="text-[10px]">
                            {q.stage === 'early' ? 'פתיחה' : q.stage === 'mid' ? 'ליבה' : 'סיום'}
                          </Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
};

export default CrossExamTab;
