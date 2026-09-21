"""Best-effort, zero-cost direct Internet access through a local UPnP gateway.

The media path remains the existing pinned-TLS socket.  UPnP only asks the
user's own router to forward an external TCP port while HandOff is running.
Routers behind CGNAT, or routers with UPnP disabled, are reported honestly as
unavailable instead of silently exposing an unusable address.
"""
from dataclasses import dataclass
import http.client
import ipaddress
import random
import socket
import threading
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
from xml.sax.saxutils import escape


SSDP_ADDRESS = ('239.255.255.250', 1900)
SSDP_QUERY = '\r\n'.join((
    'M-SEARCH * HTTP/1.1',
    'HOST: 239.255.255.250:1900',
    'MAN: "ssdp:discover"',
    'MX: 2',
    'ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1',
    '', '',
)).encode('ascii')


@dataclass(frozen=True)
class Mapping:
    host: str
    external_port: int
    internal_host: str
    control_url: str
    service_type: str


def _headers(packet):
    result = {}
    for line in packet.decode('iso-8859-1', 'replace').split('\r\n')[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip().lower()] = value.strip()
    return result


def _local_http_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Gateway supplied an unsafe description URL')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 80, socket.AF_INET, socket.SOCK_STREAM)
    def safe(item):
        address = ipaddress.ip_address(item[4][0])
        return address.is_private and not (address.is_loopback or address.is_unspecified or address.is_multicast)
    if not addresses or not all(safe(item) for item in addresses):
        raise ValueError('Gateway description is not on the private network')
    return parsed


def _http(url, method='GET', body=None, headers=None, limit=1024 * 1024):
    parsed = _local_http_url(url)
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 80, socket.AF_INET, socket.SOCK_STREAM)
    target = addresses[0][4][0]
    address = ipaddress.ip_address(target)
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError('Gateway address changed during discovery')
    request_headers = dict(headers or {})
    request_headers.setdefault('Host', parsed.netloc)
    connection = http.client.HTTPConnection(target, parsed.port or 80, timeout=3)
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    data = response.read(limit + 1)
    connection.close()
    if len(data) > limit:
        raise ValueError('Gateway response is too large')
    if response.status >= 400:
        detail = ''
        try:
            root = ElementTree.fromstring(data)
            detail = next((node.text or '' for node in root.iter() if node.tag.endswith('errorDescription')), '')
        except ElementTree.ParseError:
            pass
        raise OSError(f'Gateway rejected {method} ({response.status})' + (f': {detail}' if detail else ''))
    return data


def _service(description_url):
    root = ElementTree.fromstring(_http(description_url))
    choices = []
    for node in root.iter():
        if not node.tag.endswith('service'):
            continue
        fields = {child.tag.rsplit('}', 1)[-1]: child.text or '' for child in node}
        service_type = fields.get('serviceType', '')
        if 'WANIPConnection' in service_type or 'WANPPPConnection' in service_type:
            choices.append((service_type, urljoin(description_url, fields.get('controlURL', ''))))
    if not choices:
        raise ValueError('Router does not advertise Internet port mapping')
    choices.sort(key=lambda item: ('WANIPConnection' not in item[0], ':2' not in item[0]))
    return choices[0]


def _soap(control_url, service_type, action, values):
    arguments = ''.join(f'<{escape(key)}>{escape(str(value))}</{escape(key)}>' for key, value in values.items())
    body = ('<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{escape(service_type)}">{arguments}</u:{action}></s:Body></s:Envelope>')
    return _http(control_url, 'POST', body.encode('utf-8'), {
        'Content-Type': 'text/xml; charset="utf-8"',
        'SOAPAction': f'"{service_type}#{action}"',
        'Connection': 'close',
    })


def _discover(timeout=2.5):
    locations = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(0.25)
        deadline = __import__('time').monotonic() + timeout
        for _ in range(3):
            sock.sendto(SSDP_QUERY, SSDP_ADDRESS)
        while __import__('time').monotonic() < deadline:
            try:
                packet, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            location = _headers(packet).get('location')
            if location and location not in locations:
                locations.append(location)
    finally:
        sock.close()
    return locations


def _internal_address(control_url):
    gateway = urlsplit(control_url).hostname
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((gateway, 9))
        return sock.getsockname()[0]
    finally:
        sock.close()


def create_mapping(internal_port, lease_seconds=3600):
    """Return a usable Mapping, or raise when this network cannot expose one."""
    errors = []
    for location in _discover():
        try:
            service_type, control_url = _service(location)
            internal_host = _internal_address(control_url)
            external = ElementTree.fromstring(_soap(control_url, service_type, 'GetExternalIPAddress', {}))
            external_host = next((node.text for node in external.iter() if node.tag.endswith('NewExternalIPAddress')), None)
            if not external_host or not ipaddress.ip_address(external_host).is_global:
                raise OSError('Router is behind CGNAT or has no public address')
            ports = [internal_port] + [random.SystemRandom().randint(49152, 65535) for _ in range(4)]
            for external_port in ports:
                # Older IGD implementations accept only permanent (zero-duration)
                # leases. Prefer an expiring lease, then use their required form and
                # still remove it explicitly during normal shutdown.
                for lifetime in (lease_seconds, 0):
                    try:
                        _soap(control_url, service_type, 'AddPortMapping', {
                            'NewRemoteHost': '', 'NewExternalPort': external_port, 'NewProtocol': 'TCP',
                            'NewInternalPort': internal_port, 'NewInternalClient': internal_host,
                            'NewEnabled': 1, 'NewPortMappingDescription': 'HandOff',
                            'NewLeaseDuration': lifetime,
                        })
                        return Mapping(external_host, external_port, internal_host, control_url, service_type)
                    except OSError as exc:
                        errors.append(str(exc))
        except (OSError, ValueError, ElementTree.ParseError, socket.error) as exc:
            errors.append(str(exc))
    raise OSError(errors[-1] if errors else 'No compatible UPnP router was found')


def delete_mapping(mapping):
    _soap(mapping.control_url, mapping.service_type, 'DeletePortMapping', {
        'NewRemoteHost': '', 'NewExternalPort': mapping.external_port, 'NewProtocol': 'TCP',
    })


def renew_mapping(mapping, internal_port, lease_seconds=3600):
    error = None
    for lifetime in (lease_seconds, 0):
        try:
            _soap(mapping.control_url, mapping.service_type, 'AddPortMapping', {
                'NewRemoteHost': '', 'NewExternalPort': mapping.external_port, 'NewProtocol': 'TCP',
                'NewInternalPort': internal_port, 'NewInternalClient': mapping.internal_host,
                'NewEnabled': 1, 'NewPortMappingDescription': 'HandOff',
                'NewLeaseDuration': lifetime,
            })
            response = ElementTree.fromstring(_soap(
                mapping.control_url, mapping.service_type, 'GetExternalIPAddress', {}))
            host = next((node.text for node in response.iter() if node.tag.endswith('NewExternalIPAddress')), None)
            if not host or not ipaddress.ip_address(host).is_global:
                raise OSError('Router is behind CGNAT or has no public address')
            return Mapping(host, mapping.external_port, mapping.internal_host,
                           mapping.control_url, mapping.service_type)
        except (OSError, ValueError, ElementTree.ParseError) as exc:
            error = exc
    raise OSError(str(error or 'Could not renew router mapping'))


class DirectAccess:
    """Maintains a router mapping in a daemon thread for the app lifetime."""
    def __init__(self, port, lease_seconds=3600):
        self.port = port
        self.lease_seconds = lease_seconds
        self._mapping = None
        self._status = 'Checking direct Internet access…'
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='handoff-direct-access', daemon=True)

    def start(self):
        self._thread.start()

    def snapshot(self):
        with self._lock:
            return self._mapping, self._status

    def _set(self, mapping, status):
        with self._lock:
            self._mapping, self._status = mapping, status

    def _run(self):
        while not self._stop.is_set():
            try:
                previous, _ = self.snapshot()
                try:
                    mapping = renew_mapping(previous, self.port, self.lease_seconds) if previous else create_mapping(
                        self.port, self.lease_seconds)
                except Exception:
                    mapping = create_mapping(self.port, self.lease_seconds)
                if self._stop.is_set():
                    try:
                        delete_mapping(mapping)
                    except Exception:
                        pass
                    break
                self._set(mapping, f'Direct Internet access ready on {mapping.host}:{mapping.external_port}')
                delay = max(300, self.lease_seconds // 2)
            except Exception as exc:
                self._set(None, f'LAN only — direct Internet access unavailable: {exc}')
                delay = 120
            self._stop.wait(delay)

    def stop(self):
        self._stop.set()
        mapping, _ = self.snapshot()
        if mapping:
            try:
                delete_mapping(mapping)
            except Exception:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=2)
