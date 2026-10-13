import { useEffect, useRef } from "react";

import type { MessageNavigationTarget } from "../api/messageNavigation";
import { ConversationMessageContext } from "./ConversationMessageContext";

type Props = { target: MessageNavigationTarget; loaded: boolean | null; onClose: () => void };

export function LocatedMessage({ target, loaded, onClose }: Props) {
  const region = useRef<HTMLElement>(null);
  const { conversation, message } = target;
  useEffect(() => { region.current?.focus(); }, [conversation.id, message.id]);

  return <section aria-label="Located saved message in chat" tabIndex={-1} ref={region}>
    <h3>Located message {message.id} in conversation {conversation.id}</h3>
    <p style={{ overflowWrap: "anywhere" }}>Conversation title: {conversation.title}</p>
    {loaded === false && <p>This saved message is outside the loaded chat page. Its context is shown below.</p>}
    {loaded === true && <p>This saved message is also in the loaded chat history.</p>}
    <button type="button" onClick={onClose}>Close located message</button>
    <ConversationMessageContext conversationId={conversation.id} agentId={conversation.agent_id}
      message={message} disabled={false} onClose={onClose} />
  </section>;
}
