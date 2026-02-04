import React, { useEffect, useState } from 'react';
import { Modal, Spinner, Badge } from './ui';
import { anchorsApi } from '../api';
import type { AnchorResolveResponse, EvidenceAnchor } from '../types';
import { useApiWithToast } from '../hooks/useApiWithToast';

type EvidenceViewerModalProps = {
  isOpen: boolean;
  onClose: () => void;
  leftAnchor?: EvidenceAnchor | null;
  rightAnchor?: EvidenceAnchor | null;
  title?: string;
};

const HighlightedText: React.FC<{ text: string; start?: number; end?: number }> = ({
  text,
  start,
  end,
}) => {
  if (start === undefined || end === undefined || start < 0 || end <= start || end > text.length) {
    return <span>{text}</span>;
  }

  return (
    <span>
      {text.slice(0, start)}
      <mark className="bg-yellow-200 text-slate-900 rounded px-0.5">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </span>
  );
};

const EvidencePanel: React.FC<{
  label: string;
  data?: AnchorResolveResponse | null;
  isLoading: boolean;
}> = ({ label, data, isLoading }) => {
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-48">
        <Spinner size="md" />
        <p className="text-sm text-slate-500 mt-3">טוען ראיה...</p>
      </div>
    );
  }

  if (!data || !data.text) {
    return (
      <div className="text-sm text-slate-500 bg-slate-50 border border-dashed border-slate-200 rounded-xl p-4">
        מקור לא זמין להצגה.
      </div>
    );
  }

  const metaParts = [
    data.doc_name,
    data.page_no ? `עמ' ${data.page_no}` : null,
    data.block_index !== undefined ? `בלוק ${data.block_index}` : null,
  ].filter(Boolean);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Badge variant="neutral">{label}</Badge>
        <span className="text-xs text-slate-500">{metaParts.join(' · ')}</span>
      </div>
      <div
        className="bg-white border border-slate-200 rounded-xl p-4 text-sm leading-6 text-slate-800 whitespace-pre-wrap"
        dir="auto"
      >
        <HighlightedText text={data.text} start={data.highlight_start} end={data.highlight_end} />
      </div>
      {(data.context_before || data.context_after) && (
        <div className="text-xs text-slate-500 space-y-2">
          {data.context_before && (
            <div className="border-r-2 border-slate-200 pr-3">{data.context_before}</div>
          )}
          {data.context_after && (
            <div className="border-r-2 border-slate-200 pr-3">{data.context_after}</div>
          )}
        </div>
      )}
    </div>
  );
};

export const EvidenceViewerModal: React.FC<EvidenceViewerModalProps> = ({
  isOpen,
  onClose,
  leftAnchor,
  rightAnchor,
  title = 'השוואת ראיות',
}) => {
  const { withErrorToast } = useApiWithToast();
  const [leftData, setLeftData] = useState<AnchorResolveResponse | null>(null);
  const [rightData, setRightData] = useState<AnchorResolveResponse | null>(null);
  const [isLoadingLeft, setIsLoadingLeft] = useState(false);
  const [isLoadingRight, setIsLoadingRight] = useState(false);

  useEffect(() => {
    let isActive = true;

    const fetchAnchor = async (
      anchor: EvidenceAnchor | null | undefined,
      setData: (data: AnchorResolveResponse | null) => void,
      setLoading: (loading: boolean) => void
    ) => {
      if (!anchor || !anchor.doc_id) {
        setData(null);
        return;
      }
      setLoading(true);
      try {
        const data = await withErrorToast(
          anchorsApi.resolve({ anchor, context: 1 }),
          'שגיאה בטעינת ראיה'
        );
        if (isActive) {
          setData(data);
        }
      } catch {
        if (isActive) {
          setData(null);
        }
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    };

    if (isOpen) {
      fetchAnchor(leftAnchor, setLeftData, setIsLoadingLeft);
      fetchAnchor(rightAnchor, setRightData, setIsLoadingRight);
    } else {
      setLeftData(null);
      setRightData(null);
      setIsLoadingLeft(false);
      setIsLoadingRight(false);
    }

    return () => {
      isActive = false;
    };
  }, [isOpen, leftAnchor, rightAnchor, withErrorToast]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="xl">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <EvidencePanel label="טענה א'" data={leftData} isLoading={isLoadingLeft} />
        <EvidencePanel label="טענה ב'" data={rightData} isLoading={isLoadingRight} />
      </div>
    </Modal>
  );
};

export default EvidenceViewerModal;
