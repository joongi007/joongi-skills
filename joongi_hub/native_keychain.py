"""macOS generic-password items through Security.framework, without secret argv."""

import ctypes

from joongi_hub.errors import RpcError


def item(action, service, account, data=None):
    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    ptr = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ptr, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = ptr
    cf.CFDataCreate.argtypes = [ptr, ptr, ctypes.c_long]
    cf.CFDataCreate.restype = ptr
    cf.CFDictionaryCreate.argtypes = [ptr, ptr, ptr, ctypes.c_long, ptr, ptr]
    cf.CFDictionaryCreate.restype = ptr
    cf.CFRelease.argtypes = [ptr]
    cf.CFDataGetLength.argtypes = [ptr]
    cf.CFDataGetLength.restype = ctypes.c_long
    cf.CFDataGetBytePtr.argtypes = [ptr]
    cf.CFDataGetBytePtr.restype = ptr
    for name, args in {
        "SecItemCopyMatching": [ptr, ptr],
        "SecItemAdd": [ptr, ptr],
        "SecItemUpdate": [ptr, ptr],
        "SecItemDelete": [ptr],
    }.items():
        function = getattr(security, name)
        function.argtypes, function.restype = args, ctypes.c_int32
    allocated = []

    def constant(name):
        return ptr.in_dll(security, name).value

    def text(value):
        result = cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)
        allocated.append(result)
        return result

    def dictionary(values):
        keys = (ptr * len(values))(*[constant(k) for k in values])
        vals = (ptr * len(values))(*values.values())
        result = cf.CFDictionaryCreate(
            None,
            keys,
            vals,
            len(values),
            ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")),
            ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryValueCallBacks")),
        )
        allocated.append(result)
        return result

    try:
        attrs = {
            "kSecClass": constant("kSecClassGenericPassword"),
            "kSecAttrService": text(service),
            "kSecAttrAccount": text(account),
            "kSecUseAuthenticationUI": constant("kSecUseAuthenticationUIFail"),
        }
        if action == "read":
            attrs.update(
                kSecReturnData=ptr.in_dll(cf, "kCFBooleanTrue").value,
                kSecMatchLimit=constant("kSecMatchLimitOne"),
            )
            result = ptr()
            status = security.SecItemCopyMatching(dictionary(attrs), ctypes.byref(result))
            if status == -25300:
                return None
            if status == 0:
                try:
                    return ctypes.string_at(cf.CFDataGetBytePtr(result), cf.CFDataGetLength(result))
                finally:
                    cf.CFRelease(result)
        elif action == "delete":
            status = security.SecItemDelete(dictionary(attrs))
            if status in {0, -25300}:
                return None
        else:
            buffer = ctypes.create_string_buffer(data)
            value = cf.CFDataCreate(None, buffer, len(data))
            allocated.append(value)
            status = security.SecItemUpdate(dictionary(attrs), dictionary({"kSecValueData": value}))
            if status == -25300:
                status = security.SecItemAdd(dictionary({**attrs, "kSecValueData": value}), None)
            if status == 0:
                return None
        raise RpcError(-32045, "macOS 로그인 Keychain을 잠금 해제하고 다시 시도하세요.")
    finally:
        for value in reversed(allocated):
            if value:
                cf.CFRelease(value)
