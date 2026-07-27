/**
 * AdVideo.js — inline video advertisement for React Native.
 *
 * - Shows the poster thumbnail with a play button (NO autoplay).
 * - Tapping play starts playback and reveals native controls (play/pause/seek).
 * - Shows a buffering indicator while loading.
 * - Optional "Learn more" opens the redirect URL (with click tracking).
 *
 * Requires: react-native-video  →  npm i react-native-video
 */
import React, { useState } from 'react';
import {
  View,
  Image,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Linking,
  useWindowDimensions,
} from 'react-native';
import Video from 'react-native-video';
import { clickUrl } from './adsApi';

export default function AdVideo({ ad, height }) {
  const [paused, setPaused] = useState(true);
  const [started, setStarted] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const { width } = useWindowDimensions();
  const w = width - 24;
  const h = height || Math.round(w * 9 / 16); // 16:9 by default

  return (
    <View style={[styles.wrap, { width: w, height: h }]}>
      <Video
        source={{ uri: ad.media_url }}
        style={StyleSheet.absoluteFill}
        paused={paused}
        controls={started}          // native controls once the user starts it
        resizeMode="cover"
        repeat={false}
        playInBackground={false}
        poster={ad.thumbnail || undefined}
        posterResizeMode="cover"
        onBuffer={({ isBuffering }) => setBuffering(isBuffering)}
        onEnd={() => setPaused(true)}
        onError={() => setBuffering(false)}
      />

      {/* Poster + play button overlay (before playback begins) */}
      {!started && (
        <TouchableOpacity
          style={styles.overlay}
          activeOpacity={0.85}
          onPress={() => {
            setStarted(true);
            setPaused(false);
          }}
        >
          {ad.thumbnail ? (
            <Image source={{ uri: ad.thumbnail }} style={StyleSheet.absoluteFill} resizeMode="cover" />
          ) : null}
          <View style={styles.playBtn}>
            <Text style={styles.playIcon}>▶</Text>
          </View>
        </TouchableOpacity>
      )}

      {buffering && <ActivityIndicator style={styles.buffer} color="#fff" size="large" />}

      {ad.redirect_url ? (
        <TouchableOpacity style={styles.cta} onPress={() => Linking.openURL(clickUrl(ad)).catch(() => {})}>
          <Text style={styles.ctaText}>Learn more →</Text>
        </TouchableOpacity>
      ) : null}

      <View style={styles.tag}>
        <Text style={styles.tagText}>Ad</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderRadius: 10, overflow: 'hidden', backgroundColor: '#000' },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  playBtn: {
    width: 58, height: 58, borderRadius: 29,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center', justifyContent: 'center',
  },
  playIcon: { color: '#fff', fontSize: 22, marginLeft: 4 },
  buffer: { position: 'absolute', alignSelf: 'center', top: '45%' },
  cta: {
    position: 'absolute', left: 10, bottom: 10,
    backgroundColor: 'rgba(217,37,42,0.92)',
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6,
  },
  ctaText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  tag: {
    position: 'absolute', top: 8, right: 8,
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4,
  },
  tagText: { color: '#fff', fontSize: 9, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
});
