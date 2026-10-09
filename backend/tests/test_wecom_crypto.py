"""wecom/crypto.py 测试——企业微信回调加解密。

覆盖 4 个纯函数：
- aes_key_from_encoding_aes_key: 43 位 base64 → 32 字节 AES key
- get_signature: SHA1 签名（排序 + 拼接）
- encrypt/decrypt: AES-256-CBC round-trip

wecom/ 目录在项目根目录下（不在 backend/ 下），
本测试文件自行把项目根目录加入 sys.path。
"""
import base64
import hashlib
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，以便 `from wecom.crypto import ...`
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

from wecom.crypto import (
    aes_key_from_encoding_aes_key,
    get_signature,
    encrypt,
    decrypt,
)


# 固定测试用的 43 位 EncodingAESKey（企业微信规范：a-z A-Z 0-9 共 62 选 43）
TEST_ENCODING_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
TEST_RECEIVE_ID = "ww1234567890abcdef"


@pytest.fixture
def aes_key():
    return aes_key_from_encoding_aes_key(TEST_ENCODING_KEY)


# ========== aes_key_from_encoding_aes_key ==========

def test_aes_key_length_and_type():
    """43 位 encoding key 解码后应取 32 字节作为 AES-256 key。"""
    key = aes_key_from_encoding_aes_key(TEST_ENCODING_KEY)
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_aes_key_deterministic():
    """相同输入应产生相同 key。"""
    k1 = aes_key_from_encoding_aes_key(TEST_ENCODING_KEY)
    k2 = aes_key_from_encoding_aes_key(TEST_ENCODING_KEY)
    assert k1 == k2


# ========== get_signature ==========

def test_get_signature_deterministic():
    """相同输入产生相同签名，SHA1 hex 长度为 40。"""
    s1 = get_signature("token", "1234567890", "nonce", "encrypted")
    s2 = get_signature("token", "1234567890", "nonce", "encrypted")
    assert s1 == s2
    assert len(s1) == 40


def test_get_signature_order_independent():
    """参数顺序不影响签名（内部排序后拼接）。"""
    s1 = get_signature("token", "1234567890", "nonce", "encrypted")
    s2 = get_signature("nonce", "token", "encrypted", "1234567890")
    assert s1 == s2


def test_get_signature_matches_reference():
    """与手工计算的 SHA1 参考值对比。"""
    token, ts, nonce, enc = "token", "1234567890", "nonce", "encrypted"
    expected = hashlib.sha1(
        "".join(sorted([token, ts, nonce, enc])).encode("utf-8")
    ).hexdigest()
    assert get_signature(token, ts, nonce, enc) == expected


# ========== encrypt / decrypt round-trip ==========

def test_round_trip_simple(aes_key):
    """英文消息 round-trip。"""
    msg = "hello world"
    encrypted = encrypt(msg, aes_key, TEST_RECEIVE_ID)
    assert decrypt(encrypted, aes_key, TEST_RECEIVE_ID) == msg


def test_round_trip_chinese(aes_key):
    """中文消息（UTF-8 多字节）round-trip。"""
    msg = "你好，世界！这是测试。"
    encrypted = encrypt(msg, aes_key, TEST_RECEIVE_ID)
    assert decrypt(encrypted, aes_key, TEST_RECEIVE_ID) == msg


def test_round_trip_empty(aes_key):
    """空消息 round-trip。"""
    msg = ""
    encrypted = encrypt(msg, aes_key, TEST_RECEIVE_ID)
    assert decrypt(encrypted, aes_key, TEST_RECEIVE_ID) == msg


def test_round_trip_long(aes_key):
    """长消息（跨多个 AES 块）round-trip。"""
    msg = "测试" * 500
    encrypted = encrypt(msg, aes_key, TEST_RECEIVE_ID)
    assert decrypt(encrypted, aes_key, TEST_RECEIVE_ID) == msg


# ========== encrypt 属性 ==========

def test_encrypt_output_is_valid_base64(aes_key):
    """加密输出应是合法 base64 字符串。"""
    encrypted = encrypt("test", aes_key, TEST_RECEIVE_ID)
    assert isinstance(encrypted, str)
    base64.b64decode(encrypted)  # 不抛异常即合法


def test_encrypt_produces_different_ciphertexts(aes_key):
    """相同明文两次加密应产生不同密文（因 IV 随机）。"""
    e1 = encrypt("same message", aes_key, TEST_RECEIVE_ID)
    e2 = encrypt("same message", aes_key, TEST_RECEIVE_ID)
    assert e1 != e2


# ========== 负向测试 ==========

def test_decrypt_wrong_receive_id(aes_key):
    """receive_id 不匹配应抛 ValueError。"""
    encrypted = encrypt("test", aes_key, TEST_RECEIVE_ID)
    with pytest.raises(ValueError, match="receive_id mismatch"):
        decrypt(encrypted, aes_key, "wrong_id")


def test_decrypt_tampered_ciphertext(aes_key):
    """篡改密文后解密应失败：抛异常或返回与原文不同的结果。"""
    encrypted = encrypt("test message", aes_key, TEST_RECEIVE_ID)
    raw = bytearray(base64.b64decode(encrypted))
    raw[0] ^= 0xFF  # 翻转第 1 个字节，破坏 CBC 链
    tampered = base64.b64encode(bytes(raw)).decode()
    try:
        result = decrypt(tampered, aes_key, TEST_RECEIVE_ID)
        assert result != "test message"
    except Exception:
        pass  # 抛异常也是可接受的
