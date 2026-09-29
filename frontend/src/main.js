/**
 * Entry dispatcher — decides WHICH boot runs before anything heavy is fetched.
 *
 * `?renderGame=false` (or `=0`) is a debugging/test-performance switch: it
 * skips the engine entirely — no WebGL context, no world build, no pre-warm,
 * and none of the subsystem modules are even requested — and stands up only
 * the HTML UI (the lobby) so markup and styles can be inspected in isolation.
 * See src/dev/uionly.js for exactly what that mode offers.
 *
 * The real boot lives in ./boot.js. Both sides are dynamic imports on purpose:
 * a static import here would make the browser fetch and parse the whole engine
 * even on a UI-only load, which is precisely the cost the flag exists to avoid.
 */
const renderGame = !['false', '0'].includes(new URLSearchParams(location.search).get('renderGame'));

// Quick graphics-quality picker (AUTO / LOW / MED / HIGH / ULTRA) pinned to the
// top corner of the menu. Mounted on BOTH phone and PC and on both boot paths;
// it only imports the tiny core settings helpers, never the engine, so it does
// not undo the lazy-dispatch this file exists for. It shows once the menu shell
// is on screen (body.ns-shell-open) and reloads into the chosen pipeline.
import('./ui/quickquality.js')
  .then((m) => m.mountQuickQuality())
  .catch(() => {});

if (renderGame) {
  await import('./boot.js');
} else {
  const { bootUiOnly } = await import('./dev/uionly.js');
  await bootUiOnly();
}
