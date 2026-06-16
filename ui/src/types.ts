export interface ToolStep {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result: string | null;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  tools: ToolStep[];
  thinking: string;
  interrupted: boolean;
  pending: boolean;
}
