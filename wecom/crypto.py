# -*- coding: utf-8 -*-
"""企业微信回调加解密（官方 WXBizMsgCrypt 算法实现）。

- 签名：SHA1(排序拼接 token/timestamp/nonce/encrypt)
- 加密：AES-256-CBC，PKCS7，IV=Key 前16字节
- 密文格式：random(16B) + msg_len(4B 网络序) + msg + receive_id
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct

from Crypto.Cipher import AES


def aes_key_from_encoding_aes_key(encoding_aes_key: str) -> bytes:
    """EncodingAESKey(43位) base64 解码后取前 32 字节作为 AES-256 Key。"""
    key = base64.b64decode(encoding_aes_key + "=")
    return key[:32]


def get_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    """计算 msg_signature：对 [token, timestamp, nonce, encrypt] 排序后拼接，SHA1。"""
    sort_list = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(sort_list).encode("utf-8")).hexdigest()


def decrypt(encrypt: str, aes_key: bytes, receive_id: str) -> str:
    """解密企业微信密文，返回 (明文消息, 校验的 receive_id)。"""
    ciphertext = base64.b64decode(encrypt)
    cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
    plain = cipher.decrypt(ciphertext)
    # 去 PKCS7 填充
    pad = plain[-1]
    if pad < 1 or pad > 32:
        raise ValueError("invalid padding")
    plain = plain[:-pad]
    msg_len = struct.unpack(">I", plain[16:20])[0]
    msg = plain[20:20 + msg_len].decode("utf-8")
    rid = plain[20 + msg_len:].decode("utf-8")
    if rid != receive_id:
        raise ValueError(f"receive_id mismatch: {rid} != {receive_id}")
    return msg


def encrypt(msg: str, aes_key: bytes, receive_id: str) -> str:
    """加密明文为 Base64 密文（用于被动回复）。"""
    random_bytes = os.urandom(16)
    msg_bytes = msg.encode("utf-8")
    msg_len = struct.pack(">I", len(msg_bytes))
    plain = random_bytes + msg_len + msg_bytes + receive_id.encode("utf-8")
    pad_len = 32 - len(plain) % 32
    plain += bytes([pad_len]) * pad_len
    cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
    return base64.b64encode(cipher.encrypt(plain)).decode("utf-8")
