from app.auth_scopes import AuthScope, AuthScopes


def get_all_scopes():
    # Return dict { value: description } defined in AuthScopes in for cycle
    scopes_dict = {}
    for category_name in vars(AuthScopes):
        category = getattr(AuthScopes, category_name)
        if isinstance(category, type):
            for scope_name in dir(category):
                scope = getattr(category, scope_name)
                if isinstance(scope, AuthScope):
                    scopes_dict[scope.value] = scope.description
    return scopes_dict

