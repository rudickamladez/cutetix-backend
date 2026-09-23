"""The /events/{id}/scopes API and the grant service behind it."""
import pytest


def list_scopes(client, auth, token, event_id, user_id):
    return client.get(f"/events/{event_id}/scopes/{user_id}", headers=auth(token))


@pytest.fixture
def granted(db):
    """Scopes a user currently holds on an event, read straight from the DB.

    Going through the API would require the caller to also hold
    `events:read`, which most of these tests deliberately do not grant -
    the read path is covered on its own below.
    """
    from app import models

    def _granted(event_id, user):
        db.expire_all()
        rows = db.query(models.EventUserScope).filter_by(
            event_id=event_id, user_uuid=user.uuid).all()
        return sorted(row.scope for row in rows)

    return _granted


class TestCreatorBootstrapping:
    def test_creating_an_event_grants_the_creator_local_control(
        self, client, auth, granted, make_user, token_for,
    ):
        from app.services import event_user_scopes as service

        creator = make_user(scopes=["events:edit"])
        body = {
            "name": "new event",
            "tickets_sales_start": "2026-01-01T00:00:00",
            "tickets_sales_end": "2026-12-31T00:00:00",
            "smtp_mail_from": "a@b.c",
            "mail_text_new_ticket": "t",
            "mail_html_new_ticket": "h",
            "mail_text_cancelled_ticket": "t",
            "mail_html_cancelled_ticket": "h",
        }

        response = client.post("/events/", json=body,
                               headers=auth(token_for(creator)))

        assert response.status_code == 200
        event_id = response.json()["id"]
        assert granted(event_id, creator) == sorted(service.EVENT_CREATOR_SCOPES)

    def test_creator_needs_no_global_scope_afterwards(
        self, client, auth, make_user, token_for,
    ):
        """The point of the grants: a local admin holding an empty token."""
        creator = make_user(scopes=["events:edit"])
        body = {
            "name": "new event",
            "tickets_sales_start": "2026-01-01T00:00:00",
            "tickets_sales_end": "2026-12-31T00:00:00",
            "smtp_mail_from": "a@b.c",
            "mail_text_new_ticket": "t",
            "mail_html_new_ticket": "h",
            "mail_text_cancelled_ticket": "t",
            "mail_html_cancelled_ticket": "h",
        }
        created = client.post("/events/", json=body,
                              headers=auth(token_for(creator))).json()

        response = client.patch(f"/events/{created['id']}", json=body,
                                headers=auth(token_for(creator, scopes=[])))

        assert response.status_code == 200


class TestGrantAndRevoke:
    def test_grant_is_idempotent(self, client, auth, uid, db, make_user, make_event,
                                 token_for, grant):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")
        url = f"/events/{event.id}/scopes/{uid(target)}/tickets:read"

        first = client.put(url, headers=auth(token_for(admin, scopes=[])))
        second = client.put(url, headers=auth(token_for(admin, scopes=[])))

        assert (first.status_code, second.status_code) == (200, 200)
        from app import models
        rows = db.query(models.EventUserScope).filter_by(
            event_id=event.id, user_uuid=target.uuid, scope="tickets:read").count()
        assert rows == 1

    def test_put_replaces_the_whole_grant_set(self, client, auth, uid, granted, make_user,
                                              make_event, token_for, grant):
        """Documented PUT semantics, asserted so a change stays deliberate."""
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")
        grant(event, target, "tickets:read", "events:read")
        headers = auth(token_for(admin, scopes=[]))

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}",
                              json={"scopes": ["ticket_groups:read"]},
                              headers=headers)

        assert response.status_code == 200
        assert granted(event.id, target) == ["ticket_groups:read"]

    def test_delete_revokes(self, client, auth, uid, granted, make_user, make_event,
                            token_for, grant):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")
        grant(event, target, "tickets:read")

        response = client.delete(
            f"/events/{event.id}/scopes/{uid(target)}/tickets:read",
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 204
        assert granted(event.id, target) == []

    def test_deleting_an_ungranted_scope_is_404(self, client, auth, uid, make_user,
                                                make_event, token_for, grant):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.delete(
            f"/events/{event.id}/scopes/{uid(target)}/tickets:read",
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 404


class TestScopeValueValidation:
    """Both scope routes must agree, and neither accepts a nonsense grant."""

    @pytest.mark.parametrize("scope", [
        "bogus:scope",
        "users:edit",          # global by nature, no event-local meaning
        "users:read",
        "token_family:read",
    ])
    def test_path_route_rejects_non_event_local_scope(
        self, client, auth, uid, make_user, make_event, token_for, grant, scope,
    ):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}/{scope}",
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 422

    @pytest.mark.parametrize("scope", [
        "%20tickets:read",   # leading space
        "tickets:read%20",   # trailing space
    ])
    def test_path_route_rejects_whitespace_padded_scope(
        self, client, auth, uid, granted, make_user, make_event, token_for,
        grant, scope,
    ):
        """A path scope is rejected, not quietly trimmed.

        Two spellings of one grant is exactly what the path pattern promises
        to prevent - and it only holds if the pattern is anchored, since
        Pydantic matches `pattern` as a regex *search*.
        """
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}/{scope}",
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 422
        assert granted(event.id, target) == []

    def test_body_route_still_strips_its_scope(self, client, auth, uid, granted,
                                               make_user, make_event, token_for,
                                               grant):
        """Only the *path* is strict; a JSON body is trimmed as documented."""
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.put(
            f"/events/{event.id}/scopes/{uid(target)}",
            json={"scopes": [" tickets:read "]},
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 200
        assert granted(event.id, target) == ["tickets:read"]

    def test_body_route_rejects_the_same_values(self, client, auth, uid, make_user,
                                                make_event, token_for, grant):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        for scope in ("bogus:scope", "users:edit", "token_family:read"):
            response = client.put(
                f"/events/{event.id}/scopes/{uid(target)}",
                json={"scopes": [scope]},
                headers=auth(token_for(admin, scopes=[])),
            )
            assert response.status_code == 422, scope

    def test_missing_scopes_field_is_422_not_a_wipe(
        self, client, auth, uid, granted, make_user, make_event, token_for, grant,
    ):
        """A malformed body must not silently revoke everything."""
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")
        grant(event, target, "events:edit", "tickets:edit")

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}",
                              json={},
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 422
        assert granted(event.id, target) == ["events:edit", "tickets:edit"]

    def test_explicit_empty_list_clears_scopes(self, client, auth, uid, make_user,
                                               make_event, token_for, grant):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")
        grant(event, target, "tickets:read")

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}",
                              json={"scopes": []},
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 200
        assert response.json() == []

    def test_whitespace_padded_scope_is_accepted_once_stripped(
        self, client, auth, uid, granted, make_user, make_event, token_for, grant,
    ):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}",
                              json={"scopes": ["  tickets:read  "]},
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 200
        assert granted(event.id, target) == ["tickets:read"]


class TestAdminCannotStrandThemselves:
    """Only events:edit can manage scopes, so dropping your own last copy is
    a permanent lockout with no way back."""

    def test_local_admin_cannot_remove_their_own_events_edit(
        self, client, auth, uid, granted, make_user, make_event, token_for, grant,
    ):
        admin = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.put(
            f"/events/{event.id}/scopes/{uid(admin)}",
            json={"scopes": ["tickets:read"]},
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 409
        assert granted(event.id, admin) == ["events:edit"]

    def test_local_admin_cannot_delete_their_own_events_edit(
        self, client, auth, uid, granted, make_user, make_event, token_for, grant,
    ):
        """The single-scope DELETE revokes as effectively as the PUT above.

        Guarding only the replace route leaves the lockout reachable one
        route over, which is the whole point of this test.
        """
        admin = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.delete(
            f"/events/{event.id}/scopes/{uid(admin)}/events:edit",
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 409
        assert granted(event.id, admin) == ["events:edit"]

    def test_local_admin_may_delete_a_scope_that_keeps_them_in(
        self, client, auth, uid, granted, make_user, make_event, token_for, grant,
    ):
        """The guard is about events:edit specifically, not about self-service."""
        admin = make_user(scopes=[])
        event = make_event()
        grant(event, admin, "events:edit", "tickets:read")

        response = client.delete(
            f"/events/{event.id}/scopes/{uid(admin)}/tickets:read",
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 204
        assert granted(event.id, admin) == ["events:edit"]

    def test_global_scope_holder_may_remove_their_local_grant(
        self, client, auth, uid, make_user, make_event, token_for, grant,
    ):
        admin = make_user(scopes=["events:edit"])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.put(
            f"/events/{event.id}/scopes/{uid(admin)}",
            json={"scopes": ["tickets:read"]},
            headers=auth(token_for(admin)),
        )

        assert response.status_code == 200

    def test_global_scope_holder_may_delete_their_local_events_edit(
        self, client, auth, uid, make_user, make_event, token_for, grant,
    ):
        """Holding the scope globally means dropping the local grant is not a
        lockout, so the guard must stay out of the way."""
        admin = make_user(scopes=["events:edit"])
        event = make_event()
        grant(event, admin, "events:edit")

        response = client.delete(
            f"/events/{event.id}/scopes/{uid(admin)}/events:edit",
            headers=auth(token_for(admin)),
        )

        assert response.status_code == 204

    def test_admin_may_delete_someone_elses_last_events_edit(
        self, client, auth, uid, granted, make_user, make_event, token_for, grant,
    ):
        """Only the caller's *own* row is protected; demoting a co-admin is a
        legitimate act of administration."""
        admin = make_user(scopes=["events:edit"])
        demoted = make_user(scopes=[])
        event = make_event()
        grant(event, demoted, "events:edit")

        response = client.delete(
            f"/events/{event.id}/scopes/{uid(demoted)}/events:edit",
            headers=auth(token_for(admin)),
        )

        assert response.status_code == 204
        assert granted(event.id, demoted) == []

    def test_admin_can_remove_someone_elses_grants(self, client, auth, uid,
                                                   make_user, make_event,
                                                   token_for, grant):
        admin = make_user(scopes=["events:edit"])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, target, "events:edit", "tickets:edit")

        response = client.put(f"/events/{event.id}/scopes/{uid(target)}",
                              json={"scopes": []},
                              headers=auth(token_for(admin)))

        assert response.status_code == 200


class TestScopeRouteAuthorization:
    def test_readers_can_list_but_not_change(self, client, auth, uid, make_user,
                                             make_event, token_for, grant):
        reader = make_user(scopes=[])
        target = make_user(scopes=[])
        event = make_event()
        grant(event, reader, "events:read")
        headers = auth(token_for(reader, scopes=[]))

        listing = client.get(f"/events/{event.id}/scopes", headers=headers)
        assert listing.status_code == 200

        write = client.put(f"/events/{event.id}/scopes/{uid(target)}/tickets:read",
                           headers=headers)
        assert write.status_code == 403

    def test_unknown_user_is_404(self, client, auth, make_user, make_event,
                                 token_for):
        from uuid import uuid4

        admin = make_user(scopes=["events:edit"])
        event = make_event()

        response = client.put(f"/events/{event.id}/scopes/{uuid4()}",
                              json={"scopes": ["events:read"]},
                              headers=auth(token_for(admin)))

        assert response.status_code == 404

    def test_anonymous_cannot_list_scopes(self, client, make_event):
        event = make_event()

        response = client.get(f"/events/{event.id}/scopes")

        assert response.status_code == 401


class TestListingNamesItsGrantees:
    """``GET /events/{id}/scopes`` answers in people, not in UUIDs.

    The list is the one thing an event-local admin reads to see who works on
    their event, and they cannot resolve a UUID by any other route: both
    ``GET /users/`` and ``GET /users/{id}`` need the global ``users:read``
    scope, which is exactly what an organiser does not hold. So the names have
    to come back with the grants or the table is unreadable.
    """

    GRANTEE_FIELDS = {"uuid", "username", "full_name", "disabled"}

    @pytest.fixture
    def scene(self, make_user, make_event, grant):
        """An organiser who can read the list, and someone they granted."""
        organiser = make_user(scopes=["events:read", "events:edit"])
        colleague = make_user(scopes=[])
        event = make_event()
        grant(event, colleague, "tickets:read", "tickets:edit")
        return organiser, colleague, event

    def _rows(self, client, auth, token_for, organiser, event):
        response = client.get(
            f"/events/{event.id}/scopes", headers=auth(token_for(organiser))
        )
        assert response.status_code == 200
        return response.json()

    def test_every_grant_carries_the_grantees_name(
        self, client, auth, token_for, uid, scene
    ):
        organiser, colleague, event = scene

        rows = self._rows(client, auth, token_for, organiser, event)

        assert rows, "the granted colleague should be listed"
        for row in rows:
            assert row["user"]["username"] == colleague.username
            assert row["user"]["full_name"] == colleague.full_name
            # Flat and nested forms must agree, or a client reading either
            # silently gets a different person.
            assert row["user"]["uuid"] == row["user_uuid"] == uid(colleague)

    def test_the_grantee_carries_only_the_pickers_fields(
        self, client, auth, token_for, scene
    ):
        """Same boundary as ``GET /users/search``.

        Both responses are built from ``UserSearchResult``, so this is the same
        assertion the picker's tests make -- kept here as well, because a field
        added to the shared projection would land on this endpoint too.
        """
        organiser, _colleague, event = scene

        rows = self._rows(client, auth, token_for, organiser, event)

        for row in rows:
            assert set(row) == {"event_id", "user_uuid", "scope", "user"}
            assert set(row["user"]) == self.GRANTEE_FIELDS

    def test_it_leaks_no_e_mail_global_scopes_or_favorite_events(
        self, client, auth, token_for, scene
    ):
        """Reading a grant list must not out the holder of global powers.

        The colleague here holds nothing privileged, so the interesting case is
        the organiser's *own* row: it belongs to a user whose global scopes
        would be worth knowing about.
        """
        organiser, _colleague, event = scene

        rows = self._rows(client, auth, token_for, organiser, event)

        assert rows
        for row in rows:
            for forbidden in ("email", "scopes", "favorite_events",
                              "hashed_password"):
                assert forbidden not in row
                assert forbidden not in row["user"]

    def test_a_disabled_grantee_is_listed_and_labelled(
        self, client, auth, db, token_for, uid, scene
    ):
        """Disappearing would make the grant look gone while it still exists.

        The row is what somebody needs to find in order to remove it, so the
        listing shows it and says why it is odd.
        """
        from app import models

        organiser, _colleague, event = scene
        stale = models.User(
            username="stale-grantee",
            full_name="Stale Grantee",
            email="stale-grantee@example.invalid",
            hashed_password="not-a-real-hash",
            disabled=True,
            scopes=[],
        )
        db.add(stale)
        db.commit()
        from app.services import event_user_scopes as service

        service.grant_scopes(
            event_id=event.id, user_uuid=stale.uuid,
            scopes=["tickets:read"], db=db,
        )
        db.expire_all()

        rows = self._rows(client, auth, token_for, organiser, event)

        by_uuid = {row["user"]["uuid"]: row["user"] for row in rows}
        assert by_uuid[uid(stale)]["disabled"] is True
        assert by_uuid[uid(stale)]["full_name"] == "Stale Grantee"

    def test_the_per_user_route_stays_a_plain_grant_list(
        self, client, auth, token_for, uid, scene
    ):
        """``/scopes/{user_id}`` answers "what may this person do", for callers
        who already know who they are asking about. Only the whole-event
        listing is a display surface, so only it carries names.
        """
        organiser, colleague, event = scene

        response = client.get(
            f"/events/{event.id}/scopes/{uid(colleague)}",
            headers=auth(token_for(organiser)),
        )

        assert response.status_code == 200
        assert response.json() == [
            {"event_id": event.id, "user_uuid": uid(colleague), "scope": scope}
            for scope in ("tickets:edit", "tickets:read")
        ]

