import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import jwt
import requests

logger = logging.getLogger(__name__)


def _rfc3339_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EnableBankingService:
    """
    Minimal Enable Banking REST client (sandbox or production).
    This uses direct REST calls with a JWT signed using your private key.
    """

    def __init__(self, application_id: str, private_key_pem: str, base_url: str = "https://api.enablebanking.com", timeout: int = 30):
        self.application_id = application_id
        self.private_key_pem = private_key_pem
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _generate_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        }
        headers = {"typ": "JWT", "kid": self.application_id}
        return jwt.encode(payload, self.private_key_pem, algorithm="RS256", headers=headers)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._generate_jwt()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", None)
        if headers:
            headers = {**self._headers(), **headers}
        else:
            headers = self._headers()

        response = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.error("Enable Banking error %s %s: %s", method, url, response.text)
            raise
        return response

    def get_aspsps(self, country: str = "FR") -> List[Dict]:
        response = self._request("GET", f"/aspsps?country={country}")
        return response.json().get("aspsps", [])

    def start_auth(
        self,
        aspsp_name: str,
        country: str,
        redirect_url: str,
        access: Optional[Dict] = None,
        psu_type: str = "personal",
        auth_method: Optional[str] = None,
        state: Optional[str] = None,
    ) -> Dict:
        if access is None:
            valid_until = datetime.now(timezone.utc) + timedelta(days=90)
            access = {
                "balances": True,
                "transactions": True,
                "valid_until": _rfc3339_utc(valid_until),
            }

        data = {
            "aspsp": {"name": aspsp_name, "country": country},
            "redirect_url": redirect_url,
            "psu_type": psu_type,
            "access": access,
        }
        if auth_method:
            data["auth_method"] = auth_method
        if state:
            data["state"] = state

        response = self._request("POST", "/auth", json=data)
        return response.json()

    def exchange_code(self, code: str) -> Dict:
        response = self._request("POST", "/sessions", json={"code": code})
        return response.json()

    def get_session(self, session_id: str) -> Dict:
        response = self._request("GET", f"/sessions/{session_id}")
        return response.json()

    def get_transactions(
        self,
        account_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        continuation_key: Optional[str] = None,
    ) -> Dict:
        params: Dict[str, str] = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if continuation_key:
            params["continuation_key"] = continuation_key

        response = self._request("GET", f"/accounts/{account_id}/transactions", params=params)
        return response.json()

    def fetch_all_transactions(
        self,
        account_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_pages: int = 20,
    ) -> List[Dict]:
        all_items: List[Dict] = []
        continuation_key: Optional[str] = None

        for _ in range(max_pages):
            data = self.get_transactions(account_id, date_from=date_from, date_to=date_to, continuation_key=continuation_key)
            all_items.extend(data.get("transactions", []))
            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break

        return all_items
