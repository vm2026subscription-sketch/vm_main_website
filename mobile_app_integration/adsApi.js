/**
 * adsApi.js — tiny client for the Vidyarthi Mitra Advertisement API.
 *
 * Same backend as the website — no separate mobile admin. All ads are managed
 * from the ePaper admin panel. This module only READS ads for the app.
 *
 * Copy this file into your React Native project (e.g. src/api/adsApi.js) and
 * set BASE_URL to your production domain.
 */

// TODO: point this at your live backend.
export const BASE_URL = 'https://vidyarthimitra.org';

/**
 * Fetch active ads for a mobile position, highest priority first.
 * Only returns ads where platform is "mobile" or "both" and today is within
 * the ad's start/end date window (the server enforces this).
 *
 * @param {string} position  home_top | home_middle | home_bottom | between_epaper_cards
 * @param {number} limit
 * @returns {Promise<Array>}
 */
export async function fetchAds(position, limit = 1) {
  const url =
    `${BASE_URL}/api/v1/ads?platform=mobile` +
    `&position=${encodeURIComponent(position)}&limit=${limit}`;
  try {
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    const data = await res.json();
    return data && data.ads ? data.ads : [];
  } catch (e) {
    return [];
  }
}

/** Fire when an ad becomes visible on screen. Fire-and-forget. */
export function trackImpression(adId) {
  fetch(`${BASE_URL}/api/v1/ads/${adId}/impression`, { method: 'POST' }).catch(
    () => {}
  );
}

/**
 * Absolute click-tracking URL. Opening this in the device browser increments
 * the click count server-side and then 302-redirects to the ad's target URL.
 */
export function clickUrl(ad) {
  const path = ad.click_url || `/api/v1/ads/${ad.id}/click`;
  return `${BASE_URL}${path}`;
}
