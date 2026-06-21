"""Tests for Goal CRUD — Phase 2 gate criteria.

Owner : Adil Islam
QA    : Daksh Garg

SMILE correction: all hardcoded phase string literals updated from the
hallucinated 5-phase system to the correct 6-phase framework:

  "sense"     → "reality-emulation"     (Phase 1, default starting phase)
  "model"     → "concurrent-engineering" (Phase 2, valid forward step)
  "intervene" → "collective-intelligence" (Phase 3, used in skip test)

The transition logic itself is unchanged — forward one step allowed,
skip-forward forbidden. Only the phase names have been corrected.
"""


class TestCreateGoal:
    def test_create_returns_201(self, client, sample_goal) -> None:
        """POST /api/v1/goals/ should return 201 with the created goal."""
        response = client.post("/api/v1/goals/", json=sample_goal)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["title"] == "Learn Docker"
        assert "id" in data

    def test_create_assigns_smile_phase(self, client, sample_goal) -> None:
        """New goal should carry the SMILE phase sent in the request.

        CORRECTED: was asserting == 'sense' (hallucinated phase).
        Now asserts == 'reality-emulation' (correct Phase 1).
        """
        response = client.post("/api/v1/goals/", json=sample_goal)
        assert response.json()["smile_phase"] == "reality-emulation"  # CORRECTED

    def test_create_default_urgency_flag_is_false(self, client, sample_goal) -> None:
        """Task C: urgency_flag must default to False when not sent."""
        response = client.post("/api/v1/goals/", json=sample_goal)
        assert response.json()["urgency_flag"] is False

    def test_create_with_urgency_flag_true(self, client) -> None:
        """Task C: urgency_flag=True must be accepted and stored."""
        payload = {
            "title": "Urgent task",
            "priority": 5,
            "smile_phase": "reality-emulation",
            "urgency_flag": True,
        }
        response = client.post("/api/v1/goals/", json=payload)
        assert response.status_code in (200, 201)
        assert response.json()["urgency_flag"] is True


class TestReadGoal:
    def test_list_goals(self, client) -> None:
        """GET /api/v1/goals/ should return an empty list when store is clear."""
        response = client.get("/api/v1/goals/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_goals_returns_created_goal(self, client, sample_goal) -> None:
        """Created goal must appear in the list."""
        client.post("/api/v1/goals/", json=sample_goal)
        response = client.get("/api/v1/goals/")
        assert len(response.json()) == 1

    def test_get_goal_by_id(self, client, sample_goal) -> None:
        """GET /api/v1/goals/{id} should return the specific goal."""
        created = client.post("/api/v1/goals/", json=sample_goal).json()
        response = client.get(f"/api/v1/goals/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_nonexistent_goal_returns_404(self, client) -> None:
        response = client.get("/api/v1/goals/nonexistent-id")
        assert response.status_code == 404


class TestUpdateGoal:
    def test_update_smile_phase(self, client, sample_goal) -> None:
        """PATCH should allow a valid forward transition: Phase 1 → Phase 2.

        CORRECTED: was patching to 'model' (hallucinated).
        Now patches to 'concurrent-engineering' (correct Phase 2).
        """
        create_resp = client.post("/api/v1/goals/", json=sample_goal)
        assert create_resp.status_code in (200, 201)
        goal_id = create_resp.json()["id"]

        patch_resp = client.patch(
            f"/api/v1/goals/{goal_id}",
            json={"smile_phase": "concurrent-engineering"},  # CORRECTED
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["smile_phase"] == "concurrent-engineering"  # CORRECTED

    def test_invalid_phase_skip_rejected(self, client, sample_goal) -> None:
        """Phase 1 → Phase 3 skips Phase 2 — must be rejected with 422.

        CORRECTED: was patching to 'intervene' (hallucinated skip target).
        Now patches to 'collective-intelligence' (correct Phase 3 skip target).
        Skipping from Phase 1 (reality-emulation) over Phase 2
        (concurrent-engineering) to Phase 3 (collective-intelligence)
        is forbidden by SMILE methodology.
        """
        create_resp = client.post("/api/v1/goals/", json=sample_goal)
        assert create_resp.status_code in (200, 201)
        goal_id = create_resp.json()["id"]

        patch_resp = client.patch(
            f"/api/v1/goals/{goal_id}",
            json={"smile_phase": "collective-intelligence"},  # CORRECTED (skip over phase 2)
        )
        assert patch_resp.status_code == 422

    def test_update_urgency_flag(self, client, sample_goal) -> None:
        """Task C: PATCH can activate urgency_flag on an existing goal."""
        goal_id = client.post("/api/v1/goals/", json=sample_goal).json()["id"]
        patch_resp = client.patch(
            f"/api/v1/goals/{goal_id}",
            json={"urgency_flag": True},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["urgency_flag"] is True

    def test_patch_title_does_not_reset_urgency_flag(self, client) -> None:
        """Task C: Patching title only must NOT reset urgency_flag to False."""
        goal_id = client.post(
            "/api/v1/goals/",
            json={
                "title": "Original",
                "priority": 5,
                "smile_phase": "reality-emulation",
                "urgency_flag": True,
            },
        ).json()["id"]

        patch_resp = client.patch(f"/api/v1/goals/{goal_id}", json={"title": "Updated"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["urgency_flag"] is True  # must not have been reset


class TestDeleteGoal:
    def test_delete_returns_success(self, client, sample_goal) -> None:
        """DELETE should remove the goal and confirm via a follow-up GET."""
        create_resp = client.post("/api/v1/goals/", json=sample_goal)
        assert create_resp.status_code in (200, 201)
        goal_id = create_resp.json()["id"]

        delete_resp = client.delete(f"/api/v1/goals/{goal_id}")
        assert delete_resp.status_code == 200
        body = delete_resp.json()
        assert body["deleted"] is True
        assert body["id"] == goal_id  # field is `id` not `goal_id` — matches OpenAPI

        get_resp = client.get(f"/api/v1/goals/{goal_id}")
        assert get_resp.status_code == 404
