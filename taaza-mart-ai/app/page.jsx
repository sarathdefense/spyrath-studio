"use client";
import { useState, useRef, useEffect } from "react";

const STARTERS = [
  { emoji: "🍛", title: "Chicken Dum Biryani", sub: "Tell me about your Chicken Dum Biryani" },
  { emoji: "🥗", title: "Vegetarian Options", sub: "What vegetarian options do you have?" },
  { emoji: "🌶️", title: "Wednesday Specials", sub: "What are your Wednesday Indo Chinese specials?" },
  { emoji: "📍", title: "Location & Hours", sub: "Where are you and when are you open?" },
];

function parseSuggestions(text) {
  const match = text.match(/<suggestions>([\s\S]*?)<\/suggestions>/);
  if (match) {
    return match[1].trim().split("\n").map(l => l.trim()).filter(l => l.length > 0).slice(0, 3);
  }
  const start = text.indexOf("<suggestions>");
  if (start > -1) {
    const inner = text.slice(start + 13).trim();
    return inner.split("\n").map(l => l.trim()).filter(l => l.length > 0).slice(0, 3);
  }
  return [];
}

function stripSuggestions(text) {
  const idx = text.indexOf("<suggestions>");
  if (idx > -1) return text.slice(0, idx).trim();
  return text;
}

export default function TaazaChat() {
  const [messages, setMessages] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  const resetChat = () => { setMessages([]); setSuggestions([]); setInput(""); };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, suggestions]);

  const sendMessage = async (text) => {
    const userText = text || input.trim();
    if (!userText || isLoading) return;
    setInput("");
    setSuggestions([]);

    const newMessages = [...messages, { role: "user", content: userText }];
    setMessages(newMessages);
    setIsLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: newMessages }),
      });

      if (!res.ok) throw new Error("Request failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";

      setMessages(prev => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value, { stream: true }).split("\n").filter(l => l.startsWith("data: "));
        for (const line of lines) {
          const data = line.replace("data: ", "").trim();
          if (data === "[DONE]") continue;
          try {
            const delta = JSON.parse(data).choices?.[0]?.delta?.content || "";
            fullText += delta;
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "assistant", content: fullText };
              return updated;
            });
          } catch {}
        }
      }

      const parsed = parseSuggestions(fullText);
      setSuggestions(parsed);
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: stripSuggestions(fullText) };
        return updated;
      });
    } catch (err) {
      setMessages(prev => [...prev, { role: "assistant", content: "Something went wrong. Please call us at [(813) 564-8100](tel:8135648100)" }]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const renderText = (text) => {
    const parts = text.split(/(\[.*?\]\(.*?\)|\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      const linkMatch = part.match(/\[(.*?)\]\((.*?)\)/);
      if (linkMatch) return <a key={i} href={linkMatch[2]} target="_blank" rel="noopener noreferrer" style={{ color: "#2E7D32", textDecoration: "underline" }}>{linkMatch[1]}</a>;
      const boldMatch = part.match(/\*\*(.*?)\*\*/);
      if (boldMatch) return <strong key={i}>{boldMatch[1]}</strong>;
      return part;
    });
  };

  const renderMessage = (content) => {
    return content.split("\n").map((line, i) => {
      if (line.startsWith("- ") || line.startsWith("* ")) return <li key={i} style={{ marginLeft: "16px", marginBottom: "4px" }}>{renderText(line.slice(2))}</li>;
      if (line.trim() === "") return <br key={i} />;
      return <p key={i} style={{ margin: "4px 0" }}>{renderText(line)}</p>;
    });
  };

  return (
    <div className="app-container" style={{ background: "#F1F8E9", fontFamily: "'Segoe UI', Arial, sans-serif" }}>

      {/* Header */}
      <header style={{ background: "#1B5E20", padding: "10px 16px", display: "flex", alignItems: "center", gap: "10px", boxShadow: "0 2px 8px rgba(0,0,0,0.3)" }}>
        <div style={{ display: "flex", flexDirection: "column", flexShrink: 0 }}>
          <span style={{ color: "#A5D6A7", fontSize: "20px", fontWeight: "800", letterSpacing: "-0.5px" }}>Taaza Mart</span>
          <span style={{ color: "#81C784", fontSize: "11px" }}>AI Assistant</span>
        </div>
        <div style={{ marginLeft: "auto", flexShrink: 0, display: "flex", gap: "8px", alignItems: "center" }}>
          {messages.length > 0 && (
            <button onClick={resetChat} style={{ background: "none", border: "1px solid #555", borderRadius: "20px", color: "#AAA", padding: "4px 8px", fontSize: "11px", cursor: "pointer", whiteSpace: "nowrap" }}>🏠 Home</button>
          )}
          <a href="https://order.toasttab.com/online/taazamart" target="_blank" rel="noopener noreferrer" style={{ color: "#A5D6A7", textDecoration: "none", border: "1px solid #A5D6A7", padding: "4px 8px", borderRadius: "20px", fontSize: "11px", whiteSpace: "nowrap" }}>Order →</a>
        </div>
      </header>

      {/* Messages */}
      <div className="messages-area" style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>

        {messages.length === 0 && (
          <div style={{ textAlign: "center", marginTop: "16px" }}>
            <h2 style={{ color: "#1B5E20", fontSize: "22px", fontWeight: "700", marginBottom: "4px" }}>Welcome to Taaza Mart!</h2>
            <p style={{ color: "#2E7D32", fontSize: "13px", fontWeight: "500", marginBottom: "4px" }}>Authentic Indian Food in Tampa</p>
            <p style={{ color: "#888", fontSize: "13px", marginBottom: "16px" }}>Ask me anything about our menu, hours, or specials!</p>
            <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginBottom: "16px", flexWrap: "wrap" }}>
              <a href="tel:8135648100" style={{ display: "flex", alignItems: "center", gap: "4px", background: "#1B5E20", color: "#A5D6A7", padding: "8px 14px", borderRadius: "20px", fontSize: "12px", textDecoration: "none", fontWeight: "500" }}>📞 Call Us</a>
              <a href="https://google.com/maps/place?q=Taaza+Mart,+6260+Commerce+Palms+Dr,+Tampa,+FL+33647" target="_blank" rel="noopener noreferrer" style={{ display: "flex", alignItems: "center", gap: "4px", background: "#1B5E20", color: "#A5D6A7", padding: "8px 14px", borderRadius: "20px", fontSize: "12px", textDecoration: "none", fontWeight: "500" }}>🗺️ Directions</a>
              <a href="https://order.toasttab.com/online/taazamart" target="_blank" rel="noopener noreferrer" style={{ display: "flex", alignItems: "center", gap: "4px", background: "#2E7D32", color: "white", padding: "8px 14px", borderRadius: "20px", fontSize: "12px", textDecoration: "none", fontWeight: "500" }}>📋 Full Menu</a>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", maxWidth: "480px", margin: "0 auto", width: "100%" }}>
              {STARTERS.map(s => (
                <button key={s.title} onClick={() => sendMessage(s.sub)} style={{ background: "white", border: "1px solid #A5D6A7", borderRadius: "12px", padding: "12px 14px", cursor: "pointer", textAlign: "left", lineHeight: "1.4", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
                  <div style={{ fontSize: "20px", marginBottom: "4px" }}>{s.emoji}</div>
                  <div style={{ fontSize: "13px", fontWeight: "600", color: "#1B5E20", marginBottom: "2px" }}>{s.title}</div>
                  <div style={{ fontSize: "11px", color: "#888" }}>{s.sub}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
            {msg.role === "assistant" && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginRight: "8px", flexShrink: 0 }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "50%", background: "#2E7D32", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px" }}>🍛</div>
                <span style={{ fontSize: "9px", color: "#2E7D32", fontWeight: "600", marginTop: "2px" }}>Taaza</span>
              </div>
            )}
            <div style={{
              maxWidth: "75%", padding: "12px 16px",
              borderRadius: msg.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
              background: msg.role === "user" ? "#1B5E20" : "white",
              color: msg.role === "user" ? "#A5D6A7" : "#1A1A1A",
              fontSize: "14px", lineHeight: "1.6",
              boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
              border: msg.role === "assistant" ? "1px solid #C8E6C9" : "none",
            }}>
              {renderMessage(msg.content)}
            </div>
          </div>
        ))}

        {suggestions.length > 0 && !isLoading && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", paddingLeft: "40px" }}>
            {suggestions.map(s => (
              <button key={s} onClick={() => sendMessage(s)}
                style={{ background: "white", border: "1px solid #2E7D32", borderRadius: "20px", padding: "6px 14px", fontSize: "13px", color: "#2E7D32", cursor: "pointer" }}
                onMouseEnter={e => { e.target.style.background = "#2E7D32"; e.target.style.color = "white"; }}
                onMouseLeave={e => { e.target.style.background = "white"; e.target.style.color = "#2E7D32"; }}>
                {s}
              </button>
            ))}
          </div>
        )}

        {isLoading && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
              <div style={{ width: "32px", height: "32px", borderRadius: "50%", background: "#2E7D32", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px" }}>🍛</div>
              <span style={{ fontSize: "9px", color: "#2E7D32", fontWeight: "600", marginTop: "2px" }}>Taaza</span>
            </div>
            <div style={{ background: "white", border: "1px solid #C8E6C9", borderRadius: "18px 18px 18px 4px", padding: "12px 16px", display: "flex", gap: "4px" }}>
              {[0,1,2].map(i => <div key={i} style={{ width: "8px", height: "8px", background: "#2E7D32", borderRadius: "50%", animation: "bounce 1.2s infinite", animationDelay: `${i * 0.2}s` }} />)}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="input-area" style={{ padding: "12px 16px", background: "white", borderTop: "1px solid #C8E6C9", display: "flex", gap: "10px" }}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), sendMessage())}
          placeholder="Ask about menu, hours, specials..."
          rows={1}
          style={{ flex: 1, padding: "10px 14px", border: "1px solid #A5D6A7", borderRadius: "24px", fontSize: "16px", outline: "none", background: "#F1F8E9", color: "#1A1A1A", resize: "none", fontFamily: "inherit", lineHeight: "1.4", overflow: "hidden", maxHeight: "80px", whiteSpace: "nowrap" }}
        />
        <button onClick={() => sendMessage()} disabled={!input.trim() || isLoading}
          style={{ background: input.trim() && !isLoading ? "#2E7D32" : "#DDD", border: "none", borderRadius: "50%", width: "44px", height: "44px", cursor: input.trim() && !isLoading ? "pointer" : "not-allowed", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="white"><path d="M2 8L14 2l-4 6 4 6L2 8z"/></svg>
        </button>
      </div>

      <div style={{ padding: "6px 20px", background: "white", borderTop: "1px solid #C8E6C9", textAlign: "center" }}>
        <span style={{ fontSize: "11px", color: "#AAA" }}>Powered by </span>
        <a href="mailto:sarath.defense@gmail.com" style={{ fontSize: "11px", color: "#2E7D32", textDecoration: "none" }}>Sarath Vaddi</a>
      </div>

      <style>{`
        @keyframes bounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }
        * { box-sizing: border-box; }
        body { margin: 0; }
        li { list-style-type: disc; }
        html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; }
        .app-container { display: flex; flex-direction: column; height: 100vh; height: 100dvh; overflow: hidden; position: fixed; top: 0; left: 0; right: 0; bottom: 0; }
        .messages-area { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; }
        .input-area { flex-shrink: 0; }
      `}</style>
    </div>
  );
}
