import React, { useState } from 'react';
import { StickyNote, Plus, Trash2, Clock, Edit3 } from 'lucide-react';
import { Card, Button, EmptyState } from '../../components/ui';

interface Note {
  id: string;
  content: string;
  createdAt: Date;
  updatedAt: Date;
}

export const NotesTab: React.FC = () => {
  const [notes, setNotes] = useState<Note[]>([]);
  const [newNote, setNewNote] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');

  const addNote = () => {
    if (!newNote.trim()) return;
    const note: Note = {
      id: Date.now().toString(),
      content: newNote.trim(),
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    setNotes((prev) => [note, ...prev]);
    setNewNote('');
  };

  const deleteNote = (id: string) => {
    setNotes((prev) => prev.filter((n) => n.id !== id));
  };

  const startEdit = (note: Note) => {
    setEditingId(note.id);
    setEditContent(note.content);
  };

  const saveEdit = () => {
    if (!editingId || !editContent.trim()) return;
    setNotes((prev) =>
      prev.map((n) =>
        n.id === editingId ? { ...n, content: editContent.trim(), updatedAt: new Date() } : n
      )
    );
    setEditingId(null);
    setEditContent('');
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-lg font-bold text-slate-900">הערות</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          {notes.length} הערות במחברת
        </p>
      </div>

      {/* New note input */}
      <Card className="!p-4">
        <textarea
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          placeholder="הוסיפו הערה..."
          rows={3}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-400"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              addNote();
            }
          }}
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[11px] text-slate-400">Ctrl+Enter לשמירה</span>
          <Button
            onClick={addNote}
            disabled={!newNote.trim()}
            leftIcon={<Plus className="w-4 h-4" />}
            className="text-sm"
          >
            הוסף
          </Button>
        </div>
      </Card>

      {/* Notes list */}
      {notes.length === 0 ? (
        <EmptyState
          icon={<StickyNote className="w-12 h-12" />}
          title="אין הערות עדיין"
          description="הוסיפו הערות לתיעוד תובנות ומחשבות"
        />
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <Card key={note.id} className="!p-4 group">
              {editingId === note.id ? (
                <div>
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={3}
                    className="w-full border border-primary-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-primary-400"
                    autoFocus
                  />
                  <div className="flex justify-end gap-2 mt-2">
                    <button
                      onClick={() => setEditingId(null)}
                      className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700"
                    >
                      ביטול
                    </button>
                    <button
                      onClick={saveEdit}
                      className="px-3 py-1.5 text-xs bg-primary-600 text-white rounded-md hover:bg-primary-700"
                    >
                      שמור
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-slate-800 whitespace-pre-wrap">{note.content}</p>
                  <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-100">
                    <span className="text-[11px] text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {note.updatedAt.toLocaleString('he-IL')}
                    </span>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => startEdit(note)}
                        className="p-1.5 text-slate-400 hover:text-primary-600 rounded-md hover:bg-primary-50"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => deleteNote(note.id)}
                        className="p-1.5 text-slate-400 hover:text-danger-600 rounded-md hover:bg-danger-50"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default NotesTab;
