import React, { useEffect, useMemo, useRef, useState } from "react";

export default function AiChatPanel({
  aiUserText,
  setAiUserText,
  aiLoading,
  aiError,
  onSend,
  roomCatalog,
  selectedIds,
  setSelectedIds,
}) {
  // local chat transcript (UI only)
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Tell me what you want and what area to design for (whole unit, floors, or specific rooms).",
    },
  ]);

  const scrollRef = useRef(null);

  useEffect(() => {
    // Auto-scroll to bottom when messages change
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const catalogItems = useMemo(() => {
    // Expecting something like { items: [...] } or just [...].
    if (!roomCatalog) return [];
    if (Array.isArray(roomCatalog)) return roomCatalog;
    if (Array.isArray(roomCatalog.items)) return roomCatalog.items;
    return [];
  }, [roomCatalog]);

  const hasCatalog = catalogItems.length > 0;

  const toggleSelected = (id) => {
    // Whole unit is mutually exclusive with room selection
    if (id === "whole_unit") {
      setSelectedIds(["whole_unit"]);
      return;
    }

    const next = new Set(selectedIds || []);
    next.delete("whole_unit");

    if (next.has(id)) next.delete(id);
    else next.add(id);

    const arr = Array.from(next);
    setSelectedIds(arr.length ? arr : ["whole_unit"]);
  };

  // make sure the backend sees the full chat transcript for an ai recommendation
  const send = async () => {
    const text = (aiUserText || "").trim();
    if (!text || aiLoading) return;

    const userMsg = { role: "user", content: text };
    const updatedMessages = [...messages, userMsg];

    setMessages(updatedMessages);
    setAiUserText("");

    try {
      const payload = await onSend(text, updatedMessages);

      const questions = payload?.intent?.questions || [];
      if (questions.length) {
        setMessages((m) => {
          const existingAssistantTexts = new Set(
            m.filter((msg) => msg.role === "assistant").map((msg) => msg.content)
          );

          const newQuestionMessages = questions
            .filter((q) => !existingAssistantTexts.has(q))
            .map((q) => ({ role: "assistant", content: q }));

          return [...m, ...newQuestionMessages];
        });
      } else {
        setMessages((m) => [...m, { role: "assistant", content: "Done. I updated results." }]);
      }
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `Error: ${e.message || String(e)}` },
      ]);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "60vh" }}>
      <div style={{ fontWeight: 500, marginBottom: 8 }}>AI Assistant (based on conduit upload)</div>

      {/* Selection */}
      {/* <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 10, marginBottom: 10 }}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Scope Location</div>

        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <input
            type="checkbox"
            checked={(selectedIds || []).includes("whole_unit")}
            onChange={() => toggleSelected("whole_unit")}
          />
          Entire Unit
        </label>

        {hasCatalog ? (
          <div style={{ maxHeight: 140, overflowY: "auto", paddingRight: 6 }}>
            {catalogItems.map((it) => {
              // Support either {id,label} or conduit-ish fields
              const id = it.id || `${it.zone_name || ""}::${it.room_name || ""}`;
              const label =
                it.label ||
                (it.zone_name && it.room_name ? `${it.zone_name} — ${it.room_name}` : id);

              const checked = (selectedIds || []).includes(id);

              return (
                <label
                  key={id}
                  style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}
                >
                  <input type="checkbox" checked={checked} onChange={() => toggleSelected(id)} />
                  <span style={{ fontSize: 13 }}>{label}</span>
                </label>
              );
            })}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: "#666" }}>
            Room list not loaded yet. You can still run “whole unit”.
          </div>
        )}
      </div> */}

      {/* Transcript */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          border: "1px solid #ddd",
          borderRadius: 10,
          padding: 10,
          background: "white",
        }}
      >
        {messages.map((m, idx) => (
          <div
            key={idx}
            style={{
              //marginBottom: 10,
              display: "flex",
              justifyContent: m.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "40%",
                whiteSpace: "pre-wrap",
                padding: "8px 10px",
                borderRadius: 12,
                border: "1px solid #eee",
                background: m.role === "user" ? "#f7f7f7" : "#fff",
                fontSize: 13,
              }}
            >
              {m.content}
            </div>
          </div>
        ))}
        <div ref={scrollRef} />
      </div>

      {/* Error */}
      {aiError ? (
        <div style={{ color: "crimson", marginTop: 8, fontSize: 13 }}>{aiError}</div>
      ) : null}

      {/* Input */}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <textarea
          value={aiUserText}
          onChange={(e) => setAiUserText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Describe the system you want… (Enter to send)"
          rows={2}
          style={{
            flex: 1,
            resize: "none",
            borderRadius: 10,
            border: "1px solid #ddd",
            padding: 10,
            fontSize: 13,
          }}
        />
        <button
          type="button"
          onClick={send}
          disabled={aiLoading || !aiUserText.trim()}
          style={{
            borderRadius: 10,
            border: "1px solid #ddd",
            padding: "0 14px",
            fontWeight: 600,
            cursor: aiLoading ? "default" : "pointer",
          }}
        >
          {aiLoading ? "Thinking…" : "Send"}
        </button>
      </div>
    </div>
  );
}