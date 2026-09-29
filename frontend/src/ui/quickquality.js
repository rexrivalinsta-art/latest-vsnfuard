/**
 * Quick graphics-quality picker — a small always-visible control pinned to the
 * top-right corner of the menu shell, so a player can set LOW / MED / HIGH /
 * ULTRA (or return to AUTO) in one tap without opening Settings → Graphics.
 *
 * WHY IT RELOADS
 * --------------
 * A preset/tier change rebuilds the render pipeline (passes, render targets,
 * shader permutations are built once in RenderSystem.init). Rebuilding them live
 * is a much larger change than the engine takes, so the engine's own
 * `AdaptiveQualitySystem.setMode` persists the choice and reloads. This control
 * does exactly the same thing through the shared localStorage helpers, so it
 * works identically whether or not an engine instance is running (it also works
 * under ?renderGame=false, where there is no engine at all).
 *
 * WHERE IT SHOWS
 * --------------
 * Only while the menu shell is on screen (`body.ns-shell-open`) — quality is a
 * menu decision, and applying it reloads, so it never makes sense to offer this
 * mid-firefight where it would sit on top of the killfeed and drop the player
 * from the match on a tap.
 */

import { loadGraphicsSettings, saveGraphicsSettings } from '../core/quality.js';
import { BRAND } from '../config/branding.js';

/** [mode, short label]. AUTO first so the default is one tap away again. */
const MODES = [
  ['auto', 'AUTO'],
  ['low', 'LOW'],
  ['medium', 'MED'],
  ['high', 'HIGH'],
  ['ultra', 'ULTRA'],
];

let mounted = false;

export function mountQuickQuality() {
  if (mounted || typeof document === 'undefined' || !document.body) return;
  mounted = true;

  const accent = BRAND?.PRIMARY_BRAND || '#FF6A1A';

  const style = document.createElement('style');
  style.textContent = `
  #ns-quality{position:fixed;top:12px;right:12px;z-index:9000;display:none;gap:3px;
    padding:5px 6px;border-radius:11px;background:rgba(8,12,18,.74);
    -webkit-backdrop-filter:blur(9px);backdrop-filter:blur(9px);
    border:1px solid rgba(255,255,255,.12);box-shadow:0 8px 24px rgba(0,0,0,.45);
    align-items:center;user-select:none;font:600 11px/1 system-ui,Segoe UI,sans-serif}
  body.ns-shell-open #ns-quality{display:flex}
  #ns-quality .ns-q-label{color:rgba(255,255,255,.5);letter-spacing:.16em;
    font-size:9px;padding:0 5px 0 3px}
  #ns-quality button{appearance:none;border:0;cursor:pointer;color:#cfd8e3;
    background:transparent;padding:7px 10px;border-radius:8px;letter-spacing:.08em;
    font:inherit;min-height:32px;touch-action:manipulation;
    transition:background .15s ease,color .15s ease}
  #ns-quality button:hover{background:rgba(255,255,255,.09);color:#fff}
  #ns-quality button.ns-q-on{background:${accent};color:#0a0e14;box-shadow:0 0 0 1px ${accent}}
  @media (max-width:560px),(pointer:coarse){#ns-quality{top:8px;right:8px;padding:5px;gap:2px}
    #ns-quality button{padding:9px 11px;min-height:42px;font-size:12px}
    #ns-quality .ns-q-label{display:none}}
  `;
  document.head.appendChild(style);

  const bar = document.createElement('div');
  bar.id = 'ns-quality';
  bar.setAttribute('data-testid', 'quick-quality');
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', 'Graphics quality');

  const label = document.createElement('span');
  label.className = 'ns-q-label';
  label.textContent = 'QUALITY';
  bar.appendChild(label);

  let active = readMode();
  const buttons = new Map();

  for (const [mode, text] of MODES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.setAttribute('data-mode', mode);
    b.setAttribute('data-testid', `quality-${mode}`);
    b.title =
      mode === 'auto'
        ? 'Auto — match the device (recommended)'
        : `Force ${text} graphics`;
    b.addEventListener('click', () => select(mode));
    bar.appendChild(b);
    buttons.set(mode, b);
  }

  function readMode() {
    try {
      return loadGraphicsSettings().mode || 'auto';
    } catch {
      return 'auto';
    }
  }

  function paint() {
    for (const [mode, b] of buttons) b.classList.toggle('ns-q-on', mode === active);
  }

  function select(mode) {
    if (mode === active) return;
    const settings = loadGraphicsSettings();
    // Mirror AdaptiveQualitySystem.setMode: auto forgets the measured profile and
    // recalibrates; a manual tier is pinned and considered already calibrated.
    const patch =
      mode === 'auto'
        ? { mode, tier: null, tierCeiling: null, calibrated: false, renderScale: 1 }
        : { mode, tier: mode, tierCeiling: null, calibrated: true, renderScale: 1 };
    saveGraphicsSettings({ ...settings, ...patch });
    active = mode;
    paint();
    // Let the pressed state paint for a beat, then reload into the new pipeline.
    setTimeout(() => {
      try {
        location.reload();
      } catch {
        /* no-op outside a browser */
      }
    }, 140);
  }

  paint();
  document.body.appendChild(bar);
}
