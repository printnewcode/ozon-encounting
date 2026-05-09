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

    const modal = document.getElementById('costModal');
    const form = document.getElementById('costForm');
    const productInput = document.getElementById('costProductId');
    const priceInput = document.getElementById('costPriceInput');
    const applySalesInput = document.getElementById('costApplySales');
    const productLabel = document.getElementById('costModalProduct');
    const toast = document.getElementById('costToast');
    const undoButton = toast?.querySelector('.cost-toast-undo');
    let toastTimer = null;

    const csrfInput = form?.querySelector('[name="csrfmiddlewaretoken"]');
    const csrfToken = csrfInput ? csrfInput.value : '';

    const closeModal = () => {
        if (!modal) return;
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
    };

    const openModal = (button) => {
        if (!modal || !form) return;
        productInput.value = button.dataset.productId || '';
        form.dataset.productIds = button.dataset.productIds || button.dataset.productId || '';
        priceInput.value = button.dataset.cost || '';
        applySalesInput.checked = false;
        productLabel.textContent = `${button.dataset.article || ''} · ${button.dataset.name || ''}`;
        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');
        priceInput.focus();
        priceInput.select();
    };

    const postForm = async (url, data) => {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': csrfToken,
            },
            body: new URLSearchParams(data),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || 'Не удалось сохранить изменения.');
        }
        return payload;
    };

    const updateVisibleCost = (article, costPrice) => {
        document.querySelectorAll(`.cost-edit-button[data-article="${CSS.escape(article)}"]`).forEach(button => {
            button.dataset.cost = costPrice;
            const cell = button.closest('.cost-edit-cell');
            const value = cell?.querySelector('.row-cost-value');
            if (value) value.textContent = costPrice;
            const td = button.closest('td');
            if (td) td.dataset.sort = costPrice;
        });
    };

    const showToast = () => {
        if (!toast) return;
        if (toastTimer) clearTimeout(toastTimer);
        toast.classList.remove('show');
        void toast.offsetWidth;
        toast.classList.add('show');
        toast.setAttribute('aria-hidden', 'false');
        toastTimer = setTimeout(() => {
            toast.classList.remove('show');
            toast.setAttribute('aria-hidden', 'true');
            window.location.reload();
        }, 5000);
    };

    document.querySelectorAll('.cost-edit-button').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            openModal(button);
        });
    });

    modal?.addEventListener('click', (e) => {
        if (e.target === modal || e.target.closest('.cost-modal-close')) {
            closeModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal?.classList.contains('show')) {
            closeModal();
        }
    });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitButton = form.querySelector('[type="submit"]');
        submitButton.disabled = true;

        try {
            const payload = await postForm(modal.dataset.updateUrl, {
                product_id: productInput.value,
                product_ids: form.dataset.productIds || productInput.value,
                cost_price: priceInput.value,
                apply_to_sales: String(applySalesInput.checked),
            });
            updateVisibleCost(payload.article, payload.cost_price);
            closeModal();
            showToast();
        } catch (error) {
            alert(error.message);
        } finally {
            submitButton.disabled = false;
        }
    });

    undoButton?.addEventListener('click', async () => {
        undoButton.disabled = true;
        if (toastTimer) clearTimeout(toastTimer);
        try {
            await postForm(modal.dataset.undoUrl, {});
            window.location.reload();
        } catch (error) {
            alert(error.message);
            undoButton.disabled = false;
        }
    });
});
