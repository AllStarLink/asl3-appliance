// Follow the browser's light/dark preference, as asl-web-ui and Cockpit do.
// Loaded in <head> so the page doesn't flash light before turning dark.
(function () {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => document.documentElement.classList.toggle('pf-v6-theme-dark', query.matches);
    apply();
    query.addEventListener('change', apply);
})();
