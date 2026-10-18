// Links to other maps from a building's position in the local frame. The conversion is web/sweref.js's (SWEREF 99
// 18 00, EPSG:3011, to WGS84), shared with the walks.
import { localToLatLon } from './sweref.js';

// Google Maps at the building's position (Maps URLs, no key): https://developers.google.com/maps/documentation/urls
export function googleMapsUrl(x, z, origin) {
  const [lat, lon] = localToLatLon(x, z, origin);
  return `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lon.toFixed(6)}`;
}
