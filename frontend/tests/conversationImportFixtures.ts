import { exportData } from "./conversationExportFixtures";

export function importData() {
  const value = exportData();
  value.messages[0].content = '中文 🐍\r\n```\n<script>literal</script>\n```\nTail:  \n';
  return value;
}

export function importFile(text = JSON.stringify(importData()), name = "backup.json"): File {
  const file = new File([text], name, { type: "application/json" });
  Object.defineProperty(file, "arrayBuffer", { value: async () => new TextEncoder().encode(text).buffer });
  return file;
}

export function importResult() {
  const source = importData();
  return { schema_version: 1, conversation: { ...source.conversation, id: 92 }, message_count: source.message_count };
}

export function importResponse(data: unknown = importResult(), status = 201): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}
