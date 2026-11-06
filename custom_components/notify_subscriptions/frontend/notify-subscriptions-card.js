/**
 * notify-subscriptions-card — every user manages their own notification subscriptions.
 *
 * Config (all optional):
 *   type: custom:notify-subscriptions-card
 *   title: Світло            # heading above the topics
 *   icon: mdi:flash          # heading icon
 *   topics: [power_change, power_warning]   # which topics and in which order (default: all)
 *
 * Data comes from the notify_subscriptions/subscribe WebSocket command (the caller's topics,
 * channels and subscriptions); buttons call notify_subscriptions.set_subscription / test.
 */

const STRINGS = {
  uk: {
    off: 'Вимк',
    all: 'Усі мої',
    picked: 'Вибрані',
    summaryOff: 'Вимкнено',
    summaryAll: 'Усі мої пристрої',
    summaryPicked: 'Вибрані',
    test: 'Надіслати тест',
    testSent: 'Тест надіслано',
    testFailed: 'Не вдалося надіслати',
    loading: 'Завантаження…',
    notLoaded: 'Інтеграція Notify Subscriptions не налаштована.',
    noChannels: 'У тебе ще немає пристроїв. Встанови застосунок Home Assistant (Companion) і увійди своїм акаунтом.',
    noTopics: 'Тем ще немає.',
    unknownTopic: 'Невідома тема',
  },
  en: {
    off: 'Off',
    all: 'All mine',
    picked: 'Picked',
    summaryOff: 'Off',
    summaryAll: 'All my devices',
    summaryPicked: 'Picked',
    test: 'Send test',
    testSent: 'Test sent',
    testFailed: 'Could not send',
    loading: 'Loading…',
    notLoaded: 'The Notify Subscriptions integration is not set up.',
    noChannels: 'You have no devices yet. Install the Home Assistant Companion app and sign in.',
    noTopics: 'No topics yet.',
    unknownTopic: 'Unknown topic',
  },
};

const MODES = ['off', 'all', 'picked'];

const escapeHtml = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const STYLE = `
  :host { display: block; }
  .wrap { display: flex; flex-direction: column; gap: 24px; font-family: var(--ha-font-family-body, Roboto, sans-serif); }
  .heading { display: flex; align-items: center; gap: 8px; color: var(--primary-text-color); font-size: 20px; line-height: 28px; padding: 0 4px; }
  .heading ha-icon { --mdc-icon-size: 20px; }
  .topic { display: flex; flex-direction: column; gap: 8px; }
  .head {
    display: grid; grid-template-columns: 40px 1fr; column-gap: 10px; align-items: center;
    min-height: 56px; box-sizing: border-box; padding: 8px 12px;
    background: var(--ha-card-background, var(--card-background-color, #1c1c1c));
    border: 1px solid var(--ha-card-border-color, var(--divider-color, #2c2c2c));
    border-radius: var(--ha-card-border-radius, 12px);
  }
  .badge { width: 40px; height: 40px; border-radius: 20px; display: flex; align-items: center; justify-content: center; }
  .badge.on { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.15); color: var(--primary-color, #03a9f4); }
  .badge.off { background: rgba(128, 128, 128, 0.15); color: var(--disabled-text-color, #9e9e9e); }
  .badge ha-icon { --mdc-icon-size: 22px; }
  .name { color: var(--primary-text-color); font-size: 15px; font-weight: 500; line-height: 20px; }
  .summary { color: var(--secondary-text-color); font-size: 12px; line-height: 16px; }
  .modes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .devices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .devices .device:only-child, .devices .device.wide { grid-column: 1 / -1; }
  button { font: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  button:disabled { cursor: default; opacity: 0.5; }
  .mode {
    height: 44px; border: none; border-radius: 22px; font-size: 14px; font-weight: 500;
    background: var(--secondary-background-color, #262626); color: var(--primary-text-color);
  }
  .mode.active { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
  .device {
    height: 44px; border-radius: 22px; padding: 0 14px; display: flex; align-items: center; gap: 8px;
    font-size: 14px; background: transparent; text-align: left; overflow: hidden;
    border: 1px solid var(--divider-color, #3a3a3a); color: var(--secondary-text-color);
  }
  .device span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .device ha-icon { --mdc-icon-size: 20px; color: var(--disabled-text-color, #9e9e9e); flex: none; }
  .device.on { background: rgba(var(--rgb-green-color, 76, 175, 80), 0.16); border-color: var(--green-color, #4caf50); color: var(--primary-text-color); }
  .device.on ha-icon { color: var(--green-color, #4caf50); }
  .test {
    align-self: flex-start; display: flex; align-items: center; gap: 6px; height: 40px; padding: 0 8px;
    border: none; background: transparent; color: var(--primary-color, #03a9f4); font-size: 14px;
  }
  .test ha-icon { --mdc-icon-size: 18px; }
  .note { color: var(--secondary-text-color); font-size: 14px; padding: 0 4px; }
`;

class NotifySubscriptionsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._data = undefined;
    this._error = undefined;
    this._unsubscribe = undefined;
    this._subscribing = false;
    this._testState = {};
    this.shadowRoot.addEventListener('click', (ev) => this._onClick(ev));
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    if (config.topics !== undefined && !Array.isArray(config.topics)) {
      throw new Error('topics must be a list of topic ids');
    }
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || (!this._unsubscribe && !this._subscribing && !this._error && this.isConnected)) {
      this._subscribe();
    }
    if (first) this._render();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass && !this._unsubscribe && !this._subscribing) this._subscribe();
  }

  disconnectedCallback() {
    this._dropSubscription();
  }

  getCardSize() {
    const topics = this._visibleTopics().length || 1;
    return 1 + topics * 4;
  }

  getGridOptions() {
    return { columns: 12, rows: 'auto', min_columns: 6 };
  }

  get _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || 'en').toLowerCase();
    return STRINGS[lang.startsWith('uk') ? 'uk' : 'en'];
  }

  async _subscribe() {
    if (!this._hass?.connection || this._subscribing) return;
    this._subscribing = true;
    try {
      this._unsubscribe = await this._hass.connection.subscribeMessage(
        (data) => {
          this._data = data;
          this._error = undefined;
          this._render();
        },
        { type: 'notify_subscriptions/subscribe' },
      );
    } catch (err) {
      this._error = err?.code === 'not_loaded' ? this._t.notLoaded : err?.message || String(err);
      this._render();
    } finally {
      this._subscribing = false;
    }
  }

  _dropSubscription() {
    if (this._unsubscribe) {
      const unsub = this._unsubscribe;
      this._unsubscribe = undefined;
      Promise.resolve(unsub()).catch(() => {});
    }
  }

  _visibleTopics() {
    if (!this._data) return [];
    const byId = new Map(this._data.topics.map((t) => [t.id, t]));
    if (!this._config.topics) return this._data.topics;
    return this._config.topics.map((id) => byId.get(id) || { id, name: `${this._t.unknownTopic}: ${id}`, missing: true });
  }

  _onClick(ev) {
    const button = ev.composedPath().find((el) => el instanceof HTMLElement && el.dataset && el.dataset.action);
    if (!button || button.disabled || !this._hass) return;
    const { action, topic, mode, channel } = button.dataset;
    if (action === 'mode') {
      this._call('set_subscription', { topic, mode });
    } else if (action === 'device') {
      this._call('set_subscription', { topic, mode: 'toggle', channel });
    } else if (action === 'test') {
      this._sendTest(topic);
    }
  }

  async _call(service, data) {
    try {
      await this._hass.callService('notify_subscriptions', service, data);
    } catch (err) {
      this._error = err?.message || String(err);
      this._render();
    }
  }

  async _sendTest(topic) {
    try {
      await this._hass.callService('notify_subscriptions', 'test', { topic });
      this._testState[topic] = 'sent';
    } catch (err) {
      this._testState[topic] = 'failed';
    }
    this._render();
    clearTimeout(this._testTimer);
    this._testTimer = setTimeout(() => {
      this._testState = {};
      this._render();
    }, 3000);
  }

  _summary(sub, channels) {
    const t = this._t;
    if (!sub || sub.mode === 'off') return t.summaryOff;
    const on = channels.filter((c) => sub.mode === 'all' || sub.channels.includes(c.id));
    if (!on.length) return t.summaryOff;
    const label = sub.mode === 'all' ? t.summaryAll : t.summaryPicked;
    return `${label}: ${on.map((c) => c.name).join(', ')}`;
  }

  _renderTopic(topic) {
    const t = this._t;
    const channels = this._data.channels;
    const sub = this._data.subscriptions[topic.id] || { mode: 'off', channels: [] };
    const noChannels = channels.length === 0;
    const active = sub.mode !== 'off' && !topic.missing && !noChannels;
    const id = escapeHtml(topic.id);
    const modes = MODES.map(
      (mode) =>
        `<button class="mode${sub.mode === mode ? ' active' : ''}" data-action="mode" data-topic="${id}" data-mode="${mode}"` +
        `${noChannels || topic.missing ? ' disabled' : ''}>${t[mode]}</button>`,
    ).join('');
    const devices = channels
      .map((c) => {
        const on = sub.mode === 'all' || (sub.mode === 'picked' && sub.channels.includes(c.id));
        return (
          `<button class="device${on ? ' on' : ''}" data-action="device" data-topic="${id}" data-channel="${escapeHtml(c.id)}"` +
          `${topic.missing ? ' disabled' : ''} title="${escapeHtml(c.name)}">` +
          `<ha-icon icon="${escapeHtml(c.icon)}"></ha-icon><span>${escapeHtml(c.name)}</span></button>`
        );
      })
      .join('');
    const testState = this._testState[topic.id];
    const testLabel = testState === 'sent' ? `${t.testSent} ✓` : testState === 'failed' ? t.testFailed : t.test;
    return `
      <div class="topic" data-topic="${id}">
        <div class="head">
          <div class="badge ${active ? 'on' : 'off'}"><ha-icon icon="${escapeHtml(topic.icon || 'mdi:bell')}"></ha-icon></div>
          <div>
            <div class="name">${escapeHtml(topic.name)}</div>
            <div class="summary">${escapeHtml(noChannels ? t.summaryOff : this._summary(sub, channels))}</div>
          </div>
        </div>
        <div class="modes">${modes}</div>
        ${noChannels ? `<div class="note">${t.noChannels}</div>` : `<div class="devices">${devices}</div>`}
        <button class="test" data-action="test" data-topic="${id}"${!active || noChannels ? ' disabled' : ''}>
          <ha-icon icon="mdi:send"></ha-icon><span>${escapeHtml(testLabel)}</span>
        </button>
      </div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const t = this._t;
    const heading = this._config.title
      ? `<div class="heading">${this._config.icon ? `<ha-icon icon="${escapeHtml(this._config.icon)}"></ha-icon>` : ''}<span>${escapeHtml(this._config.title)}</span></div>`
      : '';
    let body;
    if (this._error && !this._data) {
      body = `<div class="note">${escapeHtml(this._error)}</div>`;
    } else if (!this._data) {
      body = `<div class="note">${t.loading}</div>`;
    } else {
      const topics = this._visibleTopics();
      body = topics.length ? topics.map((topic) => this._renderTopic(topic)).join('') : `<div class="note">${t.noTopics}</div>`;
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><div class="wrap">${heading}${body}</div>`;
  }
}

if (!customElements.get('notify-subscriptions-card')) {
  customElements.define('notify-subscriptions-card', NotifySubscriptionsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'notify-subscriptions-card',
    name: 'Notify Subscriptions',
    description: 'Lets every user pick which notifications they get and on which devices.',
    preview: false,
  });
  console.info('%c NOTIFY-SUBSCRIPTIONS-CARD ', 'color:#fff;background:#03a9f4');
}
