import { requestJson } from "../shared/api.js";
import { escapeHtml, showToast } from "../shared/ui.js";
import { updateSummary } from "./summary.js";

function isRegistered(host, devices) {
  const hostMac = String(host.mac || "")
    .replace(/[:-]/g, "")
    .toUpperCase();
  return devices.some(
    (device) =>
      String(device.mac || "")
        .replace(/[:-]/g, "")
        .toUpperCase() === hostMac,
  );
}

export function renderHosts(state, elements) {
  if (!state.lastScan) return;
  if (!state.hosts.length) {
    elements.scanResults.innerHTML = `
      <div class="scan-empty">
        <div>
          <span class="empty-mark">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            >
              <path d="M5 12h14M12 5v14" />
            </svg>
          </span>
          <p class="empty-title">No active hosts found</p>
          <p class="empty-copy">
            Try again after confirming this device is<br />
            connected to the local network.
          </p>
        </div>
      </div>
    `;
  } else {
    elements.scanResults.innerHTML = `<div class="scan-list">${state.hosts
      .map((host, index) => {
        const name =
          host.hostname || host.name || `Network device ${index + 1}`;
        const registered = isRegistered(host, state.devices);
        const hasMac = Boolean(host.mac);
        return `
          <div class="scan-row">
            <div>
              <div class="device-primary">${escapeHtml(name)}</div>
              <div class="device-secondary">
                ${escapeHtml(host.ip || "Unknown IP")} &nbsp;·&nbsp;
                ${escapeHtml(host.mac || "MAC unavailable")}
              </div>
            </div>
            <button
              class="button add-result"
              type="button"
              data-action="add-host"
              data-index="${index}"
              ${registered || !hasMac ? "disabled" : ""}
            >
              ${registered ? "Added" : hasMac ? "Add" : "No MAC"}
            </button>
          </div>
        `;
      })
      .join("")}</div>`;
  }
  elements.scanHint.textContent = state.hosts.length
    ? `${state.hosts.length} host${state.hosts.length === 1 ? "" : "s"} found`
    : "Scan complete";
  updateSummary(state, elements);
}

export async function runScan(state, elements) {
  elements.scanButton.disabled = true;
  elements.scanAgain.disabled = true;
  elements.scanButton.querySelector("span").textContent = "Scanning…";
  elements.scanHint.textContent = "Looking for active hosts…";
  try {
    const result = await requestJson("/api/scan", {
      method: "POST",
      body: "{}",
    });
    state.hosts = Array.isArray(result.hosts) ? result.hosts : [];
    state.lastScan = new Date();
    elements.lastScan.textContent = state.lastScan.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
    renderHosts(state, elements);
    showToast(
      `Scan complete: ${state.hosts.length} host${state.hosts.length === 1 ? "" : "s"} found`,
    );
  } catch (error) {
    elements.scanHint.textContent = "Scan unavailable";
    showToast(error.message, true);
  } finally {
    elements.scanButton.disabled = false;
    elements.scanAgain.disabled = false;
    elements.scanButton.querySelector("span").textContent = "Scan network";
  }
}
