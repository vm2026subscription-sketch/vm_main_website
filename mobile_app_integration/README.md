# Advertisement integration — React Native mobile app

These files let the **React Native app** show ads that are managed from the
**existing website ePaper admin panel**. There is **no separate mobile admin** —
the same backend serves both website and app.

## Files
| File | Purpose |
|------|---------|
| `adsApi.js` | Tiny API client (fetch ads, track impression, build click URL). Set `BASE_URL`. |
| `AdBanner.js` | Drop-in `<AdBanner position="…" />`. Renders Image, Video or Audio automatically. |
| `AdVideo.js` | Inline video player (thumbnail + play/pause, no autoplay, buffering). |
| `AdAudio.js` | Compact audio player (play/pause, seek bar, duration, buffering). |
| `UsageExamples.js` | Where to place banners (Home, between ePaper cards, and the no-ads PDF reader). |

## Setup
1. Copy all `.js` files into your RN project (e.g. `src/ads/`).
2. Install media dependencies (only needed for Video/Audio ads):
   ```bash
   npm i react-native-video @react-native-community/slider
   npx pod-install        # iOS
   ```
3. In `adsApi.js`, set `BASE_URL` to your live backend, e.g.
   `https://vidyarthimitra.org`.
4. Use it anywhere — the component picks the right player from `ad.ad_type`:
   ```jsx
   import AdBanner from './ads/AdBanner';
   <AdBanner position="home_top" />
   ```

## Advertisement types
| `ad_type` | Rendered as | Fields used |
|-----------|-------------|-------------|
| `image` (default / legacy) | Banner image | `image_url` / `media_url` |
| `video` | Inline `AdVideo` — poster thumbnail + play/pause, **no autoplay** | `media_url`, `thumbnail`, `duration` |
| `audio` | Compact `AdAudio` — play/pause, seek bar, duration, buffering, **no autoplay** | `media_url`, `duration` |

Legacy image ads (no `ad_type`) keep working unchanged — they're treated as `image`.
Impressions and clicks are tracked identically for all three types.

## Supported mobile positions
- `home_top` — Home Top Banner
- `home_middle` — Home Middle Banner
- `home_bottom` — Home Bottom Banner
- `between_epaper_cards` — inside the ePaper cards list

## Rules baked in
- Only ads with **platform = Mobile App or Both** are returned (the API is
  called with `platform=mobile`).
- Only **active** ads whose **current date is within start/end** are returned,
  sorted by **priority** (highest first) — enforced server-side.
- **Do NOT render `<AdBanner>` on the ePaper PDF/reader screen** — that keeps
  ads out of the reading experience (see `EpaperReaderScreen` in the examples).
- Tapping a banner opens the **redirect URL in the device browser** (via the
  click-tracking endpoint, so clicks are counted).
- If no ad is available, a **placeholder** is shown (pass
  `showPlaceholder={false}` to render nothing instead).
- Impressions are tracked automatically when a banner is displayed.

## API used (read-only, no auth)
```
GET  /api/v1/ads?platform=mobile&position=home_top&limit=1
POST /api/v1/ads/:id/impression
GET  /api/v1/ads/:id/click        → 302 redirect to the ad's target URL
```
Each ad object now also returns: `ad_type` (image|video|audio), `media_url`,
`thumbnail` (video poster), and `duration` (seconds), alongside the existing
`image_url`, `redirect_url`, `click_url`.

## Performance notes
- **Lazy media**: video uses `preload=metadata`, audio `preload=none`; playback
  starts only on user tap (no autoplay).
- **Caching**: media is served from Cloudinary's CDN and cached by the OS
  networking / video layer. Add a caching library (e.g. `react-native-fast-image`
  for posters) if you want stronger image caching.
- Media is **format-validated and compressed on upload** (server-side), so the
  app receives optimized files.

Ads themselves are created/edited/deleted by staff at
`/epaper-admin/ads` on the website.
