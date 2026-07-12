function app() {
  return {
    view: 'login',
    loading: false,
    error: '',

    user: null,

    authForm: { email: '', password: '' },
    registerForm: { nome: '', sobrenome: '', whatsapp: '', email: '', profissao: '', origem: '', password: '' },
    forgotSent: false,
    showPw: { login: false, register: false, resetNew: false, resetConfirm: false },

    resetToken: null,
    resetDone: false,
    resetForm: { newPassword: '', confirmPassword: '' },

    tests: [],
    selectedTest: null,
    history: [],

    // Contexto de empresa (testes organizacionais, ex.: COPSOQ)
    companySlug: null,
    company: null,          // { nome, slug, areas: [] }
    selectedArea: '',
    pendingResult: null,    // token vindo de ?r= (link de e-mail/WhatsApp)

    token: null,
    questions: [],
    testKind: 'choice',
    currentIdx: 0,
    answers: {},
    result: null,

    chat: [],
    input: '',
    streaming: false,
    streamBuffer: '',

    get currentQ() { return this.questions[this.currentIdx] || null; },
    get currentQid() { return this.currentQ ? this.currentQ.id : null; },
    get currentOptions() { return this.currentQ ? this.currentQ.options : []; },
    get currentPrompt() { return this.currentQ ? this.currentQ.prompt : ''; },
    get currentSecao() { return this.currentQ ? (this.currentQ.secao || '') : ''; },

    get needsArea() {
      return !!(this.selectedTest && this.selectedTest.empresa && this.company);
    },

    showHeader() {
      return ['dashboard', 'test-detail', 'wizard', 'result'].includes(this.view);
    },

    async init() {
      const path = window.location.pathname;
      const search = new URLSearchParams(window.location.search);
      // contexto de empresa via ?empresa=slug (persiste em localStorage)
      const emp = search.get('empresa');
      if (emp) {
        this.companySlug = emp;
        try { localStorage.setItem('tpc_empresa', emp); } catch (_) {}
      } else {
        try { this.companySlug = localStorage.getItem('tpc_empresa'); } catch (_) {}
      }
      if (this.companySlug) this.loadCompany();

      if (/\/reset\/?$/.test(path) && search.get('token')) {
        this.resetToken = search.get('token');
        this.view = 'reset';
        return;
      }
      // Link de resultado (?r=token) — abre o resultado após autenticar.
      const rt = search.get('r');
      if (rt) this.pendingResult = rt;
      await this.checkSession();
    },

    async loadCompany() {
      try {
        const r = await fetch(`api/company/${encodeURIComponent(this.companySlug)}`);
        if (r.ok) this.company = await r.json();
        else { this.company = null; }
      } catch (_) { this.company = null; }
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

    resetShowPw() {
      this.showPw = { login: false, register: false, resetNew: false, resetConfirm: false };
    },

    goView(view) {
      this.error = '';
      this.view = view;
      this.resetShowPw();
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
        if (data.super_admin) {
          // Super admin: painel server-side em /admin
          window.location.href = data.redirect || 'admin';
          return;
        }
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
      this.resetShowPw();
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
      if (this.pendingResult) {
        const t = this.pendingResult;
        this.pendingResult = null;
        await this.openResult(t);
      }
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
        this.selectedArea = '';
        if (this.selectedTest && this.selectedTest.empresa && this.companySlug && !this.company) {
          await this.loadCompany();
        }
        this.view = 'test-detail';
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.error = e.message || 'Erro ao abrir teste';
      }
    },

    async startNewTest() {
      if (!this.selectedTest || !this.selectedTest.ativo) return;
      if (this.needsArea && !this.selectedArea) { this.error = 'Selecione a sua área/setor para continuar'; return; }
      this.error = '';
      this.loading = true;
      try {
        const body = {};
        if (this.selectedTest.empresa && this.company) {
          body.company_slug = this.company.slug;
          body.area = this.selectedArea;
        }
        const r = await fetch(`api/tests/${this.selectedTest.id}/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify(body),
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
        this.questions = [];
        await this.loadQuestions(this.selectedTest.id);
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
        this.testKind = (data.lead && data.lead.test_kind) || 'choice';
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

    async loadQuestions(testId) {
      const r = await fetch(`api/tests/${testId}/questions`, { credentials: 'same-origin' });
      const data = await r.json();
      this.questions = data.questions || [];
      this.testKind = data.kind || 'choice';
    },

    async chooseOption(value) {
      const qid = this.currentQid;
      this.answers[qid] = value;
      this.error = '';
      try {
        await fetch(`api/lead/${this.token}/answers`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ answers: { [qid]: value } }),
        });
      } catch (e) { /* best-effort */ }
      // Likert (COPSOQ): avança automaticamente para agilizar as 119 questões.
      if (this.testKind === 'likert' && this.currentIdx < this.questions.length - 1) {
        setTimeout(() => this.nextQuestion(), 140);
      }
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
        // Reenvia todas as respostas no submit — evita perder a última resposta por
        // um PATCH assíncrono que não chegou/falhou.
        const r = await fetch(`api/lead/${this.token}/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ answers: this.answers }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao calcular resultado');
        }
        const data = await r.json();
        this.result = data.result;
        this.testKind = (this.result && this.result.type === 'copsoq') ? 'likert' : 'choice';
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

    // --- Resultado: arquétipos ---
    archetypesOrdered() {
      const perc = (this.result && this.result.perc) ? this.result.perc : {};
      const meta = {
        tubarao: { label: 'Tubarão' },
        lobo: { label: 'Lobo' },
        aguia: { label: 'Águia' },
        gato: { label: 'Gato' },
      };
      return Object.keys(meta)
        .map(k => ({ key: k, ...meta[k], value: perc[k] || 0 }))
        .sort((a, b) => b.value - a.value);
    },

    // --- Resultado: COPSOQ dimensional ---
    get isCopsoq() { return !!(this.result && this.result.type === 'copsoq'); },

    copsoqGrouped() {
      if (!this.isCopsoq) return [];
      const subs = this.result.subscales || [];
      return (this.result.domains || []).map(d => ({
        ...d,
        subs: subs.filter(s => s.dominio === d.key && s.score !== null && s.score !== undefined),
      })).filter(d => d.subs.length > 0);
    },

    nivelColor(nivel) {
      return { verde: '#16a34a', amarelo: '#f59e0b', vermelho: '#dc2626' }[nivel] || '#94a3b8';
    },
    nivelBg(nivel) {
      return { verde: '#dcfce7', amarelo: '#fef3c7', vermelho: '#fee2e2' }[nivel] || '#f1f5f9';
    },
    nivelLabel(nivel) {
      return { verde: 'Favorável', amarelo: 'Atenção', vermelho: 'Risco alto' }[nivel] || '—';
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
