/**
 * AdBanner.js — advertisement renderer for React Native.
 * Supports Image, Video and Audio ads. Backward compatible: an ad with no
 * ad_type (legacy) is treated as an image.
 *
 * - Fetches the highest-priority active ad for a mobile position.
 * - Tracks an impression once shown, a click on tap / "Learn more".
 * - Image: banner (opens redirect in the device browser on tap).
 * - Video: inline player with thumbnail + play/pause (NO autoplay).
 * - Audio: compact player with play/pause, seek bar, duration, buffering.
 *
 * Usage:
 *   <AdBanner position="home_top" />
 *   <AdBanner position="between_epaper_cards" showPlaceholder={false} />
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Image,
  Text,
  TouchableOpacity,
  Linking,
  StyleSheet,
  ActivityIndicator,
  useWindowDimensions,
} from 'react-native';
import { fetchAds, trackImpression, clickUrl } from './adsApi';
import AdVideo from './AdVideo';
import AdAudio from './AdAudio';

export default function AdBanner({
  position,
  height = 110,
  showPlaceholder = true,
  style,
}) {
  const [ad, setAd] = useState(null);
  const [loading, setLoading] = useState(true);
  const { width } = useWindowDimensions();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchAds(position, 1).then((ads) => {
      if (!alive) return;
      const first = ads && ads[0] ? ads[0] : null;
      setAd(first);
      setLoading(false);
      if (first) trackImpression(first.id); // tracking identical for all types
    });
    return () => {
      alive = false;
    };
  }, [position]);

  const openTarget = useCallback(() => {
    if (ad) Linking.openURL(clickUrl(ad)).catch(() => {});
  }, [ad]);

  if (loading) {
    return (
      <View style={[styles.wrap, { height }, style]}>
        <ActivityIndicator size="small" color="#d9252a" />
      </View>
    );
  }

  const hasMedia = ad && (ad.media_url || ad.image_url);
  if (!hasMedia) {
    if (!showPlaceholder) return null;
    return (
      <View style={[styles.wrap, styles.placeholder, { height }, style]}>
        <Text style={styles.placeholderText}>Advertisement</Text>
      </View>
    );
  }

  // ── Video ──
  if (ad.ad_type === 'video' && ad.media_url) {
    return (
      <View style={[styles.mediaWrap, style]}>
        <AdVideo ad={ad} />
      </View>
    );
  }

  // ── Audio ──
  if (ad.ad_type === 'audio' && ad.media_url) {
    return (
      <View style={[styles.mediaWrap, style]}>
        <AdAudio ad={ad} />
      </View>
    );
  }

  // ── Image (default / legacy) ──
  const uri = ad.media_url || ad.image_url;
  const img = (
    <>
      <Image
        source={{ uri }}
        style={{ width: width - 24, height, borderRadius: 10 }}
        resizeMode="cover"
      />
      <View style={styles.tag}>
        <Text style={styles.tagText}>Ad</Text>
      </View>
    </>
  );

  // Redirect URL is optional — only clickable when present.
  if (ad.redirect_url) {
    return (
      <TouchableOpacity
        activeOpacity={0.85}
        onPress={openTarget}
        style={[styles.wrap, { height }, style]}
        accessibilityRole="imagebutton"
        accessibilityLabel={ad.title || 'Advertisement'}
      >
        {img}
      </TouchableOpacity>
    );
  }
  return <View style={[styles.wrap, { height }, style]}>{img}</View>;
}

const styles = StyleSheet.create({
  wrap: {
    marginVertical: 10,
    marginHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    overflow: 'hidden',
  },
  mediaWrap: { marginVertical: 10, marginHorizontal: 12 },
  placeholder: {
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: '#d8d2c8',
    backgroundColor: '#faf8f4',
  },
  placeholderText: {
    color: '#9a938a',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  tag: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
  },
  tagText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
});
