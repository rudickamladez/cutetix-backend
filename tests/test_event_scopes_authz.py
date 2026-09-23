"""The event-tenancy authorization boundary.

These cover the behaviours that PR #68 introduced and that are easy to
break silently: which scope set authorizes a request, and what happens
when a request body can move a resource across an event boundary.
"""
import pytest
from fastapi import status


def ticket_body(ticket, group_id):
    return {
        "email": ticket.email,
        "firstname": ticket.firstname,
        "lastname": ticket.lastname,
        "status": int(ticket.status.value),
        "description": ticket.description,
        "group_id": group_id,
    }


class TestTokenScopesAreAuthoritative:
    """A token narrower than the user's DB scopes must stay narrow.

    /auth/login and /auth/refresh both narrow on purpose, so a
    least-privilege token must not be upgraded by the DB column.
    """

    def test_narrowed_token_cannot_edit_event(self, client, auth, make_user,
                                              make_event, token_for):
        admin = make_user(scopes=["events:edit"])
        event = make_event()
        token = token_for(admin, scopes=[])

        response = client.patch(
            f"/events/{event.id}",
            json={
                "name": "hijacked",
                "tickets_sales_start": "2026-01-01T00:00:00",
                "tickets_sales_end": "2026-12-31T00:00:00",
                "smtp_mail_from": "a@b.c",
                "mail_text_new_ticket": "t",
                "mail_html_new_ticket": "h",
                "mail_text_cancelled_ticket": "t",
                "mail_html_cancelled_ticket": "h",
            },
            headers=auth(token),
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("path,method", [
        ("/tickets/{id}", "delete"),
        ("/ticket_groups/{id}", "delete"),
        ("/events/{id}", "delete"),
    ])
    def test_narrowed_token_rejected_on_every_locally_gated_route(
        self, client, auth, make_user, make_event, make_group, make_ticket,
        token_for, path, method,
    ):
        owner = make_user(scopes=[
            "events:edit", "ticket_groups:edit", "tickets:edit",
        ])
        event = make_event()
        group = make_group(event)
        ticket = make_ticket(group)
        target = {
            "/tickets/{id}": f"/tickets/{ticket.id}",
            "/ticket_groups/{id}": f"/ticket_groups/{group.id}",
            "/events/{id}": f"/events/{event.id}",
        }[path]

        response = getattr(client, method)(target, headers=auth(token_for(owner, scopes=[])))

        assert response.status_code == 403

    def test_full_token_still_works(self, client, auth, make_user, make_event,
                                    token_for):
        admin = make_user(scopes=["events:edit"])
        event = make_event()
        body = {
            "name": "renamed",
            "tickets_sales_start": "2026-01-01T00:00:00",
            "tickets_sales_end": "2026-12-31T00:00:00",
            "smtp_mail_from": "a@b.c",
            "mail_text_new_ticket": "t",
            "mail_html_new_ticket": "h",
            "mail_text_cancelled_ticket": "t",
            "mail_html_cancelled_ticket": "h",
        }

        response = client.patch(f"/events/{event.id}", json=body,
                                headers=auth(token_for(admin)))

        assert response.status_code == 200
        assert response.json()["name"] == "renamed"

    def test_unrelated_token_scope_does_not_help(self, client, auth, make_user,
                                                 make_event, token_for):
        admin = make_user(scopes=["events:edit"])
        event = make_event()

        response = client.delete(f"/events/{event.id}",
                                 headers=auth(token_for(admin, scopes=["users:read"])))

        assert response.status_code == 403


class TestEventLocalGrants:
    def test_local_grant_replaces_global_scope(self, client, auth, make_user,
                                               make_event, token_for, grant):
        local_admin = make_user(scopes=[])
        event = make_event()
        grant(event, local_admin, "events:edit")
        body = {
            "name": "edited locally",
            "tickets_sales_start": "2026-01-01T00:00:00",
            "tickets_sales_end": "2026-12-31T00:00:00",
            "smtp_mail_from": "a@b.c",
            "mail_text_new_ticket": "t",
            "mail_html_new_ticket": "h",
            "mail_text_cancelled_ticket": "t",
            "mail_html_cancelled_ticket": "h",
        }

        response = client.patch(f"/events/{event.id}", json=body,
                                headers=auth(token_for(local_admin, scopes=[])))

        assert response.status_code == 200

    def test_grant_does_not_leak_to_other_events(self, client, auth, make_user,
                                                 make_event, token_for, grant):
        admin = make_user(scopes=[])
        mine = make_event("mine")
        theirs = make_event("theirs")
        grant(mine, admin, "events:edit", "events:read")
        headers = auth(token_for(admin, scopes=[]))

        assert client.get(f"/events/{mine.id}/scopes", headers=headers).status_code == 200
        assert client.get(f"/events/{theirs.id}/scopes", headers=headers).status_code == 403
        assert client.delete(f"/events/{theirs.id}", headers=headers).status_code == 403
        # ...but the grant on their own event still works (204 since #67).
        assert client.delete(f"/events/{mine.id}", headers=headers).status_code == 204

    def test_unknown_event_is_404_not_403(self, client, auth, make_user, token_for):
        admin = make_user(scopes=[])

        response = client.delete("/events/99999999", headers=auth(token_for(admin)))

        assert response.status_code == 404

    def test_anonymous_is_401(self, client, make_event):
        event = make_event()

        response = client.delete(f"/events/{event.id}")

        assert response.status_code == 401


class TestReparentingStaysInsideTheEvent:
    """A body may not move a resource into an event the caller does not run.

    The dependency authorizes the resource's *current* owner; without a
    second check on the destination these become cross-tenant writes.
    """

    def test_ticket_cannot_move_into_another_events_group(
        self, client, auth, db, make_user, make_event, make_group, make_ticket,
        token_for, grant,
    ):
        admin_of_first = make_user(scopes=[])
        first = make_event("first event")
        second = make_event("second event")
        first_group = make_group(first)
        second_group = make_group(second)
        ticket = make_ticket(first_group, email="attendee@example.invalid")
        grant(first, admin_of_first, "tickets:edit")

        response = client.put(
            f"/tickets/{ticket.id}",
            json=ticket_body(ticket, second_group.id),
            headers=auth(token_for(admin_of_first, scopes=[])),
        )

        assert response.status_code == 403
        db.expire_all()
        assert db.get(type(ticket), ticket.id).group_id == first_group.id

    def test_ticket_move_within_same_event_is_allowed(
        self, client, auth, db, make_user, make_event, make_group, make_ticket,
        token_for, grant,
    ):
        admin = make_user(scopes=[])
        event = make_event()
        source = make_group(event, name="source")
        destination = make_group(event, name="destination")
        ticket = make_ticket(source)
        grant(event, admin, "tickets:edit")

        response = client.put(f"/tickets/{ticket.id}",
                              json=ticket_body(ticket, destination.id),
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 200
        db.expire_all()
        assert db.get(type(ticket), ticket.id).group_id == destination.id

    def test_global_scope_can_still_move_a_ticket(
        self, client, auth, db, make_user, make_event, make_group, make_ticket,
        token_for,
    ):
        admin = make_user(scopes=["tickets:edit"])
        first, second = make_event("first"), make_event("second")
        first_group, second_group = make_group(first), make_group(second)
        ticket = make_ticket(first_group)

        response = client.put(f"/tickets/{ticket.id}",
                              json=ticket_body(ticket, second_group.id),
                              headers=auth(token_for(admin)))

        assert response.status_code == 200

    def test_ticket_group_cannot_move_to_another_event(
        self, client, auth, db, make_user, make_event, make_group, token_for, grant,
    ):
        admin = make_user(scopes=[])
        first, second = make_event("first"), make_event("second")
        group = make_group(first)
        grant(first, admin, "ticket_groups:edit")

        response = client.put(
            f"/ticket_groups/{group.id}",
            json={"name": "moved", "capacity": 5, "event_id": second.id},
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 403
        db.expire_all()
        assert db.get(type(group), group.id).event_id == first.id

    def test_ticket_group_edit_within_event_is_allowed(
        self, client, auth, db, make_user, make_event, make_group, token_for, grant,
    ):
        admin = make_user(scopes=[])
        event = make_event()
        group = make_group(event, name="original")
        grant(event, admin, "ticket_groups:edit")

        response = client.put(
            f"/ticket_groups/{group.id}",
            json={"name": "renamed", "capacity": 99, "event_id": event.id},
            headers=auth(token_for(admin, scopes=[])),
        )

        assert response.status_code == 200
        db.expire_all()
        assert db.get(type(group), group.id).name == "renamed"

    def test_moving_to_a_nonexistent_group_is_404_not_500(
        self, client, auth, make_user, make_event, make_group, make_ticket,
        token_for, grant,
    ):
        admin = make_user(scopes=[])
        event = make_event()
        group = make_group(event)
        ticket = make_ticket(group)
        grant(event, admin, "tickets:edit")

        response = client.put(f"/tickets/{ticket.id}",
                              json=ticket_body(ticket, 99999999),
                              headers=auth(token_for(admin, scopes=[])))

        assert response.status_code == 404


class TestRoutesAreActuallyGated:
    """The dependency has to be wired to the route, not just defined.

    A missing entry here is invisible in the test suite above, which only
    exercises the handful of routes someone remembered to check - and every
    one of these was unauthenticated or token-gated-only on master.
    """

    # Routes that must refuse an unauthorized caller. Collection routes are
    # covered separately - they answer with a filtered list instead of a 403.
    GATED = [
        ("get", "/events/{id}/scopes"),
        ("post", "/events/"),
        ("patch", "/events/{id}"),
        ("delete", "/events/{id}"),
        ("post", "/ticket_groups/"),
        ("get", "/ticket_groups/{id}"),
        ("put", "/ticket_groups/{id}"),
        ("delete", "/ticket_groups/{id}"),
        ("post", "/tickets/"),
        ("get", "/tickets/{id}"),
        ("put", "/tickets/{id}"),
        ("delete", "/tickets/{id}"),
    ]
    SCOPE_FOR = {
        "/events/{id}/scopes": "events:read",
        "/events/": "events:edit",
        "/events/{id}": "events:edit",
        "/ticket_groups/": "ticket_groups:edit",
        "/ticket_groups/{id}": "ticket_groups:read",
        "/tickets/": "tickets:edit",
        "/tickets/{id}": "tickets:read",
    }
    # Verbs whose gate differs from the path's default (usually `*:edit`).
    VERB_SCOPE = {
        ("put", "/ticket_groups/{id}"): "ticket_groups:edit",
        ("delete", "/ticket_groups/{id}"): "ticket_groups:edit",
        ("put", "/tickets/{id}"): "tickets:edit",
        ("delete", "/tickets/{id}"): "tickets:edit",
    }

    def _url(self, path, event, group, ticket):
        return path.format(id=event.id if path.startswith("/events") else (
            group.id if path.startswith("/ticket_groups") else ticket.id))

    def _scope(self, method, path):
        return self.VERB_SCOPE.get((method, path)) or self.SCOPE_FOR[path]

    def _body(self, method, path, event, group):
        """A schema-valid body, so a 422 can never mask the 403 under test.

        Bodies matter for POST /tickets/ and POST /ticket_groups/, which take
        the event from the body and therefore check inside the handler - after
        validation.
        """
        if method not in ("post", "put", "patch"):
            return None
        if path == "/events/":
            return {
                "name": "created",
                "tickets_sales_start": "2026-01-01T00:00:00",
                "tickets_sales_end": "2026-12-31T00:00:00",
                "smtp_mail_from": "a@b.c",
                "mail_text_new_ticket": "t",
                "mail_html_new_ticket": "h",
                "mail_text_cancelled_ticket": "t",
                "mail_html_cancelled_ticket": "h",
            }
        if path.startswith("/ticket_groups"):
            return {"name": "G", "capacity": 5, "event_id": event.id}
        return {
            "email": "attendee@example.invalid",
            "firstname": "Attendee",
            "lastname": "One",
            "status": 0,
            "description": "",
            "group_id": group.id,
        }

    # A refusal, whichever flavour. POST /events/ is the one route here with
    # no event to scope against - creating the first event is what mints the
    # creator's grants - so it is gated by FastAPI's built-in scope check,
    # which answers 401 with WWW-Authenticate; the event-local helpers answer
    # 403. Either way the write must not happen.
    REFUSED = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def _request(self, client, auth, token, method, path, event, group, ticket):
        return self._call(client, method, path, event, group, ticket,
                          headers=auth(token))

    def _call(self, client, method, path, event, group, ticket, **kwargs):
        body = self._body(method, path, event, group)
        # httpx only accepts a json= on the verbs that carry a body, and
        # passing json=None to the others is a TypeError, not "no body".
        if body is not None:
            kwargs["json"] = body
        return getattr(client, method)(self._url(path, event, group, ticket), **kwargs)

    @pytest.mark.parametrize("method,path", GATED)
    def test_anonymous_is_401(self, client, make_event, make_group, make_ticket,
                              method, path):
        event = make_event()
        group = make_group(event)
        ticket = make_ticket(group)

        response = self._call(client, method, path, event, group, ticket)

        # A 401/403 rather than 404: the gate runs before the handler, so an
        # anonymous caller cannot probe which ids exist.
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.parametrize("method,path", GATED)
    def test_scopeless_token_is_403(self, client, auth, make_user, make_event,
                                    make_group, make_ticket, token_for, method, path):
        caller = make_user(scopes=[])
        event = make_event()
        group = make_group(event)

        response = self._request(client, auth, token_for(caller, scopes=[]),
                                 method, path, event, group, make_ticket(group))

        assert response.status_code in self.REFUSED

    # POST /events/ has no event to hold a grant on, so it is not in this list.
    @pytest.mark.parametrize("method,path", [
        (method, path) for method, path in GATED if (method, path) != ("post", "/events/")
    ])
    def test_a_grant_on_another_event_is_refused(self, client, auth, make_user,
                                                 make_event, make_group, make_ticket,
                                                 token_for, grant, method, path):
        caller = make_user(scopes=[])
        grant(make_event("theirs"), caller, self._scope(method, path))
        mine = make_event("mine")
        group = make_group(mine)

        response = self._request(client, auth, token_for(caller, scopes=[]),
                                 method, path, mine, group, make_ticket(group))

        assert response.status_code in self.REFUSED

    def test_ticket_list_shows_only_readable_events(
        self, client, auth, make_user, make_event, make_group, make_ticket,
        token_for, grant,
    ):
        """A list route filters rather than refusing: an under-privileged
        caller sees nothing, and never the other event's attendees."""
        caller = make_user(scopes=[])
        theirs, mine = make_event("theirs"), make_event("mine")
        theirs_ticket = make_ticket(make_group(theirs), email="theirs@example.invalid")
        mine_ticket = make_ticket(make_group(mine), email="mine@example.invalid")
        headers = auth(token_for(caller, scopes=[]))

        assert client.get("/tickets/", headers=headers).json() == []

        grant(mine, caller, "tickets:read")
        emails = [t["email"] for t in client.get("/tickets/", headers=headers).json()]

        assert emails == ["mine@example.invalid"]
        assert theirs_ticket.id not in {
            t["id"] for t in client.get("/tickets/", headers=headers).json()
        }
        assert mine_ticket.id is not None

    def test_ticket_group_list_shows_only_readable_events(
        self, client, auth, make_user, make_event, make_group, token_for, grant,
    ):
        caller = make_user(scopes=[])
        theirs, mine = make_event("theirs"), make_event("mine")
        theirs_group = make_group(theirs, name="theirs-group")
        mine_group = make_group(mine, name="mine-group")
        headers = auth(token_for(caller, scopes=[]))

        assert client.get("/ticket_groups/", headers=headers).json() == []

        # Both scopes on the same event: the rows embed attendee data.
        grant(mine, caller, "ticket_groups:read", "tickets:read")
        rows = client.get("/ticket_groups/", headers=headers).json()

        assert [row["id"] for row in rows] == [mine_group.id]
        assert theirs_group.id not in {row["id"] for row in rows}
        assert {row["event_id"] for row in rows} == {mine.id}


class TestAttendeeDataNeedsTicketsRead:
    """Event metadata rights must not read as attendee-listing rights.

    Every route below returns attendee names and e-mail addresses, so
    `events:read` alone (or `ticket_groups:read` alone) is not enough.
    """

    def test_xlsx_needs_both_grants(self, client, auth, make_user, make_event,
                                    make_group, make_ticket, token_for, grant):
        reader = make_user(scopes=[])
        event = make_event()
        make_ticket(make_group(event))
        headers = auth(token_for(reader, scopes=[]))

        assert client.get(f"/events/xlsx/{event.id}", headers=headers).status_code == 403

        grant(event, reader, "events:read")
        assert client.get(f"/events/xlsx/{event.id}", headers=headers).status_code == 403

        grant(event, reader, "tickets:read")
        response = client.get(f"/events/xlsx/{event.id}", headers=headers)
        assert response.status_code == 200
        # The point of the route: the workbook carries the attendees.
        assert b"Attendee" in response.content or len(response.content) > 0

    def test_ticket_group_list_needs_both_grants(self, client, auth, make_user,
                                                 make_event, make_group,
                                                 token_for, grant):
        reader = make_user(scopes=[])
        event = make_event()
        make_group(event, name="Visible group")
        headers = auth(token_for(reader, scopes=[]))

        assert client.get("/ticket_groups/", headers=headers).status_code == 200
        assert client.get("/ticket_groups/", headers=headers).json() == []

        grant(event, reader, "ticket_groups:read")
        assert client.get("/ticket_groups/", headers=headers).json() == []

        grant(event, reader, "tickets:read")
        names = [g["name"] for g in client.get("/ticket_groups/", headers=headers).json()]
        assert names == ["Visible group"]

    def test_a_list_row_embeds_the_attendees(self, client, auth, make_user,
                                             make_event, make_group, make_ticket,
                                             token_for):
        """What the two-scope requirement is protecting."""
        boss = make_user(scopes=["ticket_groups:read", "tickets:read"])
        event = make_event()
        make_ticket(make_group(event), email="attendee@example.invalid")

        row = client.get("/ticket_groups/",
                         headers=auth(token_for(boss))).json()[0]

        assert [t["email"] for t in row["tickets"]] == ["attendee@example.invalid"]

    def test_event_ticket_list_needs_tickets_read(self, client, auth, make_user,
                                                  make_event, make_group,
                                                  make_ticket, token_for, grant):
        reader = make_user(scopes=[])
        event = make_event()
        make_ticket(make_group(event), email="attendee@example.invalid")
        headers = auth(token_for(reader, scopes=[]))

        assert client.get(f"/events/{event.id}", headers=headers).status_code == 200
        assert client.get(f"/events/{event.id}/tickets",
                          headers=headers).status_code == 403

        grant(event, reader, "tickets:read")
        body = client.get(f"/events/{event.id}/tickets", headers=headers).json()
        assert [t["email"] for t in body] == ["attendee@example.invalid"]


class TestGlobalAndLocalAreEitherOr:
    """The two tiers authorize independently - neither is a prerequisite."""

    def test_a_global_scope_needs_no_grant_row(self, client, auth, make_user,
                                               make_event, token_for, db):
        from app import models

        boss = make_user(scopes=["events:read"])
        event = make_event()
        assert db.query(models.EventUserScope).count() == 0

        response = client.get(f"/events/{event.id}/scopes",
                              headers=auth(token_for(boss)))

        assert response.status_code == 200
        assert response.json() == []

    def test_a_grant_needs_no_scope_on_the_token(self, client, auth, make_user,
                                                 make_event, make_group,
                                                 make_ticket, token_for, grant):
        local = make_user(scopes=[])
        event = make_event()
        group = make_group(event)
        ticket = make_ticket(group, email="attendee@example.invalid")
        grant(event, local, "tickets:read")

        response = client.get(f"/tickets/{ticket.id}",
                              headers=auth(token_for(local, scopes=[])))

        assert response.status_code == 200
        assert response.json()["email"] == "attendee@example.invalid"


class TestBadEventReferencesAre404:
    """A body naming a nonexistent event must not reach the FK layer."""

    def test_post_ticket_group_with_unknown_event(self, client, auth, make_user,
                                                  token_for):
        admin = make_user(scopes=["ticket_groups:edit"])

        response = client.post("/ticket_groups/",
                               json={"name": "G", "capacity": 5, "event_id": 99999999},
                               headers=auth(token_for(admin)))

        assert response.status_code == 404

    def test_put_ticket_group_to_unknown_event(self, client, auth, make_user,
                                               make_event, make_group, token_for):
        admin = make_user(scopes=["ticket_groups:edit"])
        event = make_event()
        group = make_group(event)

        response = client.put(f"/ticket_groups/{group.id}",
                              json={"name": "G", "capacity": 5, "event_id": 99999999},
                              headers=auth(token_for(admin)))

        assert response.status_code == 404


class TestReferentialIntegrity:
    """The declared cascades have to actually happen.

    Events and users own scope grants through ON DELETE CASCADE, and
    SQLite only honours that when asked. If it does not, a deleted
    event's grants survive - and because events.id is a plain
    autoincrement that SQLite reuses, the next event inherits them.
    """

    def test_sqlite_foreign_keys_are_enforced(self, db):
        from sqlalchemy import text

        enabled = db.execute(text("PRAGMA foreign_keys")).scalar()
        assert int(enabled) == 1

    def test_deleting_an_event_deletes_its_grants(
        self, client, auth, db, make_user, make_event, token_for, grant,
    ):
        from app import models

        admin = make_user(scopes=["events:edit"])
        event = make_event()
        grant(event, admin, "events:edit", "tickets:read")
        assert db.query(models.EventUserScope).filter_by(event_id=event.id).count() == 2

        response = client.delete(f"/events/{event.id}", headers=auth(token_for(admin)))

        assert response.status_code == 204  # since #67
        assert db.query(models.EventUserScope).filter_by(event_id=event.id).count() == 0

    def test_grants_never_survive_their_event(self, db, make_user, make_event, grant):
        """events.id is a reused autoincrement, so a grant outliving its
        event would silently brand the *next* event with the old admins."""
        from app import models
        from app.services import event_user_scopes as service

        admin = make_user(scopes=[])
        first = make_event("first")
        grant(first, admin, "events:edit")

        db.delete(first)
        db.commit()
        assert db.query(models.EventUserScope).count() == 0

        for _ in range(3):
            fresh = make_event("fresh")
            db.expire_all()
            assert not service.has_scope(
                event_id=fresh.id,
                user_uuid=admin.uuid,
                scope="events:edit",
                db=db,
            )

    def test_deleting_a_group_deletes_its_tickets(
        self, db, make_event, make_group, make_ticket,
    ):
        from app import models

        event = make_event()
        group = make_group(event)
        make_ticket(group)

        db.delete(group)
        db.commit()
        db.expire_all()

        assert db.query(models.Ticket).filter_by(group_id=group.id).count() == 0


class TestScopeResolver:
    def test_missing_resources_resolve_to_none(self, db):
        from app.middleware.event_scopes import resolve_event_id

        assert resolve_event_id("event", 99999999, db) is None
        assert resolve_event_id("ticket_group", 99999999, db) is None
        assert resolve_event_id("ticket", 99999999, db) is None

    def test_resolves_group_and_ticket_to_their_event(
        self, db, make_event, make_group, make_ticket,
    ):
        from app.middleware.event_scopes import resolve_event_id

        event = make_event()
        group = make_group(event)
        ticket = make_ticket(group)

        assert resolve_event_id("event", event.id, db) == event.id
        assert resolve_event_id("ticket_group", group.id, db) == event.id
        assert resolve_event_id("ticket", ticket.id, db) == event.id

    def test_unknown_resource_type_fails_at_definition_time(self):
        from app.middleware.event_scopes import require_event_scope

        # A typo must not surface as a 500 on every request to the route.
        with pytest.raises(ValueError):
            require_event_scope("tickets:edit", resource="ticketts")
