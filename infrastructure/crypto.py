import json
import base64
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import HexEncoder
    from nacl.public import PrivateKey, PublicKey, Box
    from nacl.secret import SecretBox
    import nacl.utils
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
        
        # E2EE: Convert Ed25519 signing key to X25519 for Diffie-Hellman Key Exchange
        if self.enabled:
            self.x25519_private = self.signing_key.to_curve25519_private_key()
            self.x25519_public = self.signing_key.verify_key.to_curve25519_public_key()
            
        self.room_key = None
        self.secret_box = None
        
    def generate_room_key(self):
        if not self.enabled: return
        self.room_key = nacl.utils.random(SecretBox.KEY_SIZE)
        self.secret_box = SecretBox(self.room_key)
        
    def set_room_key(self, key_bytes):
        if not self.enabled: return
        self.room_key = key_bytes
        self.secret_box = SecretBox(self.room_key)

    def encrypt_room_key_for_peer(self, target_pub_key_hex):
        """Encrypt the symmetric room key using the target's public key (Asymmetric)"""
        if not self.enabled or not self.room_key: return None
        target_verify_key = VerifyKey(target_pub_key_hex, encoder=HexEncoder)
        target_x25519_pub = target_verify_key.to_curve25519_public_key()
        crypto_box = Box(self.x25519_private, target_x25519_pub)
        encrypted = crypto_box.encrypt(self.room_key)
        return base64.b64encode(encrypted).decode('utf-8')

    def decrypt_room_key(self, sender_pub_key_hex, encrypted_key_b64):
        """Decrypt the symmetric room key sent by the Archon"""
        if not self.enabled: return False
        try:
            sender_verify_key = VerifyKey(sender_pub_key_hex, encoder=HexEncoder)
            sender_x25519_pub = sender_verify_key.to_curve25519_public_key()
            crypto_box = Box(self.x25519_private, sender_x25519_pub)
            encrypted = base64.b64decode(encrypted_key_b64)
            key_bytes = crypto_box.decrypt(encrypted)
            self.set_room_key(key_bytes)
            return True
        except Exception as e:
            print(f"[E2EE] Failed to decrypt room key: {e}")
            return False

    def encrypt_payload(self, plaintext_bytes):
        """Encrypt arbitrary bytes using the Room Key (Symmetric)"""
        if not self.enabled or not self.secret_box: return plaintext_bytes
        return self.secret_box.encrypt(plaintext_bytes)

    def decrypt_payload(self, ciphertext_bytes):
        if not self.enabled or not self.secret_box: return ciphertext_bytes
        try:
            return self.secret_box.decrypt(ciphertext_bytes)
        except Exception:
            return None
            
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
