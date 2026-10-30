import unittest
from cadence_audit import parse
class Tests(unittest.TestCase):
 def test_config_does_not_retain_identity_or_servers(self):
  x=parse('Configured ReceiverACSender: private-server, feed: SECRET_KEY, send_interval: 30s/30s, max age: 15s, send metadata: true, mode: 1, filtering: true',1);self.assertEqual(x['send_interval'],'30s/30s');self.assertNotIn('SECRET',str(x));self.assertNotIn('private-server',str(x))
 def test_send_fields_remain_literal(self):self.assertEqual(parse('[feed][i]sent 4,40 AC',1),dict(unix=1,kind='send',literal_first=4,literal_second=40))
 def test_unrelated_credentials_never_logged(self):self.assertIsNone(parse('fr24key=SECRET',1))
if __name__=='__main__':unittest.main()
