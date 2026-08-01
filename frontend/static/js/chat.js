document.addEventListener("DOMContentLoaded", () => {
  const chatWindow = document.getElementById("chatWindow");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const suggestedWrap = document.getElementById("suggestedWrap");
  const newChatBtn = document.getElementById("newChatBtn");
  const initialTimestamp = document.getElementById("initialTimestamp");

  // Point this at your FastAPI service (see app.py: uvicorn app:app --port 8000)
  const AI_API_BASE = "http://127.0.0.1:8000";

  function formatTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  if (initialTimestamp) initialTimestamp.textContent = formatTime();

  function appendUserMessage(text) {
    const message = document.createElement("div");
    message.className = "message user";

    const avatar = document.createElement("div");
    avatar.className = "avatar user-avatar-msg";
    avatar.textContent = "🧑";

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const p = document.createElement("p");
    p.textContent = text;
    bubble.appendChild(p);

    const time = document.createElement("span");
    time.className = "timestamp";
    time.textContent = formatTime();
    bubble.appendChild(time);

    message.appendChild(avatar);
    message.appendChild(bubble);
    chatWindow.appendChild(message);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  /**
   * Renders a bot answer WITH its explainability payload:
   * confidence badge + expandable "View sources" panel showing every
   * retrieved passage and its similarity score.
   */
  function appendBotMessage(data) {
    const message = document.createElement("div");
    message.className = "message bot";

    const avatar = document.createElement("div");
    avatar.className = "avatar bot-avatar";
    avatar.textContent = "🌿";

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const answerText = data.translated_answer || data.answer;
    const answerP = document.createElement("p");
    answerP.textContent = answerText;
    bubble.appendChild(answerP);

    // ---------- Confidence badge ----------
    if (data.confidence_label && data.confidence_label !== "none") {
      const badge = document.createElement("span");
      badge.className = `confidence-badge confidence-${data.confidence_label}`;
      const pct = Math.round((data.confidence_score || 0) * 100);
      badge.textContent = `${capitalize(data.confidence_label)} confidence · ${pct}%`;
      bubble.appendChild(badge);
    }

    // ---------- Sources / citations (expandable) ----------
    if (data.sources && data.sources.length > 0) {
      const sourcesToggle = document.createElement("button");
      sourcesToggle.className = "sources-toggle";
      sourcesToggle.type = "button";
      sourcesToggle.textContent = `📚 View ${data.sources.length} source${data.sources.length > 1 ? "s" : ""}`;

      const sourcesPanel = document.createElement("div");
      sourcesPanel.className = "sources-panel hidden";

      (data.retrieved_passages || []).forEach((passage) => {
        const card = document.createElement("div");
        card.className = "source-card";

        const scorePct = Math.round((passage.similarity_score || 0) * 100);

        card.innerHTML = `
          <div class="source-card-header">
            <strong>${escapeHtml(passage.common_name)}</strong>
            ${passage.botanical_name ? `<em>(${escapeHtml(passage.botanical_name)})</em>` : ""}
            <span class="source-score">${scorePct}% match</span>
          </div>
          ${passage.diseases_treated ? `<p><strong>Treats:</strong> ${escapeHtml(passage.diseases_treated)}</p>` : ""}
          ${passage.medicinal_properties ? `<p><strong>Properties:</strong> ${escapeHtml(passage.medicinal_properties)}</p>` : ""}
          ${passage.traditional_uses ? `<p><strong>Traditional use:</strong> ${escapeHtml(passage.traditional_uses)}</p>` : ""}
          ${passage.preparation_method ? `<p><strong>Preparation:</strong> ${escapeHtml(passage.preparation_method)}</p>` : ""}
          ${passage.how_to_take ? `<p><strong>How to take/apply:</strong> ${escapeHtml(passage.how_to_take)}</p>` : ""}
          ${passage.general_disclaimer ? `<p class="source-disclaimer"><em>${escapeHtml(passage.general_disclaimer)}</em></p>` : ""}
        `;
        sourcesPanel.appendChild(card);
      });

      sourcesToggle.addEventListener("click", () => {
        sourcesPanel.classList.toggle("hidden");
        sourcesToggle.textContent = sourcesPanel.classList.contains("hidden")
          ? `📚 View ${data.sources.length} source${data.sources.length > 1 ? "s" : ""}`
          : "📚 Hide sources";
      });

      bubble.appendChild(sourcesToggle);
      bubble.appendChild(sourcesPanel);
    }

    const time = document.createElement("span");
    time.className = "timestamp";
    time.textContent = formatTime();
    bubble.appendChild(time);

    message.appendChild(avatar);
    message.appendChild(bubble);
    chatWindow.appendChild(message);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  function showTypingIndicator() {
    const message = document.createElement("div");
    message.className = "message bot";
    message.id = "typingIndicator";

    const avatar = document.createElement("div");
    avatar.className = "avatar bot-avatar";
    avatar.textContent = "🌿";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;

    message.appendChild(avatar);
    message.appendChild(bubble);
    chatWindow.appendChild(message);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  function removeTypingIndicator() {
    const el = document.getElementById("typingIndicator");
    if (el) el.remove();
  }

  function appendErrorMessage(text) {
    const message = document.createElement("div");
    message.className = "message bot";

    const avatar = document.createElement("div");
    avatar.className = "avatar bot-avatar";
    avatar.textContent = "🌿";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = `<p>${escapeHtml(text)}</p>`;

    message.appendChild(avatar);
    message.appendChild(bubble);
    chatWindow.appendChild(message);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  async function sendMessage(text) {
    if (!text.trim()) return;

    if (suggestedWrap) suggestedWrap.style.display = "none";

    appendUserMessage(text);
    chatInput.value = "";
    sendBtn.disabled = true;
    showTypingIndicator();

    try {
      const response = await fetch(`${AI_API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody?.detail?.detail || "Request failed");
      }

      const data = await response.json();
      removeTypingIndicator();
      appendBotMessage(data);
    } catch (err) {
      removeTypingIndicator();
      appendErrorMessage(
        "Something went wrong while reaching the assistant. Make sure the AI backend is running on port 8000."
      );
      console.error(err);
    } finally {
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(chatInput.value);
  });

  document.querySelectorAll(".suggested-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const question = btn.textContent.replace(/^✨\s*/, "").trim();
      sendMessage(question);
    });
  });

  if (newChatBtn) {
    newChatBtn.addEventListener("click", () => {
      chatWindow.innerHTML = "";
      const el = document.createElement("div");
      el.className = "message bot";
      el.innerHTML = `
        <div class="avatar bot-avatar">🌿</div>
        <div class="bubble">
          <p>Hello! I'm your NativeMed AI Herbal Assistant 🌿</p>
          <p>What would you like to know today?</p>
          <span class="timestamp">${formatTime()}</span>
        </div>`;
      chatWindow.appendChild(el);
      if (suggestedWrap) suggestedWrap.style.display = "block";
    });
  }
});