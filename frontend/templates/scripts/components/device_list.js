import { requestJson } from "../shared/api.js";
import { escapeHtml, showToast } from "../shared/ui.js";
import { updateSummary } from "./summary.js";

function statusFor(device, state) {
  if (!state.statuses.has(device.id))
    return { label: "Not checked", className: "" };
  return state.statuses.get(device.id)
    ? { label: "Online", className: "online" }
    : { label: "Offline", className: "offline" };
}

function actionButtons(device, state) {
  const busyPing = state.busy.has(`${device.id}:ping`);
  const busyWake = state.busy.has(`${device.id}:wake`);
  return `
    <div class="row-actions">
      <button
        class="button"
        type="button"
        data-action="ping"
        data-id="${escapeHtml(device.id)}"
        ${busyPing ? "disabled" : ""}
        aria-label="Ping ${escapeHtml(device.name)}"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M3 12h3l2.2-6 4.6 12 2.2-6H21" />
        </svg>
        ${busyPing ? "Checking" : "Ping"}
      </button>
      <button
        class="button button-primary"
        type="button"
        data-action="wake"
        data-id="${escapeHtml(device.id)}"
        ${busyWake ? "disabled" : ""}
        aria-label="Wake ${escapeHtml(device.name)}"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M12 3v8m-5.7-5a8 8 0 1 0 11.4 0" />
        </svg>
        ${busyWake ? "Sending" : "Wake"}
      </button>
      <button
        class="icon-button"
        type="button"
        data-action="delete"
        data-id="${escapeHtml(device.id)}"
        aria-label="Remove ${escapeHtml(device.name)}"
        title="Remove device"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M4 7h16m-10 4v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" />
        </svg>
      </button>
    </div>
  `;
}

function renderEmptyState(elements, state) {
  const message = state.devices.length
    ? "No matching devices"
    : "No registered devices";
  const copy = state.devices.length
    ? "Try another name, IP address, or MAC."
    : "Scan your network or register a device to get started.";
  elements.devicesBody.innerHTML = `
    <tr>
      <td colspan="4">
        <div class="scan-empty devices-empty">
          <div>
            <span class="empty-mark">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <rect x="3.5" y="4" width="17" height="12" rx="1.5" />
                <path d="M8 20h8m-4-4v4" />
              </svg>
            </span>
            <p class="empty-title">${message}</p>
            <p class="empty-copy">${copy}</p>
          </div>
        </div>
      </td>
    </tr>
  `;
  elements.mobileDeviceList.innerHTML = `
    <div class="scan-empty mobile-empty">
      <div>
        <span class="empty-mark">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <rect x="3.5" y="4" width="17" height="12" rx="1.5" />
            <path d="M8 20h8m-4-4v4" />
          </svg>
        </span>
        <p class="empty-title">${message}</p>
        <p class="empty-copy">${copy}</p>
      </div>
    </div>
  `;
}

export function renderDevices(state, elements) {
  const query = state.query.trim().toLowerCase();
  const visibleDevices = state.devices.filter((device) =>
    [device.name, device.ip, device.mac].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(query),
    ),
  );
  elements.devicesBody.innerHTML = "";
  elements.mobileDeviceList.innerHTML = "";

  if (visibleDevices.length === 0) {
    renderEmptyState(elements, state);
    updateSummary(state, elements);
    return;
  }

  for (const device of visibleDevices) {
    const status = statusFor(device, state);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>
        <span class="device-primary">${escapeHtml(device.name)}</span>
        <div class="device-secondary">${escapeHtml(device.mac)}</div>
      </td>
      <td class="address-cell">${escapeHtml(device.ip)}</td>
      <td>
        <span class="status-pill ${status.className}">${status.label}</span>
      </td>
      <td>${actionButtons(device, state)}</td>
    `;
    elements.devicesBody.append(row);

    const mobileRow = document.createElement("section");
    mobileRow.className = "mobile-device-row";
    mobileRow.innerHTML = `
      <div class="mobile-device-top">
        <div>
          <div class="device-primary">${escapeHtml(device.name)}</div>
          <div class="device-secondary">${escapeHtml(device.mac)}</div>
        </div>
        <span class="status-pill ${status.className}">${status.label}</span>
      </div>
      <div class="mobile-addresses">
        <span>IPv4&nbsp; ${escapeHtml(device.ip)}</span>
      </div>
      ${actionButtons(device, state)}
    `;
    mobileRow.querySelector(".row-actions").classList.add("mobile-actions");
    elements.mobileDeviceList.append(mobileRow);
  }
  updateSummary(state, elements);
}

export async function loadDevices(state, elements, afterLoad) {
  try {
    const result = await requestJson("/api/devices");
    state.devices = Array.isArray(result.devices) ? result.devices : [];
    afterLoad();
  } catch (error) {
    showToast(error.message, true);
    document.getElementById("serviceDot").classList.add("error");
    document.getElementById("serviceText").textContent = "Storage unavailable";
  }
}

export async function performDeviceAction(action, deviceId, state, elements) {
  const device = state.devices.find((item) => item.id === deviceId);
  if (!device) return;
  if (
    action === "delete" &&
    !window.confirm(`Remove ${device.name} from registered devices?`)
  )
    return;

  const busyKey = `${deviceId}:${action}`;
  state.busy.add(busyKey);
  renderDevices(state, elements);
  try {
    if (action === "delete") {
      await requestJson(`/api/devices/${encodeURIComponent(deviceId)}`, {
        method: "DELETE",
      });
      state.devices = state.devices.filter((item) => item.id !== deviceId);
      state.statuses.delete(deviceId);
      showToast(`${device.name} removed`);
    } else if (action === "ping") {
      const result = await requestJson(
        `/api/devices/${encodeURIComponent(deviceId)}/ping`,
        { method: "POST", body: "{}" },
      );
      state.statuses.set(deviceId, Boolean(result.online));
      showToast(
        result.online
          ? `${device.name} is reachable`
          : `${device.name} did not respond`,
      );
    } else if (action === "wake") {
      await requestJson(`/api/devices/${encodeURIComponent(deviceId)}/wake`, {
        method: "POST",
        body: "{}",
      });
      showToast(`Wake-on-LAN packet sent to ${device.name}`);
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.busy.delete(busyKey);
    renderDevices(state, elements);
  }
}
