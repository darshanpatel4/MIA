/**
 * MIA Icon Library
 * Inline SVG icons (24x24 viewBox, stroke=currentColor) used by JS-rendered
 * markup, in place of emoji. Static chrome in index.html inlines its own SVGs
 * directly; this file covers everything built via template literals.
 */

const ICON_STROKE = 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';

const ICON = {
    bot: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="4" y="8" width="16" height="11" rx="2"/><path d="M9 8V5a3 3 0 0 1 6 0v3M9 13h.01M15 13h.01"/></svg>`,
    user: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><circle cx="12" cy="8" r="3.2"/><path d="M5 20c1.5-4 4.2-6 7-6s5.5 2 7 6"/></svg>`,
    trash: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2m-9 0 1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/></svg>`,
    pencil: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`,
    dots: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M3 12a9 9 0 0 1 15.4-6.36L21 8M3 12a9 9 0 0 0 15.4 6.36L21 16M21 8v-5m0 5h-5M3 16v5m0-5h5"/></svg>`,
    plus: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M12 5v14M5 12h14"/></svg>`,
    mic: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>`,
    send: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 11l18-8-8 18-2-8-8-2z"/></svg>`,
    play: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 4l14 8-14 8V4z"/></svg>`,
    stop: `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>`,
    mouse: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M12 2a5 5 0 0 0-5 5v10a5 5 0 0 0 10 0V7a5 5 0 0 0-5-5zM12 2v6"/></svg>`,
    fullscreen: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3m11-5v3a2 2 0 0 1-2 2h-3"/></svg>`,
    upload: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg>`,
    arrowUp: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M12 19V5M5 12l7-7 7 7"/></svg>`,
    cpu: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="6" y="6" width="12" height="12" rx="1.5"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></svg>`,
    memory: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M4 7a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7z"/><path d="M8 6v2M12 6v2M16 6v2M8 16v2M12 16v2M16 16v2"/></svg>`,
    network: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/></svg>`,
    disk: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><ellipse cx="12" cy="5" rx="8" ry="2.5"/><path d="M4 5v14c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5V5"/><path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/></svg>`,
    system: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>`,
    phone: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></svg>`,
    gear: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
    folder: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>`,
    file: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M6 2h9l5 5v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"/><path d="M14 2v6h6"/></svg>`,
    fileImage: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>`,
    fileArchive: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M6 2h12a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"/><path d="M10 2v2M14 4v2M10 6v2M14 8v2M10 10v2h4v-2"/></svg>`,
    fileCode: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="m9 8-4 4 4 4M15 8l4 4-4 4"/></svg>`,
    lock: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg>`,
    puzzle: `<svg viewBox="0 0 24 24" ${ICON_STROKE}><path d="M20.5 11a2.5 2.5 0 0 0-2.45-3H16V6.5a2.5 2.5 0 0 0-5 0V8H8.5a1 1 0 0 0-1 1v2.5a2.5 2.5 0 0 1 0 5V19a1 1 0 0 0 1 1H11a2.5 2.5 0 0 1 5 0h2.5a1 1 0 0 0 1-1v-2.5a2.5 2.5 0 0 0 3-2.45 2.5 2.5 0 0 0-2-2.45V11z"/></svg>`,
};
