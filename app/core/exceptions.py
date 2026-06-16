from fastapi import HTTPException


class UpstreamServiceError(HTTPException):
    def __init__(self, detail: str = "Upstream service unavailable") -> None:
        super().__init__(status_code=502, detail=detail)


class ValidationErrorHTTP(HTTPException):
    def __init__(self, detail: str = "Invalid request") -> None:
        super().__init__(status_code=400, detail=detail)
