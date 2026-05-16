// Error Boundary Component

import { Component, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Button } from './ui/Button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error boundary caught:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[var(--color-error)]/10 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-[var(--color-error)]" />
            </div>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
              Something went wrong
            </h2>
            <p className="text-sm text-[var(--color-text-tertiary)] mb-4">
              {this.state.error?.message || 'An unexpected error occurred'}
            </p>
            <div className="flex gap-2 justify-center">
              <Button variant="secondary" size="sm" onClick={this.handleReset}>
                <RefreshCw className="w-3 h-3 mr-1" />
                Try Again
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => window.location.reload()}
              >
                <Home className="w-3 h-3 mr-1" />
                Reload
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}