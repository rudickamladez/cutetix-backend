SCOPE_MAX_LENGTH = 64


class AuthScope:
    """Represents a single authentication scope."""
    MAX_LENGTH = SCOPE_MAX_LENGTH

    def __init__(self, scope_value: str, description: str = ""):
        if len(scope_value) > self.MAX_LENGTH:
            raise ValueError(
                f"Scope value exceeds maximum length of {self.MAX_LENGTH}")
        self.value = scope_value
        self.description = description


class AuthScopes:
    """Container for all predefined authentication scopes."""

    class Users:
        Read = AuthScope("users:read", "Read information about users.")
        Edit = AuthScope("users:edit", "Edit information about users.")

    class Event:
        Read = AuthScope("events:read", "Read information about events.")
        Edit = AuthScope("events:edit", "Edit information about events.")

    class TokenFamily:
        Read = AuthScope("token_family:read",
                         "Read all token families from DB")

    class TicketGroup:
        Read = AuthScope("ticket_groups:read",
                         "Read information about ticket groups.")
        Edit = AuthScope("ticket_groups:edit",
                         "Edit information about ticket groups.")

    class Ticket:
        Read = AuthScope("tickets:read", "Read information about tickets.")
        Edit = AuthScope("tickets:edit", "Edit information about tickets.")
