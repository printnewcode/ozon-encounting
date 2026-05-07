document.addEventListener('DOMContentLoaded', () => {
    // --- Toggle Expansion ---
    document.querySelectorAll('.group-header').forEach(header => {
        header.setAttribute('tabindex', '0');
        header.setAttribute('role', 'button');
        header.setAttribute('aria-expanded', 'false');

        const setRowsExpanded = (isExpanded) => {
            let next = header.nextElementSibling;
            while (next && next.classList.contains('child-row')) {
                const row = next;

                if (row._collapseTimer) {
                    clearTimeout(row._collapseTimer);
                    row._collapseTimer = null;
                }

                if (isExpanded) {
                    row.classList.remove('closing');
                    row.classList.add('show');
                } else {
                    row.classList.add('closing');
                    row._collapseTimer = setTimeout(() => {
                        row.classList.remove('show', 'closing');
                        row._collapseTimer = null;
                    }, 260);
                }

                next = row.nextElementSibling;
            }
        };

        const toggleHeader = () => {
            const isExpanded = !header.classList.contains('expanded');
            header.classList.toggle('expanded', isExpanded);
            header.setAttribute('aria-expanded', String(isExpanded));
            setRowsExpanded(isExpanded);
        };

        header.addEventListener('click', (e) => {
            if (e.target.closest('a') || e.target.closest('button')) return;
            toggleHeader();
        });

        header.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleHeader();
            }
        });
    });

});
