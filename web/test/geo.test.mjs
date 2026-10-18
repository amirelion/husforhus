import { test } from 'node:test';
import assert from 'node:assert/strict';
import { googleMapsUrl } from '../geo.js';
import { fromSweref, localToLatLon } from '../sweref.js';

const ORIGIN = [154025.1, 6578886.7];   // pipeline/city.py ORIGIN, Stortorget

test('SWEREF 99 18 00 to WGS84: the central meridian and Stortorget', () => {
  const [lat0, lon0] = fromSweref(150000, 6578000);
  assert.ok(Math.abs(lon0 - 18) < 1e-9);
  assert.ok(lat0 > 59.3 && lat0 < 59.35);
  const [lat, lon] = localToLatLon(0, 0, ORIGIN);
  assert.ok(Math.abs(lat - 59.32504) < 0.0005, `lat ${lat}`);    // Stortorget, about 59.3250 N 18.0706 E
  assert.ok(Math.abs(lon - 18.07063) < 0.0005, `lon ${lon}`);
  const [latS] = localToLatLon(0, 1000, ORIGIN);                   // z is south
  assert.ok(latS < lat);
});

test('the Google Maps link searches the coordinates, no key', () => {
  assert.match(googleMapsUrl(0, 0, ORIGIN), /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=59\.32\d{4},18\.07\d{4}$/);
});
