"use strict";

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const API = "/api/v1";
  const isDev = document.body.dataset.development === "true";
  const timezone = document.body.dataset.timezone || "Asia/Almaty";
  const labels = {OPEN: "Открыт", PENDING_PAYMENT: "Ожидает оплату", PAID: "Оплачен", CANCELLED: "Отменён", PENDING: "Ожидание", SUCCEEDED: "Оплачен", FAILED: "Отклонён", EXPIRED: "Истёк"};
  const failureLabels = {INSUFFICIENT_FUNDS: "На выбранном счёте недостаточно средств.", insufficient_funds: "На выбранном счёте недостаточно средств.", bank_declined: "Банк отклонил платёж.", USER_CANCELLED: "Покупатель отменил оплату.", MERCHANT_CANCELLED: "Оплата отменена кассиром.", expired: "Срок оплаты истёк.", EXPIRED: "Срок оплаты истёк.", DECLINED: "Банк отклонил платёж.", BANK_UNAVAILABLE: "Банк временно недоступен."};
  let noticeTimer;

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = String(content);
    return node;
  }
  function button(text, className, action) {
    const node = element("button", `button ${className}`, text);
    node.type = "button";
    node.addEventListener("click", () => safely(action));
    return node;
  }
  function notice(message, error = false) {
    const dialog = $("dialog[open]");
    if (dialog && error) {
      let inline = $(".dialog-notice", dialog);
      if (!inline) { inline = element("div", "form-error dialog-notice"); inline.setAttribute("role", "alert"); $("form", dialog).prepend(inline); }
      inline.textContent = message; inline.scrollIntoView({block: "nearest"});
      return;
    }
    const box = $("#notice");
    box.textContent = message;
    box.classList.toggle("error", error);
    box.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { box.hidden = true; }, error ? 8500 : 4000);
  }
  async function safely(action) {
    try { return await action(); } catch (error) { notice(error.message || "Не удалось выполнить действие.", true); }
  }
  function csrf() {
    return document.cookie.split("; ").find(item => item.startsWith("csrf_token="))?.split("=").slice(1).join("=") || "";
  }
  function parseJSON(text) {
    // Preserve large integer tokens without touching strings or using floating point.
    const preserved = text.replace(/"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g, token => {
      if (token.startsWith('"') || !/^-?\d+$/.test(token)) return token;
      const integer = BigInt(token);
      return integer > 9007199254740991n || integer < -9007199254740991n ? `"${token}"` : token;
    });
    return JSON.parse(preserved);
  }
  async function api(path, options = {}) {
    const method = options.method || "GET";
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (!["GET", "HEAD"].includes(method)) headers["X-CSRF-Token"] = decodeURIComponent(csrf());
    let response;
    try { response = await fetch(API + path, {...options, method, headers, credentials: "same-origin", cache: "no-store", body: options.body === undefined ? undefined : JSON.stringify(options.body)}); }
    catch { throw new Error("Нет связи с магазином. Проверьте подключение и повторите действие."); }
    const text = await response.text();
    let data;
    try { data = text ? parseJSON(text) : null; } catch { throw new Error("Сервер вернул неожиданный ответ. Повторите попытку."); }
    if (!response.ok) {
      if (response.status === 401 && document.body.dataset.page !== "login") {
        window.location.assign("/login");
      }
      const error = new Error(data?.error?.message || "Не удалось выполнить запрос.");
      error.code = data?.error?.code;
      error.status = response.status;
      if (response.status === 422 && data?.error?.details?.fields?.length) error.message += " Проверьте заполненные поля.";
      throw error;
    }
    return data;
  }
  function money(value) {
    const minor = BigInt(String(value ?? 0));
    const negative = minor < 0n;
    const absolute = negative ? -minor : minor;
    return `${negative ? "−" : ""}${(absolute / 100n).toLocaleString("ru-RU")},${String(absolute % 100n).padStart(2, "0")} ₸`;
  }
  function moneyInput(value) {
    const minor = BigInt(String(value ?? 0));
    return `${minor / 100n}.${String(minor % 100n).padStart(2, "0")}`;
  }
  function parsePrice(value) {
    const normalized = value.trim().replace(",", ".");
    if (!/^\d+(\.\d{1,2})?$/.test(normalized)) throw new Error("Укажите цену в тенге: например, 1250,50. Не больше двух знаков после запятой.");
    const [whole, fraction = ""] = normalized.split(".");
    const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
    if (minor > 9007199254740991n) throw new Error("Цена слишком велика для ввода через веб-интерфейс.");
    return Number(minor);
  }
  function integer(value, minimum = 0) {
    if (!/^-?\d+$/.test(String(value))) throw new Error("Количество должно быть целым числом.");
    const result = Number(value);
    if (!Number.isSafeInteger(result) || result < minimum || result > 2147483647) throw new Error("Количество вне допустимого диапазона.");
    return result;
  }
  const unit = value => value === "KG" ? "кг" : "шт.";
  const amountUnit = value => value === "KG" ? "г" : "шт.";
  const quantity = item => `${item.quantity} ${amountUnit(item.unit)}`;
  function status(value) {
    return element("span", `status ${["PENDING", "PENDING_PAYMENT"].includes(value) ? "warning" : ["FAILED", "EXPIRED", "CANCELLED"].includes(value) ? "failure" : ""}`, labels[value] || value);
  }
  const dateTime = value => new Intl.DateTimeFormat("ru-RU", {timeZone: timezone, dateStyle: "medium", timeStyle: "short"}).format(new Date(value));
  function debounce(callback, delay = 220) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => safely(() => callback(...args)), delay); };
  }
  async function submitting(form, action) {
    const submit = $("button[type=submit]", form);
    if (submit.disabled) return;
    submit.disabled = true;
    try { await action(); } finally { submit.disabled = false; }
  }
  function bindForm(id, action) {
    const form = $(id);
    form.addEventListener("submit", event => { event.preventDefault(); safely(() => submitting(form, () => action(form))); });
  }
  function pagination(container, page, onChange) {
    container.replaceChildren();
    if (!page.total) return;
    if (page.offset) container.append(button("← Назад", "secondary small", () => onChange(Math.max(0, page.offset - page.limit))));
    container.append(element("span", "", `${page.offset + 1}–${Math.min(page.offset + page.items.length, page.total)} из ${page.total}`));
    if (page.offset + page.limit < page.total) container.append(button("Далее →", "secondary small", () => onChange(page.offset + page.limit)));
  }
  async function allCategories(publicOnly = false) {
    const result = [];
    for (let offset = 0; ; offset += 100) {
      const page = await api(`${publicOnly ? "/public" : ""}/categories?limit=100&offset=${offset}`);
      result.push(...page.items);
      if (result.length >= page.total || page.items.length === 0) return result;
    }
  }
  function categoryTree(categories) {
    const result = [], visited = new Set();
    function add(parent, depth) {
      categories.filter(item => item.parent_id === parent).sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, "ru")).forEach(item => {
        if (visited.has(item.public_id)) return;
        visited.add(item.public_id); result.push({...item, depth}); add(item.public_id, depth + 1);
      });
    }
    add(null, 0);
    categories.filter(item => !visited.has(item.public_id)).forEach(item => result.push({...item, depth: 0}));
    return result;
  }
  function categoryChips(container, categories, selected, select) {
    container.replaceChildren();
    const all = button("Все товары", "", () => select(""));
    all.className = selected ? "" : "active";
    all.setAttribute("aria-pressed", String(!selected)); container.append(all);
    categoryTree(categories).filter(item => item.is_active).forEach(item => {
      const node = button(`${item.depth ? "↳ " : ""}${item.name}`, "", () => select(item.public_id));
      node.className = `${selected === item.public_id ? "active " : ""}${item.depth ? "child-chip" : ""}`;
      node.setAttribute("aria-pressed", String(selected === item.public_id)); container.append(node);
    });
  }
  function productCard(product, action) {
    const card = element(action ? "button" : "article", "product-card");
    if (action) { card.type = "button"; card.addEventListener("click", () => safely(() => action(product))); card.disabled = !product.in_stock; }
    const art = element("span", "product-art", product.unit === "KG" ? "кг" : product.name.slice(0, 1).toUpperCase());
    art.setAttribute("aria-hidden", "true"); card.append(art, element("span", "product-name", product.name));
    const price = element("div", "product-price"); price.append(element("strong", "", money(product.price_minor)), element("small", "", `за ${unit(product.unit)}`)); card.append(price);
    card.append(element("span", "product-stock", product.in_stock ? "● В наличии" : "Нет в наличии"));
    if (action) card.append(element("span", "add-circle", "+"));
    else { if (product.description) card.append(element("p", "price-description", product.description)); card.append(element("small", "muted", product.barcode)); }
    return card;
  }
  function qr(payment) {
    const image = element("img", "qr-image");
    image.src = `${API}/payments/${encodeURIComponent(payment.public_id)}/qr.png`;
    image.alt = "QR-код для оплаты в учебном банке";
    image.width = 320; image.height = 320;
    image.addEventListener("error", () => { image.hidden = true; });
    return image;
  }
  function paymentLink(payment) {
    if (!isDev || !payment.pay_url) return null;
    let url;
    try { url = new URL(payment.pay_url); } catch { return null; }
    if (!["http:", "https:"].includes(url.protocol)) return null;
    const link = element("a", "payment-link", `Открыть учебный банк ↗ ${url.href}`);
    link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    return link;
  }
  function timerText(seconds) {
    const safe = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
  }
  function paymentContent(container, order, payment, {display = false} = {}) {
    container.replaceChildren();
    if (order?.status === "PAID") {
      container.append(element("div", "success-icon", "✓"), element("h2", "", "Оплачено!"), element("p", "", "Спасибо за покупку. Хорошего дня!")); return;
    }
    if (payment?.needs_review) {
      container.append(element("h2", "", "Проверяем платёж"), element("p", "form-error", "Платёж требует проверки администратором. Не повторяйте оплату до уточнения."));
      return;
    }
    if (order?.status === "PENDING_PAYMENT") {
      container.append(element(display ? "h2" : "h3", "", "Оплатите по QR"));
      if (payment?.pay_url && payment.status === "PENDING" && payment.seconds_left > 0) {
        container.append(element("p", "", "Откройте камеру и наведите на QR-код"), qr(payment));
        const timer = element("div", "timer", timerText(payment.seconds_left)); timer.dataset.timer = "true"; container.append(timer);
        const link = paymentLink(payment); if (link) container.append(link);
      } else container.append(element("p", "", "Проверяем состояние платежа в банке. Пожалуйста, подождите."));
      return;
    }
    if (payment && ["FAILED", "EXPIRED", "CANCELLED"].includes(payment.status)) {
      container.append(element("div", "waiting-symbol", "↻"), element("h2", "", labels[payment.status]), element("p", "", failureLabels[payment.failure_reason] || "Кассир может повторить оплату или изменить чек.")); return;
    }
    container.append(element("div", "waiting-symbol", "▥"), element("h2", "", "Готовим вашу покупку"), element("p", "", "Когда кассир добавит все товары, здесь появится QR-код для оплаты."));
  }
  function readonlyItems(container, items) {
    container.replaceChildren(...items.map(item => {
      const row = element("div", "order-item");
      const content = element("div"); content.append(element("div", "item-name", item.product_name), element("div", "item-detail", `${quantity(item)} · ${money(item.unit_price_minor)} / ${unit(item.unit)}`));
      row.append(content, element("strong", "item-sum", money(item.line_total_minor))); return row;
    }));
  }

  async function initLogin() {
    bindForm("#login-form", async form => {
      $("#login-error").hidden = true;
      try {
        await api("/auth/login", {method: "POST", body: {username: form.elements.username.value, password: form.elements.password.value}});
        form.elements.password.value = ""; window.location.assign("/cashier");
      } catch (error) { $("#login-error").textContent = error.message; $("#login-error").hidden = false; }
    });
  }

  async function initCashier() {
    const requestedTerminal = new URLSearchParams(location.search).get("terminal") || "main";
    const terminal = /^[a-zA-Z0-9_-]{1,64}$/.test(requestedTerminal) ? requestedTerminal : "main";
    $("#terminal-label").textContent = `Терминал ${terminal}`;
    $("#display-link").href = `/display/${encodeURIComponent(terminal)}`;
    let order = null, selectedCategory = "", categories = [], search = "", offset = 0, requestId = 0, busy = false, pollBusy = false, orderSignature = "", pendingProduct = null;
    const focusScan = () => { if (!document.querySelector("dialog[open]")) $("#barcode").focus(); };
    async function mutate(action) {
      if (busy) return;
      busy = true;
      try { await action(); await loadOrder(); } finally { busy = false; renderOrder(true); }
    }
    async function loadOrder() {
      if (order) order = await api(`/orders/${order.public_id}`);
      renderOrder();
    }
    async function newOrder() {
      await mutate(async () => { order = await api("/orders", {method: "POST", body: {terminal_code: terminal}}); }); focusScan();
    }
    async function add(product, quantityValue) {
      if (!order || order.status !== "OPEN") throw new Error("Сначала откройте новый чек. Текущий чек должен быть доступен для изменения.");
      await mutate(async () => { order = await api(`/orders/${order.public_id}/items`, {method: "POST", body: {product_id: product.public_id, quantity: quantityValue}}); });
      $("#barcode").value = ""; focusScan();
    }
    async function selectProduct(product) {
      if (!order || order.status !== "OPEN") throw new Error("Откройте новый чек перед добавлением товаров.");
      if (product.unit === "KG") {
        pendingProduct = product; $("#quantity-product").textContent = `${product.name} · ${money(product.price_minor)} / кг`;
        $("#quantity-value").value = "500"; $("#quantity-dialog").showModal(); $("#quantity-value").select();
      } else await add(product, 1);
    }
    bindForm("#quantity-form", async () => { await add(pendingProduct, integer($("#quantity-value").value, 1)); $("#quantity-dialog").close(); focusScan(); });
    bindForm("#scan-form", async () => {
      const barcode = $("#barcode").value.trim(); if (!barcode) return;
      if (!/^([0-9]{8}|[0-9]{13})$/.test(barcode)) throw new Error("Штрихкод должен содержать 8 или 13 цифр.");
      await selectProduct(await api(`/products/by-barcode/${encodeURIComponent(barcode)}`));
    });
    async function products() {
      const currentRequest = ++requestId;
      const query = new URLSearchParams({limit: "18", offset: String(offset), is_active: "true", include_subcategories: "true"});
      if (selectedCategory) query.set("category_id", selectedCategory); if (search) query.set("q", search);
      const result = await api(`/products?${query}`); if (currentRequest !== requestId) return;
      $("#product-count").textContent = result.total;
      $("#product-grid").replaceChildren(...result.items.map(product => productCard(product, selectProduct)));
      if (!result.items.length) $("#product-grid").append(element("p", "empty-note", "Товары не найдены. Попробуйте другое название или категорию."));
      pagination($("#catalog-pagination"), result, async value => { offset = value; await products(); });
    }
    function chips() { categoryChips($("#category-chips"), categories, selectedCategory, async value => { selectedCategory = value; offset = 0; chips(); await products(); }); }
    $("#product-search").addEventListener("input", debounce(async event => { search = event.target.value.trim(); offset = 0; await products(); }));
    $("#create-order").addEventListener("click", () => safely(newOrder));
    function renderOrder(force = false) {
      const signature = JSON.stringify(order ? {...order, payment: order.payment ? {...order.payment, seconds_left: 0, qr_usable: order.payment.seconds_left > 0} : null} : null);
      if (!force && signature === orderSignature) {
        const timer = $("[data-timer]"); if (timer) timer.textContent = timerText(order?.payment?.seconds_left);
        return;
      }
      orderSignature = signature;
      $("#order-empty").hidden = !!order;
      $("#order-number").textContent = order ? `№ ${order.number}` : "Начните покупку";
      const badge = status(order?.status || "Нет чека"); badge.id = "order-status"; $("#order-status").replaceWith(badge);
      $("#order-total").textContent = money(order?.total_minor || 0);
      const items = $("#order-items"); items.replaceChildren();
      for (const item of order?.items || []) {
        const row = element("div", "order-item"), content = element("div");
        content.append(element("div", "item-name", item.product_name), element("div", "item-detail", `${money(item.unit_price_minor)} / ${unit(item.unit)}`));
        row.append(content, element("strong", "item-sum", money(item.line_total_minor)));
        if (order.status === "OPEN") {
          const controls = element("div", "quantity-controls"); controls.classList.add("span-two");
          const input = element("input"); input.type = "number"; input.min = "1"; input.max = "2147483647"; input.step = "1"; input.value = item.quantity; input.setAttribute("aria-label", `Количество ${item.product_name}, ${amountUnit(item.unit)}`);
          const update = async value => { await mutate(async () => { order = await api(`/orders/${order.public_id}/items/${item.public_id}`, {method: "PATCH", body: {quantity: integer(value, 1)}}); }); focusScan(); };
          const down = button("−", "", () => update(item.quantity - 1)); down.setAttribute("aria-label", "Уменьшить количество"); down.disabled = item.quantity <= 1 || busy;
          const up = button("+", "", () => update(item.quantity + 1)); up.setAttribute("aria-label", "Увеличить количество"); up.disabled = busy;
          input.disabled = busy; input.addEventListener("change", () => safely(() => update(input.value)));
          const remove = button("×", "remove-item", async () => { await mutate(async () => { order = await api(`/orders/${order.public_id}/items/${item.public_id}`, {method: "DELETE"}); }); focusScan(); }); remove.setAttribute("aria-label", `Удалить ${item.product_name}`); remove.disabled = busy;
          controls.append(down, input, up, element("span", "", amountUnit(item.unit)), remove); row.append(controls);
        } else row.append(element("span", "item-detail", quantity(item)));
        items.append(row);
      }
      if (order?.status === "OPEN" && !order.items.length) items.append(element("p", "empty-note", "Отсканируйте первый товар или выберите его в каталоге."));
      const payment = order?.payment, paymentPanel = $("#payment-panel");
      paymentPanel.hidden = !order || (!payment && order.status !== "PAID");
      if (!paymentPanel.hidden) paymentContent(paymentPanel, order, payment);
      const actions = $("#order-actions"); actions.replaceChildren();
      if (!order) return;
      if (order.status === "OPEN") {
        const checkout = button("Принять оплату по QR →", "primary wide", () => mutate(async () => { await api(`/orders/${order.public_id}/checkout`, {method: "POST"}); })); checkout.disabled = busy || !order.items.length || !!payment?.needs_review; actions.append(checkout);
      }
      if (order.status === "PENDING_PAYMENT" && payment) {
        actions.append(button("Проверить оплату ↻", "primary wide", () => mutate(async () => { await api(`/payments/${payment.public_id}/refresh`, {method: "POST"}); })));
        actions.append(button("Отменить платёж / изменить чек", "secondary wide", async () => { if (confirm("Отменить оплату и вернуться к изменению чека?")) await mutate(async () => { await api(`/payments/${payment.public_id}/cancel`, {method: "POST"}); }); }));
      }
      if (["OPEN", "PENDING_PAYMENT"].includes(order.status)) actions.append(button("Отменить чек", "ghost wide", async () => { if (confirm("Отменить текущий чек?")) await mutate(async () => { await api(`/orders/${order.public_id}/cancel`, {method: "POST"}); }); }));
      else {
        if (order.status === "PAID") { const receipt = element("a", "button secondary wide", "Открыть чек / печать ↗"); receipt.href = `/receipt/${order.public_id}`; receipt.target = "_blank"; receipt.rel = "noopener"; actions.append(receipt); }
        actions.append(button("Новый чек +", "primary wide", newOrder));
      }
      if (busy) $$("button", actions).forEach(node => { node.disabled = true; });
    }
    categories = await allCategories(); chips(); await products();
    const state = await api(`/public/terminals/${terminal}/display`);
    if (state.order) order = await api(`/orders/${state.order.public_id}`);
    renderOrder(); focusScan();
    document.addEventListener("pointerup", event => {
      if (!event.target.closest("input, textarea, select, button, a, dialog")) focusScan();
    });
    setInterval(async () => {
      if (pollBusy || busy || document.hidden) return;
      pollBusy = true;
      try {
        if (order) { const latest = await api(`/orders/${order.public_id}`); if (!$("#order-items").contains(document.activeElement)) { order = latest; renderOrder(); } }
        else { const state = await api(`/public/terminals/${terminal}/display`); if (state.order) { order = await api(`/orders/${state.order.public_id}`); renderOrder(); } }
      } catch (error) { notice(error.message, true); } finally { pollBusy = false; }
    }, 1500);
  }

  async function initDisplay() {
    const terminal = document.body.dataset.terminal;
    let busy = false, signature = "";
    async function refresh() {
      if (busy) return; busy = true;
      try {
        const state = await api(`/public/terminals/${encodeURIComponent(terminal)}/display`);
        $("#connection-status").textContent = "Обновление каждые 1,5 секунды";
        $("#display-idle").hidden = !!state.order; $("#display-order").hidden = !state.order;
        if (!state.order) return;
        const order = state.order;
        $("#display-order-number").textContent = `Чек № ${order.number}`;
        $("#display-item-count").textContent = `${order.items.length} поз.`;
        $("#display-total").textContent = money(order.total_minor);
        const newSignature = JSON.stringify({...state, seconds_left: 0, qr_usable: state.seconds_left > 0, payment: state.payment ? {...state.payment, seconds_left: 0} : null, order: {...order, payment: order.payment ? {...order.payment, seconds_left: 0} : null}});
        if (signature !== newSignature) { readonlyItems($("#display-items"), order.items); paymentContent($("#display-payment"), order, state.payment, {display: true}); signature = newSignature; }
        const timer = $("[data-timer]"); if (timer) timer.textContent = timerText(state.seconds_left);
      } catch { $("#connection-status").textContent = "Связь прервана. Восстанавливаем…"; } finally { busy = false; }
    }
    await refresh(); setInterval(refresh, 1500);
  }

  async function initPriceCheck() {
    let selected = "", search = "", offset = 0, currentRequest = 0;
    const categories = await allCategories(true);
    function chips() { categoryChips($("#price-categories"), categories, selected, async value => { selected = value; offset = 0; chips(); await load(); }); }
    async function load() {
      const id = ++currentRequest;
      const query = new URLSearchParams({limit: "20", offset: String(offset), include_subcategories: "true"});
      if (selected) query.set("category_id", selected);
      if (search) query.set(/^([0-9]{8}|[0-9]{13})$/.test(search) ? "barcode" : "q", search);
      const data = await api(`/public/products?${query}`); if (id !== currentRequest) return;
      $("#price-heading").textContent = search ? "Результаты поиска" : "Товары магазина";
      $("#price-count").textContent = `Найдено: ${data.total}`;
      $("#price-results").replaceChildren(...data.items.map(item => productCard(item)));
      if (!data.items.length) $("#price-results").append(element("p", "empty-note", "Не нашли такой товар. Проверьте штрихкод или попробуйте другое название."));
      pagination($("#price-pagination"), data, async value => { offset = value; await load(); });
    }
    bindForm("#price-search-form", async () => { search = $("#price-search").value.trim(); offset = 0; await load(); $("#price-search").select(); });
    $("#price-search").addEventListener("input", debounce(async () => { search = $("#price-search").value.trim(); offset = 0; await load(); }, 350));
    chips(); await load();
  }

  async function initReceipt() {
    const data = await api(`/orders/${document.body.dataset.order}/receipt`);
    const content = $("#receipt-content"); content.replaceChildren();
    const meta = element("div", "receipt-meta");
    meta.append(element("p", "", `Чек № ${data.number}`), element("p", "", `${dateTime(data.paid_at || data.created_at)} · ${timezone}`), element("p", "", `Терминал: ${data.terminal_code}`)); content.append(meta);
    data.items.forEach(item => {
      const row = element("div", "receipt-line"), detail = element("div"); row.append(element("strong", "", item.product_name));
      detail.append(element("span", "", `${quantity(item)} × ${money(item.unit_price_minor)}/${unit(item.unit)}`), element("span", "", money(item.line_total_minor))); row.append(detail); content.append(row);
    });
    const total = element("div", "receipt-total"); total.append(element("span", "", "ИТОГО"), element("span", "", money(data.total_minor))); content.append(total, element("p", "", `Оплата: ${data.payment_method} · ${labels[data.status] || data.status}`));
    $("#print-receipt").disabled = false; $("#print-receipt").addEventListener("click", () => window.print());
  }

  async function initAdmin() {
    let categories = await allCategories(), productOffset = 0, stockOffset = 0, reviewOffset = 0, currentProduct = null;
    const productForm = $("#product-form"), categoryForm = $("#category-form"), stockForm = $("#stock-form");
    function cell(value, className = "") { return element("td", className, value); }
    function noRows(body, columns, message = "Записей пока нет.") { if (!body.children.length) { const row = element("tr"), td = cell(message, "table-empty"); td.colSpan = columns; row.append(td); body.append(row); } }
    function fillCategories(select, selected = "", includeRoot = false, exclude = "") {
      select.replaceChildren();
      const empty = element("option", "", includeRoot ? "Без родителя" : "Выберите категорию"); empty.value = ""; select.append(empty);
      categoryTree(categories).filter(item => item.public_id !== exclude).forEach(item => { const option = element("option", "", `${"— ".repeat(Math.min(item.depth, 6))}${item.name}${item.is_active ? "" : " (неактивна)"}`); option.value = item.public_id; select.append(option); }); select.value = selected || "";
    }
    function openProduct(product = null) {
      currentProduct = product; productForm.reset(); const fields = productForm.elements;
      fields.public_id.value = product?.public_id || ""; fields.name.value = product?.name || ""; fields.barcode.value = product?.barcode || ""; fields.unit.value = product?.unit || "PIECE";
      fields.price.value = moneyInput(product?.price_minor || 0); fields.stock_quantity.value = product?.stock_quantity || 0; fields.min_stock_quantity.value = product?.min_stock_quantity || 0;
      fields.description.value = product?.description || ""; fields.is_active.checked = product?.is_active ?? true;
      fillCategories(fields.category_id, product?.category_id); $("#initial-stock-label").hidden = !!product;
      $("#product-dialog-title").textContent = product ? "Изменить товар" : "Новый товар"; $("#product-dialog").showModal(); fields.name.focus();
    }
    function openCategory(category = null) {
      categoryForm.reset(); const fields = categoryForm.elements;
      fields.public_id.value = category?.public_id || ""; fields.name.value = category?.name || ""; fields.slug.value = category?.slug || ""; fields.sort_order.value = category?.sort_order || 0; fields.is_active.checked = category?.is_active ?? true;
      fillCategories(fields.parent_id, category?.parent_id, true, category?.public_id); $("#category-dialog-title").textContent = category ? "Изменить категорию" : "Новая категория"; $("#category-dialog").showModal(); fields.name.focus();
    }
    function openStock(product) {
      stockForm.reset(); stockForm.elements.public_id.value = product.public_id;
      $("#stock-product-name").textContent = `${product.name} · изменение в ${amountUnit(product.unit)}. Доступно: ${product.available_quantity}.`;
      $("#stock-dialog").showModal(); stockForm.elements.delta.focus();
    }
    async function products() {
      const query = new URLSearchParams({limit: "20", offset: String(productOffset)}), search = $("#admin-product-search").value.trim(), active = $("#admin-product-active").value;
      if (search) query.set("q", search); if (active) query.set("is_active", active);
      const page = await api(`/products?${query}`), body = $("#admin-products"); body.replaceChildren();
      page.items.forEach(product => {
        const row = element("tr"), title = cell(product.name); title.append(element("small", "", product.barcode));
        const activeCell = cell(""); activeCell.append(element("span", `status ${product.is_active ? "" : "muted-status"}`, product.is_active ? "Активен" : "Скрыт"));
        const actions = element("div", "actions"); actions.append(button("Изменить", "secondary small", () => openProduct(product)), button("Остаток", "secondary small", () => openStock(product)));
        if (product.is_active) actions.append(button("Скрыть", "ghost small", async () => { if (confirm(`Скрыть товар «${product.name}» с кассы?`)) { await api(`/products/${product.public_id}`, {method: "DELETE"}); await products(); notice("Товар скрыт."); } }));
        const actionCell = cell(""); actionCell.append(actions);
        row.append(title, cell(`${money(product.price_minor)} / ${unit(product.unit)}`, "money-cell"), cell(`${product.stock_quantity} / ${product.available_quantity} ${amountUnit(product.unit)}`), activeCell, actionCell); body.append(row);
      }); noRows(body, 5); pagination($("#admin-pagination"), page, async value => { productOffset = value; await products(); });
    }
    function renderCategories() {
      const body = $("#admin-categories"); body.replaceChildren();
      categoryTree(categories).forEach(category => {
        const row = element("tr"), name = cell(`${"↳ ".repeat(Math.min(category.depth, 5))}${category.name}`), actions = element("div", "actions");
        actions.append(button("Изменить", "secondary small", () => openCategory(category)));
        if (category.is_active) actions.append(button("Скрыть", "ghost small", async () => { if (confirm(`Деактивировать категорию «${category.name}»?`)) { await api(`/categories/${category.public_id}`, {method: "DELETE"}); categories = await allCategories(); renderCategories(); } }));
        const actionCell = cell(""); actionCell.append(actions); row.append(name, cell(category.slug), cell(category.sort_order), cell(category.is_active ? "Активна" : "Скрыта"), actionCell); body.append(row);
      }); noRows(body, 5);
    }
    bindForm("#product-form", async form => {
      const f = form.elements, id = f.public_id.value;
      const data = {name: f.name.value, barcode: f.barcode.value.trim(), category_id: f.category_id.value, unit: f.unit.value, min_stock_quantity: integer(f.min_stock_quantity.value), description: f.description.value || null, is_active: f.is_active.checked};
      if (!id || !currentProduct || f.price.value !== moneyInput(currentProduct.price_minor)) data.price_minor = parsePrice(f.price.value);
      if (!id) data.stock_quantity = integer(f.stock_quantity.value);
      await api(id ? `/products/${id}` : "/products", {method: id ? "PATCH" : "POST", body: data}); $("#product-dialog").close(); await products(); notice("Товар сохранён.");
    });
    bindForm("#category-form", async form => {
      const f = form.elements, id = f.public_id.value;
      const data = {name: f.name.value, slug: f.slug.value, parent_id: f.parent_id.value || null, sort_order: integer(f.sort_order.value, -2147483648), is_active: f.is_active.checked};
      await api(id ? `/categories/${id}` : "/categories", {method: id ? "PATCH" : "POST", body: data}); $("#category-dialog").close(); categories = await allCategories(); renderCategories(); notice("Категория сохранена.");
    });
    bindForm("#stock-form", async form => {
      const f = form.elements, delta = integer(f.delta.value, -2147483647);
      if (!delta) throw new Error("Изменение остатка не может быть равно нулю.");
      if (f.reason.value === "RESTOCK" && delta < 0) throw new Error("Поставка должна увеличивать остаток. Для уменьшения выберите корректировку.");
      await api(`/products/${f.public_id.value}/stock-adjustments`, {method: "POST", body: {delta, reason: f.reason.value}}); $("#stock-dialog").close(); await products(); if (!$("#tab-stock").hidden) await lowStock(); notice("Остаток обновлён.");
    });
    async function sales(useDates = true) {
      const query = new URLSearchParams();
      if (useDates) { query.set("date_from", $("#date-from").value); query.set("date_to", $("#date-to").value); }
      if (useDates && $("#date-from").value > $("#date-to").value) throw new Error("Дата начала должна быть не позже даты окончания.");
      const data = await api(`/reports/sales?${query}`);
      $("#date-from").value = data.date_from; $("#date-to").value = data.date_to;
      $("#report-stats").replaceChildren(...[["Выручка за период", money(data.revenue_minor)], ["Оплаченные чеки", data.orders_count]].map(([title, value]) => { const card = element("div", "stat-card"); card.append(element("span", "", title), element("strong", "", value)); return card; }));
      const daily = $("#report-days"); daily.replaceChildren(...data.days.map(item => { const row = element("tr"); row.append(cell(item.date), cell(item.orders_count), cell(money(item.revenue_minor), "money-cell")); return row; })); noRows(daily, 3, "За этот период нет продаж.");
      const grouped = $("#report-categories"); grouped.replaceChildren(...data.categories.map(item => { const row = element("tr"); row.append(cell(item.name), cell(money(item.revenue_minor), "money-cell")); return row; })); noRows(grouped, 2);
      const sold = $("#report-products"); sold.replaceChildren(...data.products.map(item => { const row = element("tr"); row.append(cell(item.name), cell(quantity(item)), cell(money(item.revenue_minor), "money-cell")); return row; })); noRows(sold, 3);
    }
    async function lowStock() {
      const page = await api(`/reports/low-stock?limit=20&offset=${stockOffset}`), body = $("#low-stock"); body.replaceChildren();
      page.items.forEach(item => { const row = element("tr"), actions = cell(""); actions.append(button("Пополнить", "secondary small", () => openStock(item))); row.append(cell(item.name), cell(`${item.available_quantity} ${amountUnit(item.unit)}`), cell(`${item.min_stock_quantity} ${amountUnit(item.unit)}`), actions); body.append(row); });
      noRows(body, 4, "Всё в порядке — товаров с низким остатком нет."); pagination($("#stock-pagination"), page, async value => { stockOffset = value; await lowStock(); });
    }
    async function review() {
      const page = await api(`/reports/payments-needing-review?limit=20&offset=${reviewOffset}`), body = $("#payment-review"); body.replaceChildren();
      page.items.forEach(item => {
        const row = element("tr"), title = cell(item.public_id.slice(0, 8)); title.append(element("small", "", dateTime(item.created_at)));
        const state = cell(""); state.append(status(item.status)); const actions = cell(""); actions.append(button("Сверить с банком", "secondary small", async () => { await api(`/payments/${item.public_id}/refresh`, {method: "POST"}); await review(); notice("Статус запрошен у банка. Флаг разбора снимается только после проверки причин."); }));
        row.append(title, cell(money(item.amount_minor), "money-cell"), state, cell(item.review_reason || "Требуется ручная проверка.", "review-reason"), actions); body.append(row);
      }); noRows(body, 5, "Спорных платежей нет."); pagination($("#review-pagination"), page, async value => { reviewOffset = value; await review(); });
    }
    $$("[data-tab]").forEach(tab => tab.addEventListener("click", () => safely(async () => {
      const name = tab.dataset.tab;
      $$("[data-tab]").forEach(item => item.setAttribute("aria-selected", String(item === tab)));
      $$("[role=tabpanel]").forEach(panel => { panel.hidden = panel.id !== `tab-${name}`; });
      if (name === "reports") await sales(!!$("#date-from").value); if (name === "stock") await lowStock(); if (name === "review") await review();
    })));
    $("#add-product").addEventListener("click", () => openProduct()); $("#add-category").addEventListener("click", () => openCategory());
    $("#admin-product-search").addEventListener("input", debounce(async () => { productOffset = 0; await products(); }));
    $("#admin-product-active").addEventListener("change", () => safely(async () => { productOffset = 0; await products(); }));
    $("#refresh-stock").addEventListener("click", () => safely(lowStock)); $("#refresh-review").addEventListener("click", () => safely(review));
    bindForm("#report-form", () => sales()); renderCategories(); await products();
  }

  $$("[data-close-dialog]").forEach(node => node.addEventListener("click", () => node.closest("dialog").close()));
  $$("dialog").forEach(dialog => dialog.addEventListener("close", () => $(".dialog-notice", dialog)?.remove()));
  $("#logout")?.addEventListener("click", () => safely(async () => { await api("/auth/logout", {method: "POST"}); window.location.assign("/login"); }));
  const pages = {login: initLogin, cashier: initCashier, display: initDisplay, "price-check": initPriceCheck, receipt: initReceipt, admin: initAdmin};
  safely(() => pages[document.body.dataset.page]?.());
})();
