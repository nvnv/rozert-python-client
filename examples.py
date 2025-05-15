import os
import pprint
import typing as ty
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from os import getenv
from threading import Lock
from uuid import UUID

from rozert_client import RozertClient, DepositRequest, TransactionData


# BEGIN rozert_client.init
client = RozertClient(
    host=getenv("ROZERT_HOST", "https://ps-stage.rozert.cloud"),
    merchant_id=getenv("ROZERT_MERCHANT_ID", "<merchant id provided by rozert>"),
    secret_key=getenv("ROZERT_SECRET_KEY", "<secret key provided by rozert>"),

    # Production / sandbox environment
    sandbox=True,
)
# END rozert_client.init


def deposit_paypal_example() -> TransactionData:
    # Create deposit request

    # BEGIN rozert_client.deposit.paypal
    response = client.start_deposit(
        request=DepositRequest(
            # Wallet id provided by Rozert
            wallet_id=UUID(getenv("ROZERT_PAYPAL_SANDBOX_WALLET_ID", "<wallet id provided by rozert>")),
            amount=Decimal(100),
            currency="MXN",
            callback_url="https://merchant.com/callback",
            user_data={
                "email": "test@test.com",
                "phone": "+12345678910",
                "first_name": "John",
                "last_name": "Doe",
                "post_code": "12345",
                "city": "City",
                "state": "State",
                "address": "Address",
                "country": "Country",
            },
        ),
        url="/api/payment/v1/paypal/deposit/",
    )
    # END rozert_client.deposit.paypal

    pprint.pprint(response.dict())

    return response


def deposit_paycash_example() -> TransactionData:
    # Create deposit request

    # BEGIN rozert_client.deposit.paycash
    response = client.start_deposit(
        request=DepositRequest(
            # Wallet id provided by Rozert
            wallet_id=UUID(getenv("ROZERT_PAYCASH_SANDBOX_WALLET_ID", "<wallet id provided by rozert>")),
            amount=Decimal(100),
            currency="MXN",
            callback_url="https://merchant.com/callback",
        ),
        url="/api/payment/v1/paycash/deposit/",
    )
    # END rozert_client.deposit.paycash

    pprint.pprint(response.dict())

    return response


lock = Lock()


def run_with_error_log(func: ty.Callable) -> None:  # type: ignore[type-arg]
    try:
        func()
    except Exception as e:
        with lock:
            print(f"Error in {func}: {e}", str(e))
            raise


if __name__ == '__main__':
    with ThreadPoolExecutor(100) as pool:
        pool.submit(run_with_error_log, deposit_paypal_example)
        pool.submit(run_with_error_log, deposit_paycash_example)

        pool.shutdown(wait=True)
