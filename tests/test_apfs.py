import io
import struct
import unittest
import uuid
from apfs_metadata import scan_container,checksum_ok,Unsupported

def put(data,offset,value,kind='Q'): struct.pack_into('<'+kind,data,offset,value)
def seal(data):
    a=b=0;mod=0xffffffff
    for (word,) in struct.iter_unpack('<I',data[8:]): a=(a+word)%mod;b=(b+a)%mod
    low=(mod-(a+b)%mod)%mod;high=(mod-(a+low)%mod)%mod
    put(data,0,high<<32|low)
    return data

def fixture(name='Custom system',features=0x20,role=1,level=0):
    blocks=[bytearray(4096) for _ in range(8)]
    sb,omap,node,volume=blocks[:4]
    sb[32:36]=b'NXSB';put(sb,16,1);put(sb,36,4096,'I');put(sb,40,8);put(sb,160,1);put(sb,180,1,'I');put(sb,184,42)
    put(omap,48,2)
    put(node,32,5,'H');put(node,34,level,'H');put(node,36,1,'I');put(node,42,4,'H')
    put(node,56,0,'H');put(node,58,16,'H');put(node,60,42);put(node,68,1);put(node,4048,3)
    volume[32:36]=b'APSB';put(volume,56,features);put(volume,964,role,'H')
    encoded=name.encode();volume[704:704+len(encoded)]=encoded
    volume[1008:1024]=uuid.UUID('12345678-1234-1234-1234-123456789abc').bytes
    return io.BytesIO(b''.join(seal(b) for b in blocks))

class ApfsTests(unittest.TestCase):
    def test_sealed_system_is_identified_without_a_macos_label(self):
        volume=scan_container(fixture())[0]
        self.assertEqual(volume['name'],'Custom system');self.assertTrue(volume['sealed_system'])
    def test_linux_stub_named_macos_is_not_macos(self):
        self.assertFalse(scan_container(fixture('macOS Fake',features=0))[0]['sealed_system'])
    def test_incomplete_restore_is_not_selected_automatically(self):
        self.assertFalse(scan_container(fixture(features=0x30))[0]['sealed_system'])
    def test_non_system_volume_is_excluded(self):
        self.assertEqual(scan_container(fixture(role=64)),[])
    def test_unsupported_tree_fails_closed(self):
        with self.assertRaises(Unsupported):scan_container(fixture(level=1))
    def test_corruption_is_rejected(self):
        stream=fixture();data=bytearray(stream.getvalue());data[100]^=1
        self.assertFalse(checksum_ok(data[:4096]))
        with self.assertRaises(Unsupported):scan_container(io.BytesIO(data))
    def test_truncated_and_non_apfs_inputs_are_rejected(self):
        for data in [b'',b'zero'*4096]:
            with self.assertRaises(Unsupported):scan_container(io.BytesIO(data))
