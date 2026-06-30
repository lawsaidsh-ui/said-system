document.addEventListener("click", (event) => {
  const overdueWhatsAppButton = event.target.closest("[data-overdue-whatsapp]");
  if (overdueWhatsAppButton) {
    openOverdueWhatsAppReminder(overdueWhatsAppButton);
    return;
  }

  const whatsappButton = event.target.closest("[data-whatsapp-source-type]");
  if (whatsappButton) {
    openWhatsAppDialog(whatsappButton);
    return;
  }

  const tab = event.target.closest("[data-tab-target]");
  if (tab) {
    const tabs = tab.closest("[data-tabs]");
    const name = tab.getAttribute("data-tab-target");
    if (!tabs || !name) return;

    const scope = tabs.parentElement || document;
    scope.querySelectorAll("[data-tab-target]").forEach((item) => {
      item.classList.toggle("active", item === tab);
      item.setAttribute("aria-selected", item === tab ? "true" : "false");
    });
    scope.querySelectorAll("[data-tab-panel]").forEach((panel) => {
      panel.classList.toggle("hidden", panel.getAttribute("data-tab-panel") !== name);
    });
    history.replaceState(null, "", `#${name}`);
    return;
  }

  const sidebarToggle = event.target.closest("[data-sidebar-toggle]");
  if (sidebarToggle) {
    document.body.classList.toggle("sidebar-open");
    return;
  }

  if (event.target.closest("[data-sidebar-close]") || event.target.closest(".nav-link")) {
    document.body.classList.remove("sidebar-open");
  }

  const target = event.target.closest("[data-confirm]");
  if (!target) return;
  if (!confirm(target.getAttribute("data-confirm"))) {
    event.preventDefault();
  }
});

document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-open-dialog]");
  if (opener) {
    const dialog = document.getElementById(opener.getAttribute("data-open-dialog"));
    if (dialog && dialog.showModal) dialog.showModal();
  }
  if (event.target.closest("[data-close-dialog]")) {
    event.target.closest("dialog")?.close();
  }
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-whatsapp-open]")) {
    submitWhatsAppAttempt("opened");
  }
  if (event.target.closest("[data-whatsapp-cancel]")) {
    submitWhatsAppAttempt("cancelled");
  }
});

document.addEventListener("change", (event) => {
  if (event.target.matches("[data-whatsapp-template]")) {
    const selected = event.target.selectedOptions[0];
    const message = document.querySelector("[data-whatsapp-message]");
    if (message && selected) message.value = selected.dataset.message || "";
  }
});

document.addEventListener("change", (event) => {
  if (event.target.matches("[data-client-filter-source]")) {
    updateClientScopedOptions(event.target.dataset.clientFilterSource);
  }
  if (event.target.matches('input[name="client_mode"]')) {
    updateMatterClientMode();
  }
  if (event.target.matches('input[name="ministry_case_mode"]')) {
    updateMinistryCaseMode();
  }
  if (event.target.matches('select[name="new_client_type"]')) {
    updateNewClientTypeFields();
  }
  if (event.target.matches("[data-case-fee-payment-plan]")) {
    updateCaseFeeForm(event.target.closest("[data-case-fee-form]"));
  }
  if (event.target.matches("[data-session-matter-select]")) {
    updateSessionCourtFromMatter(event.target);
  }
  if (event.target.matches("[data-date-quality-status]")) {
    updateDateQualityForm(event.target.closest("[data-date-quality-form]"));
  }
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-case-fee-form]");
  if (!form) return;
  const checked = form.querySelectorAll('input[name="matter_ids"]:checked:not(:disabled)');
  if (!checked.length) {
    event.preventDefault();
    alert("اختر قضية واحدة على الأقل.");
  }
});

document.addEventListener("input", (event) => {
  if (event.target.matches("[data-client-search]")) {
    updateClientSearch(event.target);
  }
  if (event.target.matches("[data-matter-client-search]")) {
    updateMatterClientSearch(event.target);
  }
});

document.addEventListener("click", (event) => {
  const clientResult = event.target.closest("[data-client-search-result]");
  if (clientResult) {
    const form = clientResult.closest("form");
    const input = form?.querySelector("[data-client-search]");
    const select = form?.querySelector("[data-client-search-select]");
    if (!form || !input || !select) return;

    input.value = clientResult.dataset.clientLabel || "";
    input.dataset.selectedClientLabel = input.value;
    select.value = clientResult.dataset.clientId || "";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    form.querySelector("[data-client-search-results]")?.classList.add("hidden");
    return;
  }

  const result = event.target.closest("[data-matter-client-result]");
  if (!result) return;

  const form = result.closest("form");
  const input = form?.querySelector("[data-matter-client-search]");
  if (!form || !input) return;

  input.value = result.dataset.clientLabel || "";
  filterMatterSearchOptions(form, result.dataset.clientId || "", "", true);
  filterMatterChecklist(form, result.dataset.clientId || "", "", true);
  form.querySelector("[data-matter-client-results]")?.classList.add("hidden");
});

function normalizeSearchText(value) {
  return (value || "")
    .toString()
    .trim()
    .replace(/[أإآ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .toLowerCase();
}

function updateClientSearch(input) {
  const form = input.closest("form");
  if (!form) return;

  const query = normalizeSearchText(input.value);
  const results = form.querySelector("[data-client-search-results]");
  const select = form.querySelector("[data-client-search-select]");
  if (!results || !select) return;

  if (input.dataset.selectedClientLabel && normalizeSearchText(input.value) !== normalizeSearchText(input.dataset.selectedClientLabel)) {
    delete input.dataset.selectedClientLabel;
    select.value = "";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  results.innerHTML = "";
  if (!query) {
    delete input.dataset.selectedClientLabel;
    select.value = "";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    results.classList.add("hidden");
    return;
  }

  const matches = [];
  select.querySelectorAll("option[data-client-id]").forEach((option) => {
    const haystack = normalizeSearchText(
      [
        option.dataset.clientName,
        option.dataset.clientPhone,
        option.dataset.clientCivilId,
        option.dataset.clientCompany,
      ].join(" ")
    );
    if (!haystack.includes(query)) return;
    matches.push({
      id: option.dataset.clientId || option.value,
      name: option.dataset.clientName || option.textContent.trim(),
      phone: option.dataset.clientPhone || "",
      civilId: option.dataset.clientCivilId || "",
    });
  });

  matches.slice(0, 8).forEach((client) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "autocomplete-result";
    button.dataset.clientSearchResult = "1";
    button.dataset.clientId = client.id;
    button.dataset.clientLabel = client.phone ? `${client.name} - ${client.phone}` : client.name;
    const name = document.createElement("strong");
    name.textContent = client.name;
    const meta = document.createElement("small");
    meta.textContent = [client.phone || "بدون رقم", client.civilId].filter(Boolean).join(" · ");
    button.append(name, meta);
    results.appendChild(button);
  });

  results.classList.toggle("hidden", !matches.length);
}

function updateMatterClientSearch(input) {
  const form = input.closest("form");
  if (!form) return;

  const query = normalizeSearchText(input.value);
  const results = form.querySelector("[data-matter-client-results]");
  const select = form.querySelector("[data-matter-search-select]");
  if (!results || !select) return;

  filterMatterSearchOptions(form, "", query);
  filterMatterChecklist(form, "", query);
  results.innerHTML = "";
  if (!query) {
    results.classList.add("hidden");
    return;
  }

  const clients = new Map();
  select.querySelectorAll("option[data-client-id]").forEach((option) => {
    const haystack = normalizeSearchText(
      [
        option.dataset.clientName,
        option.dataset.clientPhone,
        option.dataset.caseNumber,
        option.dataset.ministryCaseNumber,
        option.dataset.title,
      ].join(" ")
    );
    if (!haystack.includes(query)) return;
    const clientId = option.dataset.clientId || "";
    if (!clients.has(clientId)) {
      clients.set(clientId, {
        id: clientId,
        name: option.dataset.clientName || "عميل بدون اسم",
        phone: option.dataset.clientPhone || "",
        count: 0,
      });
    }
    clients.get(clientId).count += 1;
  });

  [...clients.values()].slice(0, 8).forEach((client) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "autocomplete-result";
    button.dataset.matterClientResult = "1";
    button.dataset.clientId = client.id;
    button.dataset.clientLabel = client.phone ? `${client.name} - ${client.phone}` : client.name;
    const name = document.createElement("strong");
    name.textContent = client.name;
    const meta = document.createElement("small");
    meta.textContent = `${client.phone || "بدون رقم"} · ${client.count} قضية`;
    button.append(name, meta);
    results.appendChild(button);
  });

  results.classList.toggle("hidden", !clients.size);
}

function optionSearchText(option) {
  return normalizeSearchText(
    [
      option.dataset.clientName,
      option.dataset.clientPhone,
      option.dataset.caseNumber,
      option.dataset.ministryCaseNumber,
      option.dataset.title,
    ].join(" ")
  );
}

function filterMatterSearchOptions(form, clientId, query, autoSelect = false) {
  const select = form.querySelector("[data-matter-search-select]");
  if (!select) return;

  const normalizedQuery = normalizeSearchText(query);
  let firstVisible = "";
  let selectedIsVisible = !select.value;
  const isMultiple = select.multiple;

  select.querySelectorAll("option").forEach((option) => {
    if (!option.dataset.clientId) {
      option.hidden = false;
      option.disabled = false;
      return;
    }
    const matchesClient = clientId ? option.dataset.clientId === clientId : true;
    const haystack = optionSearchText(option);
    const matchesQuery = normalizedQuery ? haystack.includes(normalizedQuery) : true;
    const visible = matchesClient && matchesQuery;
    option.hidden = !visible;
    option.disabled = !visible;
    if (visible && !firstVisible) firstVisible = option.value;
    if (option.selected && visible) selectedIsVisible = true;
  });

  if (isMultiple) {
    if (autoSelect && firstVisible) {
      select.querySelectorAll("option").forEach((option) => {
        option.selected = option.value === firstVisible;
      });
    }
    return;
  }

  if ((autoSelect || !selectedIsVisible) && firstVisible) {
    select.value = firstVisible || "";
    updateSessionCourtFromMatter(select);
  } else if (!selectedIsVisible) {
    select.value = "";
  }
}

function filterMatterChecklist(form, clientId, query, autoCheck = false) {
  const checklist = form.querySelector("[data-matter-checklist]");
  if (!checklist) return;

  const normalizedQuery = normalizeSearchText(query);
  let firstVisibleInput = null;
  let visibleCount = 0;

  checklist.querySelectorAll("[data-client-id]").forEach((item) => {
    const input = item.querySelector('input[name="matter_ids"]');
    const matchesClient = clientId ? item.dataset.clientId === clientId : true;
    const haystack = optionSearchText(item);
    const matchesQuery = normalizedQuery ? haystack.includes(normalizedQuery) : true;
    const visible = matchesClient && matchesQuery;
    item.classList.toggle("hidden", !visible);
    if (input) input.disabled = !visible;
    if (visible) {
      visibleCount += 1;
      if (!firstVisibleInput) firstVisibleInput = input;
    } else if (input) {
      input.checked = false;
    }
  });

  if (autoCheck && firstVisibleInput) {
    checklist.querySelectorAll('input[name="matter_ids"]').forEach((input) => {
      input.checked = input === firstVisibleInput;
    });
  }

  checklist.classList.toggle("is-filtered", visibleCount > 0);
}

function updateSessionCourtFromMatter(select) {
  const form = select.closest("[data-session-form]");
  const court = form?.querySelector('input[name="court_name"]');
  const selected = select.selectedOptions[0];
  if (!court || !selected) return;
  if (!court.value && selected.dataset.courtName) court.value = selected.dataset.courtName;
}

function updateClientScopedOptions(scopeName) {
  if (!scopeName) return;
  const source = [...document.querySelectorAll("[data-client-filter-source]")].find(
    (element) => element.dataset.clientFilterSource === scopeName
  );
  if (!source) return;

  const clientId = source.value || "";
  document.querySelectorAll("[data-client-filter-target]").forEach((target) => {
    if (target.dataset.clientFilterTarget !== scopeName) return;
    let selectedOptionIsValid = !target.value;

    target.querySelectorAll("option").forEach((option) => {
      const optionClientId = option.dataset.clientId;
      if (!optionClientId) {
        option.hidden = false;
        option.disabled = false;
        return;
      }

      const isVisible = clientId ? optionClientId === clientId : !target.hasAttribute("data-empty-without-client");
      option.hidden = !isVisible;
      option.disabled = !isVisible;
      if (option.selected && isVisible) selectedOptionIsValid = true;
    });

    if (!selectedOptionIsValid) {
      target.value = "";
    }
  });
}

function updateMatterClientMode() {
  const selected = document.querySelector('input[name="client_mode"]:checked');
  const mode = selected?.value || "existing";
  const existing = document.querySelector("[data-client-existing]");
  const nextClient = document.querySelector("[data-client-new]");

  if (existing) {
    existing.classList.toggle("hidden", mode !== "existing");
    existing.querySelectorAll("select, input, textarea").forEach((field) => {
      field.disabled = mode !== "existing";
      if (field.name === "client_id") field.required = mode === "existing";
    });
  }

  if (nextClient) {
    nextClient.classList.toggle("hidden", mode !== "new");
    nextClient.querySelectorAll("select, input, textarea").forEach((field) => {
      field.disabled = mode !== "new";
      if (field.name === "new_client_full_name") field.required = mode === "new";
    });
  }
  updateNewClientTypeFields();
}

function setFieldGroupEnabled(group, enabled) {
  group.classList.toggle("hidden", !enabled);
  group.querySelectorAll("select, input, textarea").forEach((field) => {
    field.disabled = !enabled;
    field.required = false;
  });
}

function updateNewClientTypeFields() {
  const newClient = document.querySelector("[data-client-new]");
  const typeSelect = document.querySelector('select[name="new_client_type"]');
  if (!newClient || !typeSelect || newClient.classList.contains("hidden")) return;

  const isCompany = typeSelect.value === "company";
  document.querySelectorAll("[data-new-client-individual]").forEach((group) => {
    setFieldGroupEnabled(group, !isCompany);
  });
  document.querySelectorAll("[data-new-client-company]").forEach((group) => {
    setFieldGroupEnabled(group, isCompany);
  });
}

function updateMinistryCaseMode() {
  const selected = document.querySelector('input[name="ministry_case_mode"]:checked');
  const mode = selected?.value || "existing";
  const wrapper = document.querySelector("[data-ministry-case-number]");
  if (!wrapper || !selected) return;

  const input = wrapper.querySelector("input");
  wrapper.classList.toggle("hidden", mode !== "existing");
  if (input) {
    input.disabled = mode !== "existing";
    input.required = mode === "existing";
  }
}

function updateCaseFeeForm(form) {
  if (!form) return;
  const plan = form.querySelector("[data-case-fee-payment-plan]")?.value || "one_time";
  const visibleTokensByPlan = {
    one_time: new Set(["standard"]),
    installments: new Set(["standard", "installments"]),
    success_fee: new Set(["success"]),
    advance_success_fee: new Set(["success", "success_advance"]),
    advance_judgment: new Set(["judgment"]),
  };
  const visibleTokens = visibleTokensByPlan[plan] || visibleTokensByPlan.one_time;

  form.querySelectorAll("[data-case-fee-field]").forEach((group) => {
    const tokens = (group.dataset.caseFeeField || "").split(/\s+/).filter(Boolean);
    const isVisible = tokens.some((token) => visibleTokens.has(token));
    group.classList.toggle("hidden", !isVisible);
    group.querySelectorAll("input, select, textarea").forEach((field) => {
      field.disabled = !isVisible;
      const requiredFor = (field.dataset.requiredFor || "").split(/\s+/).filter(Boolean);
      field.required = isVisible && requiredFor.includes(plan);
    });
  });

  form.querySelectorAll("[data-case-fee-note]").forEach((note) => {
    note.classList.toggle("hidden", note.dataset.caseFeeNote !== plan);
  });
}

function updateDateQualityForm(form) {
  if (!form) return;
  const status = form.querySelector("[data-date-quality-status]")?.value || "confirmed";
  const dateInput = form.querySelector("[data-date-quality-date]");
  const noteWrap = form.querySelector("[data-date-quality-note-wrap]");
  const noteInput = form.querySelector("[data-date-quality-note]");

  if (dateInput) {
    dateInput.required = status !== "unknown";
    dateInput.disabled = status === "unknown";
    if (status === "unknown") dateInput.value = "";
  }
  if (noteWrap) {
    noteWrap.classList.toggle("hidden", status === "confirmed");
  }
  if (noteInput) {
    noteInput.required = status === "estimated";
    if (status === "confirmed") noteInput.value = "";
  }
}

let whatsappState = null;

function whatsappDialog() {
  return document.querySelector("[data-whatsapp-dialog]");
}

function setWhatsAppError(message) {
  const error = document.querySelector("[data-whatsapp-error]");
  if (!error) return;
  error.textContent = message || "";
  error.classList.toggle("hidden", !message);
}

async function openWhatsAppDialog(button) {
  const sourceType = button.dataset.whatsappSourceType;
  const sourceId = button.dataset.whatsappSourceId;
  const dialog = whatsappDialog();
  if (!dialog || !sourceType || !sourceId) return;

  setWhatsAppError("");
  const select = dialog.querySelector("[data-whatsapp-template]");
  const message = dialog.querySelector("[data-whatsapp-message]");
  const phone = dialog.querySelector("[data-whatsapp-phone]");
  const recipient = dialog.querySelector("[data-whatsapp-recipient]");
  if (select) select.innerHTML = '<option value="">جاري تحميل القوالب...</option>';
  if (message) message.value = "";
  if (phone) phone.value = "";
  if (recipient) recipient.textContent = "جاري تحميل بيانات العميل...";
  dialog.showModal();

  try {
    const response = await fetch(`/whatsapp/compose?source_type=${encodeURIComponent(sourceType)}&source_id=${encodeURIComponent(sourceId)}`);
    if (!response.ok) throw new Error("compose");
    const data = await response.json();
    whatsappState = data;
    if (recipient) recipient.textContent = `${data.client_name || "-"} · ${data.phone_clean || data.phone_raw || "لا يوجد رقم"}`;
    if (phone) phone.value = data.phone_clean || data.phone_raw || "";
    if (select) {
      select.innerHTML = "";
      data.templates.forEach((template) => {
        const option = document.createElement("option");
        option.value = template.id;
        option.textContent = template.name;
        option.dataset.message = template.rendered;
        select.appendChild(option);
      });
      if (!data.templates.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "لا توجد قوالب فعالة";
        select.appendChild(option);
      }
    }
    if (message) message.value = data.templates[0]?.rendered || "";
    setWhatsAppError(data.phone_error || "");
  } catch {
    whatsappState = null;
    setWhatsAppError("تعذر تحميل بيانات واتساب.");
  }
}

async function submitWhatsAppAttempt(status) {
  const dialog = whatsappDialog();
  if (!dialog || !whatsappState) {
    dialog?.close();
    return;
  }
  const select = dialog.querySelector("[data-whatsapp-template]");
  const message = dialog.querySelector("[data-whatsapp-message]");
  const body = new URLSearchParams();
  body.set("source_type", whatsappState.source_type);
  body.set("source_id", whatsappState.source_id);
  body.set("template_id", select?.value || "");
  body.set("message", message?.value || "");
  body.set("status", status);

  try {
    const response = await fetch("/whatsapp/log", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setWhatsAppError(data.detail || "تعذر تسجيل محاولة واتساب.");
      return;
    }
    if (status === "opened" && data.url) {
      window.open(data.url, "_blank", "noopener");
    }
    whatsappState = null;
    dialog.close();
  } catch {
    setWhatsAppError("تعذر الاتصال بالخادم.");
  }
}

async function openOverdueWhatsAppReminder(button) {
  const sourceType = button.dataset.sourceType;
  const sourceId = button.dataset.sourceId;
  if (!sourceType || !sourceId) return;

  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "جاري فتح واتساب...";

  const body = new URLSearchParams();
  body.set("source_type", sourceType);
  body.set("source_id", sourceId);

  try {
    const response = await fetch("/accounting/overdue-clients/whatsapp-reminder", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      alert(data.detail || "تعذر فتح تذكير واتساب.");
      return;
    }
    if (data.url) {
      window.open(data.url, "_blank", "noopener");
    }
  } catch {
    alert("تعذر الاتصال بالخادم.");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-client-filter-source]").forEach((source) => {
    updateClientScopedOptions(source.dataset.clientFilterSource);
  });
  updateMatterClientMode();
  updateMinistryCaseMode();
  document.querySelectorAll("[data-case-fee-form]").forEach(updateCaseFeeForm);
  document.querySelectorAll("[data-date-quality-form]").forEach(updateDateQualityForm);
  document.querySelectorAll("[data-session-form]").forEach((form) => {
    const select = form.querySelector("[data-session-matter-select]");
    if (select) updateSessionCourtFromMatter(select);
  });
  const whatsAppDialogElement = whatsappDialog();
  if (whatsAppDialogElement) {
    whatsAppDialogElement.addEventListener("cancel", (event) => {
      event.preventDefault();
      submitWhatsAppAttempt("cancelled");
    });
  }

  const activateTabFromHash = () => {
    const name = decodeURIComponent(window.location.hash.replace("#", ""));
    if (!name) return;
    document.querySelector(`[data-tab-target="${CSS.escape(name)}"]`)?.click();
  };
  activateTabFromHash();

  const state = document.querySelector("[data-api-state]");
  if (state) {
    fetch(`/owner-financial/api/summary${window.location.search}`)
      .then((response) => {
        if (!response.ok) throw new Error("api");
        state.textContent = "تم تحميل بيانات API بنجاح.";
      })
      .catch(() => {
        state.textContent = "تعذر الاتصال بواجهة API. البيانات المعروضة من الخادم.";
        state.classList.add("text-red-700");
      });
  }

  const exportButton = document.querySelector("[data-export-excel]");
  if (exportButton) {
    exportButton.addEventListener("click", () => {
      const table = document.querySelector("[data-export-table]");
      if (!table) return;
      const rows = [...table.querySelectorAll("tr")].map((row) =>
        [...row.children].map((cell) => `"${cell.innerText.replaceAll('"', '""')}"`).join(",")
      );
      const blob = new Blob(["\ufeff" + rows.join("\n")], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "owner-financial-report.csv";
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }

  if (!window.Chart || !window.ownerFinancialCharts) return;
  const data = window.ownerFinancialCharts;
  const palette = ["#0f2742", "#c9a646", "#15803d", "#b91c1c", "#1d4ed8", "#64748b", "#92400e"];
  const makeChart = (id, config) => {
    const canvas = document.getElementById(id);
    if (canvas) new Chart(canvas, config);
  };
  makeChart("revenueExpenseChart", {
    type: "bar",
    data: { labels: data.months, datasets: [{ label: "الإيرادات", data: data.monthly_revenue, backgroundColor: "#0f2742" }, { label: "المصاريف", data: data.monthly_expenses, backgroundColor: "#c9a646" }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
  makeChart("profitChart", {
    type: "line",
    data: { labels: data.months, datasets: [{ label: "صافي الربح", data: data.monthly_profit, borderColor: "#15803d", backgroundColor: "rgba(21,128,61,.12)", tension: .25, fill: true }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
  makeChart("serviceChart", {
    type: "doughnut",
    data: { labels: data.service_labels, datasets: [{ data: data.service_values, backgroundColor: palette }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
  makeChart("expenseChart", {
    type: "doughnut",
    data: { labels: data.expense_labels, datasets: [{ data: data.expense_values, backgroundColor: palette.slice().reverse() }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
  makeChart("collectionChart", {
    type: "line",
    data: { labels: data.collection_labels, datasets: [{ label: "المدفوع", data: data.collection_values, borderColor: "#1d4ed8", backgroundColor: "rgba(29,78,216,.12)", tension: .25, fill: true }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
  makeChart("breakEvenChart", {
    type: "bar",
    data: { labels: ["الحالي", "المتبقي"], datasets: [{ label: "نقطة التعادل", data: data.break_even_values, backgroundColor: ["#15803d", "#b91c1c"] }] },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: "y" }
  });
});
