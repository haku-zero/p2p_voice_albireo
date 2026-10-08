import json
import base64
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import HexEncoder
    has_crypto = True
except ImportError:
    has_crypto = False

from utils import config

class CryptoManager:
    def __init__(self):
        self.enabled = has_crypto
        if not self.enabled:
            print("[Crypto] PyNaCl not installed. Cryptographic verification is DISABLED.")
            return
            
        cfg = config.load_config()
        priv_key_hex = cfg.get("private_key")
        
        if priv_key_hex:
            try:
                self.signing_key = SigningKey(priv_key_hex, encoder=HexEncoder)
            except Exception:
                self.signing_key = SigningKey.generate()
                config.save_config("private_key", self.signing_key.encode(encoder=HexEncoder).decode('utf-8'))
        else:
            self.signing_key = SigningKey.generate()
            config.save_config("private_key", self.signing_key.encode(encoder=HexEncoder).decode('utf-8'))
            
        self.public_key_hex = self.signing_key.verify_key.encode(encoder=HexEncoder).decode('utf-8')
        
    def get_public_key(self):
        if not self.enabled: return "unsafe_pub_key"
        return self.public_key_hex
        
    def sign_payload(self, payload_dict):
        if not self.enabled: return payload_dict
        
        sign_dict = {k: v for k, v in payload_dict.items() if k != 'signature'}
        serialized = json.dumps(sign_dict, separators=(',', ':'), sort_keys=True).encode('utf-8')
        signed = self.signing_key.sign(serialized)
        signature_hex = base64.b64encode(signed.signature).decode('utf-8')
        
        payload_dict['signature'] = signature_hex
        return payload_dict
        
    def verify_payload(self, payload_dict, sender_pub_key_hex):
        if not self.enabled: return True
        try:
            signature_hex = payload_dict.get('signature')
            if not signature_hex: return False
            
            sign_dict = {k: v for k, v in payload_dict.items() if k != 'signature'}
            serialized = json.dumps(sign_dict, separators=(',', ':'), sort_keys=True).encode('utf-8')
            
            verify_key = VerifyKey(sender_pub_key_hex, encoder=HexEncoder)
            signature = base64.b64decode(signature_hex)
            verify_key.verify(serialized, signature)
            return True
        except Exception as e:
            print(f"[Crypto] Verification failed: {e}")
            return False
