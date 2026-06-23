"use client";
import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { ChatMessage } from "../types/api";

interface Props {
  messages: ChatMessage[];
  onSend: (q: string) => void;
  loading: boolean;
}

export default function ChatPanel({ messages, onSend, loading }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    onSend(q);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <Bot size={32} />
            <p>Ask anything about your repository</p>
            <ul>
              <li>"What does this codebase do?"</li>
              <li>"Which file handles authentication?"</li>
              <li>"Explain the database schema"</li>
            </ul>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`chat-bubble ${m.role}`}>
            <div className="bubble-avatar">
              {m.role === "user" ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className="bubble-content">
              <pre>{m.content}</pre>
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-bubble assistant loading-bubble">
            <div className="bubble-avatar"><Bot size={16} /></div>
            <div className="bubble-content">
              <Loader2 size={16} className="spin" />
              <span>Thinking…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={2}
          placeholder="Ask about the codebase…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={submit}
          disabled={loading || !input.trim()}
          aria-label="Send"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
