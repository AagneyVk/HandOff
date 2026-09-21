import socket
import unittest
from unittest.mock import patch

from host.runtime import nat


DESCRIPTION = b'''<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:2</serviceType>
<controlURL>/upnp/control/wan</controlURL>
</service></serviceList></device></root>'''


class NatTests(unittest.TestCase):
    def test_ssdp_headers_are_case_insensitive(self):
        packet = b'HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.1/root.xml\r\nST: test\r\n\r\n'
        self.assertEqual(nat._headers(packet)['location'], 'http://192.168.1.1/root.xml')

    @patch('host.runtime.nat.socket.getaddrinfo')
    def test_gateway_description_must_resolve_privately(self, lookup):
        lookup.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 80))]
        self.assertEqual(nat._local_http_url('http://router.local/root.xml').hostname, 'router.local')
        lookup.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 80))]
        with self.assertRaises(ValueError):
            nat._local_http_url('http://example.test/root.xml')

    @patch('host.runtime.nat._http', return_value=DESCRIPTION)
    def test_selects_wan_control_service(self, _):
        service, control = nat._service('http://192.168.1.1/root.xml')
        self.assertEqual(service, 'urn:schemas-upnp-org:service:WANIPConnection:2')
        self.assertEqual(control, 'http://192.168.1.1/upnp/control/wan')

    @patch('host.runtime.nat._soap')
    def test_renewal_preserves_external_port(self, soap):
        soap.side_effect = [b'', b'<r><NewExternalIPAddress>8.8.8.8</NewExternalIPAddress></r>']
        mapping = nat.Mapping('8.8.8.8', 54321, '192.168.1.10',
                              'http://192.168.1.1/control', 'urn:test:WANIPConnection:1')
        renewed = nat.renew_mapping(mapping, 47821)
        self.assertEqual(renewed.external_port, 54321)
        self.assertEqual(soap.call_args_list[0].args[2], 'AddPortMapping')
        self.assertEqual(soap.call_args_list[0].args[3]['NewExternalPort'], 54321)


if __name__ == '__main__':
    unittest.main()
