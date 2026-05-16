// Toast Component

import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { useToastStore, type Toast, type ToastType } from '../../stores/toastStore';

const icons: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle className="w-4 h-4" />,
  error: <AlertCircle className="w-4 h-4" />,
  warning: <AlertTriangle className="w-4 h-4" />,
  info: <Info className="w-4 h-4" />,
};

const styles: Record<ToastType, string> = {
  success: 'bg-[var(--color-success)]/10 border-[var(--color-success)]/20 text-[var(--color-success)]',
  error: 'bg-[var(--color-error)]/10 border-[var(--color-error)]/20 text-[var(--color-error)]',
  warning: 'bg-[var(--color-warning)]/10 border-[var(--color-warning)]/20 text-[var(--color-warning)]',
  info: 'bg-[var(--color-info)]/10 border-[var(--color-info)]/20 text-[var(--color-info)]',
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <ToastToast key={t.id} toast={t} onClose={() => removeToast(t.id)} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastToast({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -16, scale: 0.95 }}
      className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${styles[toast.type]} backdrop-blur-sm shadow-lg min-w-[280px] max-w-[400px]`}
    >
      {icons[toast.type]}
      <span className="flex-1 text-sm text-[var(--color-text-primary)]">{toast.message}</span>
      <button
        onClick={onClose}
        className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </motion.div>
  );
}