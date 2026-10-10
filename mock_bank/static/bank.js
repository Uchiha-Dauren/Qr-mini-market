"use strict";
const token = document.body.dataset.token;
const endpoint = `/api/pay/${encodeURIComponent(token)}`;
const account = document.getElementById("account");
const statusBox = document.getElementById("status");
const buttons = ["pay", "cancel", "decline"].map(id => document.getElementById(id));
const money = value => formatBankMoney(value);
let invoice = null;
let pending = false;
const labels = {CREATED:"Выберите счёт для оплаты", PAID:"Оплата прошла. Спасибо за покупку!", FAILED:"Оплата отклонена", EXPIRED:"Срок действия счёта истёк", CANCELLED:"Оплата отменена"};
const reasons = {insufficient_funds:"Недостаточно средств на демо-счёте", bank_declined:"Банк отклонил оплату"};
function render(data) {
  invoice = data;
  document.getElementById("amount").textContent = money(data.amount_minor_text);
  statusBox.textContent = reasons[data.failure_reason] || labels[data.status] || "Неизвестный статус";
  statusBox.className = data.status === "PAID" ? "success" : data.status === "CREATED" ? "" : "error";
  if (data.accounts) {
    const previous = account.value;
    account.replaceChildren(...data.accounts.map(item => {
      const option = document.createElement("option");
      option.value = item.public_id;
      option.textContent = `${item.holder_name} — ${money(item.balance_minor_text)}`;
      return option;
    }));
    if (Array.from(account.options).some(option => option.value === previous)) account.value = previous;
    if (!data.accounts.length) statusBox.textContent = "Демо-счета пока не созданы. Сообщите кассиру.";
  }
  updateButtons();
  tick();
}
function updateButtons() {
  const blocked = pending || !invoice || invoice.status !== "CREATED";
  buttons.forEach(button => { button.disabled = blocked; });
  buttons[0].disabled = blocked || !account.value;
  account.disabled = blocked;
}
function tick() {
  if (!invoice) return;
  const seconds = Math.max(0, Math.ceil((Date.parse(invoice.expires_at) - Date.now()) / 1000));
  document.getElementById("timer").textContent = invoice.status === "CREATED" ? `Осталось ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}` : "Счёт завершён";
  if (seconds === 0 && invoice.status === "CREATED") buttons[0].disabled = true;
}
async function request(path, options={}) {
  const response = await fetch(path, {...options, headers:{"Content-Type":"application/json"}, cache:"no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || "Не удалось выполнить запрос");
  return data;
}
async function load() {
  if (pending) return;
  try { render(await request(endpoint)); }
  catch (error) { statusBox.textContent = error.message || "Банк недоступен. Повторите позже."; statusBox.className = "error"; }
}
async function action(suffix, body) {
  if (pending) return;
  pending = true; updateButtons();
  try { render(await request(endpoint + suffix, {method:"POST", ...(body ? {body:JSON.stringify(body)} : {})})); }
  catch (error) { statusBox.textContent = error.message || "Проверьте соединение"; statusBox.className = "error"; }
  finally { pending = false; updateButtons(); }
}
document.getElementById("pay-form").addEventListener("submit", event => {event.preventDefault(); action("", {account_id:account.value});});
document.getElementById("cancel").addEventListener("click", () => action("/cancel"));
document.getElementById("decline").addEventListener("click", () => action("/decline"));
load(); setInterval(tick, 1000); setInterval(load, 2500);
