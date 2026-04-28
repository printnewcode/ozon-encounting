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

    // --- Table Sorting ---
    let lastCol = null, asc = true;

    document.querySelectorAll('.sortable').forEach(function (th) {
        th.addEventListener('click', function () {
            const col  = parseInt(th.dataset.col);
            const type = th.dataset.type;

            if (lastCol === col) { asc = !asc; }
            else {
                asc = true;
                document.querySelectorAll('.sortable').forEach(h => h.classList.remove('asc', 'desc'));
            }
            th.classList.toggle('asc', asc);
            th.classList.toggle('desc', !asc);
            lastCol = col;

            const tbody = document.getElementById('productsBody');
            
            // In the NEW structure, we have groups. 
            // A group is a header + several child rows.
            // Let's identify the groups.
            const allRows = Array.from(tbody.querySelectorAll('tr'));
            const groups = [];
            let currentGroup = null;

            allRows.forEach(row => {
                if (row.classList.contains('group-header')) {
                    currentGroup = { header: row, children: [] };
                    groups.push(currentGroup);
                } else if (row.classList.contains('child-row')) {
                    if (currentGroup) currentGroup.children.push(row);
                }
            });

            groups.sort(function (a, b) {
                const cellA = a.header.cells[col];
                const cellB = b.header.cells[col];
                if (!cellA || !cellB) return 0;

                const rawA = (cellA.dataset.sort !== undefined ? cellA.dataset.sort : cellA.textContent).trim();
                const rawB = (cellB.dataset.sort !== undefined ? cellB.dataset.sort : cellB.textContent).trim();

                let valA, valB;
                if (type === 'num') {
                    valA = parseFloat(rawA) || -Infinity;
                    valB = parseFloat(rawB) || -Infinity;
                } else if (type === 'date') {
                    valA = rawA || '0';
                    valB = rawB || '0';
                } else {
                    valA = rawA.toLowerCase();
                    valB = rawB.toLowerCase();
                }

                if (valA < valB) return asc ? -1 : 1;
                if (valA > valB) return asc ? 1 : -1;
                return 0;
            });

            // Re-append to tbody
            groups.forEach(group => {
                tbody.appendChild(group.header);
                group.children.forEach(child => tbody.appendChild(child));
            });
        });
    });
});
