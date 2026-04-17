function app() {
  return {
    view: 'login',
    loading: false,
    error: '',

    user: null,

    authForm: { email: '', password: '' },
    registerForm: { nome: '', sobrenome: '', whatsapp: '', email: '', profissao: '', origem: '', password: '' },
    forgotSent: false,

    resetToken: null,
    resetDone: false,
    resetForm: { newPassword: '', confirmPassword: '' },

    tests: [],
    selectedTest: null,
    history: [],

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

    showHeader() {
      return ['dashboard', 'test-detail', 'wizard', 'result'].includes(this.view);
    },

    async init() {
      const path = window.location.pathname;
      const search = new URLSearchParams(window.location.search);
      if (/\/reset\/?$/.test(path) && search.get('token')) {
        this.resetToken = search.get('token');
        this.view = 'reset';
        return;
      }
      await this.checkSession();
    },

    async checkSession() {
      try {
        const r = await fetch('api/auth/me', { credentials: 'same-origin' });
        if (r.ok) {
          const data = await r.json();
          this.user = data.user;
          await this.goDashboard();
        } else {
          this.view = 'login';
        }
      } catch (_) {
        this.view = 'login';
      }
    },

    goView(view) {
      this.error = '';
      this.view = view;
      if (view === 'forgot') this.forgotSent = false;
    },

    async doLogin() {
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch('api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify(this.authForm),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'E-mail ou senha inválidos');
        }
        const data = await r.json();
        this.user = data.user;
        this.authForm = { email: '', password: '' };
        await this.goDashboard();
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
      } finally {
        this.loading = false;
      }
    },

    async doRegister() {
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch('api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify(this.registerForm),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          let msg = 'Erro ao criar conta';
          if (typeof err.detail === 'string') msg = err.detail;
          else if (Array.isArray(err.detail)) msg = err.detail.map(d => d.msg).join(' · ');
          throw new Error(msg);
        }
        const data = await r.json();
        this.user = data.user;
        this.registerForm = { nome: '', sobrenome: '', whatsapp: '', email: '', profissao: '', origem: '', password: '' };
        await this.goDashboard();
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
      } finally {
        this.loading = false;
      }
    },

    async logout() {
      try { await fetch('api/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) {}
      this.user = null;
      this.tests = [];
      this.selectedTest = null;
      this.history = [];
      this.token = null;
      this.result = null;
      this.chat = [];
      this.answers = {};
      this.view = 'login';
    },

    async doForgot() {
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch('api/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: this.authForm.email }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao processar solicitação');
        }
        this.forgotSent = true;
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
      } finally {
        this.loading = false;
      }
    },

    async doReset() {
      this.error = '';
      if (this.resetForm.newPassword !== this.resetForm.confirmPassword) {
        this.error = 'As senhas não coincidem';
        return;
      }
      if (this.resetForm.newPassword.length < 8) {
        this.error = 'A senha precisa ter pelo menos 8 caracteres';
        return;
      }
      this.loading = true;
      try {
        const r = await fetch('api/auth/reset-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.resetToken, password: this.resetForm.newPassword }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Link inválido ou expirado');
        }
        this.resetDone = true;
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
      } finally {
        this.loading = false;
      }
    },

    async goDashboard() {
      this.error = '';
      this.view = 'dashboard';
      await this.loadTests();
    },

    async loadTests() {
      try {
        const r = await fetch('api/tests', { credentials: 'same-origin' });
        if (!r.ok) { this.view = 'login'; return; }
        const data = await r.json();
        this.tests = data.tests;
      } catch (_) { /* ignore */ }
    },

    async openTest(testId) {
      this.error = '';
      try {
        const r = await fetch(`api/tests/${testId}/history`, { credentials: 'same-origin' });
        if (!r.ok) return;
        const data = await r.json();
        this.selectedTest = data.test;
        this.history = data.history;
        this.view = 'test-detail';
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.error = e.message || 'Erro ao abrir teste';
      }
    },

    async startNewTest() {
      if (!this.selectedTest || !this.selectedTest.ativo) return;
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch(`api/tests/${this.selectedTest.id}/start`, {
          method: 'POST',
          credentials: 'same-origin',
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao iniciar teste');
        }
        const data = await r.json();
        this.token = data.token;
        this.answers = {};
        this.result = null;
        this.chat = [];
        this.currentIdx = 0;
        await this.loadQuestions();
        this.view = 'wizard';
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.error = e.message || 'Erro ao iniciar teste';
      } finally {
        this.loading = false;
      }
    },

    async openResult(token) {
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch(`api/lead/${token}`, { credentials: 'same-origin' });
        if (!r.ok) throw new Error('Não foi possível carregar o resultado');
        const data = await r.json();
        this.token = token;
        this.answers = data.answers || {};
        this.result = data.result;
        this.chat = data.chat_history || [];
        if (!this.result) throw new Error('Teste não concluído');
        this.view = 'result';
        window.scrollTo({ top: 0, behavior: 'smooth' });
        if (this.chat.length === 0) await this.initChat();
      } catch (e) {
        this.error = e.message || 'Erro';
      } finally {
        this.loading = false;
      }
    },

    async loadQuestions() {
      if (this.questions.length > 0) return;
      const r = await fetch('api/questions', { credentials: 'same-origin' });
      const data = await r.json();
      this.questions = data.questions;
    },

    async chooseOption(value) {
      this.answers[this.currentQid] = value;
      this.error = '';
      try {
        await fetch(`api/lead/${this.token}/answers`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ answers: { [this.currentQid]: value } }),
        });
      } catch (e) { /* best-effort */ }
    },

    nextQuestion() {
      if (!this.answers[this.currentQid]) { this.error = 'Selecione uma opção para avançar'; return; }
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
      if (!this.answers[this.currentQid]) { this.error = 'Selecione uma opção antes de enviar'; return; }
      this.error = '';
      this.loading = true;
      try {
        const r = await fetch(`api/lead/${this.token}/submit`, { method: 'POST', credentials: 'same-origin' });
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
        const r = await fetch(`api/chat/${this.token}/init`, { method: 'POST', credentials: 'same-origin' });
        if (!r.ok) return;
        const data = await r.json();
        if (data.message) {
          this.chat.push({ role: 'assistant', content: data.message });
          this.scrollChat();
        }
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
        const r = await fetch(`api/chat/${this.token}`, {
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

    goBackToTest() {
      if (this.selectedTest) this.openTest(this.selectedTest.id);
      else this.goDashboard();
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

    formatDate(iso) {
      if (!iso) return '';
      try {
        const d = new Date(iso);
        return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
      } catch (_) { return iso; }
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
