import type { AtlasEntry, AtlasFeature, AtlasPlace, MapEntryOwner } from '@/atlas/types';
import { AUTHOR, HADITH_TEXT, QURAN_TEXT, sha256 } from './social';

/* Sample answers of the atlas API for unit tests; placeholders stand for scripture. */

export const PLACE = {
  geoname_id: 2464470,
  label: '[تونس]',
  admin_label: '[ولاية تونس]',
  country_iso2: 'TN',
  country_label: '[تونس البلد]',
};

export const FEATURE: AtlasFeature = {
  type: 'Feature',
  id: '7400000000000000001',
  geometry: { type: 'Point', coordinates: [10.1815, 36.8065] },
  properties: {
    id: '7400000000000000001',
    title: '[عنوان البصيرة]',
    glimpse: '[لمحة البصيرة]',
    author: AUTHOR,
    place: PLACE,
    cell_m: 1000,
    precision_label: '[موقع تقريبي ضمن نحو 1000 م]',
    published_on: '2026-10-04',
  },
};

export const SECOND_FEATURE: AtlasFeature = {
  ...FEATURE,
  id: '7400000000000000002',
  properties: {
    ...FEATURE.properties,
    id: '7400000000000000002',
    title: '[بصيرة ثانية]',
    place: {
      ...PLACE,
      geoname_id: 104515,
      label: '[مكة]',
      country_iso2: 'SA',
      country_label: '[السعودية]',
    },
  },
};

export const ENTRY: AtlasEntry = {
  id: FEATURE.id,
  title: '[عنوان البصيرة]',
  glimpse: '[لمحة البصيرة]',
  relation_type: 'direct',
  explanation: '[شرح تبصرة من الخادم]',
  step: '[خطوة صغيرة]',
  concepts: ['rain'],
  author: AUTHOR,
  location: {
    point: { type: 'Point', coordinates: [10.1815, 36.8065] },
    cell_m: 1000,
    precision_label: '[موقع تقريبي ضمن نحو 1000 م]',
    meaning: 'capture_point',
    meaning_label: '[موضع الالتقاط]',
  },
  place: PLACE,
  quran: [
    {
      surah: 30,
      ayah: 50,
      surah_name: '[اسم السورة]',
      text: QURAN_TEXT,
      sha256: sha256(QURAN_TEXT),
      source_url: 'https://quranpedia.net/',
      verified: true,
    },
  ],
  hadith: [
    {
      collection: 'bukhari',
      collection_name: '[اسم الكتاب]',
      number: '1032',
      text: HADITH_TEXT,
      sha256: sha256(HADITH_TEXT),
      classification: 'صحيح',
      verification_url: 'https://dorar.net/',
      verified: true,
    },
  ],
  post_id: '7345678901234567890',
  photo_url: null,
  published_on: '2026-10-04',
};

export const PLACE_PAGE: AtlasPlace = {
  place: PLACE,
  point: { type: 'Point', coordinates: [10.1657, 36.8189] },
  entries: [FEATURE],
  next_cursor: null,
};

export const OWNER_ENTRY: MapEntryOwner = {
  id: FEATURE.id,
  insight_id: '7000000000000000001',
  title: '[عنوان البصيرة]',
  status: 'draft',
  status_message: null,
  capture: {
    latitude: 36.806512,
    longitude: 10.181534,
    accuracy_m: 12,
    source: 'device_capture',
    captured_at: null,
    measured_at: '2026-10-04T08:00:00Z',
    confirmed_at: '2026-10-04T08:00:01Z',
  },
  public: {
    point: { type: 'Point', coordinates: [10.1815, 36.8065] },
    cell_m: 1000,
    precision_label: '[موقع تقريبي ضمن نحو 1000 م]',
    meaning: 'capture_point',
    meaning_label: '[موضع الالتقاط]',
    cell: {
      type: 'Polygon',
      coordinates: [
        [
          [10.17, 36.8],
          [10.19, 36.8],
          [10.19, 36.81],
          [10.17, 36.81],
          [10.17, 36.8],
        ],
      ],
    },
  },
  place: PLACE,
  photo: false,
  published_at: null,
  withdrawn_at: null,
  created_at: '2026-10-04T08:00:00Z',
};
