function app() {
  return {
    view: 'form',
    loading: false,
    error: '',

    lead: { nome: '', sobrenome: '', whatsapp: '', email: '', profissao: '', origem: '' },
    token: null,

    questions: [],
    currentIdx: 0,
    answers: {},

    result: null,

    chat: [],
    input: '',
    streaming: false,
    streamBuffer: '',

    get currentQid() {
      const q = this.questions[this.currentIdx];
      return q ? q.id : null;
    },
    get currentOptions() {
      const q = this.questions[this.currentIdx];
      return q ? q.options : [];
    },
    get currentPrompt() {
      const q = this.questions[this.currentIdx];
      return q ? q.prompt : '';
    },

    async init() {
      const m = window.location.pathname.match(/\/r\/([0-9a-f]{32})\/?$/);
      if (m) {
        this.token = m[1];
        localStorage.setItem('tpc_token', this.token);
        await this.loadSaved();
      } else {
        const saved = localStorage.getItem('tpc_token');
        if (saved) {
          this.token = saved;
          await this.loadSaved(true);
        }
      }
    },

    async loadSaved(silent = false) {
      try {
        const r = await fetch(`api/lead/${this.token}`);
        if (!r.ok) {
          if (!silent) this.view = 'form';
          return;
        }
        const data = await r.json();
        this.lead = { ...this.lead, ...data.lead };
        if (data.result) {
          this.answers = data.answers || {};
          this.result = data.result;
          this.chat = data.chat_history || [];
          this.view = 'result';
          if (this.chat.length === 0) {
            await this.initChat();
          }
        } else if (Object.keys(data.answers || {}).length > 0) {
          await this.loadQuestions();
          this.answers = data.answers;
          this.view = 'wizard';
          const firstUnanswered = this.questions.findIndex(q => !this.answers[q.id]);
          this.currentIdx = firstUnanswered === -1 ? this.questions.length - 1 : firstUnanswered;
        } else {
          await this.loadQuestions();
          this.view = 'wizard';
        }
      } catch (e) {
        console.error(e);
        if (!silent) this.view = 'form';
      }
    },

    async loadQuestions() {
      if (this.questions.length > 0) return;
      const r = await fetch('api/questions');
      const data = await r.json();
      this.questions = data.questions;
    },

    async submitLead() {
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch('api/lead', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.lead),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao enviar dados');
        }
        const data = await r.json();
        this.token = data.token;
        localStorage.setItem('tpc_token', this.token);
        await this.loadQuestions();
        this.view = 'wizard';
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
      } finally {
        this.loading = false;
      }
    },

    async chooseOption(value) {
      this.answers[this.currentQid] = value;
      this.error = '';
      try {
        await fetch(`api/lead/${this.token}/answers`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers: { [this.currentQid]: value } }),
        });
      } catch (e) { /* best-effort autosave */ }
    },

    nextQuestion() {
      if (!this.answers[this.currentQid]) {
        this.error = 'Selecione uma opção para avançar';
        return;
      }
      if (this.currentIdx < this.questions.length - 1) {
        this.currentIdx++;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },

    prevQuestion() {
      if (this.currentIdx > 0) {
        this.currentIdx--;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },

    async submitTest() {
      if (!this.answers[this.currentQid]) {
        this.error = 'Selecione uma opção antes de enviar';
        return;
      }
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch(`api/lead/${this.token}/submit`, { method: 'POST' });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao calcular resultado');
        }
        const data = await r.json();
        this.result = data.percentuais;
        this.view = 'result';
        window.scrollTo({ top: 0, behavior: 'smooth' });
        await this.initChat();
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
      } finally {
        this.loading = false;
      }
    },

    async initChat() {
      try {
        const r = await fetch(`api/chat/${this.token}/init`, { method: 'POST' });
        if (!r.ok) return;
        const data = await r.json();
        if (data.message) {
          this.chat.push({ role: 'assistant', content: data.message });
          this.scrollChat();
        }
      } catch (e) { /* ignore */ }
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
        const r = await fetch(`api/chat/${this.token}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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
        if (this.streamBuffer) {
          this.chat.push({ role: 'assistant', content: this.streamBuffer });
        }
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
      if (eventType === 'error') {
        this.streamBuffer += `\n[${dataLines.join('\n')}]`;
        return;
      }
      this.streamBuffer += dataLines.join('\n');
      this.scrollChat();
    },

    scrollChat() {
      this.$nextTick(() => {
        const box = this.$refs.chatBox;
        if (box) box.scrollTop = box.scrollHeight;
      });
    },

    async retake() {
      if (!confirm('Deseja refazer o teste? Seu resultado atual ficará salvo.')) return;
      this.loading = true;
      try {
        const r = await fetch(`api/lead/${this.token}/retake`, { method: 'POST' });
        if (!r.ok) throw new Error('Erro ao refazer');
        const data = await r.json();
        this.token = data.token;
        localStorage.setItem('tpc_token', this.token);
        this.answers = {};
        this.result = null;
        this.chat = [];
        this.currentIdx = 0;
        await this.loadQuestions();
        this.view = 'wizard';
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    archetypesOrdered() {
      const meta = {
        tubarao: { label: 'Tubarão', bg: '#0f766e' },
        lobo: { label: 'Lobo', bg: '#be123c' },
        aguia: { label: 'Águia', bg: '#ea580c' },
        gato: { label: 'Gato', bg: '#16a34a' },
      };
      return Object.keys(meta)
        .map(k => ({ key: k, ...meta[k], value: this.result ? this.result[k] : 0 }))
        .sort((a, b) => b.value - a.value);
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
