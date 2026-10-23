// Links to other maps from a building's position in the local frame. The conversion is web/sweref.js's (SWEREF 99
// 18 00, EPSG:3011, to WGS84), shared with the walks.
import { localToLatLon } from './sweref.js';

// Google Maps for a building (Maps URLs, no key): https://developers.google.com/maps/documentation/urls
// With the card's address it searches "<address>, Stockholm", so Google opens its own place for the street number
// (its name, photos and directions) instead of a bare dropped pin; without one, the building's position.
export function googleMapsUrl(x, z, origin, address = '') {
  if (address) return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${address}, Stockholm`)}`;
  const [lat, lon] = localToLatLon(x, z, origin);
  return `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lon.toFixed(6)}`;
}
