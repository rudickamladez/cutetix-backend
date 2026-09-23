"""``GET /users/search`` - the scope-grant picker's lookup.

The endpoint exists so an event-local admin can turn a person into a UUID
without a global admin in the loop. What matters here is where the boundary
sits: who may call it, and how little it gives back.
"""
import pytest

SEARCH_FIELDS = {"uuid", "username", "full_name", "disabled"}


def search(client, token, q="someone", **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/users/search", params={"q": q, **kwargs}, headers=headers)


class TestAuthorization:
    def test_anonymous_is_401(self, client, make_user, token_for):
        assert search(client, None).status_code == 401

    def test_authenticated_but_no_grants_is_403(self, client, auth, make_user, token_for):
        """A caller who organises nothing cannot look people up."""
        plain = make_user()

        response = client.get(
            "/users/search",
            params={"q": "nobody"},
            headers=auth(token_for(plain)),
        )

        assert response.status_code == 403

    def test_event_local_grant_is_enough(self, client, auth, make_user, make_event,
                                         grant, token_for):
        organiser = make_user()
        grant(make_event(), organiser, "events:edit")

        response = client.get(
            "/users/search",
            params={"q": "nobody"},
            headers=auth(token_for(organiser)),
        )

        assert response.status_code == 200

    def test_global_events_edit_is_enough(self, client, auth, make_user, token_for):
        """Guards the ``None != []`` semantics of get_event_ids_with_scope.

        A global holder has no event_user_scopes rows, so an implementation
        that only looked at local grants would 403 them - making the global
        scope weaker than the local one.
        """
        admin = make_user(scopes=["events:edit"])

        response = client.get(
            "/users/search",
            params={"q": "nobody"},
            headers=auth(token_for(admin)),
        )

        assert response.status_code == 200

    def test_grant_on_another_scope_does_not_qualify(self, client, auth, make_user,
                                                     make_event, grant, token_for):
        organiser = make_user()
        grant(make_event(), organiser, "tickets:read")

        response = client.get(
            "/users/search",
            params={"q": "nobody"},
            headers=auth(token_for(organiser)),
        )

        assert response.status_code == 403

    def test_narrowed_token_is_403(self, client, auth, make_user, token_for):
        """A token stripped of its scopes must not be upgraded by the DB column."""
        admin = make_user(scopes=["events:edit"])

        response = client.get(
            "/users/search",
            params={"q": "nobody"},
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 403

    def test_does_not_require_the_global_users_read_scope(self, client, auth, make_user,
                                                          make_event, grant, token_for):
        """The whole point: an organiser without users:read can still search."""
        organiser = make_user()
        grant(make_event(), organiser, "events:edit")

        response = client.get(
            "/users/search",
            params={"q": "nobody"},
            headers=auth(token_for(organiser)),
        )

        assert response.status_code == 200


class TestProjection:
    @pytest.fixture
    def organiser(self, db, make_user, make_event, grant):
        user = make_user()
        grant(make_event(), user, "events:edit")
        return user

    def test_only_the_picker_fields_come_back(self, client, auth, make_user, organiser,
                                              token_for, uid):
        target = make_user()

        body = search(client, token_for(organiser), q=target.email).json()

        assert len(body) == 1
        assert set(body[0]) == SEARCH_FIELDS

    def test_leaks_no_email_scopes_or_favorite_events(self, client, auth, make_user,
                                                     organiser, token_for):
        target = make_user(scopes=["users:edit", "token_family:read"])

        body = search(client, token_for(organiser), q=target.email).json()

        assert body
        for row in body:
            assert "email" not in row
            assert "scopes" not in row
            assert "favorite_events" not in row

    def test_uuid_is_rendered_not_raw_bytes(self, client, auth, make_user, organiser,
                                            token_for, uid):
        """users.uuid is BINARY(16); the picker must receive a usable UUID."""
        target = make_user()

        body = search(client, token_for(organiser), q=target.email).json()

        assert body[0]["uuid"] == uid(target)

    def test_disabled_accounts_are_returned_and_labelled(self, client, auth, db,
                                                         organiser, token_for):
        """Filtering them out would make 'disabled account' look like 'no such person'."""
        from app import models

        name = "disabled-account-user"
        db.add(models.User(
            username=name,
            full_name="Disabled Account",
            email="disabled-account@example.invalid",
            hashed_password="not-a-real-hash",
            disabled=True,
            scopes=[],
        ))
        db.commit()

        body = search(client, token_for(organiser), q=name).json()

        assert [row["disabled"] for row in body] == [True]


class TestMatching:
    @pytest.fixture
    def organiser(self, make_user, make_event, grant):
        user = make_user()
        grant(make_event(), user, "events:edit")
        return user

    def test_unknown_address_is_an_empty_list_not_404(self, client, auth, organiser,
                                                      token_for):
        response = search(client, token_for(organiser), q="nobody@example.invalid")

        assert response.status_code == 200
        assert response.json() == []

    def test_exact_email_hit(self, client, auth, make_user, organiser, token_for):
        target = make_user()

        body = search(client, token_for(organiser), q=target.email).json()

        assert [row["username"] for row in body] == [target.username]

    def test_email_match_is_case_insensitive(self, client, auth, make_user, organiser,
                                             token_for):
        target = make_user()

        body = search(client, token_for(organiser), q=target.email.upper()).json()

        assert [row["username"] for row in body] == [target.username]

    def test_email_is_not_matched_as_a_substring(self, client, auth, db, organiser,
                                                 token_for):
        """The choice that keeps this from enumerating addresses.

        The probe strings are chosen so they cannot be mistaken for a username
        prefix - otherwise a hit would be the username branch answering, not a
        substring match on email.
        """
        from app import models

        db.add(models.User(
            username="exact-email-only",
            full_name="Exact Email Only",
            email="sub.string.target@example.invalid",
            hashed_password="not-a-real-hash",
            disabled=False,
            scopes=[],
        ))
        db.commit()

        for probe in ("sub.string", "string.target", "target@exam",
                      "example.invalid"):
            assert search(client, token_for(organiser), q=probe).json() == [], probe

        # ...but the whole address does match.
        body = search(client, token_for(organiser),
                      q="sub.string.target@example.invalid").json()
        assert [row["username"] for row in body] == ["exact-email-only"]

    def test_username_prefix_hit(self, client, auth, organiser, token_for):
        """Conftest usernames look like ``user-1a2b3c4d5e6f``."""
        body = search(client, token_for(organiser), q="user-").json()

        assert body  # every seeded user matches

    def test_username_is_not_matched_mid_string(self, client, auth, make_user,
                                                organiser, token_for):
        target = make_user()
        suffix = target.username[len("user-"):][2:]

        assert search(client, token_for(organiser), q=suffix).json() == []

    def test_username_match_is_case_insensitive(self, client, auth, make_user,
                                                organiser, token_for):
        target = make_user()

        body = search(client, token_for(organiser), q=target.username.upper()).json()

        assert [row["username"] for row in body] == [target.username]

    def test_literal_underscore_is_not_a_wildcard(self, client, auth, db, organiser,
                                                  token_for):
        """``_`` is a single-character LIKE wildcard, so an unescaped q would
        match ``prefixAsuffix`` when asked for ``prefix_suffix``."""
        from app import models

        for name in ("prefix_suffix", "prefixAsuffix"):
            db.add(models.User(
                username=name,
                full_name=name,
                email=f"{name}@example.invalid",
                hashed_password="not-a-real-hash",
                disabled=False,
                scopes=[],
            ))
        db.commit()

        body = search(client, token_for(organiser), q="prefix_suffix").json()

        assert [row["username"] for row in body] == ["prefix_suffix"]

    def test_literal_percent_is_not_a_wildcard(self, client, auth, db, organiser,
                                               token_for):
        from app import models

        # 'prefixZZZsuffix' only matches if the '%' in q is left unescaped.
        for name in ("prefix%suffix", "prefixZZZsuffix"):
            db.add(models.User(
                username=name,
                full_name=name,
                email=f"{name.replace('%', 'pct')}@example.invalid",
                hashed_password="not-a-real-hash",
                disabled=False,
                scopes=[],
            ))
        db.commit()

        body = search(client, token_for(organiser), q="prefix%suffix").json()

        assert [row["username"] for row in body] == ["prefix%suffix"]

    def test_shared_email_returns_every_account(self, client, auth, db, organiser,
                                                token_for):
        """email is indexed but not unique - so this must not .first()."""
        from app import models

        shared = "shared-address@example.invalid"
        for name in ("shared-email-one", "shared-email-two"):
            db.add(models.User(
                username=name,
                full_name=name,
                email=shared,
                hashed_password="not-a-real-hash",
                disabled=False,
                scopes=[],
            ))
        db.commit()

        body = search(client, token_for(organiser), q=shared).json()

        assert sorted(row["username"] for row in body) == [
            "shared-email-one",
            "shared-email-two",
        ]

    def test_results_are_ordered_by_username(self, client, auth, organiser, token_for):
        body = search(client, token_for(organiser), q="user-").json()

        usernames = [row["username"] for row in body]
        assert usernames == sorted(usernames)

    def test_results_are_capped(self, client, auth, db, organiser, token_for):
        from app.services.user import SEARCH_LIMIT

        for i in range(SEARCH_LIMIT + 5):
            db.add(db_new_user(f"bulk-user-{i:03d}"))
        db.commit()

        body = search(client, token_for(organiser), q="bulk-user-").json()

        assert len(body) == SEARCH_LIMIT

    def test_search_is_not_shadowed_by_the_id_route(self, client, auth, organiser,
                                                   token_for):
        """/users/{id} is declared with id: UUID - a route-order regression
        answers 422 here instead of reaching the search handler."""
        response = search(client, token_for(organiser), q="anything")

        assert response.status_code == 200


class TestQueryValidation:
    @pytest.fixture
    def organiser(self, make_user, make_event, grant):
        user = make_user()
        grant(make_event(), user, "events:edit")
        return user

    def test_two_characters_is_422(self, client, auth, organiser, token_for):
        assert search(client, token_for(organiser), q="ab").status_code == 422

    def test_missing_q_is_422(self, client, auth, organiser, token_for):
        response = client.get(
            "/users/search",
            headers=auth(token_for(organiser)),
        )

        assert response.status_code == 422

    def test_over_long_q_is_422(self, client, auth, organiser, token_for):
        assert search(
            client, token_for(organiser), q="a" * 256
        ).status_code == 422


def db_new_user(username):
    from app import models

    return models.User(
        username=username,
        full_name=username,
        email=f"{username}@example.invalid",
        hashed_password="not-a-real-hash",
        disabled=False,
        scopes=[],
    )
