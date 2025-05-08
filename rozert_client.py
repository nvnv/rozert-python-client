import base64
import datetime
import decimal
import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal
from enum import Enum
from typing import (
    Literal,
    Union,
    Optional,
    Any,
    cast,
)
from uuid import UUID

import requests
from pydantic import (
    BaseModel,
    Field,
)

logger = logging.getLogger(__name__)



class BMJsonEncoder(json.JSONEncoder):
    def default(self, obj):     # type: ignore
        if isinstance(obj, decimal.Decimal):
            return format(obj, 'f')
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, datetime.date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, '__json__'):
            return obj.__json__()
        return super().default(obj)



def sign_request(request_body: str, secret: str) -> str:
    secret_key = secret.encode()
    message = request_body
    signature = hmac.new(secret_key, message.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(signature)
    return signature.decode()


class Instruction(BaseModel):
    type: Literal["instruction_file", "instruction_qr_code"]
    link: Union[str, None] = None
    qr_code: Union[str, None] = None


class TransactionExtraFormData(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    action_url: str
    method: Literal["get", "post"]
    fields: dict[str, Any] = cast(dict[str, Any], Field(default_factory=dict))  # type: ignore

    def to_dict(self) -> dict[str, Any]:
        try:
            return self.model_dump()  # type: ignore[attr-defined]
        except AttributeError:
            return self.dict()


class TransactionData(BaseModel):
    id: str
    status: Literal["pending", "success", "failed"]
    wallet_id: UUID
    type: Literal["deposit", "withdrawal"]
    amount: Decimal
    currency: str
    instruction: Union[Instruction, None]
    decline_code: Optional[str]
    decline_reason: Optional[str]

    user_data: Optional[dict[str, Any]] = None
    user_form_data: Optional[TransactionExtraFormData] = None


class DepositRequest(BaseModel):
    wallet_id: UUID
    amount: Decimal
    currency: str
    callback_url: Optional[str] = None
    user_data: Optional[dict[str, Any]] = None
    redirect_url: Optional[str] = None


class PhoneRequired(BaseModel):
    phone: str


class StpCodiRequest(DepositRequest):
    user_data: PhoneRequired    # type: ignore[assignment]
    deposit_type: Literal["app", "qr_code"] = "app"

class WithdrawRequest(BaseModel):
    wallet_id: UUID
    amount: Decimal
    currency: str
    callback_url: Optional[str] = None
    system: str


def transaction_data_from_response(response: dict[str, Any]) -> TransactionData:
    data = {
        **response,
        "user_form_data": response.get("form"),
    }
    if hasattr(TransactionData, "model_validate"):
        return cast(Any, TransactionData).model_validate(data)
    return TransactionData(**data)  # type: ignore[arg-type]


class RozertClient:
    def __init__(
        self, *, host: str, merchant_id: str, secret_key: str,
        sandbox: bool = False,
    ):
        self.host = host
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.session = requests.Session()
        self.sandbox = sandbox

    def start_deposit(
        self,
        request: DepositRequest,
        url: str,
        user_data: Optional[dict[str, Any]] = None
    ) -> TransactionData:
        data = cast(Any, request).model_dump() if hasattr(request, "model_dump") else request.dict()

        if user_data:
            data["user_data"] = user_data

        resp = self._make_request(
            method="post",
            url=url,
            data=data,
        )
        assert isinstance(resp, dict)
        return transaction_data_from_response(resp)

    def start_withdraw(
        self, request: WithdrawRequest,
    ) -> TransactionData:
        # TODO: pass url: str as in start_deposit
        data = cast(Any, request).model_dump() if hasattr(request, "model_dump") else request.dict()

        if request.system == "rozert_paypal":
            url = "/api/payment/v1/paypal/withdraw/"
        else:
            raise RuntimeError(f"Unknown system {request.system}")

        resp = self._make_request(
            method="post",
            url=url,
            data=data,
        )
        assert isinstance(resp, dict)
        return transaction_data_from_response(resp)

    def stp_codi_deposit(self, request: StpCodiRequest) -> TransactionData:
        return self.start_deposit(
            request=request,
            url="",
            user_data=request.user_data.dict(),
        )

    def _make_request(
        self,
        method: Literal['get', 'post'],
        url: str,
        data: Union[dict[str, Any], list[Any], None],
    ) -> Union[dict[str, Any], list[Any]]:    # pragma: no cover
        data_str = data and json.dumps(data, cls=BMJsonEncoder)
        resp = self.session.request(
            method=method,
            url=f"{self.host}{url}",
            data=data_str,
            headers=self._get_headers(data_str or ''),
        )
        if not resp.ok:
            logger.warning(
                f"Rozert request failed: {resp.status_code} {resp.text[:1000]}"
            )
        resp.raise_for_status()
        return resp.json()

    # BEGIN authorization.request.example
    def _get_headers(self, data: str) -> dict[str, str]:
        result = {
            "X-Merchant-Id": self.merchant_id,
            "X-Signature": sign_request(data, self.secret_key),
            "Content-Type": "application/json",
        }
        if self.sandbox:
            result["X-Sandbox-Mode"] = "true"
        return result
    # END authorization.request.example

    def get_transaction(self, id: str) -> TransactionData:
        resp = self._make_request(
            method="get",
            url=f"/api/payment/v1/transaction/{id}/",
            data=None,
        )
        assert isinstance(resp, dict), resp
        return transaction_data_from_response(resp)
