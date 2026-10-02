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


class _AuthScopeGroup:
    @classmethod
    def all_values(cls) -> list[str]:
        return [
            scope.value
            for scope in vars(cls).values()
            if isinstance(scope, AuthScope)
        ]


class AuthScopes:
    """Container for all predefined authentication scopes."""
    @classmethod
    def all_values(cls) -> list[str]:
        return [
            scope
            for scope_group in vars(cls).values()
            if isinstance(scope_group, type)
            and issubclass(scope_group, _AuthScopeGroup)
            for scope in scope_group.all_values()
        ]

    class Users(_AuthScopeGroup):
        Read = AuthScope("users:read", "Read information about users.")
        Edit = AuthScope("users:edit", "Edit information about users.")

    class Event(_AuthScopeGroup):
        Read = AuthScope("events:read", "Read information about events.")
        Edit = AuthScope("events:edit", "Edit information about events.")

    class TokenFamily(_AuthScopeGroup):
        Read = AuthScope("token_family:read",
                         "Read all token families from DB")

    class TicketGroup(_AuthScopeGroup):
        Read = AuthScope("ticket_groups:read",
                         "Read information about ticket groups.")
        Edit = AuthScope("ticket_groups:edit",
                         "Edit information about ticket groups.")

    class Ticket(_AuthScopeGroup):
        Read = AuthScope("tickets:read", "Read information about tickets.")
        Edit = AuthScope("tickets:edit", "Edit information about tickets.")


if __name__ == "__main__":
    auth_scopes = AuthScopes()
    print(auth_scopes.all_values())
