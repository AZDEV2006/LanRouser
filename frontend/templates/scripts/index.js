import { requestJson } from "./shared/api.js";
import {
  renderDevices,
  loadDevices,
  performDeviceAction,
} from "./components/device_list.js";
import { renderHosts, runScan } from "./components/network_scan.js";
import { openRegister, saveDevice } from "./components/register_dialog.js";

const state = {
  devices: [],
  hosts: [],
  statuses: new Map(),
  query: "",
  busy: new Set(),
  lastScan: null,
};
const elements = {
  registeredCount: document.getElementById("registeredCount"),
  onlineCount: document.getElementById("onlineCount"),
  discoveredCount: document.getElementById("discoveredCount"),
  lastScan: document.getElementById("lastScan"),
  deviceBadge: document.getElementById("deviceBadge"),
  scanBadge: document.getElementById("scanBadge"),
  devicesBody: document.getElementById("devicesBody"),
  mobileDeviceList: document.getElementById("mobileDeviceList"),
  scanResults: document.getElementById("scanResults"),
  scanHint: document.getElementById("scanHint"),
  scanButton: document.getElementById("scanButton"),
  scanAgain: document.getElementById("scanAgain"),
  dialog: document.getElementById("registerDialog"),
  form: document.getElementById("registerForm"),
};

function renderAll() {
  renderDevices(state, elements);
  renderHosts(state, elements);
}

function refreshDevices() {
  return loadDevices(state, elements, renderAll);
}

async function checkService() {
  try {
    await requestJson("/health");
    document.getElementById("serviceDot").classList.add("ready");
    document.getElementById("serviceText").textContent = "Service online";
  } catch {
    document.getElementById("serviceDot").classList.add("error");
    document.getElementById("serviceText").textContent = "Service unavailable";
  }
}

document
  .getElementById("openRegister")
  .addEventListener("click", () => openRegister(null, elements));
document
  .getElementById("closeDialog")
  .addEventListener("click", () => elements.dialog.close());
document
  .getElementById("cancelRegister")
  .addEventListener("click", () => elements.dialog.close());
elements.form.addEventListener("submit", (event) =>
  saveDevice(event, elements, refreshDevices),
);
elements.scanButton.addEventListener("click", () => runScan(state, elements));
elements.scanAgain.addEventListener("click", () => runScan(state, elements));
document
  .getElementById("refreshDevices")
  .addEventListener("click", refreshDevices);
document.getElementById("deviceSearch").addEventListener("input", (event) => {
  state.query = event.target.value;
  renderDevices(state, elements);
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const { action, id, index } = button.dataset;
  if (action === "add-host") openRegister(state.hosts[Number(index)], elements);
  else performDeviceAction(action, id, state, elements);
});

checkService();
refreshDevices();
