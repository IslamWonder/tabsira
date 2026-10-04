// Sample answers of the world and practice routes for the screenshots and the
// accessibility check. The regions are the real fixed map (data/world/
// regions-1.0.json); the places, titles and counts are examples, never shown
// as anyone's practice. Wording of ranks, badges and the disclaimer follows
// the API's own (apps/api/src/messages.py).

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REGIONS_FILE = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../data/world/regions-1.0.json'
);

const OPENED = { T01: '7001', T12: '7002', T15: '7003' };
const DOMAIN_TITLES = {
  T01: 'الغيث والإحياء',
  T12: 'النفع والغرس',
  T15: 'التفكر في الخلق',
};

function regions() {
  const { regions: list } = JSON.parse(readFileSync(REGIONS_FILE, 'utf8'));
  return list.map((region) => ({
    id: region.id,
    domain_id: region.domain_id,
    name: region.name,
    domain_title: DOMAIN_TITLES[region.id] ?? 'مجال في المسار',
    position: region.position,
    fog: OPENED[region.id] === undefined,
    place_id: OPENED[region.id] ?? null,
  }));
}

export function worldSample() {
  return {
    version: '1.0',
    path_version: 'tabsira-masar-1.0',
    regions: regions(),
    places: [
      {
        id: '7001',
        region_id: 'T01',
        name: 'واحة الغيث',
        created_at: '2026-10-01T08:00:00Z',
        last_visited_at: '2026-10-03T08:00:00Z',
        insights: [
          { id: '9001', title: 'المطر يحيي الأرض', completed_at: '2026-10-01T08:00:00Z' },
          { id: '9004', title: 'قطرة تصنع نبتة', completed_at: '2026-10-03T08:00:00Z' },
        ],
        treasure: null,
      },
      {
        id: '7002',
        region_id: 'T12',
        name: 'بستان النفع',
        created_at: '2026-10-02T08:00:00Z',
        last_visited_at: null,
        insights: [
          { id: '9002', title: 'غرسة ينتفع بها الناس', completed_at: '2026-10-02T08:00:00Z' },
        ],
        treasure: { id: '8001' },
      },
      {
        id: '7003',
        region_id: 'T15',
        name: 'مرصد التفكر',
        created_at: '2026-10-03T08:00:00Z',
        last_visited_at: null,
        insights: [{ id: '9003', title: 'نظرة في السماء', completed_at: '2026-10-03T08:00:00Z' }],
        treasure: null,
      },
    ],
    relations: [
      {
        place_a_id: '7001',
        place_b_id: '7002',
        reason: 'same_scene',
        reason_label: 'من المشهد نفسه',
        question: 'كيف ترتبطان؟',
        insight_ids: ['9001', '9002'],
      },
    ],
  };
}

export function progressSample() {
  const day = (offset, looked) => ({
    day: new Date(Date.UTC(2026, 9, 4 - offset)).toISOString().slice(0, 10),
    looked,
  });
  return {
    timezone: 'UTC',
    rank: {
      id: 'mutaammil',
      title: 'متأمّل',
      hint: 'ثلاثة مشاهد فأكثر.',
      looks: 5,
      next: { id: 'mustabsir', title: 'مستبصر', minimum: 10 },
      progress: 0.29,
    },
    streak: {
      current: 3,
      best: 5,
      last_day: '2026-10-04',
      days: [
        day(0, true),
        day(1, true),
        day(2, true),
        day(3, false),
        day(4, true),
        day(5, false),
        day(6, false),
      ],
    },
    daily_quest: {
      title: 'بصيرة اليوم',
      day: '2026-10-04',
      steps: [
        { id: 'look', label: 'انظر في مشهد واحد اليوم', done: true },
        { id: 'complete', label: 'أتمّ بصيرة واحدة اليوم', done: false },
      ],
      done: false,
      days_done: 2,
    },
    sky: {
      count: 5,
      stars: [
        { concept: 'مطر', count: 3, first_seen: '2026-10-01T08:00:00Z', x: 0.22, y: 0.3 },
        { concept: 'نبات', count: 2, first_seen: '2026-10-01T08:00:00Z', x: 0.5, y: 0.55 },
        { concept: 'سماء', count: 1, first_seen: '2026-10-03T08:00:00Z', x: 0.78, y: 0.28 },
        { concept: 'غرس', count: 1, first_seen: '2026-10-02T08:00:00Z', x: 0.35, y: 0.75 },
        { concept: 'ماء', count: 4, first_seen: '2026-10-01T08:00:00Z', x: 0.68, y: 0.72 },
      ],
    },
    badges: [
      ['first-look', 'أول نظرة', 'أكملت أول مشهد عبر تبصرة.', true],
      ['seven-looks', 'سبع نظرات', 'سبعة مشاهد اكتملت حتى آخر مرحلة.', false],
      ['first-place', 'أول بقعة', 'انقشع الضباب عن أول موضع في عالمك.', true],
      ['first-treasure', 'أول كنز', 'كشفت أول كنز مخبوء في عالمك.', false],
      ['streak-3', 'ثلاثة أيام', 'نظرت ثلاثة أيام متتالية.', true],
      ['streak-7', 'أسبوع من النظر', 'سبعة أيام متتالية من النظر.', false],
    ].map(([id, title, description, earned]) => ({
      id,
      title,
      description,
      earned,
      earned_at: earned ? '2026-10-03T08:00:00Z' : null,
    })),
    counts: { looks: 5, completed: 5, actions_done: 1, places: 3, treasures: 0, questions: 2 },
    disclaimer:
      'هذه علامات على التمرين والمواظبة لا على الإيمان ولا على القبول؛ تُحتسب من أفعالك المسجلة فقط.',
  };
}
