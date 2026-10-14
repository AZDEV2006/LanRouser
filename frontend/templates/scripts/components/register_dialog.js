import { requestJson } from "../shared/api.js";
import { showToast } from "../shared/ui.js";

export function openRegister(host, elements) {
  elements.form.reset();
  if (host) {
    document.getElementById("deviceName").value =
      host.hostname || host.name || `Device ${host.ip || ""}`.trim();
    document.getElementById("deviceIp").value = host.ip || "";
    document.getElementById("deviceMac").value = host.mac || "";
  }
  elements.dialog.showModal();
  document.getElementById("deviceName").focus();
}

export async function saveDevice(event, elements, refreshDevices) {
  event.preventDefault();
  const submitButton = document.getElementById("saveDevice");
  const data = Object.fromEntries(new FormData(elements.form));
  submitButton.disabled = true;
  submitButton.textContent = "Saving…";
  try {
    await requestJson("/api/devices", {
      method: "POST",
      body: JSON.stringify(data),
    });
    elements.dialog.close();
    showToast(`${data.name} added to registered devices`);
    await refreshDevices();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Save device";
  }
}
