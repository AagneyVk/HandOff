import asyncio
import json
import unittest
from unittest.mock import patch
from host.shared.protocol import Message, ProtocolError
from host.windows.v1_host import handle

class ValidationTests(unittest.TestCase):
    def test_malformed_fields_are_protocol_errors(self):
        valid = Message('hello', {}).as_dict()
        for field, value in [('type', []), ('id', ''), ('id', 0), ('version', False), ('timestamp_us', False), ('session_id', [])]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ProtocolError):
                    Message.decode(json.dumps(dict(valid, **{field: value})))

class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = await asyncio.start_server(handle, '127.0.0.1', 0)
        self.reader, self.writer = await asyncio.open_connection('127.0.0.1', self.server.sockets[0].getsockname()[1])
    async def asyncTearDown(self):
        self.writer.close()
        await self.writer.wait_closed()
        self.server.close()
        await self.server.wait_closed()
    async def request(self, type_, payload):
        self.writer.write(Message(type_, payload).encode())
        await self.writer.drain()
        return Message.decode(await asyncio.wait_for(self.reader.readline(), 2))
    async def test_connect_list_and_reject_unimplemented_session(self):
        hello = await self.request('hello', {})
        self.assertEqual(hello.payload['media'], [])
        self.assertEqual(hello.payload['input'], [])
        with patch('host.windows.v1_host.snapshot', return_value=[]):
            result = await self.request('windows.list', {})
        self.assertEqual(result.payload['windows'], [])
        result = await self.request('session.start', {'window_id': 'win32:1'})
        self.assertEqual(result.payload['code'], 'media_unavailable')
        with patch('host.windows.v1_host.tap') as tap:
            result = await self.request('input.pointer', {'x': .5, 'y': .5})
            self.assertEqual(result.type, 'error')
            tap.assert_not_called()
    async def test_bad_message_does_not_kill_connection(self):
        bad = Message('hello', {}).as_dict()
        bad['type'] = []
        self.writer.write((json.dumps(bad)+'\n').encode())
        await self.writer.drain()
        self.assertEqual(Message.decode(await self.reader.readline()).type, 'error')
        self.assertEqual((await self.request('hello', {})).type, 'capabilities')
