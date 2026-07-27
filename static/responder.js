// Questionário. Serve os dois fluxos:
//  - colaborador logado  → /responder/{token}      (APIs /api/lead/*)
//  - convidado por e-mail → /nr1/{invite}/responder (APIs /api/nr1/*, sem sessão)
// As URLs vêm de window.__CFG; sem elas, cai no fluxo logado.
function responder() {
  const CFG = window.__CFG || {};
  const api = (p) => `${CFG.basePath}/api${p}`;
  const urls = {
    questions: CFG.questionsUrl || api(`/tests/${CFG.testId}/questions`),
    answers: CFG.answersUrl || api(`/lead/${CFG.token}/answers`),
    submit: CFG.submitUrl || api(`/lead/${CFG.token}/submit`),
    done: CFG.doneUrl || `${CFG.basePath}/resultado/${CFG.token}`,
  };
  return {
    questions: [],
    testKind: 'choice',
    currentIdx: 0,
    answers: {},
    loading: false,
    error: '',

    get currentQ() { return this.questions[this.currentIdx] || null; },
    get currentQid() { return this.currentQ ? this.currentQ.id : null; },
    get currentOptions() { return this.currentQ ? this.currentQ.options : []; },
    get currentPrompt() { return this.currentQ ? this.currentQ.prompt : ''; },
    get currentSecao() { return this.currentQ ? (this.currentQ.secao || '') : ''; },

    async init() {
      await this.loadQuestions();
    },

    async loadQuestions() {
      try {
        const r = await fetch(urls.questions, { credentials: 'same-origin' });
        if (!r.ok) { this.error = 'Não foi possível carregar as perguntas'; return; }
        const data = await r.json();
        this.questions = data.questions || [];
        this.testKind = data.kind || 'choice';
      } catch (_) { this.error = 'Erro ao carregar as perguntas'; }
    },

    async chooseOption(value) {
      const qid = this.currentQid;
      this.answers[qid] = value;
      this.error = '';
      try {
        await fetch(urls.answers, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ answers: { [qid]: value } }),
        });
      } catch (_) { /* best-effort */ }
      // Likert (COPSOQ): avança sozinho para agilizar as 119 questões.
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
        const r = await fetch(urls.submit, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ answers: this.answers }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao calcular resultado');
        }
        window.location = urls.done;
      } catch (e) {
        this.error = e.message || 'Erro inesperado';
        this.loading = false;
      }
    },
  };
}
