// Resultado + chat (página /resultado/{token}). Usa as APIs JSON existentes.
function resultado() {
  const CFG = window.__CFG || {};
  const api = (p) => `${CFG.basePath}/api${p}`;
  return {
    result: null,
    testKind: 'choice',
    chat: [],
    input: '',
    streaming: false,
    streamBuffer: '',

    async init() {
      await this.load();
    },

    async load() {
      try {
        const r = await fetch(api(`/lead/${CFG.token}`), { credentials: 'same-origin' });
        if (!r.ok) return;
        const data = await r.json();
        this.result = data.result;
        this.testKind = (data.lead && data.lead.test_kind) || 'choice';
        this.chat = data.chat_history || [];
        if (this.chat.length === 0) await this.initChat();
      } catch (_) { /* ignore */ }
    },

    get isCopsoq() { return !!(this.result && this.result.type === 'copsoq'); },

    archetypesOrdered() {
      const perc = (this.result && this.result.perc) ? this.result.perc : {};
      const meta = { tubarao: { label: 'Tubarão' }, lobo: { label: 'Lobo' }, aguia: { label: 'Águia' }, gato: { label: 'Gato' } };
      return Object.keys(meta)
        .map(k => ({ key: k, ...meta[k], value: perc[k] || 0 }))
        .sort((a, b) => b.value - a.value);
    },

    copsoqGrouped() {
      if (!this.isCopsoq) return [];
      const subs = this.result.subscales || [];
      return (this.result.domains || []).map(d => ({
        ...d,
        subs: subs.filter(s => s.dominio === d.key && s.score !== null && s.score !== undefined),
      })).filter(d => d.subs.length > 0);
    },

    nivelColor(nivel) { return { verde: '#16a34a', amarelo: '#f59e0b', vermelho: '#dc2626' }[nivel] || '#94a3b8'; },
    nivelBg(nivel) { return { verde: '#dcfce7', amarelo: '#fef3c7', vermelho: '#fee2e2' }[nivel] || '#f1f5f9'; },
    nivelLabel(nivel) { return { verde: 'Favorável', amarelo: 'Atenção', vermelho: 'Risco alto' }[nivel] || '—'; },

    async initChat() {
      try {
        const r = await fetch(api(`/chat/${CFG.token}/init`), { method: 'POST', credentials: 'same-origin' });
        if (!r.ok) return;
        const data = await r.json();
        if (data.message) { this.chat.push({ role: 'assistant', content: data.message }); this.scrollChat(); }
      } catch (_) { /* ignore */ }
    },

    async sendMessage() {
      const content = this.input.trim();
      if (!content || this.streaming) return;
      this.input = '';
      this.chat.push({ role: 'user', content });
      this.scrollChat();
      this.streaming = true;
      this.streamBuffer = '';
      try {
        const r = await fetch(api(`/chat/${CFG.token}`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ content }),
        });
        if (!r.ok || !r.body) throw new Error('Falha ao conectar ao analista');
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let eventEnd;
          while ((eventEnd = buffer.indexOf('\n\n')) !== -1) {
            const event = buffer.slice(0, eventEnd);
            buffer = buffer.slice(eventEnd + 2);
            this.handleSseEvent(event);
          }
        }
      } catch (e) {
        this.streamBuffer += `\n[Erro: ${e.message}]`;
      } finally {
        if (this.streamBuffer) this.chat.push({ role: 'assistant', content: this.streamBuffer });
        this.streamBuffer = '';
        this.streaming = false;
        this.scrollChat();
      }
    },

    handleSseEvent(raw) {
      const lines = raw.split('\n');
      let eventType = 'message';
      const dataLines = [];
      for (const line of lines) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
      }
      if (eventType === 'done') return;
      if (eventType === 'error') { this.streamBuffer += `\n[${dataLines.join('\n')}]`; return; }
      this.streamBuffer += dataLines.join('\n');
      this.scrollChat();
    },

    scrollChat() {
      this.$nextTick(() => { const box = this.$refs.chatBox; if (box) box.scrollTop = box.scrollHeight; });
    },

    renderMd(text) {
      if (!text) return '';
      const escape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      let out = escape(text);
      out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');
      out = out.replace(/\n/g, '<br>');
      return out;
    },
  };
}
