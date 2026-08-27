import unittest

from host.shared.protocol import Message, ProtocolError, normalized


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        original = Message(
            type="input.pointer",
            session_id="s1",
            payload={"x": 0.25, "y": 0.75, "action": "tap"},
        )
        decoded = Message.decode(original.encode())
        self.assertEqual(decoded.type, original.type)
        self.assertEqual(decoded.session_id, "s1")
        self.assertEqual(decoded.payload["x"], 0.25)
        self.assertEqual(decoded.id, original.id)

    def test_rejects_unknown_type(self):
        with self.assertRaises(ProtocolError):
            Message(type="magic", payload={})

    def test_normalized_bounds(self):
        self.assertEqual(normalized(0, "x"), 0.0)
        self.assertEqual(normalized(1, "x"), 1.0)
        with self.assertRaises(ProtocolError):
            normalized(1.01, "x")
        with self.assertRaises(ProtocolError):
            normalized(-0.01, "x")

    def test_bool_is_not_coordinate(self):
        with self.assertRaises(ProtocolError):
            normalized(True, "x")


if __name__ == "__main__":
    unittest.main()
