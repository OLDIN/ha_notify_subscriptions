import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import puppeteer from 'puppeteer';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import * as mdi from '@mdi/js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CARD_PATH = resolve(__dirname, '../../custom_components/notify_subscriptions/frontend/notify-subscriptions-card.js');
const CARD_CODE = readFileSync(CARD_PATH, 'utf-8');

// The same data the integration sends for Vlad on the real instance
const DATA = {
  topics: [
    { id: 'air_raid', name: 'Повітряна тривога', icon: 'mdi:bell-ring' },
    { id: 'power_change', name: 'Світло зникло / зʼявилось', icon: 'mdi:transmission-tower' },
    { id: 'power_warning', name: 'Світло вимкнеться через 5 хв', icon: 'mdi:timer-alert-outline' },
  ],
  channels: [
    { id: 'mobile_app:phone', name: 'iPhone (Владислав)', kind: 'mobile_app', icon: 'mdi:cellphone' },
    { id: 'mobile_app:mac', name: 'MacBook Pro', kind: 'mobile_app', icon: 'mdi:laptop' },
  ],
  subscriptions: {
    air_raid: { mode: 'all', channels: [] },
    power_change: { mode: 'picked', channels: ['mobile_app:phone'] },
    power_warning: { mode: 'off', channels: [] },
  },
};

const clone = (value) => JSON.parse(JSON.stringify(value));

function fakeHass({ data = DATA, error } = {}) {
  const hass = {
    language: 'uk',
    locale: { language: 'uk' },
    callService: vi.fn(async () => {}),
    unsubscribed: false,
    push: undefined,
    connection: {
      subscribeMessage: vi.fn(async (callback) => {
        if (error) throw error;
        hass.push = callback;
        callback(clone(data));
        return () => {
          hass.unsubscribed = true;
        };
      }),
    },
  };
  return hass;
}

async function mount(config = {}, hassOptions) {
  const card = document.createElement('notify-subscriptions-card');
  card.setConfig(config);
  document.body.appendChild(card);
  const hass = fakeHass(hassOptions);
  card.hass = hass;
  await vi.waitFor(() => expect(hass.connection.subscribeMessage).toHaveBeenCalled());
  await new Promise((r) => setTimeout(r, 0));
  return { card, hass, root: card.shadowRoot };
}

const text = (el) => el.textContent.replace(/\s+/g, ' ').trim();

describe('notify-subscriptions-card', () => {
  beforeAll(() => {
    window.eval(CARD_CODE);
  });

  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('shows every topic with the devices the notification goes to', async () => {
    const { root } = await mount();
    const topics = root.querySelectorAll('.topic');
    expect(topics).toHaveLength(3);
    expect(text(topics[0].querySelector('.summary'))).toBe('Усі мої пристрої: iPhone (Владислав), MacBook Pro');
    expect(text(topics[1].querySelector('.summary'))).toBe('Вибрані: iPhone (Владислав)');
    expect(text(topics[2].querySelector('.summary'))).toBe('Вимкнено');
  });

  it('marks the active mode and the devices that get the topic', async () => {
    const { root } = await mount();
    const [air, power, warning] = root.querySelectorAll('.topic');
    expect(text(air.querySelector('.mode.active'))).toBe('Усі мої');
    expect(air.querySelectorAll('.device.on')).toHaveLength(2);
    expect(text(power.querySelector('.mode.active'))).toBe('Вибрані');
    expect([...power.querySelectorAll('.device.on')].map(text)).toEqual(['iPhone (Владислав)']);
    expect(warning.querySelectorAll('.device.on')).toHaveLength(0);
    // nothing to test while the topic is off
    expect(warning.querySelector('.test').disabled).toBe(true);
  });

  it('changes the subscription through the integration actions', async () => {
    const { root, hass } = await mount();
    root.querySelector('[data-topic="power_warning"][data-mode="all"]').click();
    root.querySelector('.topic[data-topic="power_change"] [data-channel="mobile_app:mac"]').click();
    expect(hass.callService).toHaveBeenNthCalledWith(1, 'notify_subscriptions', 'set_subscription', {
      topic: 'power_warning',
      mode: 'all',
    });
    expect(hass.callService).toHaveBeenNthCalledWith(2, 'notify_subscriptions', 'set_subscription', {
      topic: 'power_change',
      mode: 'toggle',
      channel: 'mobile_app:mac',
    });
  });

  it('re-renders when the integration pushes new data', async () => {
    const { root, hass } = await mount();
    const next = clone(DATA);
    next.subscriptions.power_warning = { mode: 'all', channels: [] };
    hass.push(next);
    const warning = root.querySelector('.topic[data-topic="power_warning"]');
    expect(text(warning.querySelector('.mode.active'))).toBe('Усі мої');
    expect(warning.querySelector('.test').disabled).toBe(false);
  });

  it('sends a test and confirms it', async () => {
    const { root, hass } = await mount();
    root.querySelector('.test[data-topic="air_raid"]').click();
    await vi.waitFor(() => expect(text(root.querySelector('.test[data-topic="air_raid"]'))).toBe('Тест надіслано ✓'));
    expect(hass.callService).toHaveBeenCalledWith('notify_subscriptions', 'test', { topic: 'air_raid' });
  });

  it('shows only the configured topics, in the configured order', async () => {
    const { root } = await mount({ title: 'Світло', icon: 'mdi:flash', topics: ['power_warning', 'power_change'] });
    expect(text(root.querySelector('.heading'))).toBe('Світло');
    expect([...root.querySelectorAll('.topic')].map((t) => t.dataset.topic)).toEqual(['power_warning', 'power_change']);
  });

  it('shows an unknown topic as disabled instead of failing', async () => {
    const { root } = await mount({ topics: ['nope'] });
    const topic = root.querySelector('.topic');
    expect(text(topic.querySelector('.name'))).toBe('Невідома тема: nope');
    expect([...topic.querySelectorAll('.mode')].every((b) => b.disabled)).toBe(true);
  });

  it('explains what to do when the user has no devices', async () => {
    const data = clone(DATA);
    data.channels = [];
    const { root } = await mount({}, { data });
    expect(text(root.querySelector('.note'))).toContain('Companion');
    expect([...root.querySelectorAll('.mode')].every((b) => b.disabled)).toBe(true);
  });

  it('shows a clear message when the integration is not set up', async () => {
    const { root } = await mount({}, { error: { code: 'not_loaded', message: 'x' } });
    await vi.waitFor(() => expect(text(root.querySelector('.note'))).toBe('Інтеграція Notify Subscriptions не налаштована.'));
  });

  it('escapes names', async () => {
    const data = clone(DATA);
    data.channels[0].name = '<img src=x onerror=alert(1)>';
    const { root } = await mount({}, { data });
    expect(root.querySelector('img')).toBeNull();
    expect(text(root.querySelector('.device'))).toBe('<img src=x onerror=alert(1)>');
  });

  it('speaks English to English users', async () => {
    const card = document.createElement('notify-subscriptions-card');
    card.setConfig({});
    document.body.appendChild(card);
    const hass = fakeHass();
    hass.locale = { language: 'en' };
    hass.language = 'en';
    card.hass = hass;
    await vi.waitFor(() => expect(card.shadowRoot.querySelector('.topic')).not.toBeNull());
    expect(text(card.shadowRoot.querySelector('.summary'))).toBe('All my devices: iPhone (Владислав), MacBook Pro');
  });

  it('unsubscribes when removed from the page', async () => {
    const { card, hass } = await mount();
    card.remove();
    await vi.waitFor(() => expect(hass.unsubscribed).toBe(true));
  });

  it('rejects a non-list topics option', () => {
    const card = document.createElement('notify-subscriptions-card');
    expect(() => card.setConfig({ topics: 'air_raid' })).toThrow('topics must be a list');
  });
});

// ------------------------------------------------------------------ image snapshots
// The card is rendered in headless Chromium with Home Assistant's dark theme variables and compared
// with reference PNGs in __snapshots__/. Inter is embedded so the pictures are the same on macOS,
// Linux and CI. Re-take after intentional UI changes: rm tests/js/__snapshots__/*.png && npm test

const SNAPSHOT_DIR = resolve(__dirname, '__snapshots__');
const FONTS_DIR = resolve(__dirname, 'fonts');
const fontFace = (file) =>
  `@font-face { font-family: "TestInter"; font-weight: 100 900; src: url(data:font/woff2;base64,${readFileSync(
    resolve(FONTS_DIR, file),
  ).toString('base64')}) format('woff2'); }`;

// ha-icon stub: draws the real Material Design icon (the same set the HA frontend uses)
const ICON_NAMES = ['mdi:alarm-light', 'mdi:flash', 'mdi:send', 'mdi:cellphone', 'mdi:laptop', 'mdi:bell', ...DATA.topics.map((t) => t.icon)];
const iconKey = (name) => 'mdi' + name.replace('mdi:', '').split('-').map((p) => p[0].toUpperCase() + p.slice(1)).join('');
const ICON_PATHS = Object.fromEntries(ICON_NAMES.map((name) => [name, mdi[iconKey(name)]]));
const HA_ICON_STUB = `const ICONS = ${JSON.stringify(ICON_PATHS)};
if (!customElements.get('ha-icon')) customElements.define('ha-icon', class extends HTMLElement {
  connectedCallback() {
    const path = ICONS[this.getAttribute('icon')] || '';
    this.style.cssText = 'display:inline-flex;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);flex:none';
    this.innerHTML = '<svg viewBox="0 0 24 24" width="100%" height="100%"><path fill="currentColor" d="' + path + '"/></svg>';
  }
});`;

const PAGE = (cards) => `<!doctype html><html><head><meta charset="utf-8"><style>
${fontFace('inter-latin-wght-normal.woff2')}
${fontFace('inter-cyrillic-wght-normal.woff2')}
html, body { margin: 0; background: #111111; }
body {
  --ha-font-family-body: TestInter; --primary-color: #03a9f4; --rgb-primary-color: 3, 169, 244;
  --text-primary-color: #ffffff; --primary-text-color: #e1e1e1; --secondary-text-color: #9b9b9b;
  --disabled-text-color: #6f6f6f; --card-background-color: #1c1c1c; --ha-card-border-color: #2c2c2c;
  --secondary-background-color: #282828; --divider-color: #3a3a3a; --green-color: #4caf50; --rgb-green-color: 76, 175, 80;
}
#root { display: grid; grid-template-columns: repeat(${cards.length}, 380px); gap: 24px; padding: 24px; width: max-content; }
</style></head><body><div id="root"></div>
<script>${HA_ICON_STUB}</script>
<script>${CARD_CODE}</script>
<script>
  const cards = ${JSON.stringify(cards)};
  for (const { config, data } of cards) {
    const card = document.createElement('notify-subscriptions-card');
    card.setConfig(config);
    document.getElementById('root').appendChild(card);
    card.hass = { language: 'uk', locale: { language: 'uk' }, callService: async () => {},
      connection: { subscribeMessage: async (cb) => { cb(data); return () => {}; } } };
  }
</script></body></html>`;

describe('notify-subscriptions-card snapshots', () => {
  let browser;

  beforeAll(async () => {
    try {
      browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--font-render-hinting=none'],
        defaultViewport: { width: 900, height: 900, deviceScaleFactor: 2 },
        ...(process.env.PUPPETEER_EXECUTABLE_PATH ? { executablePath: process.env.PUPPETEER_EXECUTABLE_PATH } : {}),
      });
    } catch (err) {
      console.warn('Chromium is not available, image snapshots are skipped:', err.message);
    }
    mkdirSync(SNAPSHOT_DIR, { recursive: true });
  });

  afterAll(async () => {
    await browser?.close();
  });

  // A fresh page per picture: setContent keeps the old window and its custom element registry
  async function shoot(cards) {
    const page = await browser.newPage();
    try {
      await page.setContent(PAGE(cards), { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForFunction(() => [...document.querySelectorAll('notify-subscriptions-card')].every((c) => c.shadowRoot.querySelector('.topic')));
      const root = await page.$('#root');
      return Buffer.from(await root.screenshot());
    } finally {
      await page.close();
    }
  }

  function compare(actual, name) {
    const path = resolve(SNAPSHOT_DIR, `${name}.png`);
    if (!existsSync(path)) {
      writeFileSync(path, actual);
      console.log(`Created snapshot ${name}.png`);
      return;
    }
    const expected = PNG.sync.read(readFileSync(path));
    const got = PNG.sync.read(actual);
    if (expected.width !== got.width || expected.height !== got.height) {
      writeFileSync(resolve(SNAPSHOT_DIR, `${name}-actual-diff.png`), actual);
      throw new Error(`${name}: size ${got.width}x${got.height} != ${expected.width}x${expected.height}`);
    }
    const diff = new PNG({ width: got.width, height: got.height });
    const changed = pixelmatch(expected.data, got.data, diff.data, got.width, got.height, { threshold: 0.2 });
    if (changed / (got.width * got.height) > 0.005) {
      writeFileSync(resolve(SNAPSHOT_DIR, `${name}-actual-diff.png`), actual);
      writeFileSync(resolve(SNAPSHOT_DIR, `${name}-diff.png`), PNG.sync.write(diff));
      throw new Error(`${name}: ${changed} pixels differ`);
    }
  }

  it('settings page: alarm and power sections', async (ctx) => {
    if (!browser) ctx.skip();
    const png = await shoot([
      { config: { title: 'Тривога', icon: 'mdi:alarm-light', topics: ['air_raid'] }, data: DATA },
      { config: { title: 'Світло', icon: 'mdi:flash', topics: ['power_change', 'power_warning'] }, data: DATA },
    ]);
    compare(png, 'settings-page');
  });

  it('user without devices', async (ctx) => {
    if (!browser) ctx.skip();
    const data = clone(DATA);
    data.channels = [];
    const png = await shoot([{ config: { title: 'Тривога', icon: 'mdi:alarm-light', topics: ['air_raid'] }, data }]);
    compare(png, 'no-devices');
  });
});
