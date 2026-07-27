/**
 * UsageExamples.js — how to place AdBanner in your React Native screens.
 * Illustrative only — adapt to your own components/navigation.
 */
import React from 'react';
import { ScrollView, FlatList, View } from 'react-native';
import AdBanner from './AdBanner';

/* ─────────────────────────────────────────────────────────────
 * 1) HOME SCREEN — Top, Middle, Bottom banners
 * ───────────────────────────────────────────────────────────── */
export function HomeScreen() {
  return (
    <ScrollView>
      <AdBanner position="home_top" />

      {/* ...your top home content... */}

      <AdBanner position="home_middle" />

      {/* ...more home content... */}

      <AdBanner position="home_bottom" />
    </ScrollView>
  );
}

/* ─────────────────────────────────────────────────────────────
 * 2) BETWEEN ePAPER CARDS — inject an ad every N cards
 * ───────────────────────────────────────────────────────────── */
export function EpaperList({ editions }) {
  const AD_EVERY = 4; // show an ad after every 4 edition cards

  // Build a mixed list of cards + ad markers.
  const rows = [];
  editions.forEach((ed, i) => {
    rows.push({ type: 'card', data: ed, key: `ed-${ed.date}-${ed.language}` });
    if ((i + 1) % AD_EVERY === 0) {
      rows.push({ type: 'ad', key: `ad-${i}` });
    }
  });

  return (
    <FlatList
      data={rows}
      keyExtractor={(item) => item.key}
      renderItem={({ item }) =>
        item.type === 'ad' ? (
          <AdBanner position="between_epaper_cards" height={90} />
        ) : (
          <EpaperCard edition={item.data} />
        )
      }
    />
  );
}

/* ─────────────────────────────────────────────────────────────
 * 3) ePAPER PDF / READER SCREEN — DO NOT show ads here.
 *    Requirement: no advertisements while the user is reading an
 *    ePaper PDF. So simply render NO <AdBanner> on this screen.
 * ───────────────────────────────────────────────────────────── */
export function EpaperReaderScreen({ pdfUrl }) {
  return (
    <View style={{ flex: 1 }}>
      {/* <PdfViewer source={{ uri: pdfUrl }} /> */}
      {/* Intentionally NO AdBanner while reading. */}
    </View>
  );
}

// Placeholder card component for the example above.
function EpaperCard() {
  return null;
}
