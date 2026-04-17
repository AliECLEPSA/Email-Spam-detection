const state = {
  emails: [],
  stats: null,
  currentEmail: null,
  currentFilter: 'inbox',
  spamThreshold: Number(localStorage.getItem('spamshield-threshold') || '0.50'),
  lmStudioAvailable: false,
  lmStudioModel: null,
  chatHistory: [],
  listRenderLimit: 120,
  searchDebounceTimer: null,
  defaultApp: localStorage.getItem('spamshield-default-app') || 'Mail',
  conversationView: (localStorage.getItem('spamshield-conversation-view') || 'on'),
  density: localStorage.getItem('spamshield-density') || 'default',
  theme: localStorage.getItem('spamshield-theme') || 'default',
  priorityFirst: (localStorage.getItem('spamshield-priority-first') || 'on'),
  currentApp: localStorage.getItem('spamshield-current-app') || 'Mail',
  calendarEvents: [],
  calendarYear: null,
  calendarMonthIndex: null,
  calendarSelectedDate: null,
  assistantStatusCheckedAt: 0,
  assistantRequestInFlight: false,
};

const AVATAR_COLORS = ['#1a73e8', '#34a853', '#ea4335', '#7b1fa2', '#0288d1', '#e65100', '#00897b', '#c62828'];
const INITIAL_EMAIL_RENDER_LIMIT = 120;
const EMAIL_RENDER_STEP = 120;
const DEFAULT_APPS = ['Mail', 'Drive', 'Photos', 'Meet'];

const FILTER_LABELS = {
  inbox: 'Inbox',
  starred: 'Starred',
  sent: 'Sent',
  drafts: 'Drafts',
  important: 'High Priority',
  events: 'Events',
  generated: 'Generated Emails',
  action_required: 'Action Required',
  meetings: 'Meetings',
  finance: 'Finance',
  shipping: 'Shipping',
  newsletters: 'Newsletters',
  security: 'Security',
  spam: 'Spam',
  phishing: 'Phishing',
  safe: 'Legitimate',
};

const FOLDER_CHIP_LABELS = {
  generated: 'Generated',
  action_required: 'Action Required',
  meetings: 'Meetings',
  finance: 'Finance',
  shipping: 'Shipping',
  newsletters: 'Newsletters',
  security: 'Security',
};

document.addEventListener('DOMContentLoaded', init);

async function init() {
  bindEvents();
  applyUiPreferences();
  applyCurrentApp();
  setThresholdUi(state.spamThreshold);
  await loadEmails();
  setInterval(() => refreshAssistantStatus(), 30000);
}

function bindEvents() {
  document.getElementById('settings-trigger').addEventListener('click', (event) => {
    event.stopPropagation();
    toggleSettings();
  });
  document.getElementById('profile-trigger').addEventListener('click', (event) => {
    event.stopPropagation();
    toggleProfileMenu();
  });
  document.getElementById('apps-trigger').addEventListener('click', (event) => {
    event.stopPropagation();
    toggleAppsMenu();
  });
  document.querySelectorAll('.apps-card').forEach((card) => {
    card.addEventListener('click', () => handleAppLauncherClick(card.dataset.app));
  });
  document.getElementById('default-app-chip').addEventListener('click', cycleDefaultApp);
  document.getElementById('conversation-chip').addEventListener('click', toggleConversationView);
  document.getElementById('priority-chip').addEventListener('click', togglePriorityFirst);
  document.querySelectorAll('.theme-swatch').forEach((button) => {
    button.addEventListener('click', () => setTheme(button.dataset.theme));
  });
  document.querySelectorAll('input[name="density"]').forEach((input) => {
    input.addEventListener('change', () => setDensity(input.value));
  });
  document.getElementById('search-input').addEventListener('input', () => {
    window.clearTimeout(state.searchDebounceTimer);
    state.searchDebounceTimer = window.setTimeout(() => {
      resetListRenderLimit();
      renderList();
    }, 120);
  });
  document.getElementById('threshold-slider').addEventListener('input', (event) => {
    state.spamThreshold = Number(event.target.value);
    localStorage.setItem('spamshield-threshold', state.spamThreshold.toFixed(2));
    setThresholdUi(state.spamThreshold);
    resetListRenderLimit();
    refreshCalendarState();
    renderList();
    renderCalendar();
    if (state.currentEmail) {
      openEmailById(state.currentEmail.id);
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeAllOverlays();
    }
  });
  document.addEventListener('click', handleGlobalClick);
}

async function loadEmails() {
  const response = await fetch('/api/bootstrap');
  const payload = await response.json();
  state.emails = (payload.emails || []).map((email) => ({
    ...email,
    search_blob: [
      email.from,
      email.subject,
      email.snippet,
      email.summary,
      ...(email.folder_tags || []),
      email.generated_family_label || '',
      email.source_label || '',
    ].join(' ').toLowerCase(),
    sort_date_ts: Date.parse(email.date_iso || '') || 0,
  }));
  state.stats = payload.stats || {};
  state.lmStudioAvailable = Boolean(payload.lm_studio?.available);
  state.lmStudioModel = payload.lm_studio?.model_id || null;
  state.assistantStatusCheckedAt = Date.now();
  refreshCalendarState();
  updateChatHeader();
  setThresholdUi(state.spamThreshold);
  resetListRenderLimit();
  renderList();
  renderCalendar();
}

async function refreshAssistantStatus(force = false) {
  const now = Date.now();
  if (!force && state.assistantRequestInFlight) return;
  if (!force && state.assistantStatusCheckedAt && now - state.assistantStatusCheckedAt < 20000) return;
  try {
    const response = await fetch('/api/status');
    if (!response.ok) return;
    const payload = await response.json();
    state.lmStudioAvailable = Boolean(payload.lm_studio?.available);
    state.lmStudioModel = payload.lm_studio?.model_id || null;
    state.assistantStatusCheckedAt = Date.now();
    updateChatHeader();
  } catch (error) {
    // Keep the previous state if the status endpoint is temporarily unavailable.
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function handleGlobalClick(event) {
  const profileMenu = document.getElementById('profile-menu');
  const profileTrigger = document.getElementById('profile-trigger');
  const appsMenu = document.getElementById('apps-menu');
  const appsTrigger = document.getElementById('apps-trigger');
  const settingsDrawer = document.getElementById('settings-drawer');
  const settingsTrigger = document.getElementById('settings-trigger');

  if (!profileMenu.contains(event.target) && !profileTrigger.contains(event.target)) {
    closeProfileMenu();
  }
  if (!appsMenu.contains(event.target) && !appsTrigger.contains(event.target)) {
    closeAppsMenu();
  }
  if (!settingsDrawer.contains(event.target) && !settingsTrigger.contains(event.target)) {
    closeSettings();
  }
}

function syncScrim() {
  const scrim = document.getElementById('ui-scrim');
  const hasOverlay =
    document.getElementById('profile-menu').classList.contains('open') ||
    document.getElementById('apps-menu').classList.contains('open') ||
    document.getElementById('settings-drawer').classList.contains('open');
  scrim.classList.toggle('visible', hasOverlay);
}

function openProfileMenu() {
  closeAppsMenu();
  closeSettings();
  document.getElementById('profile-menu').classList.add('open');
  syncScrim();
}

function closeProfileMenu() {
  document.getElementById('profile-menu').classList.remove('open');
  syncScrim();
}

function toggleProfileMenu() {
  const menu = document.getElementById('profile-menu');
  if (menu.classList.contains('open')) {
    closeProfileMenu();
  } else {
    openProfileMenu();
  }
}

function openAppsMenu() {
  closeProfileMenu();
  closeSettings();
  document.getElementById('apps-menu').classList.add('open');
  syncScrim();
}

function closeAppsMenu() {
  document.getElementById('apps-menu').classList.remove('open');
  syncScrim();
}

function toggleAppsMenu() {
  const menu = document.getElementById('apps-menu');
  if (menu.classList.contains('open')) {
    closeAppsMenu();
  } else {
    openAppsMenu();
  }
}

function openSettings() {
  closeAppsMenu();
  closeProfileMenu();
  document.getElementById('settings-drawer').classList.add('open');
  syncScrim();
}

function closeSettings() {
  document.getElementById('settings-drawer').classList.remove('open');
  syncScrim();
}

function toggleSettings() {
  const drawer = document.getElementById('settings-drawer');
  if (drawer.classList.contains('open')) {
    closeSettings();
  } else {
    openSettings();
  }
}

function closeAllOverlays() {
  closeProfileMenu();
  closeAppsMenu();
  closeSettings();
}

function applyCurrentApp() {
  document.body.dataset.currentApp = state.currentApp;
  const search = document.getElementById('search-input');
  if (search) {
    search.placeholder = state.currentApp === 'Calendar' ? 'Search calendar' : 'Search mail';
  }
}

function switchApp(appName) {
  state.currentApp = appName;
  localStorage.setItem('spamshield-current-app', appName);
  applyCurrentApp();
  updateSettingsChips();
  closeAppsMenu();
  if (appName === 'Calendar') {
    renderCalendar();
  } else {
    renderList();
  }
}

function handleAppLauncherClick(appName) {
  if (appName === 'Calendar') {
    switchApp('Calendar');
    return;
  }
  if (appName === 'Mail') {
    state.defaultApp = 'Mail';
    localStorage.setItem('spamshield-default-app', state.defaultApp);
    updateSettingsChips();
    switchApp('Mail');
    return;
  }
  state.defaultApp = appName;
  localStorage.setItem('spamshield-default-app', state.defaultApp);
  updateSettingsChips();
  closeAppsMenu();
}

function updateSettingsChips() {
  const defaultChip = document.getElementById('default-app-chip');
  const conversationChip = document.getElementById('conversation-chip');
  const priorityChip = document.getElementById('priority-chip');
  if (defaultChip) defaultChip.textContent = state.defaultApp;
  document.querySelectorAll('.apps-card').forEach((card) => {
    const shouldHighlight = state.currentApp === 'Calendar'
      ? card.dataset.app === 'Calendar'
      : card.dataset.app === state.defaultApp;
    card.classList.toggle('active', shouldHighlight);
  });
  if (conversationChip) {
    const isOn = state.conversationView === 'on';
    conversationChip.textContent = isOn ? 'On' : 'Off';
    conversationChip.dataset.state = isOn ? 'on' : 'off';
  }
  if (priorityChip) {
    const isOn = state.priorityFirst === 'on';
    priorityChip.textContent = isOn ? 'Active' : 'Off';
    priorityChip.dataset.state = isOn ? 'on' : 'off';
  }
}

function applyUiPreferences() {
  document.body.dataset.theme = state.theme;
  document.body.dataset.density = state.density;
  document.body.dataset.conversationView = state.conversationView;
  document.querySelectorAll('.theme-swatch').forEach((button) => {
    button.classList.toggle('active', button.dataset.theme === state.theme);
  });
  document.querySelectorAll('input[name="density"]').forEach((input) => {
    input.checked = input.value === state.density;
  });
  updateSettingsChips();
}

function cycleDefaultApp() {
  const currentIndex = DEFAULT_APPS.indexOf(state.defaultApp);
  state.defaultApp = DEFAULT_APPS[(currentIndex + 1) % DEFAULT_APPS.length];
  localStorage.setItem('spamshield-default-app', state.defaultApp);
  updateSettingsChips();
}

function toggleConversationView() {
  state.conversationView = state.conversationView === 'on' ? 'off' : 'on';
  localStorage.setItem('spamshield-conversation-view', state.conversationView);
  applyUiPreferences();
  resetListRenderLimit();
  renderList();
}

function setDensity(value) {
  state.density = value;
  localStorage.setItem('spamshield-density', value);
  applyUiPreferences();
}

function setTheme(themeName) {
  state.theme = themeName;
  localStorage.setItem('spamshield-theme', themeName);
  applyUiPreferences();
}

function togglePriorityFirst() {
  state.priorityFirst = state.priorityFirst === 'on' ? 'off' : 'on';
  localStorage.setItem('spamshield-priority-first', state.priorityFirst);
  updateSettingsChips();
  refreshCalendarState();
  renderList();
  renderCalendar();
}

function parseEventTime(event) {
  const match = String(event?.when || '').match(/\b(\d{1,2}:\d{2}|\d{1,2}(?::\d{2})?(?:AM|PM))\b/i);
  return match ? match[1] : 'All day';
}

function dominantYearFromEvents(events) {
  const years = events
    .filter((event) => event.date)
    .map((event) => Number(event.date.slice(0, 4)));
  if (!years.length) {
    return new Date().getFullYear();
  }
  return Math.max(...years);
}

function dominantMonthForYear(events, year) {
  const counts = new Map();
  events.forEach((event) => {
    if (!event.date || Number(event.date.slice(0, 4)) !== year) return;
    const month = Number(event.date.slice(5, 7)) - 1;
    counts.set(month, (counts.get(month) || 0) + 1);
  });
  if (!counts.size) return 0;
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

function buildCalendarEvents(emails) {
  return emails
    .filter((email) => getThreatView(email) === 'legitimate')
    .flatMap((email) => (email.events || []).map((event, index) => ({
      id: `${email.id}-${index}`,
      emailId: email.id,
      subject: event.title || email.subject,
      from: email.from,
      date: event.date_iso,
      time: parseEventTime(event),
      source: event.source,
      importanceRank: email.importance_rank || 3,
      color: email.importance_color || '#1a73e8',
      weekdayFr: event.weekday_fr,
      attachments: email.attachments || [],
    })))
    .filter((event) => Boolean(event.date))
    .sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`));
}

function refreshCalendarState() {
  state.calendarEvents = buildCalendarEvents(state.emails);
  const dominantYear = dominantYearFromEvents(state.calendarEvents);
  if (state.calendarYear == null) {
    state.calendarYear = dominantYear;
  }
  if (state.calendarMonthIndex == null) {
    state.calendarMonthIndex = dominantMonthForYear(state.calendarEvents, dominantYear);
  }
  if (!state.calendarSelectedDate) {
    const firstEvent = state.calendarEvents.find((event) => Number(event.date.slice(0, 4)) === state.calendarYear);
    state.calendarSelectedDate = firstEvent ? firstEvent.date : `${state.calendarYear}-${String(state.calendarMonthIndex + 1).padStart(2, '0')}-01`;
  }
}

function eventsForDate(dateIso) {
  return state.calendarEvents.filter((event) => event.date === dateIso);
}

function monthLabel(year, monthIndex) {
  return new Intl.DateTimeFormat('en-US', {month: 'long', year: 'numeric'}).format(new Date(year, monthIndex, 1));
}

function getMonthCells(year, monthIndex) {
  const first = new Date(year, monthIndex, 1);
  const start = new Date(first);
  start.setDate(1 - first.getDay());
  return Array.from({length: 42}, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

function isoDate(dateObj) {
  return [
    dateObj.getFullYear(),
    String(dateObj.getMonth() + 1).padStart(2, '0'),
    String(dateObj.getDate()).padStart(2, '0'),
  ].join('-');
}

function selectCalendarDate(dateIso) {
  state.calendarSelectedDate = dateIso;
  renderCalendar();
}

function changeCalendarMonth(delta) {
  const next = new Date(state.calendarYear, state.calendarMonthIndex + delta, 1);
  state.calendarYear = next.getFullYear();
  state.calendarMonthIndex = next.getMonth();
  const selected = new Date(state.calendarSelectedDate || isoDate(next));
  if (selected.getFullYear() !== state.calendarYear || selected.getMonth() !== state.calendarMonthIndex) {
    state.calendarSelectedDate = isoDate(new Date(state.calendarYear, state.calendarMonthIndex, 1));
  }
  renderCalendar();
}

function goToCalendarToday() {
  const event = state.calendarEvents[0];
  if (event) {
    state.calendarYear = Number(event.date.slice(0, 4));
    state.calendarMonthIndex = Number(event.date.slice(5, 7)) - 1;
    state.calendarSelectedDate = event.date;
  } else {
    const today = new Date();
    state.calendarYear = today.getFullYear();
    state.calendarMonthIndex = today.getMonth();
    state.calendarSelectedDate = isoDate(today);
  }
  renderCalendar();
}

function renderMiniCalendar() {
  const container = document.getElementById('mini-calendar-grid');
  if (!container) return;
  const labels = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
  const cells = getMonthCells(state.calendarYear, state.calendarMonthIndex);
  const eventDates = new Set(state.calendarEvents.map((event) => event.date));
  const todayIso = isoDate(new Date());
  container.innerHTML = '';

  labels.forEach((label) => {
    const el = document.createElement('div');
    el.className = 'mini-calendar-label';
    el.textContent = label;
    container.appendChild(el);
  });

  cells.forEach((day) => {
    const dayIso = isoDate(day);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'mini-calendar-day';
    if (day.getMonth() !== state.calendarMonthIndex) button.classList.add('muted');
    if (dayIso === todayIso) button.classList.add('today');
    if (dayIso === state.calendarSelectedDate) button.classList.add('selected');
    if (eventDates.has(dayIso)) button.classList.add('has-events');
    button.textContent = String(day.getDate());
    button.onclick = () => {
      state.calendarYear = day.getFullYear();
      state.calendarMonthIndex = day.getMonth();
      selectCalendarDate(dayIso);
    };
    container.appendChild(button);
  });

  document.getElementById('mini-calendar-title').textContent = monthLabel(state.calendarYear, state.calendarMonthIndex);
}

function renderUpcomingEvents() {
  const container = document.getElementById('upcoming-events');
  if (!container) return;
  const upcoming = state.calendarEvents.slice(0, 8);
  container.innerHTML = upcoming.length
    ? upcoming.map((event) => `
        <div class="upcoming-item">
          <div class="upcoming-date">${escapeHtml(event.date)}${event.time !== 'All day' ? ` · ${escapeHtml(event.time)}` : ''}</div>
          <div class="upcoming-title">${escapeHtml(event.subject)}</div>
          <div class="upcoming-meta">${escapeHtml(event.from)}</div>
        </div>
      `).join('')
    : `<div class="day-events-empty">No dated events were extracted from the email test set for the current threshold.</div>`;
}

function renderSelectedDayPanel() {
  const headline = document.getElementById('selected-day-headline');
  const subtitle = document.getElementById('selected-day-subtitle');
  const container = document.getElementById('selected-day-events');
  if (!headline || !subtitle || !container) return;

  const selectedDate = state.calendarSelectedDate;
  if (!selectedDate) {
    headline.textContent = 'No day selected';
    subtitle.textContent = 'Choose a day to inspect the events extracted from your emails.';
    container.innerHTML = '';
    return;
  }

  const selected = new Date(`${selectedDate}T12:00:00`);
  headline.textContent = new Intl.DateTimeFormat('en-US', {weekday: 'long', day: 'numeric'}).format(selected);
  subtitle.textContent = new Intl.DateTimeFormat('en-US', {month: 'long', year: 'numeric'}).format(selected);

  const items = eventsForDate(selectedDate);
  container.innerHTML = items.length
    ? items.map((event) => `
        <div class="day-event-card" style="border-left:4px solid ${event.color}">
          <div class="day-event-time">${escapeHtml(event.time)}</div>
          <div class="day-event-title">${escapeHtml(event.subject)}</div>
          <div class="day-event-meta">${escapeHtml(event.from)}<br>${escapeHtml(event.source)}</div>
          <button class="open-email-link" type="button" onclick="openEmailFromCalendar(${event.emailId})">Open email</button>
        </div>
      `).join('')
    : `<div class="day-events-empty">No event extracted for this day.</div>`;
}

function renderCalendarGrid() {
  const container = document.getElementById('calendar-grid');
  if (!container) return;
  const cells = getMonthCells(state.calendarYear, state.calendarMonthIndex);
  const todayIso = isoDate(new Date());
  container.innerHTML = '';

  cells.forEach((day) => {
    const dayIso = isoDate(day);
    const dayEvents = eventsForDate(dayIso);
    const cell = document.createElement('div');
    cell.className = 'calendar-day-cell';
    if (day.getMonth() !== state.calendarMonthIndex) cell.classList.add('muted');
    if (dayIso === todayIso) cell.classList.add('today');
    if (dayIso === state.calendarSelectedDate) cell.classList.add('selected');
    cell.onclick = () => selectCalendarDate(dayIso);

    const eventsHtml = dayEvents.slice(0, 3).map((event) => `
      <button class="calendar-event-chip" type="button" style="background:${event.color}" onclick="event.stopPropagation(); selectCalendarDate('${event.date}')">
        ${escapeHtml(event.time !== 'All day' ? `${event.time} · ${event.subject}` : event.subject)}
      </button>
    `).join('');
    const moreCount = dayEvents.length - 3;

    cell.innerHTML = `
      <div class="calendar-day-top">
        <div class="calendar-day-number">${day.getDate()}</div>
      </div>
      <div class="calendar-day-event-list">
        ${eventsHtml}
        ${moreCount > 0 ? `<div class="calendar-more">+${moreCount} more</div>` : ''}
      </div>
    `;
    container.appendChild(cell);
  });

  document.getElementById('calendar-title').textContent = monthLabel(state.calendarYear, state.calendarMonthIndex);
}

function renderCalendar() {
  if (state.currentApp !== 'Calendar') return;
  if (state.calendarYear == null || state.calendarMonthIndex == null) {
    refreshCalendarState();
  }
  renderMiniCalendar();
  renderUpcomingEvents();
  renderCalendarGrid();
  renderSelectedDayPanel();
}

function openEmailFromCalendar(emailId) {
  switchApp('Mail');
  const inboxNode = document.querySelector('.nav-item');
  if (inboxNode) {
    setNav(inboxNode, 'inbox');
  }
  openEmailById(emailId);
}

function groupedEmails(emails) {
  const grouped = new Map();
  emails.forEach((email) => {
    const key = (email.subject || '').trim().toLowerCase() || `msg-${email.id}`;
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {...email, thread_count: 1});
      return;
    }
    const preferred = existing.sort_date_ts >= email.sort_date_ts ? existing : email;
    grouped.set(key, {
      ...preferred,
      thread_count: (existing.thread_count || 1) + 1,
    });
  });
  return Array.from(grouped.values());
}

function emailPriorityScore(email) {
  return (
    (email.importance_rank || 0) * 10 +
    (email.events?.length ? 5 : 0) +
    (email.threat_type === 'legitimate' ? 3 : 0) -
    (email.spam_probability || 0)
  );
}

function sortEmails(emails) {
  const sorted = [...emails];
  if (state.priorityFirst === 'on') {
    sorted.sort((a, b) => {
      const delta = emailPriorityScore(b) - emailPriorityScore(a);
      if (delta !== 0) return delta;
      return (b.sort_date_ts || 0) - (a.sort_date_ts || 0);
    });
    return sorted;
  }
  sorted.sort((a, b) => (b.sort_date_ts || 0) - (a.sort_date_ts || 0));
  return sorted;
}

function openChat() {
  document.getElementById('chat-panel').classList.add('open');
  document.getElementById('chat-fab-label').textContent = 'Close assistant';
}

function closeChat() {
  document.getElementById('chat-panel').classList.remove('open');
  document.getElementById('chat-fab-label').textContent = 'Open assistant';
}

function toggleChat() {
  const panel = document.getElementById('chat-panel');
  if (panel.classList.contains('open')) {
    closeChat();
  } else {
    openChat();
    window.setTimeout(() => document.getElementById('chat-input').focus(), 80);
  }
}

function nl2br(value) {
  return escapeHtml(value).replaceAll('\n', '<br>');
}

function renderMarkdownLite(text) {
  let html = escapeHtml(text || '');
  html = html.replace(/\r\n/g, '\n');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  const blocks = html.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean);
  const rendered = blocks.map((block) => {
    const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
    const isList = lines.every((line) => /^[-*•]\s+/.test(line));
    if (isList) {
      return `<ul style="margin:0;padding-left:18px">${lines.map((line) => `<li>${line.replace(/^[-*•]\s+/, '')}</li>`).join('')}</ul>`;
    }
    return `<div style="line-height:1.6">${lines.join('<br>')}</div>`;
  });
  return rendered.join('<div style="height:8px"></div>');
}

function avatarColor(name) {
  let h = 0;
  for (const ch of name) {
    h = (h * 31 + ch.charCodeAt(0)) % AVATAR_COLORS.length;
  }
  return AVATAR_COLORS[h];
}

function getThreatView(email) {
  if (email.spam_probability >= state.spamThreshold) {
    return email.phishing_score >= 4 ? 'phishing' : 'spam';
  }
  return 'legitimate';
}

function hasFolderTag(email, tag) {
  return (email.folder_tags || []).includes(tag);
}

function matchesFilter(email, filter) {
  const threatType = getThreatView(email);
  if (filter === 'inbox') return threatType === 'legitimate';
  if (filter === 'spam') return threatType === 'spam';
  if (filter === 'phishing') return threatType === 'phishing';
  if (filter === 'safe') return threatType === 'legitimate';
  if (filter === 'important') return threatType === 'legitimate' && (email.importance_rank || 0) >= 4;
  if (filter === 'events') return threatType === 'legitimate' && email.events.length > 0;
  if (filter === 'generated') return hasFolderTag(email, 'generated');
  if (filter === 'action_required') return threatType === 'legitimate' && hasFolderTag(email, 'action_required');
  if (filter === 'meetings') return threatType === 'legitimate' && hasFolderTag(email, 'meetings');
  if (filter === 'finance') return threatType === 'legitimate' && hasFolderTag(email, 'finance');
  if (filter === 'shipping') return threatType === 'legitimate' && hasFolderTag(email, 'shipping');
  if (filter === 'newsletters') return threatType === 'legitimate' && hasFolderTag(email, 'newsletters');
  if (filter === 'security') return threatType === 'legitimate' && hasFolderTag(email, 'security');
  if (filter === 'starred' || filter === 'sent' || filter === 'drafts') return false;
  return true;
}

function countForFilter(filter) {
  return state.emails.filter((email) => matchesFilter(email, filter)).length;
}

function threatPresentation(threatType) {
  if (threatType === 'legitimate') {
    return {
      badgeClass: 'badge-safe',
      badgeText: '✓ Safe',
      barClass: 'bar-safe',
      alertClass: 'alert-safe',
      alertIcon: '✅',
      alertTitle: 'This email appears legitimate',
    };
  }
  if (threatType === 'phishing') {
    return {
      badgeClass: 'badge-phish',
      badgeText: '🎣 Phish',
      barClass: 'bar-phish',
      alertClass: 'alert-phish',
      alertIcon: '🚨',
      alertTitle: 'Phishing attempt detected',
    };
  }
  return {
    badgeClass: 'badge-spam',
    badgeText: '⚠ Spam',
    barClass: 'bar-spam',
    alertClass: 'alert-spam',
    alertIcon: '⚠️',
    alertTitle: 'This email is classified as spam',
  };
}

function severityColor(score) {
  if (score < 3) return '#34a853';
  if (score < 6) return '#fbbc04';
  return '#ea4335';
}

function liveClassificationReason(email, threatType) {
  if (threatType === email.threat_type) return email.classification_reason;
  const auth = `SPF=${email.spf}, DKIM=${email.dkim}, DMARC=${email.dmarc}`;
  if (threatType === 'legitimate') {
    return `The current threshold is stricter than the default model threshold. At ${state.spamThreshold.toFixed(2)}, this email still stays below the spam cutoff, although a few signals remain worth watching (${auth}).`;
  }
  if (threatType === 'phishing') {
    return `With the custom threshold set to ${state.spamThreshold.toFixed(2)}, this email is treated as phishing because the spam probability is ${email.spam_probability.toFixed(3)} and the impersonation signals are strong (${auth}, phishing score ${email.phishing_score}).`;
  }
  return `With the custom threshold set to ${state.spamThreshold.toFixed(2)}, this email is treated as spam because the spam probability is ${email.spam_probability.toFixed(3)} and it contains several suspicious signals (${auth}, ${email.urls} URL).`;
}

function getVisibleEmails() {
  const search = document.getElementById('search-input').value.trim().toLowerCase();
  let emails = state.emails;

  emails = emails.filter((email) => matchesFilter(email, state.currentFilter));

  if (search) {
    emails = emails.filter((email) => email.search_blob.includes(search));
  }

  emails = sortEmails(emails);
  if (state.conversationView === 'on') {
    emails = groupedEmails(emails);
  }

  return emails;
}

function resetListRenderLimit() {
  state.listRenderLimit = INITIAL_EMAIL_RENDER_LIMIT;
}

function renderLoadMore(container, totalCount, renderedCount) {
  if (renderedCount >= totalCount) return;

  const wrapper = document.createElement('div');
  wrapper.style.padding = '14px';
  wrapper.style.borderTop = '1px solid #e8eaed';
  wrapper.style.background = '#fff';

  const button = document.createElement('button');
  button.className = 'quick-btn';
  button.style.width = '100%';
  button.textContent = `Load more emails (${renderedCount} / ${totalCount})`;
  button.onclick = () => {
    state.listRenderLimit += EMAIL_RENDER_STEP;
    renderList();
  };

  wrapper.appendChild(button);
  container.appendChild(wrapper);
}

function renderList() {
  const container = document.getElementById('email-items');
  const list = getVisibleEmails();
  const visibleSlice = list.slice(0, state.listRenderLimit);
  container.innerHTML = '';

  if (list.length === 0) {
    container.innerHTML = `
      <div style="padding:24px;color:#5f6368;font-size:14px">
        No emails match the current filter.
      </div>
    `;
    updateBadges();
    document.getElementById('folder-label').textContent = `${FILTER_LABELS[state.currentFilter] || state.currentFilter} · 0`;
    return;
  }

  const fragment = document.createDocumentFragment();
  visibleSlice.forEach((email) => {
    const threatType = getThreatView(email);
    const threat = threatPresentation(threatType);
    const sourceBadge = email.is_generated
      ? '<span class="source-badge source-generated">Generated</span>'
      : '';
    const row = document.createElement('div');
    row.className = 'email-row' + (email.unread ? ' unread' : '') + (state.currentEmail && state.currentEmail.id === email.id ? ' active' : '');
    row.onclick = () => openEmailById(email.id);

    const importanceBadge = threatType === 'legitimate' && email.importance_rank
      ? `<span class="importance-badge priority-${email.importance_rank}">P${email.importance_rank}</span>`
      : '';
    const threadBadge = (email.thread_count || 1) > 1
      ? `<span class="thread-count">${email.thread_count}</span>`
      : '';

    row.innerHTML = `
      <div class="threat-bar ${threat.barClass}"></div>
      <div class="email-avatar" style="background:${avatarColor(email.from)}">${escapeHtml(email.from[0] || '?')}</div>
      <div class="email-main">
        <div class="email-body-preview">
          <div class="email-header">
            <div class="email-from-line">
              <span class="email-from">${escapeHtml(email.from)}</span>
              ${threadBadge}
            </div>
          </div>
          <div class="email-subject">${escapeHtml(email.subject)}</div>
          <div class="email-snippet">${escapeHtml(email.snippet)}</div>
        </div>
        <div class="email-side-meta">
          <span class="email-time">${escapeHtml(email.time)}</span>
          ${sourceBadge}
          <span class="threat-badge ${threat.badgeClass}">${threat.badgeText}</span>
          ${importanceBadge}
        </div>
      </div>
    `;
    fragment.appendChild(row);
  });
  container.appendChild(fragment);
  renderLoadMore(container, list.length, visibleSlice.length);

  document.getElementById('folder-label').textContent = `${FILTER_LABELS[state.currentFilter] || state.currentFilter} · ${list.length}`;
  updateBadges();
}

function updateBadges() {
  const inboxUnread = state.emails.filter((email) => email.unread && matchesFilter(email, 'inbox')).length;
  const spamCount = countForFilter('spam');
  const phishCount = countForFilter('phishing');
  const importantCount = countForFilter('important');
  const eventCount = countForFilter('events');
  const generatedCount = countForFilter('generated');
  const actionRequiredCount = countForFilter('action_required');
  const meetingsCount = countForFilter('meetings');
  const financeCount = countForFilter('finance');
  const shippingCount = countForFilter('shipping');
  const newsletterCount = countForFilter('newsletters');
  const securityCount = countForFilter('security');

  document.getElementById('inbox-count').textContent = inboxUnread > 0 ? String(inboxUnread) : '';
  document.getElementById('spam-count').textContent = spamCount ? String(spamCount) : '';
  document.getElementById('phish-count').textContent = phishCount ? String(phishCount) : '';
  document.getElementById('important-count').textContent = importantCount ? String(importantCount) : '';
  document.getElementById('events-count').textContent = eventCount ? String(eventCount) : '';
  document.getElementById('generated-count').textContent = generatedCount ? String(generatedCount) : '';
  document.getElementById('action-required-count').textContent = actionRequiredCount ? String(actionRequiredCount) : '';
  document.getElementById('meetings-count').textContent = meetingsCount ? String(meetingsCount) : '';
  document.getElementById('finance-count').textContent = financeCount ? String(financeCount) : '';
  document.getElementById('shipping-count').textContent = shippingCount ? String(shippingCount) : '';
  document.getElementById('newsletters-count').textContent = newsletterCount ? String(newsletterCount) : '';
  document.getElementById('security-count').textContent = securityCount ? String(securityCount) : '';
}

function renderEmailContent(email) {
  const threatType = getThreatView(email);
  const sevColor = severityColor(email.severity_score);
  const detailChips = [];
  if (email.is_generated) {
    detailChips.push('<span class="detail-chip generated">Generated email</span>');
  }
  (email.folder_tags || [])
    .filter((tag) => tag !== 'generated')
    .slice(0, 5)
    .forEach((tag) => detailChips.push(`<span class="detail-chip">${escapeHtml(FOLDER_CHIP_LABELS[tag] || tag)}</span>`));
  if (email.is_generated && email.generated_family_label) {
    detailChips.push(`<span class="detail-chip subtle">${escapeHtml(email.generated_family_label)}</span>`);
  }
  const detailChipsHtml = detailChips.length
    ? `<div class="detail-chip-row">${detailChips.join('')}</div>`
    : '';
  const generatedSourceNote = email.is_generated
    ? `<div class="source-note">Synthetic demo email from the blind stress-test set${email.generated_difficulty ? ` · ${escapeHtml(email.generated_difficulty)} scenario` : ''}</div>`
    : '';

  const attachmentHtml = email.attachments.length
    ? `<div style="margin-top:20px">
         <div style="font-size:13px;color:#5f6368;margin-bottom:8px">📎 ${email.attachments.length} attachment(s)</div>
         ${email.attachments.map((file) => `<span class="attachment-chip">📄 ${escapeHtml(file)}</span>`).join('')}
       </div>`
    : '';

  const importanceHtml = threatType === 'legitimate' && email.importance_rank
    ? `<div style="margin-bottom:16px;padding:12px 16px;border:1px solid #e8eaed;border-radius:12px;background:#fafafb">
         <div style="font-size:12px;color:#5f6368;margin-bottom:6px">Importance</div>
         <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
           <span class="importance-badge priority-${email.importance_rank}" style="position:static">Priority ${email.importance_rank} / 5</span>
           <span style="font-size:13px;color:#202124;font-weight:500">${escapeHtml(email.importance_label.toUpperCase())}</span>
         </div>
         <div style="font-size:13px;color:#5f6368;line-height:1.5;margin-top:8px">${escapeHtml(email.importance_reason)}</div>
       </div>`
    : '';

  document.getElementById('email-content').innerHTML = `
    <h1 class="email-title">${escapeHtml(email.subject)}</h1>
    <div class="email-meta">
      <div class="meta-avatar" style="background:${avatarColor(email.from)}">${escapeHtml(email.from[0] || '?')}</div>
      <div class="meta-info">
        <div class="meta-from">${escapeHtml(email.from)} <span>&lt;${escapeHtml(email.from_addr)}&gt;</span></div>
        <div class="meta-to">received ${escapeHtml(email.time)} · ${escapeHtml(email.language.toUpperCase())} · ${escapeHtml(email.source_label || 'Mailbox')}</div>
      </div>
    </div>

    ${detailChipsHtml}
    ${generatedSourceNote}

    <div class="severity-bar-container">
      <div class="severity-label">
        <span>Threat Severity Score</span>
        <span style="color:${sevColor};font-weight:600">${email.severity_score.toFixed(2)} / 10</span>
      </div>
      <div class="severity-track">
        <div class="severity-fill" style="width:${Math.min(email.severity_score * 10, 100)}%;background:${sevColor}"></div>
      </div>
    </div>

    ${importanceHtml}

    <div class="email-body-text">${nl2br(email.body)}</div>
    ${attachmentHtml}
  `;
}

function renderAutoAnalysis(email) {
  clearTyping();
  const threatType = getThreatView(email);
  const chipClass = threatType === 'legitimate' ? 'chip-safe' : threatType === 'phishing' ? 'chip-phish' : 'chip-spam';
  const chipLabel = threatType === 'legitimate' ? 'Legitimate' : threatType === 'phishing' ? 'Phishing' : 'Spam';
  const sevColor = severityColor(email.severity_score);
  const classificationReason = liveClassificationReason(email, threatType);

  const priorityLine = threatType === 'legitimate' && email.importance_rank
    ? `<div class="score-row"><span style="font-size:11px;color:#6c7086;min-width:90px">Priority</span><span style="color:${email.importance_color};font-weight:700">P${email.importance_rank} / 5</span></div>`
    : '';

  const eventsLine = email.events.length
    ? `<div style="margin-top:8px;color:#cdd6f4">🗓️ ${escapeHtml(email.events[0].title)}${email.events[0].when ? ` · ${escapeHtml(email.events[0].when)}` : ''}</div>`
    : '';

  const msg = document.createElement('div');
  msg.className = 'chat-msg msg-bot';
  msg.innerHTML = `
    📧 <strong>Local analysis complete</strong><br><br>
    <span class="threat-chip ${chipClass}">● ${chipLabel}</span><br><br>
    <div class="score-row">
      <span style="font-size:11px;color:#6c7086;min-width:90px">Severity</span>
      <div class="score-track"><div class="score-fill" style="width:${Math.min(email.severity_score * 10, 100)}%;background:${sevColor}"></div></div>
      <span style="font-size:11px;color:${sevColor};min-width:34px;text-align:right">${email.severity_score.toFixed(2)}</span>
    </div>
    <div class="score-row">
      <span style="font-size:11px;color:#6c7086;min-width:90px">Spam prob.</span>
      <div class="score-track"><div class="score-fill" style="width:${Math.min(email.spam_probability * 100, 100)}%;background:#fab387"></div></div>
      <span style="font-size:11px;color:#fab387;min-width:34px;text-align:right">${email.spam_probability.toFixed(2)}</span>
    </div>
    ${priorityLine}
    <br>${escapeHtml(classificationReason)}
    <div style="margin-top:8px;color:#cdd6f4">${escapeHtml(email.summary)}</div>
    ${eventsLine}
    <div class="quick-btns">
      <button class="quick-btn" onclick="sendQuick('Explain why this email is spam or safe')">Explain</button>
      <button class="quick-btn" onclick="sendQuick('Summarize current email')">Summarize</button>
      <button class="quick-btn" onclick="sendQuick('What events are in this email?')">Events</button>
    </div>
    <span class="msg-time">${new Date().toLocaleTimeString('en', {hour:'2-digit', minute:'2-digit'})}</span>
  `;
  appendMsg(msg);
}

function openEmailById(emailId) {
  const email = state.emails.find((item) => item.id === emailId);
  if (!email) return;
  state.currentEmail = email;
  email.unread = false;
  renderList();
  renderEmailContent(email);
  renderAutoAnalysis(email);
}

function clearTyping() {
  const typing = document.getElementById('typing');
  if (typing) typing.remove();
}

function appendMsg(el) {
  const container = document.getElementById('chat-messages');
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

function timeStampHtml() {
  return `<span class="msg-time">${new Date().toLocaleTimeString('en', {hour:'2-digit', minute:'2-digit'})}</span>`;
}

function addMsg(text, isUser = false) {
  const div = document.createElement('div');
  div.className = `chat-msg ${isUser ? 'msg-user' : 'msg-bot'}`;
  div.innerHTML = `${text}${timeStampHtml()}`;
  appendMsg(div);
}

function showTyping() {
  clearTyping();
  const div = document.createElement('div');
  div.className = 'typing-indicator';
  div.id = 'typing';
  div.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  appendMsg(div);
}

function updateChatHeader() {
  const sub = document.querySelector('.chat-title-block .chat-sub');
  if (!sub) return;
  sub.textContent = state.lmStudioAvailable
    ? `LM Studio connected (${state.lmStudioModel}) · streaming enabled`
    : 'Local analysis mode · LM Studio optional';
}

function localAssistantReply(question) {
  const lower = question.toLowerCase();
  const email = state.currentEmail;
  if (/\b(hey|hi|hello)\b/.test(lower)) {
    return `Hello. I can analyze the selected email, explain the spam decision, summarize it, or list any extracted events.`;
  }
  if (/(\bhow are you\b|comment vas|ça va|ca va)/.test(lower)) {
    return `I'm doing well and ready to help.`;
  }
  if (/(\bthank(s| you)?\b|merci)/.test(lower)) {
    return `You're welcome.`;
  }
  if (!email) {
    return `Select an email if you want mailbox-specific analysis. I can also handle simple general questions.`;
  }

  if (lower.includes('summar')) {
    return `<strong>Summary:</strong> ${escapeHtml(email.summary)}`;
  }
  if (lower.includes('event')) {
    if (!email.events.length) {
      return `No clear event was extracted from this email.`;
    }
    return `<strong>Detected event:</strong><br>${email.events.map((event) => `${escapeHtml(event.title)} · ${escapeHtml(event.when)}<br>${escapeHtml(event.source)}`).join('<br><br>')}`;
  }
  if (lower.includes('why') || lower.includes('explain') || lower.includes('spam') || lower.includes('safe')) {
    return `<strong>Why this classification:</strong> ${escapeHtml(liveClassificationReason(email, getThreatView(email)))}<br><br>${escapeHtml(email.importance_reason)}`;
  }
  if (lower.includes('stat') || lower.includes('count')) {
    return `<strong>Demo stats:</strong><br>Total emails: ${state.stats.total_emails}<br>Held-out test emails: ${state.stats.held_out_email_count}<br>Generated demo emails: ${state.stats.generated_email_count}<br>Spam: ${state.stats.spam_count}<br>Phishing: ${state.stats.phishing_count}<br>High priority: ${state.stats.high_priority_count}<br>Events: ${state.stats.event_count}`;
  }
  return `I can summarize the selected email, explain the classification, and list detected events.`;
}

function createStreamingBotMessage() {
  clearTyping();
  const div = document.createElement('div');
  div.className = 'chat-msg msg-bot';
  div.innerHTML = `<div style="opacity:.72">Thinking...</div>${timeStampHtml()}`;
  appendMsg(div);
  return div;
}

function updateStreamingBotMessage(el, text) {
  el.innerHTML = `${renderMarkdownLite(text || '...')}${timeStampHtml()}`;
  const container = document.getElementById('chat-messages');
  container.scrollTop = container.scrollHeight;
}

async function streamAssistantReply(question) {
  state.assistantRequestInFlight = true;
  const bubble = createStreamingBotMessage();
  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        question,
        email_id: state.currentEmail ? state.currentEmail.id : null,
        history: state.chatHistory.slice(-4),
      }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let rawBuffer = '';
    let assistantText = '';

    while (true) {
      const {value, done} = await reader.read();
      rawBuffer += decoder.decode(value || new Uint8Array(), {stream: !done});

      let boundary = rawBuffer.indexOf('\n\n');
      while (boundary !== -1) {
        const eventBlock = rawBuffer.slice(0, boundary);
        rawBuffer = rawBuffer.slice(boundary + 2);

        const dataLines = eventBlock
          .split('\n')
          .map((line) => line.trim())
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim());

        for (const line of dataLines) {
          if (!line) continue;
          const event = JSON.parse(line);
          if (event.error) {
            throw new Error(event.error);
          }
          if (event.delta) {
            assistantText += event.delta;
            updateStreamingBotMessage(bubble, assistantText);
          }
        }

        boundary = rawBuffer.indexOf('\n\n');
      }

      if (done) {
        break;
      }
    }

    assistantText = assistantText.trim();
    if (!assistantText) {
      throw new Error('Empty response');
    }
    updateStreamingBotMessage(bubble, assistantText);
    return assistantText;
  } finally {
    state.assistantRequestInFlight = false;
  }
}

async function sendChat() {
  if (!state.lmStudioAvailable || Date.now() - state.assistantStatusCheckedAt > 60000) {
    await refreshAssistantStatus(true);
  }
  const input = document.getElementById('chat-input');
  const question = input.value.trim();
  if (!question) return;
  input.value = '';
  input.style.height = 'auto';
  addMsg(escapeHtml(question), true);
  state.chatHistory.push({role: 'user', content: question});
  showTyping();

  try {
    if (!state.lmStudioAvailable) {
      clearTyping();
      const fallback = localAssistantReply(question);
      state.chatHistory.push({role: 'assistant', content: fallback.replace(/<[^>]+>/g, ' ')});
      addMsg(fallback, false);
      return;
    }

    clearTyping();
    const replyText = await streamAssistantReply(question);
    state.chatHistory.push({role: 'assistant', content: replyText});
  } catch (error) {
    clearTyping();
    const fallback = localAssistantReply(question);
    state.chatHistory.push({role: 'assistant', content: fallback.replace(/<[^>]+>/g, ' ')});
    addMsg(fallback, false);
  }
}

function sendQuick(text) {
  document.getElementById('chat-input').value = text;
  sendChat();
}

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendChat();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}

function setThresholdUi(value) {
  document.getElementById('threshold-slider').value = value.toFixed(2);
  document.getElementById('threshold-value').textContent = value.toFixed(2);
  if (state.emails.length) {
    const spamLike = state.emails.filter((email) => email.spam_probability >= value).length;
    document.getElementById('threshold-note').textContent = `${spamLike} / ${state.emails.length} demo emails are currently above this threshold.`;
  }
}

function setNav(element, filter) {
  document.querySelectorAll('.nav-item').forEach((node) => node.classList.remove('active'));
  element.classList.add('active');
  state.currentFilter = filter;
  resetListRenderLimit();
  renderList();
}

function focusChat() {
  openChat();
  document.getElementById('chat-input').focus();
}

function openCompose() {
  document.getElementById('compose-modal').classList.add('open');
  setTimeout(() => document.getElementById('compose-to').focus(), 50);
}

function closeCompose() {
  document.getElementById('compose-modal').classList.remove('open');
}

window.setNav = setNav;
window.focusChat = focusChat;
window.openCompose = openCompose;
window.closeCompose = closeCompose;
window.sendChat = sendChat;
window.sendQuick = sendQuick;
window.handleChatKey = handleChatKey;
window.autoResize = autoResize;
window.loadEmails = loadEmails;
window.toggleChat = toggleChat;
window.openChat = openChat;
window.closeChat = closeChat;
window.toggleSettings = toggleSettings;
window.closeSettings = closeSettings;
window.toggleProfileMenu = toggleProfileMenu;
window.closeAllOverlays = closeAllOverlays;
window.changeCalendarMonth = changeCalendarMonth;
window.goToCalendarToday = goToCalendarToday;
window.openEmailFromCalendar = openEmailFromCalendar;
window.selectCalendarDate = selectCalendarDate;
