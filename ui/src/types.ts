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

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export type WsEvent =
  | { type: "token";         conv_id: string; content: string }
  | { type: "thinking_token"; conv_id: string; content: string }
  | { type: "tool_call";     conv_id: string; id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_result";   conv_id: string; id: string; content: string }
  | { type: "title";         conv_id: string; title: string }
  | { type: "clear_content"; conv_id: string }
  | { type: "interrupted";   conv_id: string }
  | { type: "saved";         conv_id: string; message_id: string; interrupted: boolean }
  | { type: "end";           conv_id: string };
