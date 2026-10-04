// Screenshots and an axe pass of the journey from a photo to an insight, on
// sample answers of the API (no model, no database): the scene, a scan running
// and finished, the choice of focus, the insight, its why-sheet and what «تمّ»
// earns. At 375 and 1440 px, in both themes. The verse and the hadith below are
// bracketed stand-ins, never real scripture; the sample is not live analysis.
//
//   pnpm --filter @tabsira/web exec node scripts/journey-shots.mjs <base-url> <fake-api-origin> [--out=dir]
//
// The web app must have been started with NEXT_PUBLIC_API_URL=<fake-api-origin>
// and API_INTERNAL_URL pointing at a real API (the consent check of the first paint).

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { mockApi, recordedConsentId } from './lib/api-mock.mjs';
import { emulate, visit, withPage } from './lib/chrome.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const PHOTO = readFileSync(path.join(HERE, '../public/scene/rain-olive.jpg'));
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

const SCAN = '110000000000000001';
const INSIGHT = '110000000000000002';
const SOURCE_TEXT = (label) => `[${label} يأتي من المصدر المعتمد]`;

const scan = (extra = {}) => ({
  id: SCAN,
  status: 'done',
  outcome: 'insights',
  error_code: null,
  run: 1,
  engine: 'pipeline',
  engine_label: null,
  source: 'upload',
  sensitive: false,
  image: { available: true, width: 768, height: 1344, url: `/scans/${SCAN}/image` },
  description: 'قطرات ماء على أوراق نبتة صغيرة',
  entities: [
    {
      id: 'e1',
      label_arabic: 'ورقة',
      bbox: { x: 0.1, y: 0.45, width: 0.35, height: 0.14 },
      origin: 'detector',
      status: 'observed',
    },
    {
      id: 'e2',
      label_arabic: 'ساق',
      bbox: { x: 0.42, y: 0.58, width: 0.16, height: 0.2 },
      origin: 'vlm',
      status: 'inferred',
    },
  ],
  clarification_question: null,
  insights: [
    {
      id: INSIGHT,
      title: 'الحياة في قطرة',
      glimpse: 'كيف تُحيا الأرض بعد موتها',
      anchor: { x: 0.06, y: 0.525, width: 0.36, height: 0.06 },
      relation: 'direct',
      relation_label: 'صلة مباشرة',
      completed: false,
    },
    {
      id: '110000000000000003',
      title: 'الغرس الذي يتعدّاك',
      glimpse: 'نفعٌ يبقى لمن يأتي بعدك',
      anchor: { x: 0.4, y: 0.64, width: 0.2, height: 0.12 },
      relation: 'close_conceptual',
      relation_label: 'صلة مفهومية',
      completed: false,
    },
  ],
  awaiting_verification: 0,
  events_url: `/scans/${SCAN}/events`,
  created_at: '2026-10-04T08:00:00Z',
  finished_at: '2026-10-04T08:00:09Z',
  disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
  ...extra,
});

const insight = (extra = {}) => ({
  id: INSIGHT,
  scan_id: SCAN,
  origin: 'scan',
  engine: 'pipeline',
  label: null,
  title: 'الحياة في قطرة',
  glimpse: 'كيف تُحيا الأرض بعد موتها',
  anchor: { x: 0.06, y: 0.525, width: 0.36, height: 0.06 },
  relation: 'direct',
  relation_label: 'صلة مباشرة',
  quran: {
    tag: 'القرآن',
    verse: {
      surah: 30,
      ayah: 50,
      surah_name: 'سورة [اسم]',
      text: SOURCE_TEXT('نص الآية'),
      sha256: 'a'.repeat(64),
      page: 1,
      juz: 1,
      source: {
        name: 'quranpedia.net',
        url: 'https://quranpedia.net',
        mushaf_id: 2,
        mushaf_name: 'مصحف',
        quranpedia_ayah_id: 1,
        version: 'dump:1',
        dump_version: '1',
        last_sync_at: null,
      },
      links: { quranpedia: 'https://quranpedia.net/' },
      status: 'verified_cached',
    },
    why: {
      relation: 'direct',
      relation_label: 'صلة مباشرة',
      matched_on: 'أثر المطر في الأرض والنبات',
    },
  },
  hadith: {
    tag: 'السنة',
    hadith: {
      collection: {
        slug: 'bukhari',
        name_ar: '[الكتاب]',
        source_dataset: 'd',
        source_url: 'https://example.org',
        licence: 'Unlicense',
        version: '1',
      },
      number: '1032',
      arabic_number: null,
      chapter: null,
      text: `${SOURCE_TEXT('سند الحديث')} قال النبي: ${SOURCE_TEXT('كلام النبي')} ${SOURCE_TEXT('ختام')}`,
      sha256: 'b'.repeat(64),
      spans: [],
      informational_grades: null,
      ruling: {
        ruling_text: '[حكم الدرر]',
        scholar: '[المحدّث]',
        source_book: '[الكتاب]',
        page: '[الصفحة]',
        dorar_url: 'https://dorar.net/',
        classification: 'صحيح',
        recorded_at: '2026-10-01T08:00:00Z',
      },
      eligible: true,
      links: { dorar_verification: 'https://dorar.net/hadith/search' },
      status: 'local_corpus',
    },
    why: { relation: 'action_based', relation_label: 'صلة بالفعل', matched_on: 'رؤية المطر' },
  },
  hadith_status: 'shown',
  notice: null,
  pair_complete: true,
  explanation_tag: 'شرح تبصرة',
  explanation: [
    {
      section: 'seen',
      label: 'ما ظهر',
      text: 'قطرات مطر على أوراق نبتة زيتون صغيرة، وتربة رطبة حولها.',
    },
    {
      section: 'value',
      label: 'القيمة',
      text: 'الماء سبب جعله الله للحياة، والمطر نعمة تُرى آثارها في الأرض والنبات.',
    },
    {
      section: 'quran',
      label: 'ماذا تضيف الآية',
      text: 'تدعو الآية إلى النظر في آثار الرحمة: أرض هامدة تحيا بالمطر.',
    },
    {
      section: 'sunnah',
      label: 'ماذا يضيف الحديث',
      text: 'يعلّم الحديث ما يقوله المسلم حين يرى المطر.',
    },
    {
      section: 'life',
      label: 'كيف يتصل بالحياة',
      text: 'حين ترى المطر بعد اليوم، تذكّر أثر الرحمة في الأرض.',
    },
  ],
  why: {
    visible_clues: ['قطرات ماء على الأوراق', 'تربة رطبة'],
    concept: 'الإحياء بالماء',
    limits: ['الصورة الواحدة لا تثبت أن هذه الأرض كانت هامدة ثم أُحييت.'],
    personalised_because: null,
  },
  small_step: {
    text: 'احفظ الدعاء الوارد في الحديث لتقوله حين ترى المطر.',
    kind: 'text_grounded',
    label: 'من السنة',
  },
  learning_unit: null,
  action: { state: null, at: null, means: null },
  chat: { enabled: true, used: 1, limit: 3, remaining: 2, messages: [] },
  image: { sensitive: false, url: `/scans/${SCAN}/image` },
  completed_at: null,
  place_id: null,
  created_at: '2026-10-04T08:00:10Z',
  disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
  ...extra,
});

const completion = {
  insight_id: INSIGHT,
  completed_at: '2026-10-04T08:05:00Z',
  first_time: true,
  place: { id: '110000000000000009', region_id: 'T01', name: 'واحة الغيث', created: true },
  treasure_prepared: true,
  badges_earned: ['first-look'],
  options: [
    { id: 'open_world', label: 'افتح عالمي' },
    { id: 'new_scan', label: 'صوّر مشهدًا آخر' },
    { id: 'share', label: 'شارك البصيرة' },
  ],
  suggest_account: 'هل تحفظ ما تعلّمته لنواصل من هنا؟',
  disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
};

const progress = {
  timezone: 'UTC',
  rank: { id: 'nazir', title: 'ناظر', hint: 'بدأت تنظر.', looks: 1, next: null, progress: 0 },
  streak: { current: 1, best: 1, last_day: '2026-10-04', days: [] },
  daily_quest: {
    title: 'بصيرة اليوم',
    day: '2026-10-04',
    steps: [
      { id: 'look', label: 'انظر في مشهد واحد اليوم', done: true },
      { id: 'complete', label: 'أتمّ بصيرة واحدة اليوم', done: true },
    ],
    done: true,
    days_done: 1,
  },
  sky: { count: 0, stars: [] },
  badges: [
    {
      id: 'first-look',
      title: 'أول نظرة',
      description: 'أكملت أول مشهد عبر تبصرة.',
      earned: true,
      earned_at: '2026-10-04T08:05:00Z',
    },
  ],
  counts: { looks: 1, completed: 1, actions_done: 0, places: 1, treasures: 0, questions: 0 },
  disclaimer:
    'هذه علامات على التمرين والمواظبة لا على الإيمان ولا على القبول؛ تُحتسب من أفعالك المسجلة فقط.',
};

const tutorial = {
  scene: 'rain',
  version: '1.0',
  title: 'مطر ينزل على نبتة زيتون صغيرة',
  label: 'مثال موثّق مُعدّ',
  status: 'prepared',
  image: {
    path: '/scene/rain-olive.jpg',
    width: 768,
    height: 1344,
    alt: 'نبتة زيتون صغيرة تتلقى قطرات المطر',
  },
  insights: [
    {
      slug: 'drop',
      title: 'الحياة في قطرة',
      glimpse: 'كيف تُحيا الأرض بعد موتها',
      anchor: { x: 0.06, y: 0.525, width: 0.36, height: 0.06 },
    },
    {
      slug: 'planting',
      title: 'الغرس الذي يتعدّاك',
      glimpse: 'نفعٌ يبقى لمن يأتي بعدك',
      anchor: { x: 0.4, y: 0.64, width: 0.2, height: 0.12 },
    },
  ],
  disclosure: 'x',
};

const sse = (events) =>
  events
    .map(
      ([id, event, data]) => `id: ${id}\r\nevent: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`
    )
    .join('');

function journey(shot) {
  return (method, pathname) => {
    if (pathname === '/tutorial/rain') return { status: 200, body: tutorial };
    if (pathname === `/scans/${SCAN}/image`) return { raw: PHOTO, contentType: 'image/jpeg' };
    if (pathname === `/scans/${SCAN}/events`) {
      return {
        raw: sse([
          [1, 'queued', { run: 1 }],
          [2, 'stage', { run: 1, stage: 'understanding', state: 'done' }],
          [3, 'stage', { run: 1, stage: 'searching', state: 'started' }],
        ]),
        contentType: 'text/event-stream',
      };
    }
    if (pathname === `/scans/${SCAN}`) {
      return {
        status: 200,
        body: shot.running
          ? scan({ status: 'running', outcome: null, insights: [], finished_at: null })
          : scan(),
      };
    }
    if (pathname === `/insights/${INSIGHT}`) return { status: 200, body: insight() };
    if (pathname === `/insights/${INSIGHT}/complete`) return { status: 200, body: completion };
    if (pathname === '/me/progress') return { status: 200, body: progress };
    return undefined;
  };
}

const SHOTS = [
  { name: 'scene', path: '/' },
  { name: 'scan-running', path: `/scan/${SCAN}`, running: true },
  { name: 'scan-ready', path: `/scan/${SCAN}` },
  { name: 'scan-focus', path: `/scan/${SCAN}`, click: 'ما الذي لفت نظرك؟' },
  { name: 'insight', path: `/insight/${INSIGHT}`, full: true },
  { name: 'insight-why', path: `/insight/${INSIGHT}`, click: 'لماذا ظهر هذا؟' },
  { name: 'insight-done', path: `/insight/${INSIGHT}`, click: 'تمّ', full: true, wait: 2800 },
];

async function clickByText(send, text) {
  await send('Runtime.evaluate', {
    expression: `(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim().startsWith(${JSON.stringify(text)})); if (b) b.click(); return !!b; })()`,
    returnByValue: true,
  });
}

async function main() {
  const args = process.argv.slice(2);
  const out =
    args.find((a) => a.startsWith('--out='))?.slice(6) ??
    path.resolve(HERE, '../../../docs/screenshots');
  const [base, fakeApi] = args.filter((a) => !a.startsWith('--'));
  mkdirSync(out, { recursive: true });
  const siteOrigin = new URL(base).origin;
  const consentId = await recordedConsentId();
  const state = { value: 'guest' };
  const shot = { running: false };
  let failures = 0;

  await withPage(async (page) => {
    const { send } = page;
    await send('Network.enable');
    await mockApi(page, { apiOrigin: fakeApi, siteOrigin, state, extra: journey(shot) });
    for (const item of SHOTS) {
      shot.running = item.running === true;
      for (const theme of ['dark', 'light']) {
        for (const width of [375, 1440]) {
          const height = width < 768 ? 812 : 900;
          await send('Network.clearBrowserCookies');
          await send('Network.setCookie', {
            name: 'tabsira_consent',
            value: consentId,
            url: siteOrigin,
            path: '/',
          });
          await emulate(send, { width, height, theme });
          await visit(page, new URL(item.path, base).href, 3000);
          if (item.click) {
            await clickByText(send, item.click);
            await sleep(item.wait ?? 1200);
          }
          await send('Runtime.evaluate', { expression: AXE });
          const { result } = await send('Runtime.evaluate', {
            expression: `axe.run(document, { runOnly: { type: 'tag', values: ${JSON.stringify(TAGS)} } }).then((r) => JSON.stringify(r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(' ')).slice(0, 3) }))))`,
            awaitPromise: true,
            returnByValue: true,
          });
          const blocking = JSON.parse(result.value).filter((v) =>
            ['serious', 'critical'].includes(v.impact)
          );
          failures += blocking.length;
          console.log(
            `${blocking.length === 0 ? 'ok  ' : 'FAIL'} ${item.name} ${width}px ${theme}`
          );
          for (const v of blocking) console.log(`     ${v.impact} ${v.id} ${v.nodes.join(' | ')}`);
          let shotHeight = height;
          if (item.full) {
            await send('Runtime.evaluate', {
              expression: `document.documentElement.style.setProperty('--app-height', '${height}px')`,
            });
            const metrics = await send('Page.getLayoutMetrics');
            shotHeight = Math.min(6000, Math.ceil(metrics.cssContentSize.height));
            await emulate(send, { width, height: shotHeight, theme });
            await sleep(600);
          }
          const capture = await send('Page.captureScreenshot', {
            format: 'jpeg',
            quality: 82,
            clip: { x: 0, y: 0, width, height: shotHeight, scale: 1 },
          });
          writeFileSync(
            path.join(out, `journey-${item.name}-${width}-${theme}.jpg`),
            Buffer.from(capture.data, 'base64')
          );
        }
      }
    }
  });
  if (failures > 0) process.exitCode = 1;
}

await main();
