import ipaddress
import json
import subprocess
import unittest
from unittest.mock import patch

from backend import scanner


LOCAL = ipaddress.IPv4Interface("192.168.1.37/24")


class ScannerTests(unittest.TestCase):
    def test_parse_supported_formats_and_normalize_mac(self):
        output = """
192.168.1.10\taa:bb:cc:dd:ee:10\tVendor
? (192.168.1.2) at 2:a:ee:7b:60:e4 on en0 ifscope [ethernet]
192.168.1.3 dev eth0 lladdr aa:bb:cc:dd:ee:03 REACHABLE
192.168.1.10\taa:bb:cc:dd:ee:10\t(DUP: 2)
"""
        self.assertEqual(scanner.parse_arp_output(output), [
            {"ip": "192.168.1.2", "mac": "02:0A:EE:7B:60:E4"},
            {"ip": "192.168.1.3", "mac": "AA:BB:CC:DD:EE:03"},
            {"ip": "192.168.1.10", "mac": "AA:BB:CC:DD:EE:10"},
        ])

    def test_parse_rejects_invalid_incomplete_and_non_host_entries(self):
        self.assertEqual(scanner.parse_arp_output("""
? (192.168.1.4) at (incomplete) on en0
192.168.1.5 dev eth0 lladdr aa:bb:cc:dd:ee:05 FAILED
192.168.1.255 ff:ff:ff:ff:ff:ff
224.0.0.251 01:00:5e:00:00:fb
999.168.1.2 aa:bb:cc:dd:ee:01
192.168.1.2 00:00:00:00:00:00
127.0.0.1 aa:bb:cc:dd:ee:01
"""), [])

    @patch("backend.scanner.platform.system", return_value="Linux")
    @patch("backend.scanner._output")
    def test_linux_detects_lowest_metric_route_and_actual_mask(self, output, system):
        output.side_effect = [
            json.dumps([{"dev": "wlan0", "metric": 600}, {"dev": "eth0", "metric": 100}]),
            json.dumps([{"addr_info": [{"family": "inet", "scope": "global",
                                        "local": "192.168.2.4", "prefixlen": 23}]}]),
        ]
        self.assertEqual(scanner.get_default_ipv4_network(), ipaddress.IPv4Network("192.168.2.0/23"))
        self.assertEqual(output.call_args.args[0][-1], "eth0")

    @patch("backend.scanner.platform.system", return_value="Darwin")
    @patch("backend.scanner._output")
    def test_macos_detects_network_from_hex_mask(self, output, system):
        output.side_effect = ["  interface: en0\n", "inet 192.168.1.37 netmask 0xffffff00 broadcast 192.168.1.255"]
        self.assertEqual(scanner.get_default_ipv4_network(), LOCAL.network)

    @patch("backend.scanner.platform.system", return_value="Linux")
    @patch("backend.scanner._output", return_value="[]")
    def test_missing_default_route_has_clear_error(self, output, system):
        with self.assertRaisesRegex(RuntimeError, "No default IPv4 route"):
            scanner.get_default_ipv4_network()

    @patch("backend.scanner._output")
    def test_rejects_invalid_interface_before_running_commands(self, output):
        for interface in ("-a", "eth0; touch /tmp/bad", "", 123):
            with self.subTest(interface=interface), self.assertRaises(ValueError):
                scanner.get_default_ipv4_network(interface)
        output.assert_not_called()

    @patch("backend.scanner._interface_details", return_value=("eth0", LOCAL))
    @patch("backend.scanner.shutil.which")
    def test_rejects_remote_ipv6_and_oversized_subnets(self, which, details):
        for subnet in ("10.0.0.0/24", "::/64", "not a subnet"):
            with self.subTest(subnet=subnet), self.assertRaises(ValueError):
                scanner.discover_hosts(subnet)
        details.return_value = ("eth0", ipaddress.IPv4Interface("10.0.0.1/8"))
        with self.assertRaisesRegex(ValueError, "too large"):
            scanner.discover_hosts()
        which.assert_not_called()

    @patch("backend.scanner._interface_details", return_value=("eth0", LOCAL))
    @patch("backend.scanner.shutil.which", return_value="/usr/sbin/arp-scan")
    @patch("backend.scanner._run")
    @patch("backend.scanner._ping_scan")
    def test_arp_scan_filters_results_and_uses_safe_arguments(self, fallback, run, which, details):
        run.return_value = subprocess.CompletedProcess([], 0, """
192.168.1.2 aa:bb:cc:dd:ee:02
192.168.1.37 aa:bb:cc:dd:ee:37
192.168.2.2 aa:bb:cc:dd:ee:02
192.168.1.0 aa:bb:cc:dd:ee:00
192.168.1.255 aa:bb:cc:dd:ee:ff
""", "")
        self.assertEqual(scanner.discover_hosts(), [{"ip": "192.168.1.2", "mac": "AA:BB:CC:DD:EE:02"}])
        self.assertEqual(run.call_args.args[0], [
            "/usr/sbin/arp-scan", "--interface=eth0", "--plain", "--quiet",
            "--retry=2", "192.168.1.0/24",
        ])
        fallback.assert_not_called()

    @patch("backend.scanner._interface_details", return_value=("eth0", LOCAL))
    @patch("backend.scanner.shutil.which")
    @patch("backend.scanner._run", return_value=subprocess.CompletedProcess([], 1, "", "permission denied"))
    @patch("backend.scanner._ping_scan", return_value=[])
    def test_missing_or_unprivileged_arp_scan_falls_back(self, fallback, run, which, details):
        for executable in (None, "/usr/bin/arp-scan"):
            which.return_value = executable
            self.assertEqual(scanner.discover_hosts(), [])
        self.assertEqual(fallback.call_count, 2)

    @patch("backend.scanner.platform.system", return_value="Linux")
    @patch("backend.scanner._ping", side_effect=lambda address: address == "192.168.1.2")
    @patch("backend.scanner._output", return_value="""
192.168.1.2 lladdr aa:bb:cc:dd:ee:02 STALE
192.168.1.3 lladdr aa:bb:cc:dd:ee:03 REACHABLE
192.168.1.4 lladdr aa:bb:cc:dd:ee:04 STALE
192.168.1.5 FAILED
192.168.2.5 lladdr aa:bb:cc:dd:ee:05 REACHABLE
""")
    def test_fallback_excludes_stale_hosts_and_other_networks(self, output, ping, system):
        result = scanner._ping_scan(ipaddress.IPv4Network("192.168.1.0/29"), "eth0", LOCAL.ip)
        self.assertEqual([host["ip"] for host in result], ["192.168.1.2", "192.168.1.3"])
        self.assertEqual(ping.call_count, 6)

    @patch("backend.scanner.platform.system", return_value="Darwin")
    @patch("backend.scanner._ping", return_value=True)
    @patch("backend.scanner._output", return_value="")
    def test_fallback_keeps_online_host_without_mac_and_excludes_self(self, output, ping, system):
        result = scanner._ping_scan(ipaddress.IPv4Network("192.168.1.0/30"), "en0", ipaddress.IPv4Address("192.168.1.1"))
        self.assertEqual(result, [{"ip": "192.168.1.2", "mac": ""}])
        ping.assert_called_once_with("192.168.1.2")

    @patch("backend.scanner._run", return_value=subprocess.CompletedProcess([], 2, "", "sendto: Operation not permitted"))
    def test_ping_permission_failure_is_not_an_empty_scan(self, run):
        with self.assertRaisesRegex(RuntimeError, "not permitted"):
            scanner._ping("192.168.1.2")

    @patch("backend.scanner.subprocess.run", side_effect=subprocess.TimeoutExpired("ping", 3))
    def test_ping_timeout_is_offline(self, run):
        self.assertFalse(scanner._ping("192.168.1.2"))

    @patch("backend.scanner.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_tool_has_actionable_error(self, run):
        with self.assertRaisesRegex(RuntimeError, "command not found: ip"):
            scanner._output(["ip", "-j", "route"])

    def test_flask_scan_endpoint_uses_scanner_and_reports_errors(self):
        from app import app

        client = app.test_client()
        hosts = [{"ip": "192.168.1.2", "mac": "AA:BB:CC:DD:EE:02"}]
        with patch.object(scanner, "discover_hosts", return_value=hosts):
            response = client.post("/api/scan")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"hosts": hosts})
        with patch.object(scanner, "discover_hosts", side_effect=RuntimeError("No default IPv4 route")):
            response = client.post("/api/scan")
            self.assertEqual(response.status_code, 500)
            self.assertIn("No default IPv4 route", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
