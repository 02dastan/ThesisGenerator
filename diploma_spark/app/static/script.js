/* ── Helpers ──────────────────────────────────────────────── */
const $ = id => document.getElementById(id);

const DIFFICULTY_LABELS = { easy: 'Лёгкая', medium: 'Средняя', hard: 'Сложная' };
const DIFFICULTY_BADGE  = { easy: 'badge-easy', medium: 'badge-medium', hard: 'badge-hard' };

/* ── Anti-Panic Mode ─────────────────────────────────────── */
function toggleAntiPanic() {
    const f = $('antiPanicForm');
    f.classList.toggle('hidden');
}

async function generatePanic() {
    const skills = $('panicSkills').value.trim();
    if (!skills) { alert('Введите хоть что-нибудь!'); return; }

    const data = {
        specialty: 'Другое',
        interests: skills,
        resources: '',
        deadline: '4-6 месяцев',
        work_type: 'Смешанный',
        level: 'бакалавр',
        use_ai: false,
        regenerate: false,
    };
    await sendGenerate(data);
    toggleAntiPanic();
}

/* ── Main Form Submit ────────────────────────────────────── */
document.getElementById('generateForm').addEventListener('submit', async e => {
    e.preventDefault();
    const form = e.target;

    let specialty = form.specialty.value;
    if (specialty === 'Другое') {
        specialty = ($('specialtyOther').value.trim()) || 'Другое';
    }

    const resources = [];
    if (form.res_data?.checked) resources.push('Реальные данные');
    if (form.res_lab?.checked)  resources.push('Лаборатория');
    if (form.res_server?.checked) resources.push('Сервер/хостинг');
    if (form.res_code?.checked) resources.push('Навыки программирования');
    const resOther = form.res_other?.value.trim();
    if (resOther) resources.push(resOther);

    const data = {
        specialty,
        interests:  form.interests.value.trim(),
        resources:  resources.join(', '),
        deadline:   form.deadline.value,
        work_type:  form.querySelector('input[name="work_type"]:checked')?.value || 'Смешанный',
        level:      form.querySelector('input[name="level"]:checked')?.value || 'бакалавр',
        use_ai:     form.use_ai?.checked || false,
        regenerate: false,
    };

    await sendGenerate(data);
});

let lastRequestData = null;

async function sendGenerate(data) {
    lastRequestData = data;
    $('loading').classList.remove('hidden');
    $('results').innerHTML = '';
    $('newRequestBtn').classList.add('hidden');
    $('submitBtn') && ($('submitBtn').disabled = true);

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        const json = await res.json();

        if (!res.ok) {
            throw new Error(json.detail || 'Неизвестная ошибка');
        }

        renderTopics(json.topics, data.specialty);
        saveToHistory(json.topics, data);

    } catch (err) {
        $('results').innerHTML = `
            <div class="bg-red-900/30 border border-red-500/30 rounded-xl p-5 text-red-300">
                <p class="font-semibold mb-1">Ошибка генерации</p>
                <p class="text-sm">${err.message}</p>
            </div>`;
    } finally {
        $('loading').classList.add('hidden');
        $('newRequestBtn').classList.remove('hidden');
        $('submitBtn') && ($('submitBtn').disabled = false);
    }
}

/* ── Render Topics ───────────────────────────────────────── */
function renderTopics(topics, specialty) {
    const container = $('results');
    if (!topics || !topics.length) {
        container.innerHTML = '<p class="text-center text-white/50">Темы не сгенерированы</p>';
        return;
    }

    const isPdfEnabled = true; // controlled by server but we show button anyway
    container.innerHTML = topics.map((t, i) => {
        const diff = t.difficulty || 'medium';
        const chapters = Array.isArray(t.structure) ? t.structure : [];
        return `
        <div class="topic-card" id="topic-${i}">
            <div class="flex items-start justify-between gap-4 mb-4">
                <div class="flex items-start gap-3">
                    <span class="text-2xl">💡</span>
                    <div>
                        <span class="text-gray-400 text-xs font-medium uppercase tracking-wide">Тема ${i+1}</span>
                        <h3 class="text-white text-lg font-bold leading-snug">${escHtml(t.title || '')}</h3>
                    </div>
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <span class="px-3 py-1 rounded-full text-xs font-semibold ${DIFFICULTY_BADGE[diff] || 'badge-medium'}">
                        ${DIFFICULTY_LABELS[diff] || diff}
                    </span>
                    <span class="text-gray-500 text-xs">${t.pages_approx || '?'} стр.</span>
                    <button class="star-btn text-gray-500 text-xl" title="В избранное" onclick="toggleFavorite(${i}, this)">★</button>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm mb-4">
                <div>
                    <p class="text-gray-400 text-xs uppercase tracking-wide mb-1">Актуальность</p>
                    <p class="text-gray-200">${escHtml(t.relevance || '')}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-xs uppercase tracking-wide mb-1">Научная новизна</p>
                    <p class="text-gray-200">${escHtml(t.novelty || '')}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-xs uppercase tracking-wide mb-1">Методы исследования</p>
                    <p class="text-gray-200">${escHtml(t.methods || '')}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-xs uppercase tracking-wide mb-1">Ожидаемый результат</p>
                    <p class="text-gray-200">${escHtml(t.expected_result || '')}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-xs uppercase tracking-wide mb-1">Необходимые ресурсы</p>
                    <p class="text-gray-200">${escHtml(t.required_resources || '')}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-xs uppercase tracking-wide mb-1">Структура (главы)</p>
                    <ul class="text-gray-200 space-y-0.5">
                        ${chapters.map(ch => `<li class="flex gap-1"><span class="text-indigo-400">›</span> ${escHtml(ch)}</li>`).join('')}
                    </ul>
                </div>
            </div>

            <div class="flex flex-wrap gap-2 pt-3 border-t border-white/10">
                <button onclick="downloadTxt(${i})"
                    class="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-white px-3 py-1.5 rounded-lg text-xs transition">
                    Скачать TXT
                </button>
                <button onclick="downloadPdf(${i})"
                    class="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-white px-3 py-1.5 rounded-lg text-xs transition">
                    Скачать PDF
                </button>
                <button onclick="regenerateSingle(${i})"
                    class="flex items-center gap-1.5 bg-yellow-600/20 hover:bg-yellow-600/40 text-yellow-300 px-3 py-1.5 rounded-lg text-xs transition">
                    Плохая идея — переделать
                </button>
                <button onclick="enhanceTopic(${i})"
                    class="flex items-center gap-1.5 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 px-3 py-1.5 rounded-lg text-xs transition">
                    Усилить тему
                </button>
            </div>
        </div>`;
    }).join('');

    // Mark favorites
    const favs = getFavorites();
    topics.forEach((_, i) => {
        const title = topics[i].title;
        if (favs.some(f => f.title === title)) {
            const btn = document.querySelector(`#topic-${i} .star-btn`);
            if (btn) btn.classList.add('active');
        }
    });

    window._currentTopics = topics;
    window._currentSpecialty = specialty;
}

/* ── Regenerate / Enhance ───────────────────────────────── */
async function regenerateSingle(idx) {
    if (!lastRequestData) return;
    await sendGenerate({ ...lastRequestData, regenerate: true });
}

async function enhanceTopic(idx) {
    if (!window._currentTopics) return;
    const topic = window._currentTopics[idx];
    const data = {
        ...lastRequestData,
        interests: lastRequestData.interests + `. Усиль эту тему: ${topic.title}. Добавь сравнение нескольких моделей, внедрение в реальную организацию, количественные метрики.`,
        regenerate: true,
    };
    await sendGenerate(data);
}

/* ── Download TXT ────────────────────────────────────────── */
function downloadTxt(idx) {
    const t = window._currentTopics[idx];
    const chapters = Array.isArray(t.structure) ? t.structure.join('\n  ') : '';
    const text = `ТЕМА ДИПЛОМНОЙ РАБОТЫ
=====================
${t.title}

АКТУАЛЬНОСТЬ:
${t.relevance}

НАУЧНАЯ НОВИЗНА:
${t.novelty}

СТРУКТУРА:
  ${chapters}

МЕТОДЫ ИССЛЕДОВАНИЯ:
${t.methods}

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
${t.expected_result}

НЕОБХОДИМЫЕ РЕСУРСЫ:
${t.required_resources}

СЛОЖНОСТЬ: ${DIFFICULTY_LABELS[t.difficulty] || t.difficulty}
ПРИМЕРНЫЙ ОБЪЁМ: ${t.pages_approx} страниц

Сгенерировано DiplomaSpark`;

    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `diploma_idea_${idx+1}.txt`;
    a.click();
}

/* ── Download PDF ────────────────────────────────────────── */
async function downloadPdf(idx) {
    const topics = [window._currentTopics[idx]];
    const specialty = window._currentSpecialty || '';
    const url = `/api/download_pdf?topics=${encodeURIComponent(JSON.stringify(topics))}&specialty=${encodeURIComponent(specialty)}`;
    try {
        const res = await fetch(url);
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || 'Ошибка генерации PDF');
            return;
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `diploma_idea_${idx+1}.pdf`;
        a.click();
    } catch {
        alert('Ошибка загрузки PDF');
    }
}

/* ── Favorites (localStorage) ───────────────────────────── */
function getFavorites() {
    try { return JSON.parse(localStorage.getItem('ds_favorites') || '[]'); } catch { return []; }
}

function saveFavorites(favs) {
    localStorage.setItem('ds_favorites', JSON.stringify(favs));
}

function toggleFavorite(idx, btn) {
    const topic = window._currentTopics?.[idx];
    if (!topic) return;
    const favs = getFavorites();
    const existing = favs.findIndex(f => f.title === topic.title);
    if (existing >= 0) {
        favs.splice(existing, 1);
        btn.classList.remove('active');
    } else {
        favs.push(topic);
        btn.classList.add('active');
    }
    saveFavorites(favs);
    renderFavorites();
}

function renderFavorites() {
    const favs = getFavorites();
    const section = $('favoritesSection');
    const list = $('favoritesList');
    if (!favs.length) { section?.classList.add('hidden'); return; }
    section?.classList.remove('hidden');
    if (list) {
        list.innerHTML = favs.map((f, i) => `
            <div class="bg-white/5 border border-white/10 rounded-xl p-4 flex items-start justify-between gap-3">
                <div>
                    <p class="text-white font-semibold">${escHtml(f.title)}</p>
                    <p class="text-gray-400 text-xs mt-1">${escHtml(f.relevance?.substring(0, 100))}...</p>
                </div>
                <button onclick="removeFavorite(${i})" class="text-red-400 hover:text-red-300 text-xs flex-shrink-0">Удалить</button>
            </div>`).join('');
    }
}

function removeFavorite(idx) {
    const favs = getFavorites();
    favs.splice(idx, 1);
    saveFavorites(favs);
    renderFavorites();
}

/* ── History (localStorage) ─────────────────────────────── */
function saveToHistory(topics, data) {
    const history = JSON.parse(localStorage.getItem('ds_history') || '[]');
    history.unshift({
        date: new Date().toLocaleString('ru'),
        specialty: data.specialty,
        topics,
    });
    localStorage.setItem('ds_history', JSON.stringify(history.slice(0, 20)));
    renderHistory();
}

function renderHistory() {
    const list = $('historyList');
    if (!list) return;
    const history = JSON.parse(localStorage.getItem('ds_history') || '[]');
    if (!history.length) {
        list.innerHTML = '<p class="text-gray-500 text-sm">История пуста</p>';
        return;
    }
    list.innerHTML = history.map((h, i) => `
        <div class="border-b border-white/5 pb-3 mb-3">
            <p class="text-white text-xs font-semibold">${escHtml(h.specialty)}</p>
            <p class="text-gray-500 text-xs">${h.date}</p>
            <p class="text-gray-400 text-xs">${h.topics?.length || 0} тем</p>
            <button onclick="loadFromHistory(${i})" class="text-indigo-400 text-xs hover:text-indigo-300 mt-1">Загрузить</button>
        </div>`).join('');
}

function loadFromHistory(idx) {
    const history = JSON.parse(localStorage.getItem('ds_history') || '[]');
    const entry = history[idx];
    if (!entry) return;
    renderTopics(entry.topics, entry.specialty);
    $('newRequestBtn').classList.remove('hidden');
    $('historyDropdown').classList.add('hidden');
}

function toggleHistory() {
    const d = $('historyDropdown');
    d.classList.toggle('hidden');
    if (!d.classList.contains('hidden')) renderHistory();
}

/* ── Reset Form ──────────────────────────────────────────── */
function resetForm() {
    $('results').innerHTML = '';
    $('newRequestBtn').classList.add('hidden');
    $('generateForm').reset();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ── Utils ───────────────────────────────────────────────── */
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/* ── Init ────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    renderFavorites();
    renderHistory();
});
