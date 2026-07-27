// Per-goal detail is a dynamic client-side route. The static adapter can't
// prerender an open-ended :id set, so we opt this route OUT of the layout's
// prerender=true. adapter-static's fallback (404.html) hydrates this route
// client-side on GitHub Pages. The page paints only from the checked-in public
// snapshot until the server exposes a visibility-enforced Goal projection.
export const prerender = false;
export const ssr = false;
