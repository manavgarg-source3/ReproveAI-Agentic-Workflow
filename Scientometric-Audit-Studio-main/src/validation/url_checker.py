"""
HTTP URL status interpreter and accessibility checker.
Prevents false classification of 403 bot blocks / auth gates as broken URLs.
"""
from typing import Optional, Tuple


class URLStatusInterpreter:
    """
    Interprets HTTP status codes for scholarly articles and DOI targets.
    """

    @staticmethod
    def classify(http_status: Optional[int], redirect_count: int = 0, error: Optional[str] = None) -> Tuple[str, str]:
        """
        Returns (status_category, user_explanation).
        """
        if error:
            if "TIMEOUT" in error.upper():
                return ("TIMEOUT", "Request timed out while contacting server.")
            return ("NETWORK_ERROR", f"Network error: {error}")

        if http_status is None:
            return ("UNCHECKED", "HTTP check was not performed.")

        if http_status == 200:
            if redirect_count > 0:
                return ("REDIRECT_REACHABLE", f"URL resolved with {redirect_count} redirect(s) to 200 OK.")
            return ("REACHABLE", "URL directly reachable with 200 OK.")

        if http_status in (301, 302, 303, 307, 308):
            return ("REDIRECTING", f"URL returned redirect status {http_status}.")

        if http_status in (401, 403):
            return (
                "ACCESS_RESTRICTED",
                f"HTTP {http_status} returned. Resource is protected by bot-check, authentication, or paywall; NOT necessarily broken.",
            )

        if http_status == 404:
            return ("BROKEN_NOT_FOUND", "HTTP 404: The target resource does not exist on the server.")

        if http_status == 410:
            return ("GONE", "HTTP 410: The resource has been permanently removed by the publisher.")

        if 500 <= http_status <= 599:
            return ("SERVER_ERROR", f"Publisher server error HTTP {http_status}.")

        return ("UNEXPECTED_STATUS", f"Received unexpected HTTP status {http_status}.")

