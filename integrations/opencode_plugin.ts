import { z } from "zod";
import * as fs from "fs";
import * as path from "path";

const MT_BASE_URL = process.env.MT_BASE_URL || "http://localhost:8000";
const REQUEST_TIMEOUT = 5000;

function resolveNamespace(): string {
  const defaultNamespace = "default";

  const checkDir = (dir: string): string | null => {
    const configPath = path.join(dir, ".mt", "config.json");
    try {
      if (fs.existsSync(configPath)) {
        const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
        if (config.namespace) {
          return config.namespace;
        }
      }
    } catch {
      // Ignore errors and continue searching
    }
    return null;
  };

  let currentDir = process.cwd();
  const root = path.parse(currentDir).root;

  while (true) {
    const found = checkDir(currentDir);
    if (found) {
      return found;
    }

    if (currentDir === root) {
      break;
    }

    const parent = path.dirname(currentDir);
    if (parent === currentDir) {
      break;
    }
    currentDir = parent;
  }

  return defaultNamespace;
}

async function mtFetch(
  endpoint: string,
  options: RequestInit = {}
): Promise<{ ok: boolean; data?: unknown; error?: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(`${MT_BASE_URL}${endpoint}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      return {
        ok: false,
        error: `HTTP ${response.status}: ${response.statusText}`,
      };
    }

    const data = await response.json();
    return { ok: true, data };
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error) {
      if (err.name === "AbortError") {
        return { ok: false, error: "Request timeout" };
      }
      return { ok: false, error: err.message };
    }
    return { ok: false, error: "Unknown error" };
  }
}

// Automatic context retrieval - called before each LLM request
export async function getAutoContext(query: string, topK: number = 5): Promise<string> {
  const namespace = resolveNamespace();
  
  const result = await mtFetch("/memory/recall", {
    method: "POST",
    body: JSON.stringify({
      query,
      top_k: topK,
      namespace,
    }),
  });

  if (!result.ok) {
    return "";
  }

  const data = result.data as {
    memories?: Array<{
      content: string;
      truth_score: number;
      memory_type?: string;
    }>;
  };

  const memories = data?.memories ?? [];
  if (memories.length === 0) {
    return "";
  }

  const lines = ["## Relevant Context from Memory Thread:\n"];
  memories.forEach((mem, i) => {
    lines.push(`\n${i + 1}. [${mem.memory_type ?? "memory"}] (score: ${mem.truth_score.toFixed(2)})`);
    lines.push(`   ${mem.content.slice(0, 200)}${mem.content.length > 200 ? "..." : ""}`);
  });

  return lines.join("\n");
}

// Auto-remember - stores important info automatically
export async function autoRemember(content: string, autoType: string = "fact"): Promise<boolean> {
  const namespace = resolveNamespace();
  
  // Determine memory type from content
  let memoryType = autoType;
  const lower = content.toLowerCase();
  
  if (lower.includes("decided") || lower.includes("going with") || lower.includes("chose") || lower.includes("switched to")) {
    memoryType = "decision";
  } else if (lower.includes("failed") || lower.includes("didn't work") || lower.includes("issue") || lower.includes("problem")) {
    memoryType = "failure";
  } else if (lower.includes("prefer") || lower.includes("like") || lower.includes("hate") || lower.includes("love")) {
    memoryType = "preference";
  } else if (lower.includes("i am") || lower.includes("my name") || lower.includes("i live")) {
    memoryType = "identity";
  }

  const confidence = memoryType === "decision" ? 0.9 : 0.8;

  const result = await mtFetch("/memory/remember", {
    method: "POST",
    body: JSON.stringify({
      content,
      memory_type: memoryType,
      confidence,
      namespace,
      source: "opencode_auto",
    }),
  });

  return result.ok;
}

// Check for contradictions before storing
export async function checkContradiction(content: string): Promise<{ hasContradiction: boolean; existing?: string }> {
  const namespace = resolveNamespace();
  
  const result = await mtFetch("/memory/check_contradiction", {
    method: "POST",
    body: JSON.stringify({
      content,
      namespace,
    }),
  });

  if (!result.ok) {
    return { hasContradiction: false };
  }

  const data = result.data as {
    has_contradiction: boolean;
    conflicting_memory?: string;
  };

  return {
    hasContradiction: data.has_contradiction,
    existing: data.conflicting_memory,
  };
}

export const mt_recall = {
  description:
    "Search Memory Thread for relevant context about this project before answering any question. Always call this first.",
  parameters: z.object({
    query: z.string().describe("Search query"),
    top_k: z.number().min(1).max(20).default(5).describe("Number of results to return"),
  }),
  execute: async (args: { query: string; top_k?: number }) => {
    const namespace = resolveNamespace();
    const topK = args.top_k ?? 5;

    const result = await mtFetch("/memory/recall", {
      method: "POST",
      body: JSON.stringify({
        query: args.query,
        top_k: topK,
        namespace,
      }),
    });

    if (!result.ok) {
      return `MT server unavailable — continuing without memory context (${result.error})`;
    }

    const data = result.data as {
      memories?: Array<{
        content: string;
        truth_score: number;
        confidence: number;
        authority: number;
        memory_type?: string;
      }>;
      total_found?: number;
    };

    const memories = data?.memories ?? [];
    if (memories.length === 0) {
      return `No memories found for query: "${args.query}"`;
    }

    const lines = [
      `=== Memory Thread Recall: ${args.query} ===`,
      `Namespace: ${namespace} | Found: ${data?.total_found ?? memories.length} results`,
      "",
    ];

    memories.forEach((mem, i) => {
      lines.push(
        `${i + 1}. [${mem.memory_type ?? "memory"}] Score: ${mem.truth_score.toFixed(3)} | Conf: ${mem.confidence.toFixed(2)} | Auth: ${mem.authority.toFixed(2)}`
      );
      lines.push(`   ${mem.content.slice(0, 200)}${mem.content.length > 200 ? "..." : ""}`);
      lines.push("");
    });

    return lines.join("\n");
  },
};

export const mt_remember = {
  description:
    "Store an important decision, failure, preference, or fact into Memory Thread. Never store raw conversation text.",
  parameters: z.object({
    content: z.string().min(1).describe("Content to store"),
    type: z
      .enum(["decision", "failure", "preference", "fact", "event"])
      .default("fact")
      .describe("Type of memory"),
    confidence: z.number().min(0).max(1).default(0.8).describe("Confidence score 0-1"),
  }),
  execute: async (args: { content: string; type?: string; confidence?: number }) => {
    const namespace = resolveNamespace();
    const memoryType = args.type ?? "fact";
    const confidence = args.confidence ?? 0.8;

    const result = await mtFetch("/memory/remember", {
      method: "POST",
      body: JSON.stringify({
        content: args.content,
        memory_type: memoryType,
        confidence,
        namespace,
        source: "opencode_plugin",
      }),
    });

    if (!result.ok) {
      return `Failed to remember: ${result.error}`;
    }

    const data = result.data as { entity_id?: string; id?: string };
    const entityId = data?.entity_id ?? data?.id ?? "unknown";

    return `✓ Stored [${memoryType}] in namespace "${namespace}" (entity_id: ${entityId})`;
  },
};

export const mt_check_contradiction = {
  description:
    "Check if new information contradicts existing memories before storing.",
  parameters: z.object({
    content: z.string().min(1).describe("Content to check for contradictions"),
  }),
  execute: async (args: { content: string }) => {
    const namespace = resolveNamespace();

    const result = await mtFetch("/memory/check_contradiction", {
      method: "POST",
      body: JSON.stringify({
        content: args.content,
        namespace,
      }),
    });

    if (!result.ok) {
      return `Contradiction check failed: ${result.error}`;
    }

    const data = result.data as {
      has_contradiction: boolean;
      conflicting_memory?: string;
      explanation?: string;
    };

    if (!data.has_contradiction) {
      return "✓ No contradictions detected";
    }

    return `⚠ Contradiction detected!\n  Existing: ${data.conflicting_memory?.slice(0, 100) ?? "unknown"}\n  Explanation: ${data.explanation ?? "None"}`;
  },
};

export const mt_status = {
  description: "Get Memory Thread health and stats for current project.",
  parameters: z.object({}),
  execute: async () => {
    const namespace = resolveNamespace();

    const [healthResult, statsResult] = await Promise.all([
      mtFetch("/health"),
      mtFetch(`/stats?namespace=${encodeURIComponent(namespace)}`),
    ]);

    if (!healthResult.ok) {
      return `MT server unavailable — continuing without memory context (${healthResult.error})`;
    }

    const health = healthResult.data as {
      status?: string;
      postgres_connected?: boolean;
    };
    const stats = statsResult.ok
      ? (statsResult.data as { total_memories?: number; avg_truth_score?: number })
      : null;

    const lines = [
      "=== Memory Thread Status ===",
      `Namespace: ${namespace}`,
      `Status: ${health?.status ?? "unknown"}`,
      `PostgreSQL: ${health?.postgres_connected ? "✓ connected" : "✗ disconnected"}`,
      "",
      "Stats:",
      `  Total Memories: ${stats?.total_memories ?? "N/A"}`,
      `  Avg Truth Score: ${stats?.avg_truth_score?.toFixed(3) ?? "N/A"}`,
    ];

    return lines.join("\n");
  },
};

export const mt_forget = {
  description: "Remove a specific memory from Memory Thread.",
  parameters: z.object({
    entity_id: z.string().describe("Entity ID to forget"),
  }),
  execute: async (args: { entity_id: string }) => {
    const namespace = resolveNamespace();

    const result = await mtFetch(`/memory/${args.entity_id}`, {
      method: "DELETE",
    });

    if (!result.ok) {
      return `Failed to forget: ${result.error}`;
    }

    return `✓ Forgotten entity ${args.entity_id} from namespace "${namespace}"`;
  },
};
