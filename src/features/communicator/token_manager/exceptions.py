class UnknownResponseError(RuntimeError):
    pass


class DeviceCodeRequestError(RuntimeError):
    pass


class DeviceCodeExpiredError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


class TokenFileError(RuntimeError):
    pass
