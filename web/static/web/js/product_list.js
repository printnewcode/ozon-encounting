document.addEventListener('DOMContentLoaded', () => {
    const CHILDREN_PAGE_SIZE = 15;

    // --- Toggle Expansion ---
    document.querySelectorAll('.group-header').forEach(header => {
        if (header.classList.contains('no-expand')) return;

        header.setAttribute('tabindex', '0');
        header.setAttribute('role', 'button');
        header.setAttribute('aria-expanded', 'false');
        header._visibleChildren = CHILDREN_PAGE_SIZE;

        const setRowsExpanded = (isExpanded) => {
            let next = header.nextElementSibling;
            let visibleRegularRows = 0;
            let hiddenRegularRows = 0;
            while (next && next.classList.contains('child-row')) {
                const row = next;

                if (row._collapseTimer) {
                    clearTimeout(row._collapseTimer);
                    row._collapseTimer = null;
                }

                if (isExpanded) {
                    if (row.classList.contains('load-more-row')) {
                        row.classList.toggle('show', hiddenRegularRows > 0);
                        row.classList.remove('closing');
                    } else if (visibleRegularRows < header._visibleChildren) {
                        row.classList.remove('closing');
                        row.classList.add('show');
                        visibleRegularRows += 1;
                    } else {
                        row.classList.remove('show', 'closing');
                        hiddenRegularRows += 1;
                    }
                } else {
                    header._visibleChildren = CHILDREN_PAGE_SIZE;
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

    document.querySelectorAll('.load-more-children').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const row = button.closest('.load-more-row');
            let header = row?.previousElementSibling;
            while (header && !header.classList.contains('group-header')) {
                header = header.previousElementSibling;
            }
            if (!header) return;

            header._visibleChildren += CHILDREN_PAGE_SIZE;
            let next = header.nextElementSibling;
            let visibleRegularRows = 0;
            let hiddenRegularRows = 0;
            while (next && next.classList.contains('child-row')) {
                const child = next;
                if (child.classList.contains('load-more-row')) {
                    child.classList.toggle('show', hiddenRegularRows > 0);
                    child.classList.remove('closing');
                } else if (visibleRegularRows < header._visibleChildren) {
                    child.classList.remove('closing');
                    child.classList.add('show');
                    visibleRegularRows += 1;
                } else {
                    child.classList.remove('show', 'closing');
                    hiddenRegularRows += 1;
                }
                next = child.nextElementSibling;
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
    const accrualModal = document.getElementById('accrualModal');
    const accrualGrossPrice = document.getElementById('accrualGrossPrice');
    const accrualDeductions = document.getElementById('accrualDeductions');
    const accrualNetIncome = document.getElementById('accrualNetIncome');
    const accrualServices = document.getElementById('accrualServices');
    const accrualItems = document.getElementById('accrualItems');
    let toastTimer = null;

    const csrfInput = form?.querySelector('[name="csrfmiddlewaretoken"]');
    const csrfToken = csrfInput ? csrfInput.value : '';

    const closeModal = () => {
        if (!modal) return;
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
    };

    const closeAccrualModal = () => {
        if (!accrualModal) return;
        accrualModal.classList.remove('show');
        accrualModal.setAttribute('aria-hidden', 'true');
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

    const SERVICE_LABELS = {
        MarketplaceServiceItemDirectFlowLogistic: 'Логистика до покупателя',
        MarketplaceServiceItemDirectFlowTrans: 'Магистральная доставка',
        MarketplaceServiceItemDirectFlowDelivToCustomer: 'Доставка покупателю',
        MarketplaceServiceItemDirectFlowDeliveryToCustomer: 'Доставка покупателю',
        MarketplaceServiceItemDeliveryToHandoverPlaceOzon: 'Доставка до места передачи OZON',
        MarketplaceServiceItemRedistributionLastMileCourier: 'Последняя миля, курьер',
        MarketplaceRedistributionOfAcquiringOperation: 'Эквайринг',
        MarketplaceServiceItemStorage: 'Хранение',
        MarketplaceServiceItemFulfillment: 'Сборка и обработка отправления',
        MarketplaceServiceItemPickup: 'Забор отправления',
        MarketplaceServiceItemReturnFlowLogistic: 'Логистика возврата',
        MarketplaceServiceItemReturnNotDelivToCustomer: 'Возврат недоставленного товара',
    };

    const OPERATION_LABELS = {
        OperationAgentDeliveredToCustomer: 'Доставка покупателю',
        OperationAgentStornoDeliveredToCustomer: 'Отмена доставки покупателю',
        OperationMarketplaceServiceStorage: 'Хранение',
        ClientReturnAgentOperation: 'Возврат покупателя',
    };

    const translatedLabel = (value, labels) => {
        const text = String(value || '').trim();
        return labels[text] || text;
    };

    const formatMoney = (value) => {
        const number = Number(String(value || '0').replace(',', '.'));
        if (!Number.isFinite(number)) return '0.00';
        return number.toFixed(2);
    };

    const hasMoneyValue = (value) => {
        if (value === null || value === undefined || value === '') return false;
        const number = Number(String(value).replace(',', '.'));
        return Number.isFinite(number) && Math.abs(number) > 0;
    };

    const renderList = (container, rows, emptyText) => {
        if (!container) return;
        container.innerHTML = '';
        if (!rows || rows.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'accrual-empty';
            empty.textContent = emptyText;
            container.appendChild(empty);
            return;
        }
        rows.forEach(row => {
            const item = document.createElement('div');
            item.className = 'accrual-list-row';

            const label = document.createElement('span');
            label.textContent = row.label;
            const value = document.createElement('strong');
            value.textContent = row.value;

            item.append(label, value);
            container.appendChild(item);
        });
    };

    const openAccrualModal = (button) => {
        if (!accrualModal) return;
        let details = {};
        try {
            details = JSON.parse(button.dataset.details || '{}');
        } catch (_) {
            details = {};
        }

        if (accrualGrossPrice) accrualGrossPrice.textContent = formatMoney(details.gross_price);
        if (accrualDeductions) accrualDeductions.textContent = formatMoney(details.deductions_total);
        if (accrualNetIncome) accrualNetIncome.textContent = formatMoney(details.net_income);

        const serviceRows = (details.services || []).filter(service => hasMoneyValue(service.price)).map(service => ({
            label: translatedLabel(service.name || service.code, SERVICE_LABELS) || 'Списание',
            value: formatMoney(service.price),
        }));
        const serviceTotal = (details.services || []).reduce((total, service) => {
            const number = Number(String(service.price || '0').replace(',', '.'));
            return Number.isFinite(number) && number < 0 ? total + Math.abs(number) : total;
        }, 0);
        const deductionsTotal = Number(String(details.deductions_total || '0').replace(',', '.'));
        const remainder = Number.isFinite(deductionsTotal) ? deductionsTotal - serviceTotal : 0;
        if (remainder > 0.004) {
            serviceRows.push({
                label: 'Разница без детализации OZON',
                value: formatMoney(-remainder),
            });
        }

        renderList(
            accrualServices,
            serviceRows,
            'Списания не переданы в операции.'
        );

        const itemRows = [];
        if (details.operation_name || details.operation_type) {
            const operationLabel = translatedLabel(details.operation_name || details.operation_type, OPERATION_LABELS);
            itemRows.push({
                label: '',
                value: operationLabel,
            });
        }
        (details.items || []).forEach(item => {
            if (hasMoneyValue(item.accruals_for_sale)) {
                itemRows.push({ label: 'Начислено за продажу', value: formatMoney(item.accruals_for_sale) });
            }
            if (hasMoneyValue(item.sale_commission)) {
                itemRows.push({ label: 'Комиссия с продажи', value: formatMoney(item.sale_commission) });
            }
            if (hasMoneyValue(item.payout)) {
                itemRows.push({ label: 'Выплата по товару', value: formatMoney(item.payout) });
            }
        });
        renderList(accrualItems, itemRows, 'Дополнительных данных нет.');

        accrualModal.classList.add('show');
        accrualModal.setAttribute('aria-hidden', 'false');
    };

    document.querySelectorAll('.cost-edit-button').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            openModal(button);
        });
    });

    document.querySelectorAll('.accrual-info-button').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            openAccrualModal(button);
        });
    });

    modal?.addEventListener('click', (e) => {
        if (e.target === modal || e.target.closest('.cost-modal-close')) {
            closeModal();
        }
    });

    accrualModal?.addEventListener('click', (e) => {
        if (e.target === accrualModal || e.target.closest('.accrual-modal-close')) {
            closeAccrualModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal?.classList.contains('show')) {
            closeModal();
        }
        if (e.key === 'Escape' && accrualModal?.classList.contains('show')) {
            closeAccrualModal();
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
