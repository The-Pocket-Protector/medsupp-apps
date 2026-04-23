// Extract current page - no top-level const to avoid REPL redeclaration
JSON.stringify(await page.evaluate(() => {
    const table = document.querySelector('table');
    const rows = table ? Array.from(table.querySelectorAll('tbody tr')).map(tr =>
        Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
    ) : [];
    const next = document.querySelector('.ui-paginator-next');
    const has_next = next ? !next.classList.contains('ui-state-disabled') : false;
    const pg = document.querySelector('.ui-paginator-current');
    const page_info = pg ? pg.textContent.trim() : '';
    return { rows, has_next, page_info };
}))
