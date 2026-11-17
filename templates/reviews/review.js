"use strict";
const reviewData = JSON.parse(document.getElementById("review-data").textContent);
let savedReceipt = null;
let submitting = false;
let receiptId = null;
// Store only a lookup handle in this tab, never approvals, comments or tokens.
const receiptStorageKey = 'video-workflow-review-receipt:' + JSON.stringify([
  reviewData.task_id, reviewData.stage, reviewData.language, reviewData.round_id,
  reviewData.version, reviewData.content_sha256, reviewData.entry
]);
function rememberReceipt(id) {
  try { window.sessionStorage.setItem(receiptStorageKey, id); } catch (_) { /* optional tab storage */ }
}
function collectReview() {
  const receipt = {...reviewData, submitted_at: new Date().toISOString(), items: []};
  document.querySelectorAll(".item[data-index]").forEach(card => {
    const source = reviewData.items[Number(card.dataset.index)];
    const decision = card.querySelector("[data-decision]").value;
    const comment = card.querySelector("[data-comment]").value.trim();
    const checks = {};
    card.querySelectorAll("[data-check]").forEach(input => {checks[input.dataset.check] = input.checked;});
    const selected = card.querySelector("[data-selection]");
    if (decision === "approved") {
      if (source.approval_blockers.length) throw Error(source.id + "：独立检查未完成，不能通过");
      if (!source.required_checks.every(k => checks[k] === true)) throw Error(source.id + "：请完成全部关键核对项");
      if (selected && !selected.value) throw Error(source.id + "：请选择 A 或 B");
    }
    if (decision === "needs_changes" && !comment) throw Error(source.id + "：请写明修改意见");
    const item = {id: source.id, version: source.version, content_sha256: source.content_sha256, decision, comment, checks};
    if (selected) item.selected_text = selected.value;
    receipt.items.push(item);
  });
  return receipt;
}
const labels = {received: "已接收，等待处理", processing: "处理中", archiving: "处理结果已保存，归档待完成", completed: "处理完成", failed: "处理失败，可使用同一收据重试"};
function showStatus(result) {
  if (!/^[a-f0-9]{64}$/.test(result.id || '')) throw Error('无效收据编号，状态待核');
  receiptId = result.id;
  rememberReceipt(receiptId);
  document.getElementById("refresh").disabled = !window.REVIEW_TRANSPORT?.status_url;
  document.getElementById("status").textContent = (labels[result.state] || "已接收，处理状态待核") + "\n收据编号：" + result.id;
}
document.getElementById("refresh").addEventListener("click", async () => {
  const transport = window.REVIEW_TRANSPORT;
  if (!receiptId || !transport?.status_url) return;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(transport.status_url + encodeURIComponent(receiptId), {
      headers: {"X-Review-Token": transport.token}, signal: controller.signal});
    const result = await response.json();
    if (!response.ok || result.accepted !== true || result.id !== receiptId) throw Error("状态查询未确认");
    showStatus(result);
  } catch (error) {
    document.getElementById("status").textContent = "状态待核；已保存的收据不受影响。可再次查询。\n收据编号：" + receiptId;
  } finally { clearTimeout(timer); }
});
document.getElementById("submit").addEventListener("click", async () => {
  if (submitting) return;
  const status = document.getElementById("status");
  try {
    savedReceipt = collectReview();
    const transport = window.REVIEW_TRANSPORT;
    if (!transport) throw Error("当前为离线页面，未提交。可下载收据后使用本地接收器导入。");
    submitting = true;
    document.getElementById("submit").disabled = true;
    status.textContent = "正在提交，尚未收到保存确认…";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    let response, result;
    try {
      response = await fetch(transport.submit_url, {method: "POST", headers: {"Content-Type": "application/json", "X-Review-Token": transport.token}, body: JSON.stringify(savedReceipt), signal: controller.signal});
      result = await response.json();
    } finally { clearTimeout(timer); }
    if (!response.ok || result.accepted !== true) throw Error("未确认接收：" + (result.error || response.status));
    showStatus(result);
  } catch (error) {
    status.textContent = "提交未完成或结果待核：" + error.message + "\n意见已保留；结果不明时可重复提交同一结论核对，不会新增生产任务。";
  } finally {
    submitting = false;
    document.getElementById("submit").disabled = false;
  }
});
document.getElementById("download").addEventListener("click", () => {
  try {
    savedReceipt = collectReview();
    const url = URL.createObjectURL(new Blob([JSON.stringify(savedReceipt, null, 2)], {type: "application/json"}));
    const a = document.createElement("a"); a.href = url;
    a.download = "review-" + reviewData.stage + "-" + reviewData.task_id.replace(/[^\w-]/g, "_") + "-" + reviewData.version + ".json";
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById("status").textContent = "收据已导出；下载不代表已提交或已接收。";
  } catch (error) {document.getElementById("status").textContent = error.message;}
});
try {
  const remembered = window.sessionStorage.getItem(receiptStorageKey);
  if (/^[a-f0-9]{64}$/.test(remembered || '')) {
    receiptId = remembered;
    document.getElementById('refresh').disabled = !window.REVIEW_TRANSPORT?.status_url;
    document.getElementById('status').textContent = '已恢复本轮收据编号；当前处理状态待查询。审核选项未自动恢复。\n收据编号：' + receiptId;
  }
} catch (_) { /* Storage restrictions must not block review submission. */ }
