// Export Utilities

import type { ChatMessage, Memory } from '../api/types';

export function exportAsMarkdown(
  messages: ChatMessage[],
  memories: Memory[]
): string {
  let md = '# MemoryThread Chat Session\n\n';
  md += `Export Date: ${new Date().toISOString()}\n\n`;
  md += '---\n\n';

  for (const msg of messages) {
    const role = msg.role === 'user' ? '**You**' : '**MemoryThread AI**';
    md += `### ${role}\n`;
    md += `${msg.content}\n\n`;

    if (msg.role === 'assistant' && msg.memories && msg.memories.length > 0) {
      md += `*Recall: ${msg.memories.length} memories (avg truth: ${(
        msg.memories.reduce((sum, m) => sum + m.truth_score, 0) /
        msg.memories.length
      ).toFixed(2)})*\n\n`;
    }
  }

  if (memories.length > 0) {
    md += '---\n\n';
    md += '### Stored Memories\n\n';
    for (const m of memories) {
      md += `- ${m.content}\n`;
      md += `  - truth: ${m.truth_score.toFixed(2)}, conf: ${(m.confidence * 100).toFixed(0)}%, auth: ${(m.authority * 100).toFixed(0)}%\n`;
    }
  }

  return md;
}

export function exportAsJSON(
  messages: ChatMessage[],
  memories: Memory[]
): string {
  return JSON.stringify(
    {
      exportedAt: new Date().toISOString(),
      messages,
      memories,
    },
    null,
    2
  );
}

export function downloadFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}