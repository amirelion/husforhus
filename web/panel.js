// The legend panel's remembered state. Pure, so it can be tested without a browser.

// localStorage key for the viewer's last choice: 'collapsed' or 'open'.
export const LEGEND_KEY = 'hfh-legend';

// Should the legend start collapsed? A stored choice wins. Without one, phones (a bottom sheet) and narrow
// desktops (the panel would cover too much of the map) start collapsed; wide desktops start open.
export function initialCollapsed({ stored, phone, wide }) {
  if (stored === 'collapsed') return true;
  if (stored === 'open') return false;
  return Boolean(phone) || !wide;
}
