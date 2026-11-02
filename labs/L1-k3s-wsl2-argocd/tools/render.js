const { chromium } = require('playwright');
(async () => {
  const [,, inp, out] = process.argv;
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + inp, { waitUntil: 'load' });
  await p.pdf({ path: out, format: 'A4', landscape: true, printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:7pt;width:100%;padding:0 12mm;color:#6b7280;display:flex;justify-content:space-between;font-family:DejaVu Sans"><span>L1 Week 1 - k3s on WSL2 + Argo CD (halo)</span><span>Page <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
    margin: { top: '13mm', bottom: '14mm', left: '12mm', right: '12mm' } });
  await b.close();
})();
