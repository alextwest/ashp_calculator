// The host sends its resolved theme, including changes to System default.
export function initializeTheme() {
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');
  const generatorOrigin = import.meta.env.VITE_GENERATOR_ORIGIN ||
    'https://wonderful-desert-0055d690f-staging.eastus2.1.azurestaticapps.net';
  let hostTheme;
  const apply = () => {
    document.documentElement.dataset.theme = hostTheme || (media?.matches ? 'dark' : 'light');
  };
  window.addEventListener('message', event => {
    if (window.parent === window || event.source !== window.parent || event.origin !== generatorOrigin) return;
    if (event.data?.type !== 'proposal_theme' || !['light', 'dark'].includes(event.data.theme)) return;
    hostTheme = event.data.theme;
    apply();
  });
  media?.addEventListener?.('change', apply);
  apply();
}
