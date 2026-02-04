import React, { useEffect, useState } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { Users, Plus, FileText, Loader2, UserCircle } from 'lucide-react';
import { witnessesApi } from '../../api';
import { Card, Badge, EmptyState, Button } from '../../components/ui';
import type { Case, Witness } from '../../types';

export const WitnessesTab: React.FC = () => {
  const { notebookId } = useParams();
  useOutletContext<{ notebook: Case }>();
  const [witnesses, setWitnesses] = useState<Witness[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!notebookId) return;
    const fetch = async () => {
      setIsLoading(true);
      try {
        const data = await witnessesApi.list(notebookId);
        setWitnesses(data);
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

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900">עדים</h2>
          <p className="text-sm text-slate-500 mt-0.5">{witnesses.length} עדים</p>
        </div>
        <Button
          variant="secondary"
          leftIcon={<Plus className="w-4 h-4" />}
          className="text-sm"
        >
          הוסף עד
        </Button>
      </div>

      {witnesses.length === 0 ? (
        <EmptyState
          icon={<Users className="w-12 h-12" />}
          title="אין עדים עדיין"
          description="הוסיפו עדים לתיק כדי לנהל תצהירים ולתכנן חקירות"
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {witnesses.map((w) => (
            <Card key={w.id} variant="interactive" className="!p-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center">
                  <UserCircle className="w-6 h-6 text-slate-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-bold text-slate-900">{w.name}</h3>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                    {w.side && (
                      <Badge variant={w.side === 'ours' ? 'primary' : 'neutral'} className="text-[10px]">
                        {w.side === 'ours' ? 'שלנו' : 'צד שכנגד'}
                      </Badge>
                    )}
                  </div>
                  {w.versions && w.versions.length > 0 && (
                    <div className="flex items-center gap-1.5 mt-2 text-xs text-slate-500">
                      <FileText className="w-3.5 h-3.5" />
                      <span>{w.versions.length} גירסאות תצהיר</span>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default WitnessesTab;
