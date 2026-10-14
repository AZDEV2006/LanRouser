export function updateSummary(state, elements) {
  elements.registeredCount.textContent = state.devices.length;
  elements.deviceBadge.textContent = state.devices.length;
  elements.discoveredCount.textContent = state.hosts.length
    ? state.hosts.length
    : state.lastScan
      ? "0"
      : "--";
  elements.scanBadge.textContent = state.hosts.length;
  elements.onlineCount.textContent = [...state.statuses.values()].filter(
    Boolean,
  ).length;
}
