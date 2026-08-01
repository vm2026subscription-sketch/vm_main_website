/**
 * AdAudio.js — compact audio advertisement player for React Native.
 *
 * - Play / Pause button (NO autoplay).
 * - Seek bar with current time / duration.
 * - Buffering indicator.
 * - Optional "Learn more" opens the redirect URL (with click tracking).
 *
 * Requires:
 *   react-native-video               →  npm i react-native-video
 *   @react-native-community/slider   →  npm i @react-native-community/slider
 */
import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Linking,
} from 'react-native';
import Video from 'react-native-video';
import Slider from '@react-native-community/slider';
import { clickUrl } from './adsApi';

function fmt(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

export default function AdAudio({ ad }) {
  const ref = useRef(null);
  const [paused, setPaused] = useState(true);
  const [buffering, setBuffering] = useState(false);
  const [duration, setDuration] = useState(ad.duration || 0);
  const [position, setPosition] = useState(0);
  const [seeking, setSeeking] = useState(false);

  return (
    <View style={styles.wrap}>
      <Video
        ref={ref}
        source={{ uri: ad.media_url }}
        paused={paused}
        audioOnly
        playInBackground={false}
        style={styles.hidden}
        onLoad={({ duration: d }) => setDuration(d || ad.duration || 0)}
        onProgress={({ currentTime }) => { if (!seeking) setPosition(currentTime); }}
        onBuffer={({ isBuffering }) => setBuffering(isBuffering)}
        onEnd={() => { setPaused(true); setPosition(0); }}
        onError={() => setBuffering(false)}
      />

      {!!ad.title && (
        <Text style={styles.title} numberOfLines={1}>{ad.title}</Text>
      )}

      <View style={styles.row}>
        <TouchableOpacity style={styles.btn} onPress={() => setPaused((p) => !p)}>
          {buffering ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.btnIcon}>{paused ? '▶' : '❚❚'}</Text>
          )}
        </TouchableOpacity>

        <Slider
          style={styles.slider}
          minimumValue={0}
          maximumValue={duration || 1}
          value={position}
          minimumTrackTintColor="#d9252a"
          maximumTrackTintColor="#e1dad0"
          thumbTintColor="#d9252a"
          onSlidingStart={() => setSeeking(true)}
          onValueChange={(v) => setPosition(v)}
          onSlidingComplete={(v) => {
            if (ref.current) ref.current.seek(v);
            setSeeking(false);
          }}
        />

        <Text style={styles.time}>{fmt(position)} / {fmt(duration)}</Text>
      </View>

      {ad.redirect_url ? (
        <TouchableOpacity onPress={() => Linking.openURL(clickUrl(ad)).catch(() => {})}>
          <Text style={styles.cta}>Learn more →</Text>
        </TouchableOpacity>
      ) : null}

      <View style={styles.tag}><Text style={styles.tagText}>Ad</Text></View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 1, borderColor: '#e1dad0', borderRadius: 10,
    padding: 12, backgroundColor: '#fff',
  },
  hidden: { height: 0, width: 0 },
  title: { fontSize: 13, fontWeight: '700', color: '#221f1f', marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center' },
  btn: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: '#d9252a',
    alignItems: 'center', justifyContent: 'center',
  },
  btnIcon: { color: '#fff', fontSize: 15, fontWeight: '700' },
  slider: { flex: 1, marginHorizontal: 8 },
  time: { fontSize: 11, color: '#6b645b', minWidth: 74, textAlign: 'right' },
  cta: { color: '#d9252a', fontSize: 12, fontWeight: '700', marginTop: 8 },
  tag: { position: 'absolute', top: 8, right: 10, backgroundColor: 'rgba(0,0,0,0.5)', paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 },
  tagText: { color: '#fff', fontSize: 9, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
});
